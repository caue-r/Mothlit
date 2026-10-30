"""Configuration: non-sensitive values in the .env, secrets in the keyring.

The .env is looked up first in the current folder (handy during development) and then
in %APPDATA%\\Mothlit\\.env, which is where `setup` writes it.
"""

import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

import keyring
import keyring.errors
from dotenv import load_dotenv

KEYRING_SERVICE = "mothlit"

# Keyring entry names
SECRET_LAMP_KEY = "lamp_local_key"
SECRET_SMARTTHINGS_PAT = "smartthings_pat"

log = logging.getLogger(__name__)


class ConfigError(Exception):
    """Missing or invalid configuration."""


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Mothlit"


def env_path() -> Path:
    return config_dir() / ".env"


@dataclass
class Config:
    lamp_id: str
    lamp_ip: str
    lamp_version: float
    ac_device_id: str
    lamp_name: str = "Lamp"


def load() -> Config:
    # load_dotenv does not override variables that are already set: the local .env wins.
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(env_path())
    try:
        version = float(os.environ.get("LAMP_VERSION", "3.3"))
    except ValueError as e:
        raise ConfigError("Invalid LAMP_VERSION in the .env (e.g. 3.3, 3.5).") from e
    return Config(
        lamp_id=os.environ.get("LAMP_ID", ""),
        lamp_ip=os.environ.get("LAMP_IP", ""),
        lamp_version=version,
        ac_device_id=os.environ.get("SMARTTHINGS_DEVICE_ID", ""),
        lamp_name=os.environ.get("LAMP_NAME") or "Lamp",
    )


def save_env(values: dict[str, str]) -> Path:
    """Merges `values` into the user's .env and returns the path written."""
    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _read_env(path)
    current.update(values)
    _write_env(path, current)
    return path


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")


# --- file log (the .exe has no console) ---


def setup_logging() -> Path:
    """Log in %APPDATA%\\Mothlit\\mothlit.log, rotated (up to ~3 MB). Unhandled errors go there too."""
    path = config_dir() / "mothlit.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # chatty libraries (tinytuya at DEBUG even logs session keys)
    for name in ("httpx", "httpcore", "tinytuya", "urllib3", "pywebview", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)

    def record(kind, value, traceback, thread=None):
        logging.getLogger("mothlit").critical("Unhandled error%s", f" in thread {thread}" if thread else "",
                                              exc_info=(kind, value, traceback))

    sys.excepthook = record
    threading.excepthook = lambda a: record(a.exc_type, a.exc_value, a.exc_traceback, a.thread.name)
    return path


# --- app preferences (non-sensitive) ---

DEFAULT_PREFERENCES = {"close_to_tray": False}


def preferences_path() -> Path:
    return config_dir() / "preferences.json"


def read_preferences() -> dict:
    """Saved preferences, filled in with the defaults. Missing or corrupted file = defaults."""
    try:
        saved = json.loads(preferences_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULT_PREFERENCES, **{k: v for k, v in saved.items() if k in DEFAULT_PREFERENCES}}


def save_preference(name: str, value) -> dict:
    if name not in DEFAULT_PREFERENCES:
        raise ConfigError(f"Unknown preference: {name}")
    preferences = {**read_preferences(), name: value}
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preferences, indent=2), encoding="utf-8")
    return preferences


SECRET_SMARTTHINGS_OAUTH = "smartthings_oauth"

# Windows Credential Manager accepts up to 2560 bytes per secret (UTF-16: ~1280
# characters). Larger values (OAuth tokens can be long) are stored in chunks.
_CHUNK = 1000


def save_secret_json(name: str, data: dict) -> None:
    text = json.dumps(data, separators=(",", ":"))
    chunks = [text[i : i + _CHUNK] for i in range(0, len(text), _CHUNK)] or [""]
    old = int(read_secret(f"{name}#n") or 0)
    for i, chunk in enumerate(chunks):
        save_secret(f"{name}#{i}", chunk)
    save_secret(f"{name}#n", str(len(chunks)))  # last: it only "counts" once everything is written
    for i in range(len(chunks), old):
        delete_secret(f"{name}#{i}")


def read_secret_json(name: str) -> dict | None:
    total = read_secret(f"{name}#n")
    if not total:
        return None
    parts = [read_secret(f"{name}#{i}") for i in range(int(total))]
    if any(p is None for p in parts):
        return None
    try:
        return json.loads("".join(parts))
    except ValueError:
        return None


def delete_secret_json(name: str) -> None:
    total = int(read_secret(f"{name}#n") or 0)
    delete_secret(f"{name}#n")
    for i in range(total):
        delete_secret(f"{name}#{i}")


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def read_secret(name: str) -> str | None:
    return keyring.get_password(KEYRING_SERVICE, name)


def save_secret(name: str, value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, name, value)


# --- settings saved by older versions, which used Portuguese names ---

_LEGACY_ENV_KEYS = {
    "LAMPADA_ID": "LAMP_ID",
    "LAMPADA_IP": "LAMP_IP",
    "LAMPADA_VERSAO": "LAMP_VERSION",
    "LAMPADA_NOME": "LAMP_NAME",
}
_LEGACY_LAMP_KEY = "lampada_local_key"
_LEGACY_PREFERENCES = ("preferencias.json", {"fechar_para_bandeja": "close_to_tray"})
_LEGACY_OAUTH_FIELDS = {"expira_em": "expires_at"}


def migrate_legacy() -> None:
    """Renames settings saved by older versions. Idempotent: cheap to call on every start."""
    try:
        path = env_path()
        values = _read_env(path)
        if any(old in values for old in _LEGACY_ENV_KEYS):
            _write_env(path, {_LEGACY_ENV_KEYS.get(k, k): v for k, v in values.items()})

        old_key = read_secret(_LEGACY_LAMP_KEY)
        if old_key is not None:
            if read_secret(SECRET_LAMP_KEY) is None:
                save_secret(SECRET_LAMP_KEY, old_key)
            delete_secret(_LEGACY_LAMP_KEY)

        oauth = read_secret_json(SECRET_SMARTTHINGS_OAUTH)
        if oauth and any(old in oauth for old in _LEGACY_OAUTH_FIELDS):
            save_secret_json(SECRET_SMARTTHINGS_OAUTH, {_LEGACY_OAUTH_FIELDS.get(k, k): v for k, v in oauth.items()})

        file_name, keys = _LEGACY_PREFERENCES
        old_prefs = config_dir() / file_name
        if old_prefs.exists():
            if not preferences_path().exists():
                try:
                    saved = json.loads(old_prefs.read_text(encoding="utf-8"))
                except ValueError:
                    saved = {}
                for old, new in keys.items():
                    if old in saved:
                        save_preference(new, saved[old])
            old_prefs.unlink()
    except Exception:  # never blocks startup: at worst the user runs setup again
        log.exception("Could not migrate the settings from an older version")
