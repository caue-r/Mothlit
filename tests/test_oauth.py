"""SmartThings OAuth: code exchange, refresh with refresh-token rotation, and errors."""

import base64
import threading
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from mothlit.devices.smartthings import (
    AuthOAuth,
    AuthorizationError,
    DeviceError,
    OAuthCredentials,
    SmartThingsClient,
    authorization_url,
    exchange_code,
)


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def token_server(responses, requests):
    """MockTransport for the token endpoint. `responses`: list of (status, json) consumed in order."""

    def handler(req: httpx.Request):
        requests.append({"url": str(req.url), "auth": req.headers.get("Authorization"),
                         "body": {k: v[0] for k, v in parse_qs(req.content.decode()).items()}})
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def credentials(expires_at):
    return OAuthCredentials("cid", "secret", "access-1", "refresh-1", expires_at)


def test_authorization_url():
    url, state = authorization_url("cid", "https://httpbin.org/get", state="xyz")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://api.smartthings.com/oauth/authorize?")
    assert q == {"client_id": ["cid"], "response_type": ["code"], "redirect_uri": ["https://httpbin.org/get"],
                 "scope": ["r:devices:* x:devices:*"], "state": ["xyz"]}
    assert state == "xyz"


def test_exchange_code_uses_basic_auth():
    requests = []
    t = token_server([(200, {"access_token": "a", "refresh_token": "r", "expires_in": 86399})], requests)
    cred = exchange_code("cid", "secret", "ABC123", "https://httpbin.org/get", transport=t, clock=Clock(100))
    assert cred == OAuthCredentials("cid", "secret", "a", "r", 100 + 86399)
    assert requests[0]["auth"] == "Basic " + base64.b64encode(b"cid:secret").decode()
    assert requests[0]["body"] == {"grant_type": "authorization_code", "code": "ABC123", "client_id": "cid",
                                   "redirect_uri": "https://httpbin.org/get"}


def test_fallback_endpoint_when_the_first_does_not_exist():
    requests = []
    t = token_server([(404, {}), (200, {"access_token": "a", "refresh_token": "r"})], requests)
    exchange_code("cid", "secret", "ABC", transport=t)
    assert [r["url"] for r in requests] == ["https://api.smartthings.com/oauth/token",
                                            "https://api.smartthings.com/v1/oauth/token"]


def test_invalid_code():
    t = token_server([(400, {"error": "invalid_grant"})], [])
    with pytest.raises(DeviceError, match="Invalid or already used authorization code"):
        exchange_code("cid", "secret", "old", transport=t)


def test_valid_token_does_not_refresh():
    clock = Clock()
    auth = AuthOAuth(credentials(clock.now + 3600), save=lambda c: None,
                     transport=token_server([], []), clock=clock)
    assert auth.token() == "access-1"


def test_refreshes_before_expiry_and_saves_the_new_refresh_token():
    clock = Clock()
    saved, requests = [], []
    t = token_server([(200, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 86399})],
                     requests)
    auth = AuthOAuth(credentials(clock.now + 60), save=saved.append, transport=t, clock=clock)
    assert auth.token() == "access-2"  # 1 min left: refreshed before using it
    assert requests[0]["body"] == {"grant_type": "refresh_token", "refresh_token": "refresh-1", "client_id": "cid"}
    assert saved[-1].refresh_token == "refresh-2"  # the old refresh token is dead; the new one was stored
    assert saved[-1].expires_at == clock.now + 86399


def test_expired_refresh_asks_for_new_authorization():
    clock = Clock()
    t = token_server([(400, {"error": "invalid_grant"})], [])
    auth = AuthOAuth(credentials(clock.now - 1), save=lambda c: None, transport=t, clock=clock)
    with pytest.raises(AuthorizationError, match="authorize again"):
        auth.token()


def test_401_refreshes_once_even_with_several_threads():
    clock = Clock()
    requests = []
    t = token_server([(200, {"access_token": "access-2", "refresh_token": "refresh-2"})], requests)
    auth = AuthOAuth(credentials(clock.now + 3600), save=lambda c: None, transport=t, clock=clock)
    results = []
    threads = [threading.Thread(target=lambda: results.append(auth.refresh("access-1"))) for _ in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert results == [True] * 5
    assert len(requests) == 1  # the other threads reused the already refreshed token
    assert auth.token() == "access-2"


def test_client_refreshes_and_retries_the_request_after_401():
    clock = Clock()
    token_t = token_server([(200, {"access_token": "access-2", "refresh_token": "refresh-2"})], [])
    auth = AuthOAuth(credentials(clock.now + 3600), save=lambda c: None, transport=token_t, clock=clock)

    def api(req: httpx.Request):
        if req.headers["Authorization"] == "Bearer access-1":
            return httpx.Response(401)  # revoked early
        return httpx.Response(200, json={"components": {}})

    client = SmartThingsClient(auth, transport=httpx.MockTransport(api))
    assert client.status("dev1") == {"components": {}}


def test_save_failure_keeps_the_token_in_memory():
    clock = Clock()
    t = token_server([(200, {"access_token": "access-2", "refresh_token": "refresh-2"})], [])

    def broken_save(_):
        raise OSError("keyring unavailable")

    auth = AuthOAuth(credentials(clock.now - 1), save=broken_save, transport=t, clock=clock)
    assert auth.token() == "access-2"
