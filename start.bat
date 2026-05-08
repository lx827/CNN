@echo off
chcp 65001 >nul
title 风机故障诊断系统 — 一键启动

echo ==========================================
echo  风机齿轮箱智能故障诊断系统 — 一键启动
echo ==========================================
echo.
echo 本脚本将依次启动：后端服务、边端采集、前端界面
echo 每个服务会单独打开一个窗口
echo.
pause

:: 获取当前目录
set "ROOT=%~dp0"

:: 启动后端
echo [1/3] 启动云端后端...
start "云端后端 (Cloud API)" cmd /k "cd /d "%ROOT%cloud" && venv\Scripts\activate && python -m app.main"

:: 等待后端初始化
timeout /t 3 /nobreak >nul

:: 启动边端
echo [2/3] 启动边端采集...
start "边端采集 (Edge Client)" cmd /k "cd /d "%ROOT%edge" && venv\Scripts\activate && python edge_client.py"

:: 等待边端初始化
timeout /t 2 /nobreak >nul

:: 启动前端
echo [3/3] 启动前端界面...
start "前端界面 (Vue DevServer)" cmd /k "cd /d "%ROOT%wind-turbine-diagnosis" && npm run dev"

echo.
echo ==========================================
echo  三个窗口已启动，请稍等片刻
echo  前端将自动打开浏览器访问 http://localhost:3000
echo  API 文档地址: http://localhost:8000/docs
echo ==========================================
pause
