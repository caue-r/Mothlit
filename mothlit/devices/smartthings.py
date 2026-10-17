"""Cliente mínimo da SmartThings REST API.

A autenticação fica isolada: o cliente só pede `auth.token()` e, se receber 401,
chama `auth.renovar(token_rejeitado)` uma vez.

- `AuthPAT`: Personal Access Token. Simples, mas tokens novos valem só 24 h.
- `AuthOAuth`: app OAuth-In (criado pela SmartThings CLI). O access token vale ~24 h e
  é renovado sozinho com o refresh token, que vale 30 dias e muda a cada renovação.
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

from .base import ErroDispositivo

API_URL = "https://api.smartthings.com/v1"

# A documentação nova cita /v1/oauth/...; os apps OAuth-In criados pela CLI usam /oauth/...
URL_AUTORIZACAO = "https://api.smartthings.com/oauth/authorize"
URLS_TOKEN = ("https://api.smartthings.com/oauth/token", "https://api.smartthings.com/v1/oauth/token")
ESCOPOS = "r:devices:* x:devices:*"
REDIRECT_PADRAO = "https://httpbin.org/get"
MARGEM_RENOVACAO_S = 10 * 60  # renova um pouco antes de expirar

log = logging.getLogger(__name__)


class ErroAutorizacao(ErroDispositivo):
    """A autorização acabou (refresh token expirado/revogado): é preciso autorizar de novo."""


class Autenticacao(Protocol):
    def token(self) -> str: ...

    def renovar(self, token_rejeitado: str | None = None) -> bool:
        """Tenta obter um token novo. Devolve True se há um token novo para tentar de novo."""
        ...


class AuthPAT:
    """Personal Access Token. PATs novos expiram em 24 h e não podem ser renovados."""

    tipo = "pat"

    def __init__(self, token: str):
        self._token = token

    def token(self) -> str:
        return self._token

    def renovar(self, token_rejeitado: str | None = None) -> bool:
        return False


@dataclass
class CredenciaisOAuth:
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    expira_em: float  # epoch (s)

    def para_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: dict) -> "CredenciaisOAuth":
        return cls(**{k: dados[k] for k in ("client_id", "client_secret", "access_token", "refresh_token",
                                            "expira_em")})


class AuthOAuth:
    """Access token com renovação automática e thread-safe.

    `salvar` recebe as credenciais novas a cada renovação. Isso é crítico: o refresh
    token antigo deixa de valer assim que é usado, então o novo precisa ir para o
    keyring na hora; se o app fechar sem salvar, só autorizando de novo.
    """

    tipo = "oauth"

    def __init__(self, credenciais: CredenciaisOAuth, salvar: Callable[[CredenciaisOAuth], None],
                 transport: httpx.BaseTransport | None = None, relogio: Callable[[], float] = time.time):
        self._cred = credenciais
        self._salvar = salvar
        self._transport = transport
        self._relogio = relogio
        self._trava = threading.Lock()

    @property
    def expira_em(self) -> float:
        return self._cred.expira_em

    def token(self) -> str:
        with self._trava:
            if self._relogio() >= self._cred.expira_em - MARGEM_RENOVACAO_S:
                self._renovar()
            return self._cred.access_token

    def renovar(self, token_rejeitado: str | None = None) -> bool:
        with self._trava:
            # Várias threads podem receber 401 juntas: só a primeira renova, as outras reaproveitam.
            if token_rejeitado and token_rejeitado != self._cred.access_token:
                return True
            self._renovar()
            return True

    def _renovar(self) -> None:
        log.info("Renovando o token da SmartThings")
        dados = pedir_token(
            self._cred.client_id, self._cred.client_secret,
            {"grant_type": "refresh_token", "refresh_token": self._cred.refresh_token,
             "client_id": self._cred.client_id},
            self._transport,
        )
        novas = replace(
            self._cred,
            access_token=dados["access_token"],
            refresh_token=dados.get("refresh_token") or self._cred.refresh_token,
            expira_em=self._relogio() + float(dados.get("expires_in") or 86399),
        )
        self._cred = novas
        try:
            self._salvar(novas)
        except Exception:  # segue com o token em memória; na próxima renovação tenta salvar de novo
            log.exception("Não consegui salvar o token renovado da SmartThings")


def url_autorizacao(client_id: str, redirect_uri: str = REDIRECT_PADRAO, state: str | None = None) -> tuple[str, str]:
    """URL para o usuário autorizar o app no navegador. Devolve (url, state)."""
    state = state or secrets.token_urlsafe(16)
    parametros = {"client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
                  "scope": ESCOPOS, "state": state}
    return f"{URL_AUTORIZACAO}?{urlencode(parametros)}", state


def trocar_codigo(client_id: str, client_secret: str, codigo: str, redirect_uri: str = REDIRECT_PADRAO,
                  transport: httpx.BaseTransport | None = None, relogio: Callable[[], float] = time.time
                  ) -> CredenciaisOAuth:
    """Troca o código de autorização (do redirect) pelos tokens."""
    dados = pedir_token(
        client_id, client_secret,
        {"grant_type": "authorization_code", "code": codigo, "client_id": client_id, "redirect_uri": redirect_uri},
        transport,
    )
    return CredenciaisOAuth(client_id, client_secret, dados["access_token"], dados["refresh_token"],
                            relogio() + float(dados.get("expires_in") or 86399))


def pedir_token(client_id: str, client_secret: str, corpo: dict, transport=None) -> dict:
    basico = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {basico}", "Accept": "application/json"}
    resposta = None
    with httpx.Client(timeout=10.0, transport=transport) as http:
        for url in URLS_TOKEN:
            try:
                resposta = http.post(url, data=corpo, headers=headers)
            except httpx.TimeoutException as e:
                raise ErroDispositivo("A SmartThings não respondeu a tempo ao renovar o acesso.") from e
            except httpx.HTTPError as e:
                raise ErroDispositivo("Sem conexão com a SmartThings. Verifique a internet.") from e
            if resposta.status_code not in (404, 405):  # endpoint errado: tenta o próximo
                break

    if resposta.status_code in (400, 401):
        try:
            erro = resposta.json().get("error", "")
        except ValueError:
            erro = ""
        if corpo.get("grant_type") == "refresh_token":
            raise ErroAutorizacao(
                "A autorização da SmartThings expirou ou foi revogada. "
                "Rode 'uv run python -m mothlit setup' para autorizar de novo."
            )
        if erro == "invalid_grant":
            raise ErroDispositivo("Código de autorização inválido ou já usado. Gere um novo no navegador.")
        raise ErroDispositivo(f"A SmartThings recusou a autorização ({erro or resposta.status_code}). "
                              "Confira o Client ID e o Client Secret.")
    if resposta.status_code >= 400:
        raise ErroDispositivo(f"Falha ao obter o token da SmartThings (HTTP {resposta.status_code}).")
    try:
        dados = resposta.json()
        dados["access_token"]
    except (ValueError, KeyError) as e:
        raise ErroDispositivo("Resposta inválida da SmartThings ao obter o token.") from e
    return dados

class SmartThingsClient:
    def __init__(self, auth: Autenticacao, timeout: float = 8.0, transport: httpx.BaseTransport | None = None):
        self._auth = auth
        self._http = httpx.Client(base_url=API_URL, timeout=timeout, transport=transport)

    def listar_dispositivos(self) -> list[dict[str, Any]]:
        itens: list[dict[str, Any]] = []
        url: str | None = "/devices"
        while url:
            dados = self._requisicao("GET", url)
            itens.extend(dados.get("items", []))
            proximo = (dados.get("_links") or {}).get("next") or {}
            url = proximo.get("href")
        return itens

    def dispositivo(self, device_id: str) -> dict[str, Any]:
        return self._requisicao("GET", f"/devices/{device_id}")

    def status(self, device_id: str) -> dict[str, Any]:
        return self._requisicao("GET", f"/devices/{device_id}/status")

    def executar(
        self,
        device_id: str,
        capability: str,
        comando: str,
        argumentos: list | None = None,
        componente: str = "main",
    ) -> None:
        cmd: dict[str, Any] = {"component": componente, "capability": capability, "command": comando}
        if argumentos is not None:
            cmd["arguments"] = argumentos
        dados = self._requisicao("POST", f"/devices/{device_id}/commands", json={"commands": [cmd]})
        for resultado in dados.get("results", []):
            if resultado.get("status") not in (None, "ACCEPTED", "COMPLETED"):
                raise ErroDispositivo(f"O ar-condicionado recusou o comando '{comando}'.")

    def fechar(self) -> None:
        self._http.close()

    def _requisicao(self, metodo: str, url: str, **kwargs) -> dict[str, Any]:
        resposta = None
        for tentativa in range(2):
            token = self._auth.token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.smartthings+json;v=1",
            }
            try:
                resposta = self._http.request(metodo, url, headers=headers, **kwargs)
            except httpx.TimeoutException as e:
                raise ErroDispositivo("A SmartThings não respondeu a tempo.") from e
            except httpx.HTTPError as e:
                raise ErroDispositivo("Sem conexão com a SmartThings. Verifique a internet.") from e
            if resposta.status_code == 401 and tentativa == 0 and self._auth.renovar(token):
                continue
            break

        codigo = resposta.status_code
        if codigo == 401:
            if getattr(self._auth, "tipo", "") == "pat":
                raise ErroDispositivo("Token da SmartThings expirado ou inválido (tokens pessoais valem 24 h). "
                                      "Cole um novo em Configurações ou rode o setup com OAuth.")
            raise ErroDispositivo("A SmartThings recusou o acesso. Rode 'uv run python -m mothlit setup'.")
        if codigo == 403:
            raise ErroDispositivo("O token da SmartThings não tem permissão para isso.")
        if codigo == 404:
            raise ErroDispositivo("Aparelho não encontrado na SmartThings.")
        if codigo == 429:
            raise ErroDispositivo("Muitas requisições à SmartThings. Aguarde um pouco.")
        if codigo >= 400:
            raise ErroDispositivo(f"A SmartThings recusou a operação (HTTP {codigo}).")
        try:
            return resposta.json() if resposta.content else {}
        except ValueError as e:
            raise ErroDispositivo("Resposta inválida da SmartThings.") from e
