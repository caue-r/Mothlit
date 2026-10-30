@echo off
rem Updates the installed Mothlit with the current code: builds the executable and reinstalls.
rem If Mothlit is open, it is closed and reopened in the tray with the new version.
cd /d "%~dp0.."
echo Building the executable...
uv run pyinstaller packaging/mothlit.spec --noconfirm --log-level WARN
if errorlevel 1 (
    echo.
    echo Failed to build the executable.
    pause
    exit /b 1
)
echo Checking the built executable...
"dist\Mothlit\mothlit-cli.exe" verify
if errorlevel 1 (
    echo.
    echo The new executable failed the check. The installed version was NOT changed.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
