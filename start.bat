@echo off
setlocal
rem Use this file's directory so it works when launched by double-click.
cd /d "%~dp0"
if not exist "edge\venv\Scripts\activate.bat" (
    echo Missing edge virtual environment: edge\venv
    pause
    exit /b 1
)
call "edge\venv\Scripts\activate.bat"
set "PYTHONUTF8=1"
python "edge\replay.py" %*
set "REPLAY_EXIT=%ERRORLEVEL%"
if not "%REPLAY_EXIT%"=="0" pause
exit /b %REPLAY_EXIT%
