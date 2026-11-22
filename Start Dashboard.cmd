@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run scripts\setup.ps1 first. See README.md.
  pause
  exit /b 1
)
echo Cypress Forge - http://127.0.0.1:8765
echo Keep this window open. Press Ctrl+C to stop.
echo.
powershell.exe -NoProfile -File "%~dp0scripts\start.ps1"
if errorlevel 1 pause
