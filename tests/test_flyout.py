"""Tray quick panel: open/close, without opening real windows."""

from unittest.mock import MagicMock

from mothlit.ui import flyout
from mothlit.ui.flyout import QuickPanel


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def panel(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(flyout.time, "monotonic", clock)
    monkeypatch.setattr(flyout, "position", lambda w, h: (10, 20))
    p = QuickPanel.__new__(QuickPanel)  # without creating the pywebview window
    p.window = MagicMock()
    p.window.native = None  # no native form: the real Windows calls are skipped
    p.visible = False
    p._hidden_at = 0.0
    p._native_ready = True
    return p, clock


def test_click_opens_and_clicking_again_closes(monkeypatch):
    p, _ = panel(monkeypatch)
    p.toggle()
    assert p.visible
    p.window.show.assert_called_once()
    p.window.move.assert_called_with(10, 20)
    p.window.evaluate_js.assert_called_with("window.onShow && onShow()")
    p.toggle()
    assert not p.visible
    p.window.hide.assert_called_once()


def test_click_on_the_icon_that_closed_the_panel_does_not_reopen(monkeypatch):
    p, clock = panel(monkeypatch)
    p.toggle()
    p.hide()  # lost focus because the user clicked the tray icon...
    clock.now += 0.05
    p.toggle()  # ...and the click arrives right after: it must stay closed
    assert not p.visible
    clock.now += 1
    p.toggle()  # a real click, later, opens it
    assert p.visible


def test_hiding_twice_does_not_duplicate(monkeypatch):
    p, _ = panel(monkeypatch)
    p.toggle()
    p.hide()
    p.hide()  # JS blur + Windows Deactivate arrive together
    p.window.hide.assert_called_once()


def test_frame_and_position_are_integers():
    width, height = flyout._frame()
    x, y = flyout.position(flyout.WIDTH, flyout.HEIGHT)
    assert all(isinstance(v, int) for v in (width, height, x, y))
    assert width >= 0 and height >= 0
