@echo off
cd /d "%~dp0"
title CONNECT TASTYTRADE
echo.
echo  ================================================================
echo    CONNECT TASTYTRADE  -  read-only setup
echo  ================================================================
echo.
echo    Your password is typed into THIS window, used once to get a
echo    token, then forgotten. It is never saved to settings.json,
echo    never written to any log, and never sent anywhere but
echo    tastytrade's own login.
echo.
echo    You will see a * for each character you type. If you see
echo    nothing at all, the window has not got focus - click it first.
echo.
echo    This places NO orders and does NOT switch the bot off Webull.
echo.
python setup_tastytrade.py
echo.
echo  ----------------------------------------------------------------
echo    Window stays open so you can read the checklist above.
echo  ----------------------------------------------------------------
pause
