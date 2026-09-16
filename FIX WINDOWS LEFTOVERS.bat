@echo off
setlocal enabledelayedexpansion
title Discord Sniper - fix my Windows leftovers
rem ------------------------------------------------------------------
rem  ONE double-click. Two jobs:
rem    1. Kill the "Can not find script file _announcer_hidden.vbs"
rem       popup. The Fill Announcer was removed 2026-09-15; its Startup
rem       shortcut and its 30-minute revive task outlived it.
rem    2. Install the weekday 8:55 AM task that runs START HERE, so the
rem       Discord room tabs are open before 9:15. Nothing else reopens
rem       them: roomSchedule() only CLOSES at 16:30.
rem  Safe to run twice. Anything already done reports as already done.
rem ------------------------------------------------------------------
echo.
echo   ============================================================
echo     Discord Sniper - fixing Windows leftovers
echo   ============================================================
echo.
echo   [1/2] Removing the dead Fill Announcer launchers
echo.

set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\fill-announcer.vbs"
if exist "%VBS%" (
  del /q "%VBS%" >nul 2>&1
  if exist "%VBS%" (echo         [FAILED]  Startup shortcut would not delete.) else (echo         [REMOVED] Startup shortcut fill-announcer.vbs)
) else (
  echo         [GONE]    Startup shortcut was not there.
)

schtasks /query /tn "Fill Announcer revive" >nul 2>&1
if errorlevel 1 (
  echo         [GONE]    Revive task was not there.
) else (
  schtasks /delete /tn "Fill Announcer revive" /f >nul 2>&1
  schtasks /query /tn "Fill Announcer revive" >nul 2>&1
  if errorlevel 1 (echo         [REMOVED] Task "Fill Announcer revive" - the popup stops now.) else (echo         [FAILED]  Task still there. Right-click this file, Run as administrator.)
)

echo.
echo   [2/2] Installing the weekday 8:55 AM START HERE task
echo.
set "TARGET=%~dp0launch-sniper.bat"
if not exist "%TARGET%" (
  echo         [FAILED]  launch-sniper.bat is not next to this file.
) else (
  schtasks /create /tn "Discord Sniper - START HERE 8:55" /tr "\"%TARGET%\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:55 /f >nul 2>&1
  if errorlevel 1 (
    echo         [FAILED]  Windows refused. Right-click this file, Run as administrator.
  ) else (
    echo         [DONE]    Task created - runs Mon-Fri at 8:55 AM.
    for /f "tokens=1,* delims=:" %%a in ('schtasks /query /tn "Discord Sniper - START HERE 8:55" /fo LIST 2^>nul ^| findstr /i "Next Run Time"') do echo         Next run:%%b
  )
)

echo.
echo   ============================================================
echo     Done. The popup is gone and the mornings are scheduled.
echo     Note: a scheduled task cannot wake a sleeping PC. If the
echo     machine sleeps overnight, run START HERE by hand.
echo   ============================================================
echo.
pause
