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
rem uv run auto-syncs the workspace env (equiv. uv sync) before launching
set "PYTHONUTF8=1"
uv run python scripts\dc24_start.py %*
if errorlevel 1 pause
