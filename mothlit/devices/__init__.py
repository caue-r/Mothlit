"""Adaptadores de dispositivo e fábricas a partir da configuração."""

from .. import config
from .ar_condicionado import ArCondicionado, EstadoAr
from .base import Device, ErroDispositivo
from .lampada import EstadoLampada, Lampada
from .smartthings import AuthPAT, SmartThingsClient

__all__ = [
    "ArCondicionado",
    "Device",
    "ErroDispositivo",
    "EstadoAr",
    "EstadoLampada",
    "Lampada",
    "criar_ar",
    "criar_lampada",
]

_DICA_SETUP = "Rode 'python -m mothlit setup'."


def criar_lampada(cfg: config.Config | None = None) -> Lampada:
    cfg = cfg or config.carregar()
    chave = config.ler_segredo(config.SEGREDO_LAMPADA_KEY)
    if not (cfg.lampada_id and cfg.lampada_ip and chave):
        raise config.ErroConfiguracao(f"Lâmpada não configurada. {_DICA_SETUP}")
    return Lampada(cfg.lampada_id, cfg.lampada_ip, chave, cfg.lampada_versao)


def criar_ar(cfg: config.Config | None = None) -> ArCondicionado:
    cfg = cfg or config.carregar()
    token = config.ler_segredo(config.SEGREDO_SMARTTHINGS_PAT)
    if not (cfg.ar_device_id and token):
        raise config.ErroConfiguracao(f"Ar-condicionado não configurado. {_DICA_SETUP}")
    return ArCondicionado(SmartThingsClient(AuthPAT(token)), cfg.ar_device_id)
