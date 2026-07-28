@echo off
title Discord Sniper - first push to GitHub
cd /d "%~dp0"
echo ============================================================
echo   DISCORD SNIPER  ^>  GitHub
echo ============================================================
echo.
echo Do this FIRST, in your browser:
echo.
echo   1. Go to  https://github.com/new
echo   2. Repository name:  discord-sniper
echo   3. Set it to PRIVATE
echo   4. Do NOT tick "Add a README" - leave every box empty
echo   5. Click "Create repository"
echo.
echo Then come back here and press a key.
pause >nul
echo.
if not exist ".git" (
  git init
  git branch -M main
  git add -A
  git commit -m "Discord Sniper"
)
git remote remove origin >nul 2>&1
git remote add origin https://github.com/giancuffaro/discord-sniper.git
echo Pushing...
echo A GitHub login window may pop up. Sign in and it will finish on its own.
echo.
git push -u origin main
echo.
if errorlevel 1 (
  echo ------------------------------------------------------------
  echo  That did not go through. The usual reasons:
  echo   - the repo on GitHub was not created yet, or has a different name
  echo   - you ticked "Add a README" so GitHub already put a commit in it
  echo     ^(fix: run   git pull origin main --allow-unrelated-histories
  echo      then run this file again^)
  echo   - the login window was closed before finishing
  echo  Copy whatever is printed above and send it to Claude.
  echo ------------------------------------------------------------
) else (
  echo ------------------------------------------------------------
  echo  Done. From now on you only need   UPDATE.bat
  echo ------------------------------------------------------------
)
pause
