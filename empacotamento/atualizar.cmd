@echo off
rem Atualiza o Mothlit instalado com o c?digo atual: gera o execut?vel e reinstala.
rem Se o Mothlit estiver aberto, ele ? fechado e reaberto na bandeja com a vers?o nova.
cd /d "%~dp0.."
echo Gerando o executavel...
uv run pyinstaller empacotamento/mothlit.spec --noconfirm --log-level WARN
if errorlevel 1 (
    echo.
    echo Falha ao gerar o executavel.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*