"""Minimal SmartThings REST API client.

Authentication is kept separate: the client only asks for `auth.token()` and, on a 401,
calls `auth.refresh(rejected_token)` once.

- `AuthPAT`: Personal Access Token. Simple, but new tokens are only valid for 24 h.
- `AuthOAuth`: OAuth-In app (created with the SmartThings CLI). The access token lasts ~24 h and
  is refreshed automatically with the refresh token, which lasts 30 days and changes on every refresh.
"""

import base64
import logging
import secrets
import threading
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Protocol
from urllib.parse import urlencode

import httpx

from .base import DeviceError

API_URL = "https://api.smartthings.com/v1"

# The new docs mention /v1/oauth/...; OAuth-In apps created by the CLI use /oauth/...
AUTHORIZE_URL = "https://api.smartthings.com/oauth/authorize"
TOKEN_URLS = ("https://api.smartthings.com/oauth/token", "https://api.smartthings.com/v1/oauth/token")
SCOPES = "r:devices:* x:devices:*"
DEFAULT_REDIRECT = "https://httpbin.org/get"
REFRESH_MARGIN_S = 10 * 60  # refresh a little before it expires

log = logging.getLogger(__name__)


class AuthorizationError(DeviceError):
    """The authorization is over (refresh token expired/revoked): the user must authorize again."""


class Authentication(Protocol):
    def token(self) -> str: ...

    def refresh(self, rejected_token: str | None = None) -> bool:
        """Tries to get a new token. Returns True if there is a new token to retry with."""
        ...


class AuthPAT:
    """Personal Access Token. New PATs expire in 24 h and cannot be refreshed."""

    kind = "pat"

    def __init__(self, token: str):
        self._token = token

    def token(self) -> str:
        return self._token

    def refresh(self, rejected_token: str | None = None) -> bool:
        return False


@dataclass
class OAuthCredentials:
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    expires_at: float  # epoch (s)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OAuthCredentials":
        return cls(**{k: data[k] for k in ("client_id", "client_secret", "access_token", "refresh_token",
                                           "expires_at")})


class AuthOAuth:
    """Access token with automatic, thread-safe refresh.

    `save` receives the new credentials on every refresh. This is critical: the old refresh
    token stops working as soon as it is used, so the new one must go to the keyring right
    away; if the app closes without saving it, the only way back is authorizing again.
    """

    kind = "oauth"

    def __init__(self, credentials: OAuthCredentials, save: Callable[[OAuthCredentials], None],
                 transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.time):
        self._cred = credentials
        self._save = save
        self._transport = transport
        self._clock = clock
        self._lock = threading.Lock()

    @property
    def expires_at(self) -> float:
        return self._cred.expires_at

    def token(self) -> str:
        with self._lock:
            if self._clock() >= self._cred.expires_at - REFRESH_MARGIN_S:
                self._refresh()
            return self._cred.access_token

    def refresh(self, rejected_token: str | None = None) -> bool:
        with self._lock:
            # Several threads may get a 401 at once: only the first refreshes, the others reuse it.
            if rejected_token and rejected_token != self._cred.access_token:
                return True
            self._refresh()
            return True

    def _refresh(self) -> None:
        log.info("Refreshing the SmartThings token")
        data = request_token(
            self._cred.client_id, self._cred.client_secret,
            {"grant_type": "refresh_token", "refresh_token": self._cred.refresh_token,
             "client_id": self._cred.client_id},
            self._transport,
        )
        new = replace(
            self._cred,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or self._cred.refresh_token,
            expires_at=self._clock() + float(data.get("expires_in") or 86399),
        )
        self._cred = new
        try:
            self._save(new)
        except Exception:  # keeps the token in memory; the next refresh tries to save again
            log.exception("Could not save the refreshed SmartThings token")


def authorization_url(client_id: str, redirect_uri: str = DEFAULT_REDIRECT,
                      state: str | None = None) -> tuple[str, str]:
    """URL for the user to authorize the app in the browser. Returns (url, state)."""
    state = state or secrets.token_urlsafe(16)
    params = {"client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
              "scope": SCOPES, "state": state}
    return f"{AUTHORIZE_URL}?{urlencode(params)}", state


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str = DEFAULT_REDIRECT,
                  transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.time
                  ) -> OAuthCredentials:
    """Exchanges the authorization code (from the redirect) for the tokens."""
    data = request_token(
        client_id, client_secret,
        {"grant_type": "authorization_code", "code": code, "client_id": client_id, "redirect_uri": redirect_uri},
        transport,
    )
    return OAuthCredentials(client_id, client_secret, data["access_token"], data["refresh_token"],
                            clock() + float(data.get("expires_in") or 86399))


