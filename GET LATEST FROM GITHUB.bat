@echo off
cd /d "%~dp0"
echo ================================================
echo   Getting the latest from GitHub...
echo ================================================
git pull
echo.
echo Up to date. You can start working now.
echo.
pause
