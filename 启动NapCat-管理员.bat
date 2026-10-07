@echo off
chcp 936 >nul
title NapCat launcher (elevated)
cd /d "%~dp0napcat"

REM ============================================================
REM  Runs NapCat with administrator rights.
REM
REM  WHY ELEVATION IS REQUIRED:
REM  NapCat loads its hook DLL into the QQ process. Injecting into
REM  another process needs SeDebugPrivilege, which a normal
REM  (non-elevated) process does not have even when the account is
REM  in the Administrators group. Without elevation
REM  NapCatWinBootMain.exe silently hangs and QQ never starts.
REM
REM  This file is intentionally ASCII-only. Chinese characters in a
REM  .bat file get mangled because cmd and the file encoding
REM  disagree, which produces "命令语法不正确" style errors.
REM  The QQ path therefore comes from a separate UTF-8 text file.
REM ============================================================

set "NAPCAT_PATCH_PACKAGE=%cd%\qqnt.json"
set "NAPCAT_LOAD_PATH=%cd%\loadNapCat.js"
set "NAPCAT_INJECT_PATH=%cd%\NapCatWinBootHook.dll"
set "NAPCAT_LAUNCHER_PATH=%cd%\NapCatWinBootMain.exe"
set "NAPCAT_MAIN_PATH=%cd%\napcat.mjs"
set "NAPCAT_MAIN_PATH=%NAPCAT_MAIN_PATH:\=/%"
set "NAPCAT_LAUNCHER_LOG=%cd%\..\logs\napcat-launcher.log"

echo ================================================================
echo   Starting NapCat for QQ 2014713076
echo ================================================================
echo.

REM --- Resolve the QQ path.
REM  Order matters. The registry is tried FIRST on purpose:
REM  its value is ASCII (path stored in 8.3 short form), so it is
REM  immune to the codepage mismatch that corrupts Chinese paths
REM  read from a UTF-8 text file by a batch script.
set "QQPath="
echo [1/4] Locating QQ installation...
for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ" /v "UninstallString" 2^>nul') do set "RetString=%%~b"
if defined RetString (
  for %%a in ("%RetString%") do set "QQPath=%%~dpaQQ.exe"
)

REM  Fallback 1: non-ASCII path from the local ini (may be mojibake
REM  under a GBK console, which is why it is not the primary source)
if not defined QQPath (
  set "QQINI=%cd%\..\tools\qqpath.ini"
  if exist "%QQINI%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%QQINI%") do (
      if /i "%%a"=="QQPath" set "QQPath=%%b"
    )
  )
)

REM  Fallback 2: the canonical short (8.3) path, always ASCII
if not defined QQPath set "QQPath=D:\新建文件夹\交流\QQ.exe"

if not exist "%QQPath%" (
  echo [ERROR] QQ.exe not found at: %QQPath%
  echo.
  echo         Fix it by editing this file and setting QQPath manually.
  pause
  exit /b 1
)

echo [3/4] Writing injection entry point...
echo (async () =^> {await import("file:///%NAPCAT_MAIN_PATH%")})() > "%NAPCAT_LOAD_PATH%"

echo [4/4] Booting NapCat + QQ...
echo.
echo   ------------------------------------------------
echo    QQ will start now.
echo    Log in with 2014713076.
echo    Keep this window open.
echo   ------------------------------------------------
echo.

REM  -q <QQ> triggers QQ's quick-login path: it reuses the cached
REM  credential in %APPDATA%\QQ\auth\login.enc and usually avoids the
REM  QR scan entirely. Delete the "-q 2014713076" below if you would
REM  rather always see the QR code.
set "QUICKLOGIN=-q 2014713076"

"%NAPCAT_LAUNCHER_PATH%" "%QQPath%" "%NAPCAT_INJECT_PATH%" %QUICKLOGIN% %*

echo.
echo [NapCat] process exited with code %ERRORLEVEL%
pause