def request_token(client_id: str, client_secret: str, body: dict, transport=None) -> dict:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}", "Accept": "application/json"}
    response = None
    with httpx.Client(timeout=10.0, transport=transport) as http:
        for url in TOKEN_URLS:
            try:
                response = http.post(url, data=body, headers=headers)
            except httpx.TimeoutException as e:
                raise DeviceError("SmartThings did not respond in time while refreshing access.") from e
            except httpx.HTTPError as e:
                raise DeviceError("No connection to SmartThings. Check the internet.") from e
            if response.status_code not in (404, 405):  # wrong endpoint: try the next one
                break

    if response.status_code in (400, 401):
        try:
            error = response.json().get("error", "")
        except ValueError:
            error = ""
        if body.get("grant_type") == "refresh_token":
            raise AuthorizationError(
                "The SmartThings authorization expired or was revoked. "
                "Run 'uv run python -m mothlit setup' to authorize again."
            )
        if error == "invalid_grant":
            raise DeviceError("Invalid or already used authorization code. Get a new one in the browser.")
        raise DeviceError(f"SmartThings refused the authorization ({error or response.status_code}). "
                          "Check the Client ID and the Client Secret.")
    if response.status_code >= 400:
        raise DeviceError(f"Failed to get the SmartThings token (HTTP {response.status_code}).")
    try:
        data = response.json()
        data["access_token"]
    except (ValueError, KeyError) as e:
        raise DeviceError("Invalid response from SmartThings while getting the token.") from e
    return data

class SmartThingsClient:
    def __init__(self, auth: Authentication, timeout: float = 8.0, transport: httpx.BaseTransport | None = None):
        self._auth = auth
        self._http = httpx.Client(base_url=API_URL, timeout=timeout, transport=transport)

    def list_devices(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url: str | None = "/devices"
        while url:
            data = self._request("GET", url)
            items.extend(data.get("items", []))
            next_page = (data.get("_links") or {}).get("next") or {}
            url = next_page.get("href")
        return items

    def device(self, device_id: str) -> dict[str, Any]:
        return self._request("GET", f"/devices/{device_id}")

    def status(self, device_id: str) -> dict[str, Any]:
        return self._request("GET", f"/devices/{device_id}/status")

    def execute(
        self,
        device_id: str,
        capability: str,
        command: str,
        arguments: list | None = None,
        component: str = "main",
    ) -> None:
        cmd: dict[str, Any] = {"component": component, "capability": capability, "command": command}
        if arguments is not None:
            cmd["arguments"] = arguments
        data = self._request("POST", f"/devices/{device_id}/commands", json={"commands": [cmd]})
        for result in data.get("results", []):
            if result.get("status") not in (None, "ACCEPTED", "COMPLETED"):
                raise DeviceError(f"The air conditioner refused the command '{command}'.")

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        response = None
        for attempt in range(2):
            token = self._auth.token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.smartthings+json;v=1",
            }
            try:
                response = self._http.request(method, url, headers=headers, **kwargs)
            except httpx.TimeoutException as e:
                raise DeviceError("SmartThings did not respond in time.") from e
            except httpx.HTTPError as e:
                raise DeviceError("No connection to SmartThings. Check the internet.") from e
            if response.status_code == 401 and attempt == 0 and self._auth.refresh(token):
                continue
            break

        code = response.status_code
        if code == 401:
            if getattr(self._auth, "kind", "") == "pat":
                raise DeviceError("SmartThings token expired or invalid (personal tokens last 24 h). "
                                  "Paste a new one in Settings or run setup with OAuth.")
            raise DeviceError("SmartThings refused access. Run 'uv run python -m mothlit setup'.")
        if code == 403:
            raise DeviceError("The SmartThings token does not have permission for this.")
        if code == 404:
            raise DeviceError("Device not found on SmartThings.")
        if code == 429:
            raise DeviceError("Too many requests to SmartThings. Wait a little.")
        if code >= 400:
            raise DeviceError(f"SmartThings refused the operation (HTTP {code}).")
        try:
            return response.json() if response.content else {}
        except ValueError as e:
            raise DeviceError("Invalid response from SmartThings.") from e
