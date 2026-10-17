"""OAuth da SmartThings: troca de código, renovação com rotação do refresh token e erros."""

import base64
import threading
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from mothlit.devices.smartthings import (
    AuthOAuth,
    CredenciaisOAuth,
    ErroAutorizacao,
    ErroDispositivo,
    SmartThingsClient,
    trocar_codigo,
    url_autorizacao,
)


class Relogio:
    def __init__(self, agora=1_000_000.0):
        self.agora = agora

    def __call__(self):
        return self.agora


def servidor_token(respostas, pedidos):
    """MockTransport do endpoint de token. `respostas`: lista de (status, json) consumida em ordem."""

    def handler(req: httpx.Request):
        pedidos.append({"url": str(req.url), "auth": req.headers.get("Authorization"),
                        "corpo": {k: v[0] for k, v in parse_qs(req.content.decode()).items()}})
        status, corpo = respostas.pop(0)
        return httpx.Response(status, json=corpo)

    return httpx.MockTransport(handler)


def credenciais(expira_em):
    return CredenciaisOAuth("cid", "segredo", "acesso-1", "renova-1", expira_em)


def test_url_de_autorizacao():
    url, state = url_autorizacao("cid", "https://httpbin.org/get", state="xyz")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://api.smartthings.com/oauth/authorize?")
    assert q == {"client_id": ["cid"], "response_type": ["code"], "redirect_uri": ["https://httpbin.org/get"],
                 "scope": ["r:devices:* x:devices:*"], "state": ["xyz"]}
    assert state == "xyz"


def test_trocar_codigo_usa_basic_auth():
    pedidos = []
    t = servidor_token([(200, {"access_token": "a", "refresh_token": "r", "expires_in": 86399})], pedidos)
    cred = trocar_codigo("cid", "segredo", "ABC123", "https://httpbin.org/get", transport=t, relogio=Relogio(100))
    assert cred == CredenciaisOAuth("cid", "segredo", "a", "r", 100 + 86399)
    assert pedidos[0]["auth"] == "Basic " + base64.b64encode(b"cid:segredo").decode()
    assert pedidos[0]["corpo"] == {"grant_type": "authorization_code", "code": "ABC123", "client_id": "cid",
                                   "redirect_uri": "https://httpbin.org/get"}


def test_endpoint_alternativo_quando_o_primeiro_nao_existe():
    pedidos = []
    t = servidor_token([(404, {}), (200, {"access_token": "a", "refresh_token": "r"})], pedidos)
    trocar_codigo("cid", "segredo", "ABC", transport=t)
    assert [p["url"] for p in pedidos] == ["https://api.smartthings.com/oauth/token",
                                           "https://api.smartthings.com/v1/oauth/token"]


def test_codigo_invalido():
    t = servidor_token([(400, {"error": "invalid_grant"})], [])
    with pytest.raises(ErroDispositivo, match="Código de autorização inválido"):
        trocar_codigo("cid", "segredo", "velho", transport=t)


def test_token_valido_nao_renova():
    relogio = Relogio()
    auth = AuthOAuth(credenciais(relogio.agora + 3600), salvar=lambda c: None,
                     transport=servidor_token([], []), relogio=relogio)
    assert auth.token() == "acesso-1"


def test_renova_antes_de_expirar_e_salva_o_refresh_novo():
    relogio = Relogio()
    salvas, pedidos = [], []
    t = servidor_token([(200, {"access_token": "acesso-2", "refresh_token": "renova-2", "expires_in": 86399})],
                       pedidos)
    auth = AuthOAuth(credenciais(relogio.agora + 60), salvar=salvas.append, transport=t, relogio=relogio)
    assert auth.token() == "acesso-2"  # faltava 1 min: renovou antes de usar
    assert pedidos[0]["corpo"] == {"grant_type": "refresh_token", "refresh_token": "renova-1", "client_id": "cid"}
    assert salvas[-1].refresh_token == "renova-2"  # o refresh antigo morreu; o novo foi guardado
    assert salvas[-1].expira_em == relogio.agora + 86399


def test_refresh_expirado_pede_nova_autorizacao():
    relogio = Relogio()
    t = servidor_token([(400, {"error": "invalid_grant"})], [])
    auth = AuthOAuth(credenciais(relogio.agora - 1), salvar=lambda c: None, transport=t, relogio=relogio)
    with pytest.raises(ErroAutorizacao, match="autorizar de novo"):
        auth.token()


def test_401_renova_uma_vez_mesmo_com_varias_threads():
    relogio = Relogio()
    pedidos = []
    t = servidor_token([(200, {"access_token": "acesso-2", "refresh_token": "renova-2"})], pedidos)
    auth = AuthOAuth(credenciais(relogio.agora + 3600), salvar=lambda c: None, transport=t, relogio=relogio)
    resultados = []
    threads = [threading.Thread(target=lambda: resultados.append(auth.renovar("acesso-1"))) for _ in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert resultados == [True] * 5
    assert len(pedidos) == 1  # as outras threads reaproveitaram o token já renovado
    assert auth.token() == "acesso-2"


def test_cliente_renova_e_repete_a_requisicao_apos_401():
    relogio = Relogio()
    token_t = servidor_token([(200, {"access_token": "acesso-2", "refresh_token": "renova-2"})], [])
    auth = AuthOAuth(credenciais(relogio.agora + 3600), salvar=lambda c: None, transport=token_t, relogio=relogio)

    def api(req: httpx.Request):
        if req.headers["Authorization"] == "Bearer acesso-1":
            return httpx.Response(401)  # revogado antes da hora
        return httpx.Response(200, json={"components": {}})

    cliente = SmartThingsClient(auth, transport=httpx.MockTransport(api))
    assert cliente.status("dev1") == {"components": {}}


def test_falha_ao_salvar_nao_perde_o_token_em_memoria():
    relogio = Relogio()
    t = servidor_token([(200, {"access_token": "acesso-2", "refresh_token": "renova-2"})], [])

    def salvar_quebrado(_):
        raise OSError("keyring indisponível")

    auth = AuthOAuth(credenciais(relogio.agora - 1), salvar=salvar_quebrado, transport=t, relogio=relogio)
    assert auth.token() == "acesso-2"
