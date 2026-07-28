@echo off
title DISCORD SNIPER - SETUP
cd /d "%~dp0"
echo.
echo   Installing the two things this bot needs...
echo.
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo   That didn't work. The usual cause is Python not being installed,
  echo   or being installed without "Add to PATH" ticked.
  echo   Get it from python.org, tick that box, then run this again.
  pause
  exit /b 1
)
if not exist settings.json (
  copy settings.example.json settings.json >nul
  echo.
  echo   Made you a settings.json. Open it and put in your bot token
  echo   and the channel ID before you run the bot.
)
echo.
echo   Done. Next: run TEST.bat to see how it reads your room's messages.
pause
