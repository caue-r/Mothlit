"""Mothlit window with pywebview (WebView2 on Windows).

The interface is HTML/CSS/JS in `web/`. The JavaScript calls the public methods of
`Api` (`pywebview.api.<method>()`); pywebview runs each call in a separate thread,
so the network never freezes the interface. Every response is a plain dict:
`{"ok": True, "data": ...}` or `{"ok": False, "error": "friendly message"}`.
"""

import ctypes
import json
import logging
import threading
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

import webview

from .. import config, startup
from ..config import ConfigError
from ..devices import (
    AcState,
    AirConditioner,
    DeviceError,
    Lamp,
    LampState,
    create_ac,
    create_lamp,
    create_smartthings_auth,
)
from ..devices.smartthings import AuthPAT, SmartThingsClient
from . import brand

WEB = Path(__file__).resolve().parent / "web"
WIDTH, HEIGHT = 420, 760
BACKGROUND = "#09090b"

log = logging.getLogger(__name__)


def _ac_dict(s: AcState) -> dict[str, Any]:
    return {
        "name": s.label,
        "on": s.on,
        "target": s.target_temp,
        "range": list(s.target_range),
        "room": s.room_temp,
        "mode": s.mode,
        "modes": s.modes,
        "fan": s.fan,
        "fans": s.fans,
        "optional": s.optional_mode,
        "optionals": s.optional_modes,
        "oscillation": s.oscillation,
        "oscillations": s.oscillations,
    }


def _light_dict(s: LampState, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "on": s.on,
        "mode": s.mode,
        "brightness": s.brightness,
        "temperature": s.color_temp,
        "hsv": list(s.color_hsv) if s.color_hsv else None,
        "supportsColor": s.supports_color,
        "supportsTemperature": s.supports_temp,
    }


def _create(factory):
    try:
        return factory(), None
    except ConfigError as e:
        return None, str(e)


