"""Tray quick panel: a small frameless window that opens right next to the tray.

It opens with a click on the tray icon and disappears when it loses focus (clicking outside),
like Windows' own quick panels. For the full app there is the expand button.
"""

import ctypes
import logging
import sys
import time
from ctypes import wintypes
from pathlib import Path

import webview

log = logging.getLogger(__name__)

WEB = Path(__file__).resolve().parent / "web"
WIDTH, HEIGHT = 340, 264
MARGIN = 12  # distance from the taskbar and the screen edge
# Clicking the tray icon with the panel open: the panel loses focus (and hides) an instant
# before the click arrives. Without this time window, it would reopen right away.
IGNORE_CLICK_AFTER_HIDE_S = 0.5


def position(width: int, height: int) -> tuple[int, int]:
    """Corner of the work area next to the taskbar, in logical pixels (pywebview's)."""
    if sys.platform != "win32":
        return 100, 100
    u = ctypes.windll.user32
    area = wintypes.RECT()
    u.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)  # SPI_GETWORKAREA (physical pixels)
    scale = u.GetDpiForSystem() / 96
    screen_width = u.GetSystemMetrics(0)
    x = area.right / scale - width - MARGIN
    y = area.bottom / scale - height - MARGIN
    if area.top > 0:  # taskbar at the top
        y = area.top / scale + MARGIN
    if area.left > 0 and area.right >= screen_width:  # taskbar on the left
        x = area.left / scale + MARGIN
    return int(x), int(y)


def _frame() -> tuple[int, int]:
    """How much the frameless window "loses" from the size asked of pywebview (logical pixels).

    pywebview sizes it as if the standard Windows frame were there (borders + title bar) and then
    hides it; what remains visible is smaller. We add that back.
    """
    if sys.platform != "win32":
        return 0, 0
    u = ctypes.windll.user32
    scale = u.GetDpiForSystem() / 96
    border_x = u.GetSystemMetrics(32) + u.GetSystemMetrics(92)  # SM_CXSIZEFRAME + SM_CXPADDEDBORDER
    border_y = u.GetSystemMetrics(33) + u.GetSystemMetrics(92)  # SM_CYSIZEFRAME + SM_CXPADDEDBORDER
    caption = u.GetSystemMetrics(4)  # SM_CYCAPTION
    return round(2 * border_x / scale), round((2 * border_y + caption) / scale)


class QuickPanel:
    def __init__(self, api, background: str):
        x, y = position(WIDTH, HEIGHT)
        extra_w, extra_h = _frame()
        # Created already in the right place: in pywebview, move() only works after the window was shown.
        self.window = webview.create_window(
            "Mothlit · quick controls", url=str(WEB / "flyout.html"), js_api=api,
            width=WIDTH + extra_w, height=HEIGHT + extra_h, x=x, y=y, resizable=False, frameless=True,
            easy_drag=False, background_color=background, hidden=True, on_top=True,
        )
        self.visible = False
        self._hidden_at = 0.0
        self._native_ready = False

    # --- open / close ---

    def toggle(self) -> None:
        """Click on the tray icon."""
        if self.visible:
            self.hide()
        elif time.monotonic() - self._hidden_at >= IGNORE_CLICK_AFTER_HIDE_S:
            self.show()

    def show(self) -> None:
        self._hide_from_taskbar()
        self.window.show()
        self.visible = True
        self.window.move(*position(WIDTH, HEIGHT))  # in case the screen/taskbar changed since creation
        self._setup_native()
        try:
            ctypes.windll.user32.SetForegroundWindow(self.window.native.Handle.ToInt32())
        except Exception:
            pass
        self.window.evaluate_js("window.onShow && onShow()")

    def hide(self) -> None:
        if not self.visible:
            return
        self.visible = False
        self._hidden_at = time.monotonic()
        self.window.hide()

    def destroy(self) -> None:
        """Closes the panel together with the app (otherwise webview.start never returns).

        Does not use window.destroy(): in pywebview it waits for the window to have been shown, and
        the panel may never have been opened. It closes the native form, asynchronously.
        """
        try:
            from System import Action

            native = self.window.native
            native.BeginInvoke(Action(native.Close))
        except Exception:
            log.debug("Panel already closed", exc_info=True)

    # --- native window (WinForms) ---

    def _hide_from_taskbar(self) -> None:
        """WS_EX_TOOLWINDOW: no taskbar button and out of Alt+Tab, like the Windows panels.

        (Do not use WinForms' ShowInTaskbar: it recreates the window and takes down the WebView2 inside it.)
        """
        if sys.platform != "win32":
            return
        try:
            native = self.window.native
            if not native.IsHandleCreated:
                return
            u = ctypes.windll.user32
            u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            hwnd = native.Handle.ToInt32()
            style = u.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            u.SetWindowLongW(hwnd, -20, (style | 0x80) & ~0x40000)  # +TOOLWINDOW, -APPWINDOW
        except Exception:
            log.debug("Could not remove the panel from the taskbar", exc_info=True)

    def _setup_native(self) -> None:
        """Once: rounded corners and hide on focus loss (the form's Deactivate)."""
        if self._native_ready:
            return
        try:
            from .app import _round_corners

            _round_corners(self.window)
            self.window.native.Deactivate += lambda *_: self.hide()
            self._native_ready = True
        except Exception:
            log.debug("Native panel setup unavailable", exc_info=True)
