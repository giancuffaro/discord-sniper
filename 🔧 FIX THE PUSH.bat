@echo off
title DISCORD SNIPER - fix the push
cd /d "%~dp0"
echo.
echo   ============================================================
echo     Fixing "rejected - non-fast-forward"
echo   ============================================================
echo.
echo   What happened: GitHub has an older version of this project on
echo   it, and git won't let you push over the top of something it
echo   doesn't recognise. Nothing is broken and nothing is lost.
echo.
echo   What this does: keeps THIS PC's files exactly as they are -
echo   they're the newest - and ties the old GitHub history onto
echo   them so git is happy. No force-push, no history thrown away.
echo.
echo   It also stops log files being uploaded. The Webull SDK writes
echo   one on its own, and those can contain your account id.
echo.
pause

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo.
  echo   This folder isn't connected to GitHub at all. Run
  echo   "FIRST PUSH TO GITHUB.bat" instead.
  echo.
  pause
  exit /b 1
)

echo.
echo   [1/4] Making sure log files stay off GitHub...
findstr /C:"*.log" .gitignore >nul 2>&1
if errorlevel 1 (
  echo.>> .gitignore
  echo # log files - noise, and they can contain account ids>> .gitignore
  echo *.log>> .gitignore
)
git rm --cached -q --ignore-unmatch webull_trade_sdk.log >nul 2>&1
git rm --cached -q --ignore-unmatch trades.log >nul 2>&1
git rm --cached -q --ignore-unmatch settings.json >nul 2>&1

echo   [2/4] Saving this PC's work...
git add -A
git diff --cached --quiet
if errorlevel 1 git commit -q -m "latest build from this PC"

echo   [3/4] Getting GitHub's history...
git fetch origin main
if errorlevel 1 (
  echo.
  echo   Couldn't reach GitHub. Either the sign-in window was closed,
  echo   or there's no internet. Try again.
  echo.
  pause
  exit /b 1
)

echo   [4/4] Joining the two together, keeping this PC's files...
git merge -s ours origin/main --allow-unrelated-histories -q -m "keep this PC's version - it's the newer build"
if errorlevel 1 (
  echo.
  echo   The merge didn't take. Don't guess at it - send me exactly
  echo   what's printed above and I'll give you the next step.
  echo.
  pause
  exit /b 1
)

git push origin main
if errorlevel 1 (
  echo.
  echo   Still refused. Send me what's printed above - that's a
  echo   different problem to the one this file fixes.
  echo.
  pause
  exit /b 1
)

echo.
echo   ============================================================
echo     Done. GitHub now matches this PC.
echo   ============================================================
echo.
echo   From here on just use "PUSH CHANGES.bat" - you shouldn't
echo   need this file again.
echo.
pause