class Api:
    """Methods called by the JavaScript. Private attributes (starting with _) are not exposed."""

    def __init__(self, lamp: Lamp | None = None, ac: AirConditioner | None = None,
                 lamp_error: str | None = None, ac_error: str | None = None):
        self._lamp, self._lamp_error = lamp, lamp_error
        self._ac, self._ac_error = ac, ac_error
        self._window = None
        # last known on/off of each device (used by the tray menu)
        self._on: dict[str, bool | None] = {"ac": None, "light": None}
        self._quitting = False
        self._flyout = None  # tray quick panel (ui.flyout.QuickPanel)
        self._open_full: Callable[[str | None], None] | None = None
        self._on_change: Callable[[], None] | None = None

    @classmethod
    def from_config(cls) -> "Api":
        lamp, lamp_error = _create(create_lamp)
        ac, ac_error = _create(create_ac)
        return cls(lamp, ac, lamp_error, ac_error)

    # --- air conditioner ---

    def ac_state(self):
        r = self._use_ac(lambda ac: _ac_dict(ac.state()))
        if r["ok"]:
            self._remember("ac", r["data"]["on"])
        return r

    def ac_power(self, on: bool):
        r = self._use_ac(lambda ac: ac.turn_on() if on else ac.turn_off())
        if r["ok"]:
            self._remember("ac", bool(on))
        return r

    def toggle_ac(self):
        """Reads the current state and flips it (used by the tray)."""
        return self._toggle(self.ac_state, self.ac_power)

    def ac_temperature(self, value: float):
        return self._use_ac(lambda ac: ac.set_temperature(float(value)))

    def ac_mode(self, mode: str):
        return self._use_ac(lambda ac: ac.set_mode(str(mode)))

    def ac_fan(self, speed: str):
        return self._use_ac(lambda ac: ac.set_fan(str(speed)))

    def ac_optional(self, mode: str):
        return self._use_ac(lambda ac: ac.set_optional_mode(str(mode)))

    def ac_oscillation(self, mode: str):
        return self._use_ac(lambda ac: ac.set_oscillation(str(mode)))

    # --- lamp ---

    def light_state(self):
        r = self._use_light(lambda lamp: _light_dict(lamp.state(), lamp.name))
        if r["ok"]:
            self._remember("light", r["data"]["on"])
        return r

    def light_power(self, on: bool):
        r = self._use_light(lambda lamp: lamp.turn_on() if on else lamp.turn_off())
        if r["ok"]:
            self._remember("light", bool(on))
        return r

    def toggle_light(self):
        """Reads the current state and flips it (used by the tray)."""
        return self._toggle(self.light_state, self.light_power)

    def light_brightness(self, percent: int):
        return self._use_light(lambda lamp: lamp.set_brightness(round(percent)))

    def light_temperature(self, percent: int):
        return self._use_light(lambda lamp: lamp.set_color_temp(round(percent)))

    def light_hsv(self, h: float, s: float, v: float):
        return self._use_light(lambda lamp: lamp.set_hsv(h, s, v))

    def last_on(self, which: str) -> bool | None:
        """Last known on/off ("ac" or "light"), without going to the network."""
        return self._on.get(which)

    # --- window and configuration ---

    def settings(self):
        cfg = config.load()
        auth = create_smartthings_auth()
        return {"ok": True, "data": {
            "lampIp": cfg.lamp_ip or "–",
            "lampVersion": cfg.lamp_version,
            "acId": cfg.ac_device_id or "–",
            "env": str(config.env_path()),
            "smartthings": {
                "kind": getattr(auth, "kind", None),
                "expiresAt": getattr(auth, "expires_at", None),  # OAuth only (epoch in seconds)
            },
        }}

    def replace_smartthings_token(self, token: str):
        """Plan B: paste a new personal access token (PAT). Validated with SmartThings before saving."""
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "Paste the token before saving."}
        cfg = config.load()
        client = SmartThingsClient(AuthPAT(token))
        try:
            if cfg.ac_device_id:
                client.device(cfg.ac_device_id)
            else:
                client.list_devices()
        except DeviceError as e:
            return {"ok": False, "error": f"Token not accepted: {e}"}
        finally:
            client.close()
        config.save_secret(config.SECRET_SMARTTHINGS_PAT, token)
        config.delete_secret_json(config.SECRET_SMARTTHINGS_OAUTH)  # switches to the PAT
        self._ac, self._ac_error = _create(create_ac)
        return self.settings()

    def minimize(self):
        """Goes to the tray: disappears from the screen and the taskbar."""
        if self._window:
            self._window.hide()

    def close(self):
        """× button: goes to the tray or quits, depending on the preference."""
        if config.read_preferences()["close_to_tray"]:
            self.minimize()
            return {"ok": True, "data": "tray"}
        self.quit()
        return {"ok": True, "data": "quit"}

    def hide_flyout(self):
        """The quick panel lost focus (or Esc)."""
        if self._flyout:
            self._flyout.hide()

    def open_full(self, tab: str | None = None):
        """Expand button / arrows of the quick panel: opens the full window, optionally on a tab."""
        self.hide_flyout()
        if self._open_full:
            self._open_full(tab)

    def quit(self):
        """Really quits (tray menu), ignoring the close-to-tray preference."""
        self._quitting = True
        if self._window:
            self._window.destroy()

    def preferences(self):
        prefs = config.read_preferences()
        return {"ok": True, "data": {
            "launchAtStartup": startup.enabled(),
            "launchSupported": startup.supported(),
            "closeToTray": bool(prefs["close_to_tray"]),
        }}

    def set_preference(self, name: str, value: bool):
        try:
            if name == "launchAtStartup":
                startup.set_enabled(bool(value))
            elif name == "closeToTray":
                config.save_preference("close_to_tray", bool(value))
            else:
                return {"ok": False, "error": f"Unknown preference: {name}"}
        except OSError as e:
            return {"ok": False, "error": f"Could not save the preference: {e}"}
        return self.preferences()

    # --- internals ---

    def _remember(self, which: str, on: bool) -> None:
        if self._on[which] != on:
            self._on[which] = on
            if self._on_change:
                self._on_change()

    @staticmethod
    def _toggle(read, power):
        current = read()
        if not current["ok"]:
            return current
        new = not current["data"]["on"]
        r = power(new)
        return {**r, "data": new} if r["ok"] else r

    def _use_ac(self, action: Callable[[AirConditioner], Any]):
        return self._run(self._ac, self._ac_error, action)

    def _use_light(self, action: Callable[[Lamp], Any]):
        return self._run(self._lamp, self._lamp_error, action)

    @staticmethod
    def _run(device, config_error, action):
        if device is None:
            return {"ok": False, "configured": False, "error": config_error}
        try:
            return {"ok": True, "data": action(device)}
        except DeviceError as e:
            return {"ok": False, "configured": True, "error": str(e)}
        except Exception as e:  # never leaves the interface without an answer
            log.exception("Unexpected error")
            return {"ok": False, "configured": True, "error": f"Unexpected error: {e}"}


def _round_corners(window) -> None:
    """Windows 11: rounded corners and a subtle border on the frameless window."""
    if sys.platform != "win32":
        return
    try:
        hwnd = window.native.Handle.ToInt32()
        for attribute, value in ((33, 2), (34, 0x00272422)):  # CORNER_PREFERENCE=ROUND, BORDER_COLOR (0x00BBGGRR)
            v = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:  # cosmetic: without it the window just has square corners
        log.debug("Could not round the corners", exc_info=True)


