"""Launch at Windows startup, using a fake winreg (does not touch the real registry)."""

import sys

import pytest

from mothlit import startup


class FakeKey:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, root, path):
        return FakeKey(self.values)

    CreateKey = OpenKey

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], self.REG_SZ

    def SetValueEx(self, key, name, _reserved, _type, value):
        key.values[name] = value

    def DeleteValue(self, key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]


@pytest.fixture
def registry(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(startup, "winreg", fake)
    return fake


def test_turns_on_and_off(registry):
    assert startup.enabled() is False
    startup.set_enabled(True)
    assert startup.enabled() is True
    assert registry.values["Mothlit"].endswith("-m mothlit --tray")
    startup.set_enabled(False)
    assert startup.enabled() is False
    startup.set_enabled(False)  # turning off again does not break


def test_command_uses_pythonw_without_console():
    assert "pythonw.exe" in startup.command().lower()


def test_executable_command(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\Mothlit\Mothlit.exe")
    assert startup.command() == r'"C:\Apps\Mothlit\Mothlit.exe" --tray'


def test_outside_windows(monkeypatch):
    monkeypatch.setattr(startup, "winreg", None)
    assert startup.supported() is False
    assert startup.enabled() is False
    with pytest.raises(OSError):
        startup.set_enabled(True)
