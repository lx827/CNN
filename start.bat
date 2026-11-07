@echo off
setlocal
rem 旧数据集回放链(edge_client/replay.py)已随重构 #46 退役;一键入口统一为 DC24 实机链路。
call "%~dp0start_dc24.bat" %*
exit /b %ERRORLEVEL%
