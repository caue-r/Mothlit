from unittest.mock import MagicMock

import pytest

from mothlit.devices import ArCondicionado, ErroDispositivo

# Resumo do GET /devices/{id} e /status reais do Samsung (componente main)
DISPOSITIVO = {
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
        }
    }
}


def ar_falso(status=STATUS):
    cliente = MagicMock()
    cliente.dispositivo.return_value = DISPOSITIVO
    cliente.status.return_value = status
    return ArCondicionado(cliente, "dev1"), cliente


def test_estado_le_atributos_reais():
    ar, _ = ar_falso()
    e = ar.estado()
    assert e.ligado is True
    assert e.temperatura_ambiente == 25
    assert e.temperatura_alvo == 26
    assert e.faixa_alvo == (18, 30, 1)
    assert e.modo == "auto"
    assert e.modos == ["auto", "cool", "dry", "wind"]
    assert e.ventiladores == ["auto"]  # available tem prioridade sobre supported
    assert "dustSensor" not in e.capabilities  # desativada pelo aparelho


def test_usa_supported_quando_nao_ha_available():
    status = {"components": {"main": {**STATUS["components"]["main"]}}}
    status["components"]["main"]["airConditionerFanMode"] = {
        "fanMode": {"value": "low"},
        "supportedAcFanModes": {"value": ["auto", "low"]},
    }
    ar, _ = ar_falso(status)
    assert ar.estado().ventiladores == ["auto", "low"]


def test_comandos_usam_nomes_da_api():
    ar, cliente = ar_falso()
    ar.ligar()
    ar.desligar()
    ar.definir_modo("cool")
    ar.definir_ventilador("high")
    cliente.executar.assert_any_call("dev1", "switch", "on", None, "main")
    cliente.executar.assert_any_call("dev1", "switch", "off", None, "main")
    cliente.executar.assert_any_call("dev1", "airConditionerMode", "setAirConditionerMode", ["cool"], "main")
    cliente.executar.assert_any_call("dev1", "airConditionerFanMode", "setFanMode", ["high"], "main")


def test_temperatura_respeita_faixa_lida():
    ar, cliente = ar_falso()
    ar.estado()  # carrega a faixa 18-30
    assert ar.definir_temperatura(10) == 18
    cliente.executar.assert_called_with(
        "dev1", "thermostatCoolingSetpoint", "setCoolingSetpoint", [18], "main"
    )
    assert ar.definir_temperatura(99) == 30


def test_capability_ausente_nao_envia_comando():
    ar, cliente = ar_falso()
    cliente.dispositivo.return_value = {"components": [{"id": "main", "capabilities": [{"id": "switch"}]}]}
    with pytest.raises(ErroDispositivo, match="não suporta"):
        ar.definir_modo("cool")
    cliente.executar.assert_not_called()
