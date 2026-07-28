@echo off
title DISCORD SNIPER - bridge (leave this window open)
cd /d "%~dp0"
if exist ".venv\Scripts\activate" call .venv\Scripts\activate
python bridge.py
echo.
echo The bridge stopped. Nothing can trade until you start it again.
pause
