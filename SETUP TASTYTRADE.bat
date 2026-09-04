@echo off
cd /d "%~dp0"
title CONNECT TASTYTRADE
echo.
echo  ================================================================
echo    CONNECT TASTYTRADE  -  OAuth setup, no password
echo  ================================================================
echo.
echo    You are NOT asked for your tastytrade password. Not here,
echo    not anywhere in this program.
echo.
echo    You need two strings, both made in your own browser:
echo.
echo      1. my.tastytrade.com  ^>  Manage  ^>  API Access
echo         ^>  OAuth Applications  ^>  create one
echo         callback:  http://localhost:8000
echo         COPY THE CLIENT SECRET  (shown once, never again)
echo.
echo      2. same application  ^>  Manage  ^>  Create Grant
echo         COPY THE REFRESH TOKEN
echo.
echo    Paste them below. Refresh tokens never expire, so this is a
echo    one-time setup. You can revoke the grant any time from your
echo    tastytrade account without changing your password.
echo.
echo    This places NO orders and does NOT switch the bot off Webull.
echo.
python setup_tastytrade.py
echo.
echo  ----------------------------------------------------------------
echo    Window stays open so you can read the checklist above.
echo  ----------------------------------------------------------------
pause
