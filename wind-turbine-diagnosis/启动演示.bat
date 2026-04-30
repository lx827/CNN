@echo off
title Wind Turbine Diagnosis System
echo ============================================
echo   Wind Turbine Gearbox Diagnosis System
echo ============================================
echo.

where node >nul 2>nul
if %errorlevel%==0 (
    echo Starting local server...
    echo.
    cd /d "%~dp0"
    node server.cjs
    echo.
    echo Server stopped.
    pause
    goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
    echo Starting local server with Python...
    echo.
    cd /d "%~dp0"
    start http://localhost:8080
    python -m http.server 8080 --directory dist
    echo.
    echo Server stopped.
    pause
    goto :end
)

echo ERROR: Python or Node.js not found.
echo.
echo Please install one of these and try again.
echo.
pause
goto :eof

:end
