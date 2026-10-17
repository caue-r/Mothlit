import json

import httpx
import pytest

from mothlit.devices import ErroDispositivo
from mothlit.devices.smartthings import AuthPAT, SmartThingsClient


def cliente(handler, auth=None):
    return SmartThingsClient(auth or AuthPAT("tok"), transport=httpx.MockTransport(handler))


def test_envia_token_e_pagina_lista():
    chamadas = []

    def handler(req: httpx.Request):
        chamadas.append(req)
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

    assert [d["deviceId"] for d in cliente(handler).listar_dispositivos()] == ["a", "b"]
    assert len(chamadas) == 2


def test_executar_monta_corpo_do_comando():
    corpo = {}

    def handler(req: httpx.Request):
        corpo.update(json.loads(req.content))
        assert req.url.path == "/v1/devices/dev1/commands"
        return httpx.Response(200, json={"results": [{"id": "x", "status": "ACCEPTED"}]})

    cliente(handler).executar("dev1", "thermostatCoolingSetpoint", "setCoolingSetpoint", [24])
    assert corpo == {
        "commands": [
            {
                "component": "main",
                "capability": "thermostatCoolingSetpoint",
                "command": "setCoolingSetpoint",
                "arguments": [24],
            }
        ]
    }


def test_comando_falho_gera_erro():
    handler = lambda req: httpx.Response(200, json={"results": [{"id": "x", "status": "FAILED"}]})  # noqa: E731
    with pytest.raises(ErroDispositivo, match="recusou"):
        cliente(handler).executar("dev1", "switch", "on")


@pytest.mark.parametrize(
    ("codigo", "trecho"), [(401, "expirado"), (403, "permissão"), (404, "não encontrado"), (500, "HTTP 500")]
)
def test_erros_http_amigaveis(codigo, trecho):
    with pytest.raises(ErroDispositivo, match=trecho):
        cliente(lambda req: httpx.Response(codigo)).status("dev1")


def test_timeout_amigavel():
    def handler(req):
        raise httpx.ConnectTimeout("lento", request=req)

    with pytest.raises(ErroDispositivo, match="a tempo"):
        cliente(handler).status("dev1")


def test_401_tenta_renovar_uma_vez():
    class AuthRenovavel:
        def __init__(self):
            self.atual = "velho"

        def token(self):
            return self.atual

        def renovar(self, token_rejeitado=None):
            assert token_rejeitado == "velho"
            self.atual = "novo"
            return True

    def handler(req):
        if req.headers["Authorization"] == "Bearer velho":
            return httpx.Response(401)
        return httpx.Response(200, json={"components": {}})

    assert cliente(handler, AuthRenovavel()).status("dev1") == {"components": {}}
