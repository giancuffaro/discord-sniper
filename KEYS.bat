@echo off
title DISCORD SNIPER - Webull keys
cd /d "%~dp0"
if exist ".venv\Scripts\activate" call .venv\Scripts\activate
python setup_keys.py
pause
