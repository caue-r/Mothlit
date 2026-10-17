# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: gera dist/Mothlit/ com dois executáveis que compartilham as dependências.

- Mothlit.exe      sem console: interface + bandeja (é o que inicia com o Windows)
- mothlit-cli.exe  com console: setup, test-lampada, test-ar

Uso:  uv run pyinstaller empacotamento/mothlit.spec --noconfirm
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

RAIZ = Path(SPECPATH).parent
sys.path.insert(0, str(RAIZ))
from mothlit import __version__  # noqa: E402
from mothlit.ui.marca import gerar_ico  # noqa: E402

ICONE = str(gerar_ico(RAIZ / "build" / "mothlit.ico"))
numeros = tuple(int(n) for n in __version__.split(".")) + (0,) * (4 - len(__version__.split(".")))


def versao(nome_interno: str, descricao: str) -> VSVersionInfo:
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numeros, prodvers=numeros),
        kids=[
            StringFileInfo([StringTable("041604B0", [  # pt-BR, Unicode
                StringStruct("ProductName", "Mothlit"),
                StringStruct("FileDescription", descricao),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductVersion", __version__),
                StringStruct("InternalName", nome_interno),
                StringStruct("OriginalFilename", f"{nome_interno}.exe"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0416, 1200])]),
        ],
    )


a = Analysis(
    [str(RAIZ / "empacotamento" / "mothlit_app.py")],
    pathex=[str(RAIZ)],
    datas=[(str(RAIZ / "mothlit" / "ui" / "web"), "mothlit/ui/web")]
    # o keyring descobre o backend do Windows pelos metadados do pacote
    + copy_metadata("keyring"),
    hiddenimports=[
        "pystray._win32",  # o pystray escolhe o backend em tempo de execução
        "keyring.backends.Windows",
    ],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

app = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Mothlit", console=False, icon=ICONE,
    version=versao("Mothlit", "Mothlit"), upx=False,
)
cli = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="mothlit-cli", console=True, icon=ICONE,
    version=versao("mothlit-cli", "Mothlit (linha de comando)"), upx=False,
)
COLLECT(app, cli, a.binaries, a.datas, name="Mothlit", upx=False)
