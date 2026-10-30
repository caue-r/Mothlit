"""Tuya (Ekaza) lamp adapter over the LAN with tinytuya."""

import threading
from dataclasses import dataclass

import tinytuya

from .base import DeviceError

# tinytuya error codes (tinytuya.error_codes) translated for the user
_ERROR_MESSAGES = {
    "901": "Lamp unreachable. Is it plugged in and on the same network?",
    "902": "The lamp took too long to respond.",
    "905": "Lamp unreachable. Is it plugged in and on the same network?",
    "914": "The lamp refused the connection: check the local_key and the protocol version.",
}


@dataclass
class LampState:
    on: bool
    mode: str  # "white", "colour", "scene" or "music"
    brightness: int  # 0-100 %
    color_temp: int | None  # 0-100 % (0 = warm, 100 = cool)
    color_rgb: tuple[int, int, int] | None
    supports_temp: bool
    supports_color: bool
    color_hsv: tuple[float, float, float] | None = None  # each component from 0 to 1


class Lamp:
    name = "Lamp"

    def __init__(
        self,
        device_id: str,
        ip: str,
        local_key: str,
        version: float,
        timeout: float = 2.0,
        bulb: tinytuya.BulbDevice | None = None,
    ):
        # tinytuya's default is 5 s x 5 retries (up to 45 s). Here the worst case is ~5 s.
        self._bulb = bulb or tinytuya.BulbDevice(
            device_id,
            ip,
            local_key,
            version=version,
            connection_timeout=timeout,
            connection_retry_limit=2,
            connection_retry_delay=1,
        )
        # The tinytuya socket is not thread-safe: one command at a time.
        self._lock = threading.Lock()

    # --- commands ---

    def turn_on(self) -> None:
        self._execute(self._bulb.turn_on)

    def turn_off(self) -> None:
        self._execute(self._bulb.turn_off)

    def set_brightness(self, percent: int) -> None:
        # 0 % in tinytuya turns the lamp off; the useful minimum is 1 %.
        self._execute(self._bulb.set_brightness_percentage, _clamp(percent, 1, 100))

    def set_color_temp(self, percent: int) -> None:
        self._execute(self._bulb.set_colourtemp_percentage, _clamp(percent, 0, 100))

    def set_color(self, r: int, g: int, b: int) -> None:
        self._execute(self._bulb.set_colour, *(_clamp(c, 0, 255) for c in (r, g, b)))

    def set_hsv(self, h: float, s: float, v: float) -> None:
        """Color by hue/saturation/value, each from 0 to 1 (used by the color wheel)."""
        h, s, v = (max(0.0, min(1.0, float(x))) for x in (h, s, v))
        self._execute(self._bulb.set_hsv, h, s, max(v, 0.01))

    # --- reading ---

    def state(self) -> LampState:
        with self._lock:
            status = _check(self._call(self._bulb.status))
            if not self._bulb.bulb_configured:
                self._bulb.detect_bulb(response=status)
            if not self._bulb.bulb_configured:
                raise DeviceError("This device was not recognized as a lamp (unexpected DPS).")

            dps = status.get("dps", {})
            dpset = self._bulb.dpset
            maximum = self._max_value()

            def dp(feature):
                key = dpset.get(feature)
                return dps.get(key) if key else None

            mode = dp("mode") or "white"
            supports_temp = bool(dpset.get("colourtemp"))
            supports_color = bool(dpset.get("colour"))

            color = hsv = None
            hexcolor = dp("colour")
            if supports_color and isinstance(hexcolor, str) and hexcolor:
                try:
                    color = tinytuya.BulbDevice.hexvalue_to_rgb(hexcolor, dpset.get("value_hexformat"))
                    hsv = tinytuya.BulbDevice.hexvalue_to_hsv(hexcolor, dpset.get("value_hexformat"))
                except (ValueError, IndexError):
                    color = hsv = None

            # In colour mode the brightness lives in the V of the HSV, not in the brightness DP.
            if mode == "colour" and isinstance(hexcolor, str) and hexcolor:
                try:
                    _, _, v = tinytuya.BulbDevice.hexvalue_to_hsv(hexcolor, dpset.get("value_hexformat"))
                    brightness = round(v * 100)
                except (ValueError, IndexError):
                    brightness = 0
            else:
                brightness = _percent(dp("brightness"), maximum)

            temp = dp("colourtemp")
            return LampState(
                on=bool(dp("switch")),
                mode=mode,
                brightness=brightness,
                color_temp=_percent(temp, maximum) if supports_temp and temp is not None else None,
                color_rgb=tuple(color) if color else None,
                supports_temp=supports_temp,
                supports_color=supports_color,
                color_hsv=tuple(hsv) if hsv else None,
            )

    # --- internals ---

    def _max_value(self) -> int:
        maximum = self._bulb.dpset.get("value_max") or -1
        if maximum < 1:
            default = tinytuya.BulbDevice.DEFAULT_DPSET.get(self._bulb.bulb_type, {})
            maximum = default.get("value_max") or 1000
        return maximum

    def _execute(self, function, *args) -> None:
        with self._lock:
            _check(self._call(function, *args))

    @staticmethod
    def _call(function, *args):
        try:
            return function(*args)
        except (ValueError, RuntimeError) as e:
            raise DeviceError(f"Lamp: {e}") from e
        except OSError as e:
            raise DeviceError(_ERROR_MESSAGES["905"]) from e


def _check(response):
    """tinytuya returns errors as a dict {'Error', 'Err', 'Payload'} instead of raising."""
    if isinstance(response, dict) and "Error" in response:
        code = str(response.get("Err"))
        raise DeviceError(_ERROR_MESSAGES.get(code, f"Lamp: {response['Error']}"))
    return response if isinstance(response, dict) else {}


def _percent(value, maximum: int) -> int:
    if not isinstance(value, (int, float)):
        return 0
    return _clamp(round(value * 100 / maximum), 0, 100)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))
