@echo off
title Remove the Fill Announcer leftovers
rem ------------------------------------------------------------------
rem  The Fill Announcer was removed 2026-09-15 (G: reinstall when the
rem  bot is profitable). Its Windows launchers outlived it: a Startup
rem  shortcut and a scheduled task that fires every 30 minutes and now
rem  pops "Can not find script file". This deletes both. Safe to run
rem  twice - anything already gone is reported as gone.
rem ------------------------------------------------------------------
echo.
echo   Removing the Fill Announcer leftovers...
echo.

set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\fill-announcer.vbs"
if exist "%VBS%" (
  del /q "%VBS%"
  if exist "%VBS%" (echo   [FAILED]  Startup shortcut could not be deleted.) else (echo   [REMOVED] Startup shortcut fill-announcer.vbs)
) else (
  echo   [GONE]    Startup shortcut was not there.
)

schtasks /query /tn "Fill Announcer revive" >nul 2>&1
if %errorlevel%==0 (
  schtasks /delete /tn "Fill Announcer revive" /f >nul 2>&1
  schtasks /query /tn "Fill Announcer revive" >nul 2>&1
  if errorlevel 1 (echo   [REMOVED] Scheduled task "Fill Announcer revive") else (echo   [FAILED]  Task still there - right-click this file and Run as administrator.)
) else (
  echo   [GONE]    Scheduled task was not there.
)

echo.
echo   Done. Nothing else to do - close this window.
echo.
pause
