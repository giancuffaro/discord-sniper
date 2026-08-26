@echo off
rem ============================================================
rem  AUTO PUSH - push-on-change (8/26, his ask: "can we push
rem  automatically when we change something?").
rem  Runs as a quiet resident loop: every 45 seconds it looks for
rem  changes and commits+pushes only when there are any - so an
rem  edit reaches GitHub within a minute instead of within half
rem  an hour. Single-instance: the Task Scheduler job (every 30
rem  min, via _autopush_hidden.vbs) now just revives the loop if
rem  it ever died - a second copy sees the fresh heartbeat file
rem  and exits immediately. Pulls and retries once if GitHub is
rem  ahead. settings.json stays gitignored - keys never travel.
rem ============================================================
cd /d "%~dp0"

rem --- single instance: a heartbeat younger than 2 min means the
rem --- loop is already running somewhere; this copy stands down.
powershell -nop -c "$f='.autopush.alive'; if(Test-Path $f){$a=(Get-Date)-(Get-Item $f).LastWriteTime; if($a.TotalSeconds -lt 120){exit 1}}; exit 0" >nul 2>&1
if errorlevel 1 exit /b 0

:loop
rem heartbeat (also proves to the next scheduled copy we're alive)
type nul > ".autopush.alive"

rem --- clear stale lock files that block git ---
if exist ".git\index.lock"  del /f /q ".git\index.lock"  >nul 2>&1
if exist ".git\HEAD.lock"   del /f /q ".git\HEAD.lock"   >nul 2>&1

git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "auto-push %date% %time%" >nul 2>&1
  git push origin main >nul 2>&1
  if errorlevel 1 (
    git pull --rebase origin main >nul 2>&1
    git push origin main >nul 2>&1
  )
)

timeout /t 45 /nobreak >nul
goto loop
