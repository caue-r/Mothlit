<#
.SYNOPSIS
    Installs Mothlit for the current user (no administrator).

.DESCRIPTION
    - Copies dist\Mothlit to %LOCALAPPDATA%\Programs\Mothlit (or -Destination)
    - Creates the "Mothlit" shortcut in the Start Menu (unless -NoShortcut)
    - If "Launch at Windows startup" is on, points the registry to the new Mothlit.exe
    Configuration and secrets (%APPDATA%\Mothlit and keyring) are not touched.

.EXAMPLE
    uv run pyinstaller packaging/mothlit.spec --noconfirm
    powershell -ExecutionPolicy Bypass -File packaging\install.ps1
#>
param(
    [string]$Destination = (Join-Path $env:LOCALAPPDATA "Programs\Mothlit"),
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"

# Opened with a double click (parent = Explorer or install.cmd), the window would close before you could read it.
function Wait-ForEnter {
    $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
    $name = (Get-Process -Id $parent -ErrorAction SilentlyContinue).ProcessName
    if ($name -in @("explorer", "cmd")) { Read-Host "`nPress Enter to close" | Out-Null }
}

trap {
    Write-Host "`nError: $($_.Exception.Message)" -ForegroundColor Red
    Wait-ForEnter
    exit 1
}

$source = Join-Path $PSScriptRoot "..\dist\Mothlit" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $source -or -not (Test-Path (Join-Path $source "Mothlit.exe"))) {
    throw "dist\Mothlit\Mothlit.exe not found. Run first: uv run pyinstaller packaging/mothlit.spec --noconfirm"
}

# A running Mothlit locks the files: close only the ones running from the destination.
$running = Get-Process -Name "Mothlit", "mothlit-cli" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Destination, [StringComparison]::OrdinalIgnoreCase) }
$reopen = [bool]($running | Where-Object { $_.ProcessName -eq "Mothlit" })
if ($running) {
    Write-Host "Closing the running Mothlit..."
    # Ask it to quit cleanly (the tray icon goes away); only force it if it does not close in time.
    # "Mothlit.Sair" is the event name used by versions before the English rename.
    foreach ($eventName in @("Local\Mothlit.Quit", "Local\Mothlit.Sair")) {
        try {
            $quit = [System.Threading.EventWaitHandle]::OpenExisting($eventName)
            [void]$quit.Set()
            $quit.Dispose()
        } catch { }
    }
    $running | Wait-Process -Timeout 8 -ErrorAction SilentlyContinue
    $running | Where-Object { -not $_.HasExited } | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

Write-Host "Copying to $Destination ..."
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
# /MIR makes the destination identical to the build (removes files from old versions)
robocopy $source $Destination /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Copy failed (robocopy $LASTEXITCODE)." }
$exe = Join-Path $Destination "Mothlit.exe"

if (-not $NoShortcut) {
    $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "Mothlit.lnk"
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($menu)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $Destination
    $shortcut.IconLocation = "$exe,0"
    $shortcut.Description = "Control the lamp and the air conditioner"
    $shortcut.Save()
    Write-Host "Start Menu shortcut created."
}

$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $run -Name "Mothlit" -ErrorAction SilentlyContinue) {
    Set-ItemProperty -Path $run -Name "Mothlit" -Value "`"$exe`" --tray"
    Write-Host "Launch at Windows startup: updated to the installed executable."
}

Write-Host "`nDone! Mothlit installed at $exe" -ForegroundColor Green
if ($reopen) {
    Start-Process -FilePath $exe -ArgumentList "--tray" -WorkingDirectory $Destination
    Write-Host "Mothlit was open: reopened it in the tray with the new version."
}
if (-not $NoShortcut) { Write-Host "Open it from the Start Menu: Mothlit" }
Wait-ForEnter
