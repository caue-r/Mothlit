from unittest.mock import MagicMock

import pytest

from mothlit.devices import AirConditioner, DeviceError

# Summary of the real Samsung GET /devices/{id} and /status (main component)
DEVICE = {
    "label": "Bedroom AC",
    "components": [
        {
            "id": "main",
            "capabilities": [
                {"id": c}
                for c in (
                    "switch",
                    "airConditionerMode",
                    "airConditionerFanMode",
                    "temperatureMeasurement",
                    "thermostatCoolingSetpoint",
                    "dustSensor",
                    "custom.disabledCapabilities",
                    "fanOscillationMode",
                    "custom.airConditionerOptionalMode",
                )
            ],
        }
    ]
}

STATUS = {
    "components": {
        "main": {
            "switch": {"switch": {"value": "on"}},
            "airConditionerMode": {
                "availableAcModes": {"value": ["auto", "cool", "dry", "wind"]},
                "supportedAcModes": {"value": ["auto", "cool", "dry", "wind"]},
                "airConditionerMode": {"value": "auto"},
            },
            "airConditionerFanMode": {
                "fanMode": {"value": "auto"},
                "supportedAcFanModes": {"value": ["auto", "low", "medium", "high", "turbo"]},
                "availableAcFanModes": {"value": ["auto"]},
            },
            "temperatureMeasurement": {"temperatureRange": {"value": None}, "temperature": {"value": 25, "unit": "C"}},
            "thermostatCoolingSetpoint": {
                "coolingSetpointRange": {"value": {"minimum": 18, "maximum": 30, "step": 1}, "unit": "C"},
                "coolingSetpoint": {"value": 26, "unit": "C"},
            },
            "custom.disabledCapabilities": {"disabledCapabilities": {"value": ["dustSensor"]}},
            "fanOscillationMode": {
                "supportedFanOscillationModes": {"value": ["fixed", "vertical", "horizontal", "all"]},
                "availableFanOscillationModes": {"value": None},
                "fanOscillationMode": {"value": "fixed"},
            },
            "custom.airConditionerOptionalMode": {
                "supportedAcOptionalMode": {"value": ["off", "sleep", "quiet", "windFree"]},
                "availableAcOptionalMode": {"value": None},
                "acOptionalMode": {"value": "off"},
            },
        }
    }
}


def fake_ac(status=STATUS):
    client = MagicMock()
    client.device.return_value = DEVICE
    client.status.return_value = status
    return AirConditioner(client, "dev1"), client


def test_state_reads_real_attributes():
    ac, _ = fake_ac()
    s = ac.state()
    assert s.on is True
    assert s.room_temp == 25
    assert s.target_temp == 26
    assert s.target_range == (18, 30, 1)
    assert s.mode == "auto"
    assert s.modes == ["auto", "cool", "dry", "wind"]
    assert s.fans == ["auto"]  # available takes priority over supported
    assert "dustSensor" not in s.capabilities  # disabled by the device


def test_state_samsung_extras():
    ac, _ = fake_ac()
    s = ac.state()
    assert s.label == "Bedroom AC"
    assert s.oscillation == "fixed"
    assert s.oscillations == ["fixed", "vertical", "horizontal", "all"]
    assert s.optional_mode == "off"
    assert "sleep" in s.optional_modes


def test_extra_commands_use_api_names():
    ac, client = fake_ac()
    ac.set_oscillation("vertical")
    ac.set_optional_mode("sleep")
    client.execute.assert_any_call("dev1", "fanOscillationMode", "setFanOscillationMode", ["vertical"], "main")
    client.execute.assert_any_call(
        "dev1", "custom.airConditionerOptionalMode", "setAcOptionalMode", ["sleep"], "main"
    )


def test_uses_supported_when_there_is_no_available():
    status = {"components": {"main": {**STATUS["components"]["main"]}}}
    status["components"]["main"]["airConditionerFanMode"] = {
        "fanMode": {"value": "low"},
        "supportedAcFanModes": {"value": ["auto", "low"]},
    }
    ac, _ = fake_ac(status)
    assert ac.state().fans == ["auto", "low"]


def test_commands_use_api_names():
    ac, client = fake_ac()
    ac.turn_on()
    ac.turn_off()
    ac.set_mode("cool")
    ac.set_fan("high")
    client.execute.assert_any_call("dev1", "switch", "on", None, "main")
    client.execute.assert_any_call("dev1", "switch", "off", None, "main")
    client.execute.assert_any_call("dev1", "airConditionerMode", "setAirConditionerMode", ["cool"], "main")
    client.execute.assert_any_call("dev1", "airConditionerFanMode", "setFanMode", ["high"], "main")


def test_temperature_respects_the_range_read():
    ac, client = fake_ac()
    ac.state()  # loads the 18-30 range
    assert ac.set_temperature(10) == 18
    client.execute.assert_called_with(
        "dev1", "thermostatCoolingSetpoint", "setCoolingSetpoint", [18], "main"
    )
    assert ac.set_temperature(99) == 30


def test_missing_capability_sends_no_command():
    ac, client = fake_ac()
    client.device.return_value = {"components": [{"id": "main", "capabilities": [{"id": "switch"}]}]}
    with pytest.raises(DeviceError, match="does not support"):
        ac.set_mode("cool")
    client.execute.assert_not_called()
