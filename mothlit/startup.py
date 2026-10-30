"""Launch at Windows startup: entry in HKCU\\...\\CurrentVersion\\Run (current user only, no admin).

The app opens hidden in the tray (`--tray`) and without a console (pythonw / windowed .exe).
The state comes from the registry itself, so the UI always shows the truth.
"""

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # outside Windows
    winreg = None

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Mothlit"


def command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller executable
        return f'"{sys.executable}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" -m mothlit --tray'


def supported() -> bool:
    return winreg is not None


def enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            winreg.QueryValueEx(key, NAME)
        return True
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    if winreg is None:
        raise OSError("Launching at startup is only supported on Windows.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        if on:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
