"""The bridge to JavaScript: always answers plain dicts, never lets an exception escape."""

from unittest.mock import MagicMock

from mothlit.devices import AcState, DeviceError, LampState
from mothlit.ui.app import Api


def ac_state():
    return AcState(
        on=True, target_temp=24.0, target_range=(16.0, 30.0, 1.0), room_temp=25.0,
        mode="cool", modes=["auto", "cool"], fan="auto", fans=["auto", "low"],
        capabilities={"switch"}, oscillation="fixed", oscillations=["fixed", "all"], optional_mode="off",
        optional_modes=["off", "sleep"], label="Bedroom AC",
    )


def light_state():
    return LampState(on=True, mode="colour", brightness=40, color_temp=30, color_rgb=(255, 0, 0),
                     supports_temp=True, supports_color=True, color_hsv=(0.0, 1.0, 0.4))


def test_ac_state_becomes_serializable_dict():
    ac = MagicMock()
    ac.state.return_value = ac_state()
    r = Api(ac=ac).ac_state()
    assert r["ok"] is True
    assert r["data"]["name"] == "Bedroom AC"
    assert r["data"]["range"] == [16.0, 30.0, 1.0]
    assert r["data"]["optionals"] == ["off", "sleep"]
    assert "capabilities" not in r["data"]  # a set is not JSON serializable


def test_light_state_becomes_dict():
    lamp = MagicMock()
    lamp.name = "Bedroom"
    lamp.state.return_value = light_state()
    r = Api(lamp=lamp).light_state()
    assert r["data"] == {
        "name": "Bedroom", "on": True, "mode": "colour", "brightness": 40, "temperature": 30,
        "hsv": [0.0, 1.0, 0.4], "supportsColor": True, "supportsTemperature": True,
    }


def test_commands_reach_the_adapters():
    ac, lamp = MagicMock(), MagicMock()
    api = Api(lamp=lamp, ac=ac)
    api.ac_power(False)
    api.ac_temperature(23)
    api.ac_mode("dry")
    api.ac_oscillation("all")
    api.light_power(True)
    api.light_brightness(55.4)
    api.light_hsv(0.5, 0.8, 0.3)
    ac.turn_off.assert_called_once()
    ac.set_temperature.assert_called_with(23.0)
    ac.set_mode.assert_called_with("dry")
    ac.set_oscillation.assert_called_with("all")
    lamp.turn_on.assert_called_once()
    lamp.set_brightness.assert_called_with(55)
    lamp.set_hsv.assert_called_with(0.5, 0.8, 0.3)


def test_device_error_becomes_message():
    lamp = MagicMock()
    lamp.turn_on.side_effect = DeviceError("Lamp unreachable.")
    assert Api(lamp=lamp).light_power(True) == {"ok": False, "configured": True, "error": "Lamp unreachable."}


def test_unexpected_error_does_not_escape():
    ac = MagicMock()
    ac.state.side_effect = KeyError("x")
    r = Api(ac=ac).ac_state()
    assert r["ok"] is False and r["error"].startswith("Unexpected error")


def test_toggle_reads_state_and_flips_it():
    lamp = MagicMock()
    lamp.name = "Bedroom"
    lamp.state.return_value = light_state()  # on
    api = Api(lamp=lamp)
    r = api.toggle_light()
    assert r["ok"] is True and r["data"] is False
    lamp.turn_off.assert_called_once()
    assert api.last_on("light") is False


def test_toggle_with_error_sends_no_command():
    ac = MagicMock()
    ac.state.side_effect = DeviceError("No internet.")
    r = Api(ac=ac).toggle_ac()
    assert r == {"ok": False, "configured": True, "error": "No internet."}
    ac.turn_on.assert_not_called()
    ac.turn_off.assert_not_called()


def test_state_change_notifies_the_tray():
    ac = MagicMock()
    ac.state.return_value = ac_state()  # on
    api = Api(ac=ac)
    notices = []
    api._on_change = lambda: notices.append(api.last_on("ac"))
    assert api.last_on("ac") is None
    api.ac_state()
    api.ac_state()  # same state: no new notice
    api.ac_power(False)
    assert notices == [True, False]


