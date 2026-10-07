@echo off
chcp 936 >nul
title 开机自动启动 - QQ志愿活动监测
cd /d "%~dp0"

echo ================================================================
echo   设置开机自动启动
echo ----------------------------------------------------------------
echo   做法：在「启动」文件夹里放一个入口，开机登录后自动运行。
echo
echo   【重要】为什么还需要你点一下：
echo     NapCat 要往 QQ 进程里注入代码，这需要管理员权限。
echo     你的账户不在管理员组，所以每次开机 Windows 会弹一次
echo     UAC 询问框，你点「是」即可。这一下无法省掉。
echo
echo   不需要你操作的部分（监听服务+看门狗）会自动静默启动。
echo ================================================================
echo.
echo 按任意键开始安装，Ctrl+C 取消...
pause >nul

set "VBS=%TEMP%\mk_startup_lnk.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%~dp0开机启动.bat"

if not exist "%TARGET%" (
  echo [错误] 找不到 %TARGET%
  pause
  exit /b 1
)
if not exist "%STARTUP%" (
  echo [错误] 找不到启动文件夹: %STARTUP%
  pause
  exit /b 1
)

> "%VBS%" echo Set oWS = WScript.CreateObject("WScript.Shell")
>> "%VBS%" echo sLinkFile = "%STARTUP%\QQ志愿活动监测.lnk"
>> "%VBS%" echo Set oLink = oWS.CreateShortcut(sLinkFile)
>> "%VBS%" echo oLink.TargetPath = "%TARGET%"
>> "%VBS%" echo oLink.WorkingDirectory = "%~dp0"
>> "%VBS%" echo oLink.WindowStyle = 7
>> "%VBS%" echo oLink.Description = "QQ 志愿活动秒级提醒"
>> "%VBS%" echo oLink.Save

cscript //nologo "%VBS%"
del "%VBS%" 2>nul
set "VBS="

echo.
if exist "%STARTUP%\QQ志愿活动监测.lnk" (
  echo [成功] 已写入启动项：
  echo   %STARTUP%\QQ志愿活动监测.lnk
) else (
  echo [失败] 启动项没有写入成功，请把上面的报错发给我
)
echo.
echo ================================================================
echo   完成。下次开机登录后会自动启动。
echo
echo   卸载：删掉这个文件即可
echo     %STARTUP%\QQ志愿活动监测.lnk
echo ================================================================
pause
