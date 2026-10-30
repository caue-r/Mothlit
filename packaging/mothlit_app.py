"""Ponto de entrada do executável (o PyInstaller precisa de um script, não de `python -m`)."""

import sys

from mothlit.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
