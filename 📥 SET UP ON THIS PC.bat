@echo off
title DISCORD SNIPER - set up on this PC
cd /d "%~dp0"
echo.
echo   ============================================================
echo     Setting Discord Sniper up on this computer.
echo   ============================================================
echo.
echo   This pulls the latest code down from your GitHub, installs
echo   what Python needs, and tells you the two things only you can
echo   do (your keys, and loading the extension into Chrome).
echo.
pause

where git >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Git isn't installed on this PC. Get it from:
  echo       https://git-scm.com/download/win
  echo   Click Next through the whole installer, the defaults are fine.
  echo   Then run this file again.
  echo.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python isn't installed on this PC. Get it from:
  echo       https://www.python.org/downloads/
  echo   On the FIRST screen of the installer, tick
  echo       "Add Python to PATH"
  echo   That box is the reason this fails for most people.
  echo   Then run this file again.
  echo.
  pause
  exit /b 1
)

echo.
echo   [1/3] Getting the latest code from GitHub...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo         This folder isn't linked to GitHub yet. Linking it...
  git init >nul 2>&1
  git remote add origin https://github.com/giancuffaro/discord-sniper.git >nul 2>&1
  git fetch origin main
  if errorlevel 1 (
    echo.
    echo         Couldn't reach the repo. Either you're not signed in to
    echo         GitHub on this PC yet ^(a sign-in window should have popped
    echo         up^), or there's no internet. Try again once you're signed in.
    echo.
    pause
    exit /b 1
  )
  git checkout -B main origin/main
) else (
  git stash >nul 2>&1
  git pull origin main
)

echo.
echo   [2/3] Installing what Python needs...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
python -m pip install --upgrade webull-openapi-python-sdk
if errorlevel 1 (
  echo.
  echo         That didn't finish. Usually it's Python installed without
  echo         "Add to PATH" ticked. Reinstall from python.org with that
  echo         box ticked and run this again.
  echo.
  pause
  exit /b 1
)

if not exist settings.json (
  copy settings.example.json settings.json >nul
  echo.
  echo   [3/3] Made you a fresh settings.json on this PC.
) else (
  echo.
  echo   [3/3] You already have a settings.json here - leaving it alone.
)

echo.
echo   ============================================================
echo     Done. Two things left, and only you can do them:
echo   ============================================================
echo.
echo     1. Run KEYS.bat and put your Webull App Key and Secret in.
echo        Your keys are NOT in GitHub - that's on purpose - so every
echo        new PC needs them typed in once.
echo.
echo     2. Load the extension into Chrome:
echo          - go to  chrome://extensions
echo          - turn on Developer mode ^(top right^)
echo          - click Load unpacked
echo          - pick the "extension" folder inside this one
echo.
echo     Then start BRIDGE.bat and leave that window open.
echo.
echo     Start on DRY RUN. The popup has a LIVE / DRY RUN button now -
echo     leave it on DRY RUN until you've watched a full session.
echo.
pause
