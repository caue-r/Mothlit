# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: builds dist/Mothlit/ with two executables that share the dependencies.

- Mothlit.exe      no console: interface + tray (this is what launches at Windows startup)
- mothlit-cli.exe  with console: setup, test-lamp, test-ac

Usage:  uv run pyinstaller packaging/mothlit.spec --noconfirm
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

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from mothlit import __version__  # noqa: E402
from mothlit.ui.brand import make_ico  # noqa: E402

ICON = str(make_ico(ROOT / "build" / "mothlit.ico"))
numbers = tuple(int(n) for n in __version__.split(".")) + (0,) * (4 - len(__version__.split(".")))


def version_info(internal_name: str, description: str) -> VSVersionInfo:
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("040904B0", [  # en-US, Unicode
                StringStruct("ProductName", "Mothlit"),
                StringStruct("FileDescription", description),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductVersion", __version__),
                StringStruct("InternalName", internal_name),
                StringStruct("OriginalFilename", f"{internal_name}.exe"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )


a = Analysis(
    [str(ROOT / "packaging" / "mothlit_app.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "mothlit" / "ui" / "web"), "mothlit/ui/web")]
    # keyring discovers the Windows backend through the package metadata
    + copy_metadata("keyring"),
    hiddenimports=[
        "pystray._win32",  # pystray picks its backend at runtime
        "keyring.backends.Windows",
    ],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

app = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Mothlit", console=False, icon=ICON,
    version=version_info("Mothlit", "Mothlit"), upx=False,
)
cli = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="mothlit-cli", console=True, icon=ICON,
    version=version_info("mothlit-cli", "Mothlit (command line)"), upx=False,
)
COLLECT(app, cli, a.binaries, a.datas, name="Mothlit", upx=False)
