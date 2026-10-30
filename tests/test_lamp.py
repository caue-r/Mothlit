from unittest.mock import MagicMock

import pytest
import tinytuya

from mothlit.devices import DeviceError, Lamp

# Real status of the Ekaza panel (type B, protocol 3.5)
WHITE_STATUS = {
    "dps": {
        "20": True,
        "21": "white",
        "22": 500,
        "23": 342,
        "24": "000003e803e8",
        "25": "000e0d0000000000000000c80000",
        "26": 0,
        "34": True,
    }
}


def fake_bulb(status=WHITE_STATUS):
    """Real BulbDevice (no network) with a mocked status(), to test the actual detection."""
    bulb = tinytuya.BulbDevice("id", "127.0.0.1", "0123456789abcdef", version=3.5)
    bulb.status = MagicMock(return_value=status)
    for method in (
        "turn_on", "turn_off", "set_brightness_percentage", "set_colourtemp_percentage", "set_colour", "set_hsv"
    ):
        setattr(bulb, method, MagicMock(return_value={"dps": {}}))
    return bulb


def test_state_white_mode():
    state = Lamp("id", "ip", "key", 3.5, bulb=fake_bulb()).state()
    assert state.on is True
    assert state.mode == "white"
    assert state.brightness == 50
    assert state.color_temp == 34
    assert state.color_rgb == (255, 0, 0)
    assert state.supports_color and state.supports_temp


def test_state_colour_mode_uses_hsv_v_as_brightness():
    status = {"dps": {**WHITE_STATUS["dps"], "21": "colour", "24": "007803e801f4"}}  # h=120 s=1000 v=500
    state = Lamp("id", "ip", "key", 3.5, bulb=fake_bulb(status)).state()
    assert state.mode == "colour"
    assert state.brightness == 50
    h, s, v = state.color_hsv
    assert round(h * 360) == 120 and s == 1.0 and v == 0.5
    assert state.color_rgb[1] > state.color_rgb[0]


def test_commands_pass_through_to_tinytuya():
    bulb = fake_bulb()
    lamp = Lamp("id", "ip", "key", 3.5, bulb=bulb)
    lamp.turn_on()
    lamp.turn_off()
    lamp.set_brightness(0)  # 0 % would turn it off; the minimum is 1 %
    lamp.set_color_temp(150)
    lamp.set_color(300, -5, 10)
    bulb.turn_on.assert_called_once()
    bulb.turn_off.assert_called_once()
    bulb.set_brightness_percentage.assert_called_with(1)
    bulb.set_colourtemp_percentage.assert_called_with(100)
    bulb.set_colour.assert_called_with(255, 0, 10)
    lamp.set_hsv(0.5, 2.0, 0)  # clamps to 0..1 and avoids zero brightness
    bulb.set_hsv.assert_called_with(0.5, 1.0, 0.01)


def test_network_error_becomes_friendly_message():
    bulb = fake_bulb({"Error": "Network Error: Device Unreachable", "Err": "905", "Payload": None})
    with pytest.raises(DeviceError, match="unreachable"):
        Lamp("id", "ip", "key", 3.5, bulb=bulb).state()


def test_wrong_key_or_version():
    bulb = fake_bulb()
    bulb.turn_on.return_value = {"Error": "Check device key or version", "Err": "914", "Payload": None}
    with pytest.raises(DeviceError, match="local_key"):
        Lamp("id", "ip", "key", 3.5, bulb=bulb).turn_on()


def test_socket_exception_becomes_device_error():
    bulb = fake_bulb()
    bulb.turn_off.side_effect = OSError("boom")
    with pytest.raises(DeviceError):
        Lamp("id", "ip", "key", 3.5, bulb=bulb).turn_off()
