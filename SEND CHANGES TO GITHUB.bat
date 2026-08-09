@echo off
cd /d "%~dp0"
echo ================================================
echo   Sending your changes up to GitHub...
echo ================================================
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
git add -A
git commit -m "update from %COMPUTERNAME% - %date% %time%"
git push -u origin main
echo.
if errorlevel 1 (
  echo If it said REJECTED: double-click "GET LATEST FROM GITHUB" first, then run this again.
) else (
  echo Done - your changes are on GitHub.
)
echo.
pause
