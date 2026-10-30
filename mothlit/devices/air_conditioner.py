"""Samsung air conditioner adapter via the SmartThings API."""

import threading
from dataclasses import dataclass, field

from .base import DeviceError
from .smartthings import SmartThingsClient

CAP_SWITCH = "switch"
CAP_SETPOINT = "thermostatCoolingSetpoint"
CAP_MODE = "airConditionerMode"
CAP_FAN = "airConditionerFanMode"
CAP_TEMPERATURE = "temperatureMeasurement"
CAP_OSCILLATION = "fanOscillationMode"
CAP_OPTIONAL = "custom.airConditionerOptionalMode"  # Samsung: sleep, quiet, windFree...

DEFAULT_RANGE = (16.0, 30.0, 1.0)


@dataclass
class AcState:
    on: bool
    target_temp: float | None
    target_range: tuple[float, float, float]  # minimum, maximum, step
    room_temp: float | None
    mode: str | None
    modes: list[str] = field(default_factory=list)
    fan: str | None = None
    fans: list[str] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    oscillation: str | None = None
    oscillations: list[str] = field(default_factory=list)
    optional_mode: str | None = None
    optional_modes: list[str] = field(default_factory=list)
    label: str = ""


class AirConditioner:
    name = "Air conditioner"

    def __init__(self, client: SmartThingsClient, device_id: str, component: str = "main"):
        self._client = client
        self._id = device_id
        self._component = component
        self._capabilities: set[str] | None = None
        self.label = ""
        self._range = DEFAULT_RANGE
        self._lock = threading.Lock()

    def capabilities(self) -> set[str]:
        """Capabilities declared by the device (read once via GET /devices/{id})."""
        if self._capabilities is None:
            data = self._client.device(self._id)
            self.label = data.get("label") or data.get("name") or ""
            for comp in data.get("components", []):
                if comp.get("id") == self._component:
                    self._capabilities = {c["id"] for c in comp.get("capabilities", [])}
                    break
            else:
                raise DeviceError("The air conditioner does not have the expected main component.")
        return self._capabilities

    # --- commands ---

    def turn_on(self) -> None:
        self._execute(CAP_SWITCH, "on")

    def turn_off(self) -> None:
        self._execute(CAP_SWITCH, "off")

    def set_temperature(self, value: float) -> float:
        minimum, maximum, _ = self._range
        value = max(minimum, min(maximum, value))
        # The API accepts a number; we send an integer when there is no fraction (e.g. 24, not 24.0).
        self._execute(CAP_SETPOINT, "setCoolingSetpoint", [int(value) if value == int(value) else value])
        return value

    def set_mode(self, mode: str) -> None:
        self._execute(CAP_MODE, "setAirConditionerMode", [mode])

    def set_fan(self, speed: str) -> None:
        self._execute(CAP_FAN, "setFanMode", [speed])

    def set_oscillation(self, mode: str) -> None:
        self._execute(CAP_OSCILLATION, "setFanOscillationMode", [mode])

    def set_optional_mode(self, mode: str) -> None:
        self._execute(CAP_OPTIONAL, "setAcOptionalMode", [mode])

    # --- reading ---

    def state(self) -> AcState:
        with self._lock:
            caps = set(self.capabilities())
            comp = self._client.status(self._id).get("components", {}).get(self._component, {})

        def value(cap, attribute):
            return ((comp.get(cap) or {}).get(attribute) or {}).get("value")

        # Some capabilities are declared but disabled on this model.
        caps -= set(value("custom.disabledCapabilities", "disabledCapabilities") or [])

        setpoint_range = value(CAP_SETPOINT, "coolingSetpointRange")
        if isinstance(setpoint_range, dict) and "minimum" in setpoint_range and "maximum" in setpoint_range:
            self._range = (float(setpoint_range["minimum"]), float(setpoint_range["maximum"]),
                           float(setpoint_range.get("step") or 1))

        # "available*" changes with the current mode (e.g. in auto the only fan speed is auto);
        # "supported*" is the device's full list.
        modes = value(CAP_MODE, "availableAcModes") or value(CAP_MODE, "supportedAcModes") or []
        fans = value(CAP_FAN, "availableAcFanModes") or value(CAP_FAN, "supportedAcFanModes") or []

        return AcState(
            on=value(CAP_SWITCH, "switch") == "on",
            target_temp=_number(value(CAP_SETPOINT, "coolingSetpoint")),
            target_range=self._range,
            room_temp=_number(value(CAP_TEMPERATURE, "temperature")),
            mode=value(CAP_MODE, "airConditionerMode"),
            modes=list(modes),
            fan=value(CAP_FAN, "fanMode"),
            fans=list(fans),
            capabilities=caps,
            oscillation=value(CAP_OSCILLATION, "fanOscillationMode"),
            oscillations=list(
                value(CAP_OSCILLATION, "availableFanOscillationModes")
                or value(CAP_OSCILLATION, "supportedFanOscillationModes")
                or []
            ),
            optional_mode=value(CAP_OPTIONAL, "acOptionalMode"),
            optional_modes=list(
                value(CAP_OPTIONAL, "availableAcOptionalMode") or value(CAP_OPTIONAL, "supportedAcOptionalMode") or []
            ),
            label=self.label,
        )

    # --- internals ---

    def _execute(self, capability: str, command: str, arguments: list | None = None) -> None:
        with self._lock:
            if capability not in self.capabilities():
                raise DeviceError(f"The air conditioner does not support '{capability}'.")
            self._client.execute(self._id, capability, command, arguments, self._component)


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
