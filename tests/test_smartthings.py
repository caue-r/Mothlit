import json

import httpx
import pytest

from mothlit.devices import DeviceError
from mothlit.devices.smartthings import AuthPAT, SmartThingsClient


def client(handler, auth=None):
    return SmartThingsClient(auth or AuthPAT("tok"), transport=httpx.MockTransport(handler))


def test_sends_token_and_pages_the_list():
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        assert req.headers["Authorization"] == "Bearer tok"
        if req.url.params.get("page") == "1":
            return httpx.Response(200, json={"items": [{"deviceId": "b"}], "_links": {}})
        return httpx.Response(
            200,
            json={
                "items": [{"deviceId": "a"}],
                "_links": {"next": {"href": "https://api.smartthings.com/v1/devices?page=1"}},
            },
        )

    assert [d["deviceId"] for d in client(handler).list_devices()] == ["a", "b"]
    assert len(calls) == 2


def test_execute_builds_the_command_body():
    body = {}

    def handler(req: httpx.Request):
        body.update(json.loads(req.content))
        assert req.url.path == "/v1/devices/dev1/commands"
        return httpx.Response(200, json={"results": [{"id": "x", "status": "ACCEPTED"}]})

    client(handler).execute("dev1", "thermostatCoolingSetpoint", "setCoolingSetpoint", [24])
    assert body == {
        "commands": [
            {
                "component": "main",
                "capability": "thermostatCoolingSetpoint",
                "command": "setCoolingSetpoint",
                "arguments": [24],
            }
        ]
    }


def test_failed_command_raises():
    handler = lambda req: httpx.Response(200, json={"results": [{"id": "x", "status": "FAILED"}]})  # noqa: E731
    with pytest.raises(DeviceError, match="refused"):
        client(handler).execute("dev1", "switch", "on")


@pytest.mark.parametrize(
    ("code", "snippet"), [(401, "expired"), (403, "permission"), (404, "not found"), (500, "HTTP 500")]
)
def test_friendly_http_errors(code, snippet):
    with pytest.raises(DeviceError, match=snippet):
        client(lambda req: httpx.Response(code)).status("dev1")


def test_friendly_timeout():
    def handler(req):
        raise httpx.ConnectTimeout("slow", request=req)

    with pytest.raises(DeviceError, match="in time"):
        client(handler).status("dev1")


def test_401_tries_to_refresh_once():
    class RefreshableAuth:
        def __init__(self):
            self.current = "old"

        def token(self):
            return self.current

        def refresh(self, rejected_token=None):
            assert rejected_token == "old"
            self.current = "new"
            return True

    def handler(req):
        if req.headers["Authorization"] == "Bearer old":
            return httpx.Response(401)
        return httpx.Response(200, json={"components": {}})

    assert client(handler, RefreshableAuth()).status("dev1") == {"components": {}}
