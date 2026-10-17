"""Cliente mínimo da SmartThings REST API.

A autenticação fica isolada: o cliente só pede `auth.token()` e, se receber 401,
tenta `auth.renovar()` uma vez. Hoje usamos PAT; trocar por OAuth com refresh
token é só criar outra classe com esses dois métodos.
"""

from typing import Any, Protocol

import httpx

from .base import ErroDispositivo

API_URL = "https://api.smartthings.com/v1"


class Autenticacao(Protocol):
    def token(self) -> str: ...

    def renovar(self) -> bool:
        """Tenta obter um token novo. Devolve True se conseguiu."""
        ...


class AuthPAT:
    """Personal Access Token. PATs novos expiram em 24 h e não podem ser renovados."""

    def __init__(self, token: str):
        self._token = token

    def token(self) -> str:
        return self._token

    def renovar(self) -> bool:
        return False


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
            headers = {
                "Authorization": f"Bearer {self._auth.token()}",
                "Accept": "application/vnd.smartthings+json;v=1",
            }
            try:
                resposta = self._http.request(metodo, url, headers=headers, **kwargs)
            except httpx.TimeoutException as e:
                raise ErroDispositivo("A SmartThings não respondeu a tempo.") from e
            except httpx.HTTPError as e:
                raise ErroDispositivo("Sem conexão com a SmartThings. Verifique a internet.") from e
            if resposta.status_code == 401 and tentativa == 0 and self._auth.renovar():
                continue
            break

        codigo = resposta.status_code
        if codigo == 401:
            raise ErroDispositivo("Token da SmartThings inválido ou expirado. Rode 'uv run python -m mothlit setup'.")
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