TITLE = "Mothlit"
_MUTEX = "Local\\Mothlit.SingleInstance"
_SHOW_EVENT = "Local\\Mothlit.Show"
_QUIT_EVENT = "Local\\Mothlit.Quit"  # the installer asks the app to quit before updating
_handles = []  # the mutex and events live as long as the process


def _kernel32():
    k = ctypes.windll.kernel32
    for function in (k.CreateMutexW, k.CreateEventW, k.OpenEventW):
        function.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def _already_running(bring_window: bool = True) -> bool:
    """Single instance. If Mothlit is already running, asks it to show up and returns True.

    The request goes through a named Windows event (not FindWindow), because the window of an
    instance that started hidden in the tray does not even exist for the system yet.
    """
    if sys.platform != "win32":
        return False
    k = _kernel32()
    _handles.append(k.CreateMutexW(None, False, _MUTEX))
    if k.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    if bring_window:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY: lets the other instance come to the front
        event = k.OpenEventW(0x0002, False, _SHOW_EVENT)  # EVENT_MODIFY_STATE
        if event:
            k.SetEvent(event)
            k.CloseHandle(event)
    return True


def _serve_event(name: str, action: Callable[[], None], description: str) -> None:
    """Thread that waits for a named Windows event (another instance, or the installer) and runs `action`."""
    if sys.platform != "win32":
        return
    k = _kernel32()
    event = k.CreateEventW(None, False, False, name)  # auto-reset
    _handles.append(event)

    def wait():
        while k.WaitForSingleObject(event, 0xFFFFFFFF) == 0:  # INFINITE / WAIT_OBJECT_0
            log.info("Request received: %s", description)
            try:
                action()
            except Exception:
                log.exception("Failed to handle the request: %s", description)

    threading.Thread(target=wait, name=f"event-{description}", daemon=True).start()

def run(in_tray: bool = False) -> None:
    """Opens the window. `in_tray`: starts hidden (used when launching at Windows startup)."""
    from ..tray import Tray
    from .flyout import QuickPanel

    if _already_running(bring_window=not in_tray):
        return
    debug = bool(os.environ.get("MOTHLIT_DEBUG"))
    import keyring

    from .. import __version__

    log.info("Mothlit %s starting (executable: %s, tray: %s, keyring: %s)", __version__,
             getattr(sys, "frozen", False), in_tray, type(keyring.get_keyring()).__name__)
    api = Api.from_config()
    log.info("Lamp: %s | AC: %s (%s)", "ok" if api._lamp else api._lamp_error,
             "ok" if api._ac else api._ac_error, getattr(create_smartthings_auth(), "kind", None))
    window = webview.create_window(
        TITLE, url=str(WEB / "index.html"), js_api=api, width=WIDTH, height=HEIGHT,
        resizable=False, frameless=True, easy_drag=False, background_color=BACKGROUND, hidden=in_tray,
    )
    api._window = window

    def show() -> None:
        window.show()
        window.restore()
        _round_corners(window)
        try:
            ctypes.windll.user32.SetForegroundWindow(window.native.Handle.ToInt32())
        except Exception:
            pass
        window.evaluate_js("window.onRestore && onRestore()")  # fade-in and fresh data

    def on_closing():
        # Alt+F4 also honors "minimize to tray on close"; "Quit" in the tray does not.
        if not api._quitting and config.read_preferences()["close_to_tray"]:
            window.hide()
            return False
        return True

    panel = QuickPanel(api, BACKGROUND)
    api._flyout = panel

    def open_full(tab: str | None = None) -> None:
        show()
        if tab in ("climate", "light"):
            window.evaluate_js(f"window.selectTab && selectTab({json.dumps(tab)})")

    api._open_full = open_full

    tray = Tray(
        api,
        on_open=show,
        on_click=panel.toggle,
        on_quit=api.quit,
        on_change=lambda: window.evaluate_js("window.refreshAll && refreshAll()"),
    )
    api._on_change = tray.refresh_menu

    window.events.closing += on_closing
    _serve_event(_SHOW_EVENT, show, "show the window")
    _serve_event(_QUIT_EVENT, api.quit, "quit to update")
    window.events.shown += lambda: _round_corners(window)
    window.events.loaded += lambda: log.info("Interface loaded")
    window.events.restored += lambda: window.evaluate_js("window.onRestore && onRestore()")
    window.events.closed += tray.stop
    window.events.closed += panel.destroy  # without this webview.start never returns
    tray.start()
    webview.start(debug=debug, icon=str(brand.ico_file()))
