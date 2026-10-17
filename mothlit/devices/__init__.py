"""Adaptadores de dispositivo e fábricas a partir da configuração."""

from .. import config
from .ar_condicionado import ArCondicionado, EstadoAr
from .base import Device, ErroDispositivo
from .lampada import EstadoLampada, Lampada
from .smartthings import AuthOAuth, AuthPAT, CredenciaisOAuth, SmartThingsClient

__all__ = [
    "ArCondicionado",
    "Device",
    "ErroDispositivo",
    "EstadoAr",
    "EstadoLampada",
    "Lampada",
    "criar_ar",
    "criar_auth_smartthings",
    "criar_lampada",
]

_DICA_SETUP = "Rode 'uv run python -m mothlit setup'."


def criar_lampada(cfg: config.Config | None = None) -> Lampada:
    cfg = cfg or config.carregar()
    chave = config.ler_segredo(config.SEGREDO_LAMPADA_KEY)
    if not (cfg.lampada_id and cfg.lampada_ip and chave):
        raise config.ErroConfiguracao(f"Lâmpada não configurada. {_DICA_SETUP}")
    lampada = Lampada(cfg.lampada_id, cfg.lampada_ip, chave, cfg.lampada_versao)
    lampada.nome = cfg.lampada_nome
    return lampada


def salvar_credenciais_oauth(credenciais: CredenciaisOAuth) -> None:
    config.salvar_segredo_json(config.SEGREDO_SMARTTHINGS_OAUTH, credenciais.para_dict())


def criar_auth_smartthings() -> AuthOAuth | AuthPAT | None:
    """OAuth (renova sozinho) se configurado; senão o token pessoal (PAT)."""
    dados = config.ler_segredo_json(config.SEGREDO_SMARTTHINGS_OAUTH)
    if dados:
        try:
            return AuthOAuth(CredenciaisOAuth.de_dict(dados), salvar=salvar_credenciais_oauth)
        except KeyError:
            pass  # credenciais incompletas: cai para o PAT
    token = config.ler_segredo(config.SEGREDO_SMARTTHINGS_PAT)
    return AuthPAT(token) if token else None


def criar_ar(cfg: config.Config | None = None) -> ArCondicionado:
    cfg = cfg or config.carregar()
    auth = criar_auth_smartthings()
    if not (cfg.ar_device_id and auth):
        raise config.ErroConfiguracao(f"Ar-condicionado não configurado. {_DICA_SETUP}")
    return ArCondicionado(SmartThingsClient(auth), cfg.ar_device_id)
