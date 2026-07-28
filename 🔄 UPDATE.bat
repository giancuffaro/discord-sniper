@echo off
title UPDATE - Discord Sniper
cd /d "%~dp0"
echo Pulling the latest version from GitHub...
echo.
git stash >nul 2>&1
git pull origin main
echo.
echo Update complete.
echo.
echo If the extension files changed, open chrome://extensions and hit the
echo reload arrow on Discord Sniper so Chrome picks up the new version.
echo.
timeout /t 8 >nul
exit
