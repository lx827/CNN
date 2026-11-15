@echo off
rem 本地工作站一键入口:启动本机分析后端 + 前端 + DC24 采集进程。
rem 云端部署用 deploy.sh;树莓派边端见 deploy/edge/ 与 edge/acquire/deploy/pi/。
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
