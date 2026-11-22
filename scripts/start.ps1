param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.venv\Scripts\python.exe')) { throw 'Run scripts\setup.ps1 first.' }
if (!(Test-Path 'frontend\dist\index.html')) { throw 'Frontend missing. Run scripts\setup.ps1 first.' }
& .\.venv\Scripts\python.exe -m backend.launcher
$launcherResult = $LASTEXITCODE
if ($launcherResult -eq 10) {
    if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8765/' }
    exit 0
}
if ($launcherResult -ne 0) { exit $launcherResult }
Write-Host 'Cypress Forge: http://127.0.0.1:8765   (Ctrl+C to stop)'
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --no-proxy-headers
exit $LASTEXITCODE
