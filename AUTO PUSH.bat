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

rem --- single instance: a live owner PID remains valid even when git or the
rem --- network blocks longer than two minutes. A dead owner is replaced.
powershell -nop -c "$owner=(Get-CimInstance Win32_Process -Filter ('ProcessId='+$PID)).ParentProcessId; $f='.autopush.pid'; $prior=0; if(Test-Path $f){[void][int]::TryParse((Get-Content -Raw $f -EA SilentlyContinue),[ref]$prior)}; if($prior -and $prior -ne $owner){$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$prior) -EA SilentlyContinue; if($p -and $p.Name -eq 'cmd.exe' -and $p.CommandLine -like '*AUTO PUSH.bat*'){exit 1}}; [IO.File]::WriteAllText($f,[string]$owner); exit 0" >nul 2>&1
if errorlevel 1 exit /b 0

:loop
rem heartbeat (also proves to the next scheduled copy we're alive)
type nul > ".autopush.alive"

rem Runtime state/logs stay on this PC. --cached removes old tracked copies
rem from Git without deleting the local files; .gitignore keeps them out.
git rm -r --cached --ignore-unmatch state.json.bak "webull_api.log*" telemetry-test.csv shadow_ratchet.csv >nul 2>&1
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
  rem Every parser rule must survive every retained message before it ships.
  rem The gate compares the staged parser with HEAD under each room's live
  rem grammar and refuses invented symbols. Its full delta remains reviewable.
  git diff --cached --name-only | findstr /x /c:"extension/parser.js" /c:"extension/rooms.txt" /c:"extension/optionable.txt" >nul 2>&1
  if not errorlevel 1 (
    node parser_gate.js --base HEAD --show 80 > "daily-audits\PARSER-HISTORY-LATEST.txt" 2>&1
    if errorlevel 1 goto gate_failed
    git add "daily-audits\PARSER-HISTORY-LATEST.txt" >nul 2>&1
  )
  git commit -m "auto-push %date% %time%" >nul 2>&1
)

rem Push is independent of committing. If the network failed after a commit,
rem every later pass retries even while the working tree stays clean. Never
rem delete Git lock files or auto-rebase over another active Git operation.
for /f %%N in ('git rev-list --count origin/main..HEAD 2^>nul') do (
  if not "%%N"=="0" git push origin main >nul 2>&1
)

timeout /t 45 /nobreak >nul
goto loop

:gate_failed
rem Leave the change staged and local. The next pass retries after it is fixed.
timeout /t 45 /nobreak >nul
goto loop
