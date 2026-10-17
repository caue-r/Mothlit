"""Contrato comum entre a UI e os adaptadores de dispositivo."""

from typing import Any, Protocol


class ErroDispositivo(Exception):
    """Falha ao falar com um aparelho.

    A mensagem já é amigável e pode ir direto para a barra de status.
    """


class Device(Protocol):
    nome: str

    def ligar(self) -> None: ...

    def desligar(self) -> None: ...

    def estado(self) -> Any: ...
