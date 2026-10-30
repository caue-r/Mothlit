"""Iniciar com o Windows: entrada em HKCU\\...\\CurrentVersion\\Run (só o usuário atual, sem admin).

O app abre escondido na bandeja (`--bandeja`) e sem console (pythonw / .exe janela).
O estado vem do próprio registro, então a interface sempre mostra a verdade.
"""

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # fora do Windows
    winreg = None

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "Mothlit"


def comando() -> str:
    if getattr(sys, "frozen", False):  # executável do PyInstaller
        return f'"{sys.executable}" --bandeja'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpretador = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpretador}" -m mothlit --bandeja'


def suportado() -> bool:
    return winreg is not None


def ativo() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE) as chave:
            winreg.QueryValueEx(chave, NOME)
        return True
    except OSError:
        return False


def definir(ligado: bool) -> None:
    if winreg is None:
        raise OSError("Iniciar com o sistema só é suportado no Windows.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CHAVE) as chave:
        if ligado:
            winreg.SetValueEx(chave, NOME, 0, winreg.REG_SZ, comando())
        else:
            try:
                winreg.DeleteValue(chave, NOME)
            except FileNotFoundError:
                pass
