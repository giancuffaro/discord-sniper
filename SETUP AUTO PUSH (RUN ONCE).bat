@echo off
cd /d "%~dp0"
title SETUP AUTO PUSH - every 30 minutes, forever
echo ================================================================
echo   One-time setup: registers a Windows scheduled task that
echo   pushes this folder to GitHub every 30 minutes, hidden, only
echo   when something actually changed. After this, nothing is ever
echo   lost to a sync rollback again - GitHub always has the latest.
echo ================================================================
echo.
schtasks /Create /F /TN "DiscordSniper AutoPush" /TR "wscript.exe \"%~dp0_autopush_hidden.vbs\"" /SC MINUTE /MO 30
if errorlevel 1 (
  echo   Couldn't register the task - run this file as Administrator
  echo   ^(right-click, Run as administrator^) and try again.
) else (
  echo.
  echo   Done. First push runs within 30 minutes; running one now too...
  wscript.exe "%~dp0_autopush_hidden.vbs"
  echo   You can delete this setup file. To undo ever:
  echo     schtasks /Delete /TN "DiscordSniper AutoPush" /F
)
echo.
pause
