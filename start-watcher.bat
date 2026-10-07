@echo off
chcp 936 >nul
title QQ 志愿活动监测 - 请勿关闭本窗口
cd /d "%~dp0"
set PY=C:\Users\wxzhe\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe

echo ================================================================
echo   QQ 志愿活动秒级提醒系统
echo   本窗口必须保持开启，关掉窗口 = 停止监听
echo   最小化即可，不要点 X
echo ================================================================
echo.

if not exist "%PY%" (
  echo [错误] 找不到 Python: %PY%
  echo 请把本文件里的 PY= 改成你机器上的 python.exe 路径
  pause
  exit /b 1
)

:loop
echo [%date% %time%] 启动监听服务...
"%PY%" -u "%~dp0app\main.py"
echo.
echo [%date% %time%] 监听服务已退出（代码 %errorlevel%），5 秒后自动重启...
timeout /t 5 /nobreak >nul
goto loop
