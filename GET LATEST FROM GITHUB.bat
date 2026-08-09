@echo off
cd /d "%~dp0"
echo ================================================
echo   Getting the latest from GitHub...
echo ================================================
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
git pull
echo.
echo Up to date. You can start working now.
echo.
pause
