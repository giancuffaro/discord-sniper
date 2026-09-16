@echo off
setlocal
title Install the 8:55 START HERE schedule
rem ------------------------------------------------------------------
rem  WHY THIS EXISTS (G, 2026-09-16: "the tabs should be open and their
rem  not"). Nothing reopens Discord room tabs at 9:15. roomSchedule()
rem  only CLOSES at 16:30, and openMissingRooms() runs on the START HERE
rem  token only - his 9/8 rule that a tab he closes stays closed. So if
rem  START HERE has not run that morning, the Discord lane reads NOTHING
rem  all day and says so only in the health file. This installs a
rem  weekday 8:55 AM task that runs it. Safe to run twice.
rem ------------------------------------------------------------------
echo.
echo   Installing the weekday 8:55 AM START HERE task...
echo.

set "TARGET=%~dp0launch-sniper.bat"
if not exist "%TARGET%" (
  echo   [FAILED]  launch-sniper.bat is not next to this file.
  echo             Put this .bat in the discord-sniper folder and run it again.
  echo.
  pause
  exit /b 1
)

schtasks /create /tn "Discord Sniper - START HERE 8:55" /tr "\"%TARGET%\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:55 /f >nul 2>&1
if errorlevel 1 (
  echo   [FAILED]  Windows refused to create the task.
  echo             Right-click this file and pick "Run as administrator".
) else (
  echo   [DONE]    Task "Discord Sniper - START HERE 8:55" created.
  echo             Runs Mon-Fri at 8:55 AM, opens every ON room before 9:15.
)
echo.
echo   Next run:
schtasks /query /tn "Discord Sniper - START HERE 8:55" /fo LIST 2>nul | findstr /i "Next Run Time"
echo.
echo   The PC must be awake at 8:55 for this to fire. If it sleeps,
echo   run START HERE by hand - the task cannot wake a sleeping machine
echo   unless you tick that box in Task Scheduler.
echo.
pause
