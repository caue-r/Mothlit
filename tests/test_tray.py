from unittest.mock import MagicMock

from mothlit.tray import Tray


def tray(api):
    t = Tray(api, on_open=MagicMock(), on_quit=MagicMock(), on_change=MagicMock())
    t._icon = MagicMock(HAS_NOTIFICATION=True)  # does not create the real icon
    return t


def test_labels_follow_the_last_state():
    api = MagicMock()
    api.last_on.side_effect = {"light": True, "ac": None}.get
    t = tray(api)
    assert t._label("light") == "Turn light off"
    assert t._label("ac") == "Turn AC on/off"


def test_toggle_notifies_and_asks_for_reread():
    api = MagicMock()
    api.toggle_ac.return_value = {"ok": True, "data": True}
    t = tray(api)
    t._toggle("ac")
    t._icon.notify.assert_called_with("Air conditioner turned on.", "Mothlit")
    t._icon.update_menu.assert_called_once()
    t._on_change.assert_called_once()


def test_error_becomes_notification():
    api = MagicMock()
    api.toggle_light.return_value = {"ok": False, "error": "Lamp unreachable."}
    t = tray(api)
    t._toggle("light")
    t._icon.notify.assert_called_with("Lamp unreachable.", "Mothlit")


def test_left_click_opens_the_quick_panel():
    open_, click = MagicMock(), MagicMock()
    t = Tray(MagicMock(), on_open=open_, on_quit=MagicMock(), on_click=click)
    t._click()
    click.assert_called_once()
    open_.assert_not_called()
    t._open()  # "Open Mothlit" in the right-click menu still opens the full app
    open_.assert_called_once()


def test_without_quick_panel_the_click_opens_the_app():
    open_ = MagicMock()
    t = Tray(MagicMock(), on_open=open_, on_quit=MagicMock())
    t._click()
    open_.assert_called_once()


def test_quit_stops_icon_and_closes_window():
    t = tray(MagicMock())
    t._quit()
    t._icon.stop.assert_called_once()
    t._on_quit.assert_called_once()
