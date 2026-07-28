@echo off
title DISCORD SNIPER - SETUP
cd /d "%~dp0"
echo.
echo   Installing the two things this bot needs...
echo.
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
python -m pip install --upgrade webull-openapi-python-sdk
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
  echo   Made you a settings.json. Your keys go in it - use KEYS.bat,
  echo   don't edit it by hand.
)
echo.
echo   Done. Next:
echo     TEST.bat    - see how it reads your room's messages
echo     KEYS.bat    - put your Webull API key in
echo     BRIDGE.bat  - the program that actually places the orders
pause
