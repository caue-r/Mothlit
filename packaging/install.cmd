@echo off
rem Instala o Mothlit com dois cliques (sem precisar mexer na pol?tica de execu??o do PowerShell).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
