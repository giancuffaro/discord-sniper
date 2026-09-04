@echo off
cd /d "%~dp0"
title CONNECT TRADIER
echo.
echo  ================================================================
echo    CONNECT TRADIER  -  read-only setup
echo  ================================================================
echo.
echo    FUND THE ACCOUNT FIRST. Tradier's own API page says:
echo      "If your account is unfunded for more than 60 days your API
echo       access will be revoked. Once funded, you will need to
echo       regenerate your API keys to regain access."
echo    A key made on an empty account is a key you make twice.
echo.
echo    Where the token comes from:
echo      web.tradier.com  ^>  your name, top right  ^>  API Access
echo      ^>  Generate Production Key  ^>  copy it
echo.
echo    Pressing that button is YOU accepting Tradier's API Agreement.
echo    That one is yours alone - nothing here can press it for you.
echo.
echo    Tokens do NOT expire until you regenerate them.
echo.
echo    This places NO orders and does NOT switch the bot off Webull.
echo.
python setup_tradier.py
echo.
echo  ----------------------------------------------------------------
echo    Window stays open so you can read the checklist above.
echo  ----------------------------------------------------------------
pause
