"""Executable entry point (PyInstaller needs a script, not `python -m`)."""

import sys

from mothlit.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
