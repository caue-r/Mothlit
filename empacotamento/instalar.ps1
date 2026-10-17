<#
.SYNOPSIS
    Instala o Mothlit para o usuário atual (sem administrador).

.DESCRIPTION
    - Copia dist\Mothlit para %LOCALAPPDATA%\Programs\Mothlit (ou -Destino)
    - Cria o atalho "Mothlit" no Menu Iniciar (a menos que -SemAtalho)
    - Se "Iniciar com o Windows" estiver ligado, aponta o registro para o novo Mothlit.exe
    Configuração e segredos (%APPDATA%\Mothlit e keyring) não são tocados.

.EXAMPLE
    uv run pyinstaller empacotamento/mothlit.spec --noconfirm
    powershell -ExecutionPolicy Bypass -File empacotamento\instalar.ps1
#>
param(
    [string]$Destino = (Join-Path $env:LOCALAPPDATA "Programs\Mothlit"),
    [switch]$SemAtalho
)

$ErrorActionPreference = "Stop"
$origem = Join-Path $PSScriptRoot "..\dist\Mothlit" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $origem -or -not (Test-Path (Join-Path $origem "Mothlit.exe"))) {
    throw "Não achei dist\Mothlit\Mothlit.exe. Rode antes: uv run pyinstaller empacotamento/mothlit.spec --noconfirm"
}

# O Mothlit aberto trava os arquivos: fecha só os que estão rodando a partir do destino.
$abertos = Get-Process -Name "Mothlit", "mothlit-cli" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Destino, [StringComparison]::OrdinalIgnoreCase) }
if ($abertos) {
    Write-Host "Fechando o Mothlit em execução..."
    $abertos | Stop-Process -Force
    Start-Sleep -Seconds 1
}

Write-Host "Copiando para $Destino ..."
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
# /MIR deixa o destino idêntico ao build (remove arquivos de versões antigas)
robocopy $origem $Destino /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar (robocopy $LASTEXITCODE)." }
$exe = Join-Path $Destino "Mothlit.exe"

if (-not $SemAtalho) {
    $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "Mothlit.lnk"
    $atalho = (New-Object -ComObject WScript.Shell).CreateShortcut($menu)
    $atalho.TargetPath = $exe
    $atalho.WorkingDirectory = $Destino
    $atalho.IconLocation = "$exe,0"
    $atalho.Description = "Controle da lâmpada e do ar-condicionado"
    $atalho.Save()
    Write-Host "Atalho criado no Menu Iniciar."
}

$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $run -Name "Mothlit" -ErrorAction SilentlyContinue) {
    Set-ItemProperty -Path $run -Name "Mothlit" -Value "`"$exe`" --bandeja"
    Write-Host "Iniciar com o Windows: atualizado para o executável instalado."
}

Write-Host "Pronto: $exe"
