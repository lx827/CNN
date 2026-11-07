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
if not exist ".venv\Scripts\python.exe" (
  echo First run: creating workspace environment with uv sync...
  uv sync
  if errorlevel 1 (
    echo uv sync failed.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
set "PYTHONUTF8=1"
python scripts\dc24_start.py %*
if errorlevel 1 pause
