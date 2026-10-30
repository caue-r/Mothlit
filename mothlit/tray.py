"""System tray icon with quick actions (pystray).

pystray runs in its own thread (safe on Windows). Actions that use the network
run in yet another thread, so the tray menu never freezes.
"""

import ctypes
import logging
import sys
import threading
from typing import Callable

import pystray

from .ui import brand

log = logging.getLogger(__name__)


class _SharpIcon(pystray.Icon):
    """pystray.Icon that hands Windows the icon at the exact tray size.

    pystray loads the icon at the default size (32 px) and Windows scales it down for the tray
    (16 px at 100%), which makes the moth smaller and blurry. Here we load, from our multi-size
    .ico, the frame of the right size (SM_CXSMICON, which already accounts for display scaling).
    If anything fails, it falls back to pystray's normal behavior.
    """

    def __init__(self, *args, ico=None, **kwargs):
        self._ico = ico
        super().__init__(*args, **kwargs)

    def _assert_icon_handle(self):
        if self._icon_handle:
            return
        if self._ico and sys.platform == "win32":
            try:
                from pystray._util import win32

                side = ctypes.windll.user32.GetSystemMetrics(49)  # SM_CXSMICON
                handle = win32.LoadImage(None, str(self._ico), win32.IMAGE_ICON, side, side, win32.LR_LOADFROMFILE)
                if handle:
                    self._icon_handle = handle
                    return
            except Exception:
                log.debug("Sharp icon unavailable; using the pystray default", exc_info=True)
        super()._assert_icon_handle()


class Tray:
    def __init__(self, api, on_open: Callable[[], None], on_quit: Callable[[], None],
                 on_change: Callable[[], None] | None = None, on_click: Callable[[], None] | None = None):
        """`api` is the same `ui.app.Api` used by the window; `on_change` tells the window to reread the state.

        `on_click`: left click on the icon (the quick panel). Without it, the click opens the full app.
        """
        self._api = api
        self._on_open = on_open
        self._on_click = on_click or on_open
        self._on_quit = on_quit
        self._on_change = on_change
        try:
            ico = brand.tray_ico()
        except Exception:  # the sharp icon is cosmetic: it must never stop the app from opening
            log.exception("Could not build the tray icon; using the default")
            ico = None
        self._icon = _SharpIcon(
            "mothlit",
            brand.tray_image(64),
            "Mothlit",
            ico=ico,
            menu=pystray.Menu(
                # default item = left click; hidden in the right-click menu
                pystray.MenuItem("Quick controls", self._click, default=True, visible=False),
                pystray.MenuItem("Open Mothlit", self._open),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda _: self._label("light"), lambda: self._action("light")),
                pystray.MenuItem(lambda _: self._label("ac"), lambda: self._action("ac")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def start(self) -> None:
        threading.Thread(target=self._icon.run, name="tray", daemon=True).start()

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            log.debug("Tray already stopped", exc_info=True)

    def refresh_menu(self) -> None:
        """Recomputes the dynamic labels (call it when the device state changes)."""
        try:
            self._icon.update_menu()
        except Exception:
            log.debug("Could not refresh the tray menu", exc_info=True)

    # --- menu ---

    def _label(self, which: str) -> str:
        name = "light" if which == "light" else "AC"
        on = self._api.last_on(which)
        if on is None:
            return f"Turn {name} on/off"
        return f"Turn {name} off" if on else f"Turn {name} on"

    def _open(self) -> None:
        self._on_open()

    def _click(self) -> None:
        self._on_click()

    def _quit(self) -> None:
        self.stop()
        self._on_quit()

    def _action(self, which: str) -> None:
        threading.Thread(target=self._toggle, args=(which,), name=f"tray-{which}", daemon=True).start()

    def _toggle(self, which: str) -> None:
        r = self._api.toggle_light() if which == "light" else self._api.toggle_ac()
        if r["ok"]:
            name = "Lamp" if which == "light" else "Air conditioner"
            self._notify(f"{name} turned {'on' if r['data'] else 'off'}.")
        else:
            self._notify(r.get("error") or "Failed to talk to the device.")
        self.refresh_menu()
        if self._on_change:
            self._on_change()

    def _notify(self, message: str) -> None:
        if self._icon.HAS_NOTIFICATION:
            try:
                self._icon.notify(message, "Mothlit")
            except Exception:
                log.debug("Notification failed", exc_info=True)
