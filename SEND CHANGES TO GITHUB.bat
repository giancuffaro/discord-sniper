@echo off
cd /d "%~dp0"
echo ================================================
echo   Sending your changes up to GitHub...
echo ================================================
git add -A
git commit -m "update from %COMPUTERNAME% - %date% %time%"
git push
echo.
if errorlevel 1 (
  echo If it said REJECTED: double-click "GET LATEST FROM GITHUB" first, then run this again.
) else (
  echo Done - your changes are on GitHub. Your other devices can now Get Latest.
)
echo.
pause