def test_close_honors_preference(monkeypatch):
    from mothlit import config

    api = Api()
    api._window = MagicMock()
    monkeypatch.setattr(config, "read_preferences", lambda: {"close_to_tray": True})
    assert api.close()["data"] == "tray"
    api._window.hide.assert_called_once()
    api._window.destroy.assert_not_called()

    monkeypatch.setattr(config, "read_preferences", lambda: {"close_to_tray": False})
    assert api.close()["data"] == "quit"
    api._window.destroy.assert_called_once()


def test_open_full_hides_the_panel_and_opens_on_the_tab():
    api = Api()
    api._flyout = MagicMock()
    opened = []
    api._open_full = opened.append
    api.open_full("light")
    api._flyout.hide.assert_called_once()
    assert opened == ["light"]
    api.hide_flyout()
    assert api._flyout.hide.call_count == 2


def test_quit_ignores_preference():
    api = Api()
    api._window = MagicMock()
    api.quit()
    assert api._quitting is True
    api._window.destroy.assert_called_once()


def test_set_preferences(monkeypatch):
    from mothlit import config, startup

    state = {"registry": False, "tray": False}
    monkeypatch.setattr(startup, "enabled", lambda: state["registry"])
    monkeypatch.setattr(startup, "supported", lambda: True)
    monkeypatch.setattr(startup, "set_enabled", lambda v: state.__setitem__("registry", v))
    monkeypatch.setattr(config, "read_preferences", lambda: {"close_to_tray": state["tray"]})
    monkeypatch.setattr(config, "save_preference", lambda n, v: state.__setitem__("tray", v))
    api = Api()
    assert api.set_preference("launchAtStartup", True)["data"]["launchAtStartup"] is True
    assert api.set_preference("closeToTray", True)["data"]["closeToTray"] is True
    assert api.set_preference("other", True)["ok"] is False


def test_registry_write_error_becomes_message(monkeypatch):
    from mothlit import startup

    def fail(_):
        raise PermissionError("access denied")

    monkeypatch.setattr(startup, "set_enabled", fail)
    r = Api().set_preference("launchAtStartup", True)
    assert r["ok"] is False and "access denied" in r["error"]


def _cfg():
    from mothlit import config

    return config.Config("lamp", "1.2.3.4", 3.5, "ac-1")


def test_replace_token_validates_before_saving(monkeypatch):
    from mothlit import config
    from mothlit.ui import app as mod

    saved, deleted = {}, []
    client = MagicMock()
    monkeypatch.setattr(mod, "SmartThingsClient", lambda auth: client)
    monkeypatch.setattr(config, "load", _cfg)
    monkeypatch.setattr(config, "save_secret", lambda n, v: saved.__setitem__(n, v))
    monkeypatch.setattr(config, "delete_secret_json", deleted.append)
    monkeypatch.setattr(mod, "create_ac", lambda: "new-ac")
    monkeypatch.setattr(mod, "create_smartthings_auth", lambda: mod.AuthPAT("new"))

    api = Api()
    r = api.replace_smartthings_token("  new  ")
    client.device.assert_called_once_with("ac-1")
    assert saved == {config.SECRET_SMARTTHINGS_PAT: "new"}
    assert deleted == [config.SECRET_SMARTTHINGS_OAUTH]
    assert api._ac == "new-ac"
    assert r["data"]["smartthings"] == {"kind": "pat", "expiresAt": None}


def test_rejected_token_is_not_saved(monkeypatch):
    from mothlit import config
    from mothlit.ui import app as mod

    client = MagicMock()
    client.device.side_effect = DeviceError("SmartThings token expired or invalid.")
    monkeypatch.setattr(mod, "SmartThingsClient", lambda auth: client)
    monkeypatch.setattr(config, "load", _cfg)
    save = MagicMock()
    monkeypatch.setattr(config, "save_secret", save)

    r = Api().replace_smartthings_token("bad")
    assert r["ok"] is False and r["error"].startswith("Token not accepted")
    save.assert_not_called()
    assert Api().replace_smartthings_token("   ")["ok"] is False


def test_device_not_configured():
    r = Api(ac_error="Air conditioner not configured.").ac_state()
    assert r == {"ok": False, "configured": False, "error": "Air conditioner not configured."}
