@echo off
chcp 936 >nul
title QQ志愿活动监测 - 开机启动
cd /d "%~dp0"

set "PY=C:\Users\wxzhe\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

echo ================================================================
echo   QQ 志愿活动监测  开机启动
echo ================================================================
echo.

if not exist "%PY%" (
  echo [错误] 找不到 Python: %PY%
  pause
  exit /b 1
)

echo [1/3] 启动监听服务（后台静默）...
start "QQ监听服务" /min "%PY%" -u "%~dp0app\main.py"
timeout /t 3 /nobreak >nul

echo [2/3] 启动看门狗（后台静默）...
start "QQ看门狗" /min "%PY%" -u "%~dp0tools\watchdog.py" --interval 120 --quiet
timeout /t 2 /nobreak >nul

echo [3/3] 启动 QQ + NapCat（需要提权）...
echo.
echo   ------------------------------------------------
echo    接下来会弹一个 UAC 询问框，请点「是」
echo    这是 NapCat 注入 QQ 所必需的，无法省略
echo   ------------------------------------------------
echo.
timeout /t 3 /nobreak >nul

REM 用 PowerShell 的 RunAs 提权，直接运行 NapCat 启动批处理。
REM 这条路径是实际验证过能成功的：
REM   - VBS 的 WScript.Shell 没有 ShellExecute（只有 Run，且 Run 不接受 verb），
REM     所以 VBS 自己无法提权，只能靠批处理二次自提权，多闪一次窗口且不可靠。
REM   - 这里直接用 Start-Process -Verb RunAs，一步到位。
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0启动NapCat-管理员.bat' -Verb RunAs"

echo.
echo 已启动。本窗口 15 秒后自动关闭。
timeout /t 15 /nobreak >nul