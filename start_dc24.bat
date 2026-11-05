@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "edge\venv\Scripts\python.exe" (
  echo 未找到 edge 虚拟环境，请先按 docs\DC24_ACQUISITION.md 配置。
  pause
  exit /b 1
)
echo DC24 实时采集边端：保持此窗口运行，在 CNN 的“真实采集”页面设置任务。
echo 请先让原厂程序脱机，释放 TCP 6800；此启动器不启动旧数据集回放。
echo 不带参数时读取边端现有云端地址；可用 start_dc24.bat http://127.0.0.1:8000 指定本机后端。
call "edge\venv\Scripts\activate.bat"
if "%~1"=="" (
  python edge\dc24_agent.py
) else (
  python edge\dc24_agent.py --cloud "%~1"
)
pause
