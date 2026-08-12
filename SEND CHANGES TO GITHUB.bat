@echo off
cd /d "%~dp0"
echo ================================================
echo   Sending your changes up to GitHub...
echo ================================================
REM --- clear any stale lock files that block git ---
if exist ".git\index.lock"  del /f /q ".git\index.lock"  >nul 2>&1
if exist ".git\HEAD.lock"    del /f /q ".git\HEAD.lock"   >nul 2>&1
if exist ".git\config.lock"  del /f /q ".git\config.lock" >nul 2>&1
for /r ".git\refs" %%L in (*.lock) do del /f /q "%%L" >nul 2>&1
git add -A
git commit -m "update from %COMPUTERNAME% - %date% %time%"
git push -u origin main
if errorlevel 1 (
  echo.
  echo ================================================
  echo   GitHub said no - pulling what's up there and
  echo   trying once more. This happens when the other
  echo   PC pushed something since your last pull.
  echo ================================================
  git pull --no-rebase --no-edit
  git push -u origin main
)
echo.
if errorlevel 1 (
  echo Still not pushed. Your work is SAFE and committed on this PC -
  echo nothing was lost. Check your internet, then run this again.
  echo If it mentions a CONFLICT, tell Claude before doing anything else.
) else (
  echo Done - your changes are on GitHub.
)
echo.
pause
