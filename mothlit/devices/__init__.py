"""Device adapters and factories built from the configuration."""

from .. import config
from .air_conditioner import AcState, AirConditioner
from .base import Device, DeviceError
from .lamp import Lamp, LampState
from .smartthings import AuthOAuth, AuthPAT, OAuthCredentials, SmartThingsClient

__all__ = [
    "AcState",
    "AirConditioner",
    "Device",
    "DeviceError",
    "Lamp",
    "LampState",
    "create_ac",
    "create_lamp",
    "create_smartthings_auth",
]

_SETUP_HINT = "Run 'uv run python -m mothlit setup'."


def create_lamp(cfg: config.Config | None = None) -> Lamp:
    cfg = cfg or config.load()
    key = config.read_secret(config.SECRET_LAMP_KEY)
    if not (cfg.lamp_id and cfg.lamp_ip and key):
        raise config.ConfigError(f"Lamp not configured. {_SETUP_HINT}")
    lamp = Lamp(cfg.lamp_id, cfg.lamp_ip, key, cfg.lamp_version)
    lamp.name = cfg.lamp_name
    return lamp


def save_oauth_credentials(credentials: OAuthCredentials) -> None:
    config.save_secret_json(config.SECRET_SMARTTHINGS_OAUTH, credentials.to_dict())


def create_smartthings_auth() -> AuthOAuth | AuthPAT | None:
    """OAuth (refreshes itself) if configured; otherwise the personal access token (PAT)."""
    data = config.read_secret_json(config.SECRET_SMARTTHINGS_OAUTH)
    if data:
        try:
            return AuthOAuth(OAuthCredentials.from_dict(data), save=save_oauth_credentials)
        except KeyError:
            pass  # incomplete credentials: fall back to the PAT
    token = config.read_secret(config.SECRET_SMARTTHINGS_PAT)
    return AuthPAT(token) if token else None


def create_ac(cfg: config.Config | None = None) -> AirConditioner:
    cfg = cfg or config.load()
    auth = create_smartthings_auth()
    if not (cfg.ac_device_id and auth):
        raise config.ConfigError(f"Air conditioner not configured. {_SETUP_HINT}")
    return AirConditioner(SmartThingsClient(auth), cfg.ac_device_id)
