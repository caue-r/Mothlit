@echo off
rem Installs Mothlit with a double click (no need to change the PowerShell execution policy).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
