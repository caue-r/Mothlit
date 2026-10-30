import json

import pytest

from mothlit import config
from mothlit.devices import create_ac, create_lamp


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for var in ("LAMP_ID", "LAMP_IP", "LAMP_VERSION", "SMARTTHINGS_DEVICE_ID"):
        monkeypatch.delenv(var, raising=False)
    vault = {}
    monkeypatch.setattr(config.keyring, "get_password", lambda s, n: vault.get((s, n)))
    monkeypatch.setattr(config.keyring, "set_password", lambda s, n, v: vault.__setitem__((s, n), v))

    def delete(s, n):
        if (s, n) not in vault:
            raise config.keyring.errors.PasswordDeleteError(n)
        del vault[(s, n)]

    monkeypatch.setattr(config.keyring, "delete_password", delete)
    return vault


def test_save_env_merges_values(environment):
    config.save_env({"LAMP_ID": "a", "LAMP_IP": "1.2.3.4"})
    path = config.save_env({"LAMP_IP": "5.6.7.8"})
    assert path.read_text(encoding="utf-8") == "LAMP_ID=a\nLAMP_IP=5.6.7.8\n"


def test_secrets_go_to_the_keyring(environment):
    config.save_secret(config.SECRET_LAMP_KEY, "secret")
    assert environment == {("mothlit", "lamp_local_key"): "secret"}
    assert config.read_secret(config.SECRET_LAMP_KEY) == "secret"


def test_large_json_secret_is_chunked(environment):
    data = {"access_token": "a" * 2500, "refresh_token": "r" * 1500, "expires_at": 1.5}
    config.save_secret_json("oauth", data)
    assert all(len(v) <= 1000 for v in environment.values())  # fits the Windows limit
    assert config.read_secret_json("oauth") == data
    config.save_secret_json("oauth", {"short": 1})  # rewriting smaller deletes the leftover chunks
    assert config.read_secret_json("oauth") == {"short": 1}
    assert ("mothlit", "oauth#4") not in environment


def test_factory_prefers_oauth(environment):
    from mothlit.devices import create_smartthings_auth
    from mothlit.devices.smartthings import AuthOAuth, AuthPAT

    config.save_secret(config.SECRET_SMARTTHINGS_PAT, "pat")
    assert isinstance(create_smartthings_auth(), AuthPAT)
    config.save_secret_json(config.SECRET_SMARTTHINGS_OAUTH, {
        "client_id": "c", "client_secret": "s", "access_token": "a", "refresh_token": "r", "expires_at": 0})
    assert isinstance(create_smartthings_auth(), AuthOAuth)


def test_default_and_saved_preferences(environment):
    assert config.read_preferences() == {"close_to_tray": False}
    config.save_preference("close_to_tray", True)
    assert config.read_preferences() == {"close_to_tray": True}


def test_corrupted_preferences_fall_back_to_defaults(environment):
    config.preferences_path().parent.mkdir(parents=True, exist_ok=True)
    config.preferences_path().write_text("{this is not json", encoding="utf-8")
    assert config.read_preferences() == {"close_to_tray": False}


def test_unknown_preference(environment):
    with pytest.raises(config.ConfigError):
        config.save_preference("theme", "light")


def test_factories_require_setup(environment):
    with pytest.raises(config.ConfigError, match="setup"):
        create_lamp()
    with pytest.raises(config.ConfigError, match="setup"):
        create_ac()


def test_lamp_factory_uses_env_and_keyring(environment):
    cfg = config.Config("id1", "192.168.0.10", 3.5, "")
    config.save_secret(config.SECRET_LAMP_KEY, "0123456789abcdef")
    assert create_lamp(cfg).name == "Lamp"


def test_migrates_settings_from_older_versions(environment, tmp_path):
    folder = tmp_path / "Mothlit"
    folder.mkdir()
    (folder / ".env").write_text("LAMPADA_ID=id1\nLAMPADA_IP=192.168.0.10\nSMARTTHINGS_DEVICE_ID=ac-1\n",
                                 encoding="utf-8")
    (folder / "preferencias.json").write_text(json.dumps({"fechar_para_bandeja": True}), encoding="utf-8")
    environment[("mothlit", "lampada_local_key")] = "key"
    config.save_secret_json(config.SECRET_SMARTTHINGS_OAUTH, {"client_id": "c", "expira_em": 5})

    config.migrate_legacy()
    config.migrate_legacy()  # running again changes nothing

    assert (folder / ".env").read_text(encoding="utf-8") == (
        "LAMP_ID=id1\nLAMP_IP=192.168.0.10\nSMARTTHINGS_DEVICE_ID=ac-1\n")
    assert config.read_preferences() == {"close_to_tray": True}
    assert not (folder / "preferencias.json").exists()
    assert config.read_secret(config.SECRET_LAMP_KEY) == "key"
    assert ("mothlit", "lampada_local_key") not in environment
    assert config.read_secret_json(config.SECRET_SMARTTHINGS_OAUTH) == {"client_id": "c", "expires_at": 5}
