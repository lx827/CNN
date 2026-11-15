@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Missing uv. Install: https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
rem Use the explicitly installed driver group; never auto-sync another driver.
set "PYTHONUTF8=1"
uv run --no-sync python scripts\dc24_start.py %*
if errorlevel 1 pause
