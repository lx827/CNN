@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "cloud\venv\Scripts\python.exe" (
  echo Missing cloud virtual environment. See docs\DC24_ACQUISITION.md.
  pause
  exit /b 1
)
call "cloud\venv\Scripts\activate.bat"
set "PYTHONUTF8=1"
python scripts\dc24_start.py %*
if errorlevel 1 pause
