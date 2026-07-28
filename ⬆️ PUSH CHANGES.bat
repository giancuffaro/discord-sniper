@echo off
title DISCORD SNIPER - push changes to GitHub
cd /d "%~dp0"
echo.
echo   Sending this folder up to GitHub.
echo.
echo   Safe to run any time. Your settings.json, your trades.log and your
echo   STOP file are ignored by git - they stay on this PC only.
echo.

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo   This folder isn't connected to GitHub yet.
  echo   Run "FIRST PUSH TO GITHUB.bat" instead - that one sets it up.
  echo.
  pause
  exit /b 1
)

git add -A
git diff --cached --quiet
if not errorlevel 1 (
  echo   Nothing has changed since the last push. You're already up to date.
  echo.
  pause
  exit /b 0
)

echo   About to send:
git diff --cached --name-status
echo.

set /p MSG="  Short note about this change (or just press Enter): "
if "%MSG%"=="" set MSG=update

git commit -q -m "%MSG%"
git push origin main
if errorlevel 1 (
  echo.
  echo   That didn't go through. The usual reasons:
  echo.
  echo     - GitHub asked you to sign in and you closed the window.
  echo       Run this again and finish the sign-in.
  echo.
  echo     - Something changed on GitHub that isn't on this PC. Run
  echo       "UPDATE.bat" first to pull it down, then run this again.
  echo.
  echo     - No internet.
  echo.
  echo   Your work is safe either way - it's committed locally, it just
  echo   hasn't been uploaded yet.
  echo.
  pause
  exit /b 1
)

echo.
echo   Done. It's on GitHub.
echo.
pause
