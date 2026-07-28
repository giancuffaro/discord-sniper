@echo off
title DISCORD SNIPER - LIVE LISTENER
cd /d "%~dp0"
echo.
echo   Starting. To halt it instantly, make a file called STOP in this
echo   folder - the bot checks for it before every single order.
echo.
python listener.py
echo.
echo   The bot stopped. Read the message above for the reason.
pause
