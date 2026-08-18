@echo off
rem ============================================================
rem  AUTO PUSH - runs hidden every 30 minutes (Task Scheduler).
rem  His rule (8/18): "anytime we do anything id like it pushed
rem  automatically." Commits only when something changed; pulls
rem  and retries once if GitHub is ahead. Silent by design - the
rem  scheduled task runs it through _autopush_hidden.vbs.
rem ============================================================
cd /d "%~dp0"
rem --- clear stale lock files that block git ---
if exist ".git\index.lock"  del /f /q ".git\index.lock"  >nul 2>&1
if exist ".git\HEAD.lock"   del /f /q ".git\HEAD.lock"   >nul 2>&1
git add -A >nul 2>&1
git diff --cached --quiet && exit /b 0
git commit -m "auto-push %date% %time%" >nul 2>&1
git push origin main >nul 2>&1
if errorlevel 1 (
  git pull --rebase origin main >nul 2>&1
  git push origin main >nul 2>&1
)
exit /b 0
