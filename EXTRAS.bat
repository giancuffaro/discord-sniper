@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title DISCORD SNIPER - EXTRAS

rem ===========================================================
rem  The rare stuff. Day to day you never open this file -
rem  "START HERE" does the whole morning by itself, and the
rem  Webull keys go in through the extension popup.
rem
rem  This is for the odd day something needs poking.
rem ===========================================================

:menu
cls
echo.
echo   ============================================================
echo               D I S C O R D   S N I P E R  -  extras
echo   ============================================================
echo.
echo    ^(Day to day you don't need this file. START HERE does
echo     everything, and the Webull keys go in through the
echo     extension popup's Settings.^)
echo.
echo      1   Stop the bridge
echo      2   Show me what the bridge has been doing
echo      3   Check the keys work: live + paper  ^(places no orders^)
echo      4   Test how it reads the room's messages
echo      6   Send my changes up to GitHub
echo      7   Get the latest down from GitHub
echo      8   Turn the 9:25 morning alarm off
echo      9   Put keys in here: live AND paper/sandbox keys
echo     10   Practice the reader on a chat export
echo.
echo      0   Close this
echo.
set "PICK="
set /p PICK="   Number: "

if "!PICK!"=="1"  goto stopbridge
if "!PICK!"=="2"  goto showlog
if "!PICK!"=="3"  goto checkkeys
if "!PICK!"=="4"  goto readtest
if "!PICK!"=="6"  goto push
if "!PICK!"=="7"  goto pull
if "!PICK!"=="8"  goto alarmoff
if "!PICK!"=="9"  goto keys
if "!PICK!"=="10" goto drill
if "!PICK!"=="0"  exit /b 0
goto menu


rem ============================================================
rem  1 - stop the bridge
rem ============================================================
:stopbridge
cls
echo.
echo   Stopping the bridge. It runs hidden, so there's no window to
echo   close - this is how you shut it down. Once it's stopped,
echo   nothing can reach your broker no matter what Chrome does.
echo.

powershell -NoProfile -Command ^
  "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*bridge.py*' };" ^
  "if (-not $p) { Write-Host '  It wasn''t running. Nothing to stop.'; exit 0 };" ^
  "$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force };" ^
  "Write-Host ('  Stopped ' + @($p).Count + ' bridge process(es).')"

echo.
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; Write-Host '  Something is STILL answering on port 8787. Restart the PC if it will not go.' } catch { Write-Host '  Confirmed: nothing is listening. The bridge is down.' }"
goto back


rem ============================================================
rem  2 - the bridge's log
rem ============================================================
:showlog
cls
echo.
if not exist bridge.log (
  echo   There's no log yet. That means the bridge has never been
  echo   started hidden on this PC - double-click START HERE first.
  goto back
)
echo   The last 40 lines of what the bridge has been saying. The
echo   reason for anything going wrong is usually the bottom line.
echo.
powershell -NoProfile -Command "Get-Content -Path 'bridge.log' -Tail 40"
goto back


rem ============================================================
rem  3 - check the keys
rem ============================================================
:checkkeys
cls
echo.
echo   Checking everything that has to be working before a trade can
echo   go out. This places NO orders - the most it does is ask for a
echo   price.
echo.
call :needpython || goto back
python check_keys.py
goto back


rem ============================================================
rem  4 - read test
rem ============================================================
:readtest
cls
echo.
echo   Nothing here can place a trade. This only shows you how it
echo   reads the lines in samples.txt.
echo.
call :needpython || goto back
if not exist "%~dp0tune.py" (
  echo   The parser tuner was retired. Use these instead:
  echo     python replay_check.py        - what did we miss today
  echo     python audit_history.py       - what have we missed ever
  echo     python scoreboard.py 10       - which rooms actually signal
  goto :eof
)
python tune.py
goto back


rem ============================================================
rem  10 - drill a chat export
rem ============================================================
:drill
cls
echo.
echo   Nothing here can place a trade. This runs a whole chat export
echo   through the same reader that trades and writes a report: what
echo   would fire, what gets ignored, and exactly why. That report is
echo   how a room's wording gets learned - anything that reads wrong,
echo   send the report over and the reader gets tuned on it.
echo.
echo   Get the file first: extension popup, "Export chat". It saves
echo   signal-room-chat.txt ^(usually into Downloads^). Scroll far back
echo   in the channel before exporting - scrolled history is captured
echo   too, and it is never traded.
echo.
call :needpython || goto back
set "XF="
set /p XF="   Export file (Enter = Downloads\signal-room-chat.txt): "
if "!XF!"=="" set "XF=%USERPROFILE%\Downloads\signal-room-chat.txt"
set "ROOMPICK="
set /p ROOMPICK="   One room only? (Enter = all, or: main / aristotle / midas / aristotle-small): "
if not exist "%~dp0drill.py" (
  echo   The room drill was retired. audit_history.py covers it now.
  goto :eof
)
python drill.py "!XF!" !ROOMPICK!
if exist "drill-report.txt" start "" notepad "drill-report.txt"
goto back



rem ============================================================
rem  6 - push
rem ============================================================
:push
cls
echo.
call :needgit || goto back

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 goto firstpush

rem  "Nothing has changed" used to end the whole thing right here, which was
rem  wrong in one important case: a commit that was made and then REFUSED by
rem  GitHub is already committed, so there's nothing left to stage and this
rem  looked like everything was fine while the work sat unpushed. Now it goes
rem  and pushes anyway - if GitHub already has it, the push is a no-op and
rem  costs a second.
git add -A
git diff --cached --quiet
if errorlevel 1 goto stageit
echo   Nothing new since last time - checking GitHub actually has it.
echo.
goto sendit

:stageit
echo   About to send:
git diff --cached --name-status
echo.
set "MSG="
set /p MSG="   Short note about this change, or just press Enter: "
if "!MSG!"=="" set MSG=update
git commit -q -m "!MSG!"

:sendit
git push origin main
if not errorlevel 1 (
  echo.
  echo   Done. GitHub matches this PC.
  goto back
)

echo.
echo   That didn't go through. Your work is safe either way - it's
echo   saved on this PC, it just hasn't been uploaded.
echo.
echo   If it says "rejected" or "non-fast-forward", GitHub has an
echo   older version it doesn't recognise. I can join the two
echo   together, keeping this PC's files exactly as they are.
echo.
set "ANS="
set /p ANS="   Try that? Y to go ahead, anything else to skip: "
if /i not "!ANS!"=="Y" goto back

echo.
echo   Keeping log files off GitHub first...
findstr /C:"*.log" .gitignore >nul 2>&1
if errorlevel 1 (
  echo.>> .gitignore
  echo # log files - noise, and they can contain account ids>> .gitignore
  echo *.log>> .gitignore
)
git rm --cached -q --ignore-unmatch webull_trade_sdk.log >nul 2>&1
git rm --cached -q --ignore-unmatch trades.log >nul 2>&1
git rm --cached -q --ignore-unmatch settings.json >nul 2>&1
git add -A
git diff --cached --quiet
if errorlevel 1 git commit -q -m "latest build from this PC"

git fetch origin main
if errorlevel 1 (
  echo.
  echo   Couldn't reach GitHub - no internet, or the sign-in window
  echo   was closed.
  goto back
)
git merge -s ours origin/main --allow-unrelated-histories -q -m "keep this PC's version - it's the newer build"
git push origin main
if errorlevel 1 (
  echo.
  echo   Still refused. Send me exactly what's printed above - that's
  echo   a different problem to the one this fixes.
  goto back
)
echo.
echo   Sorted. GitHub matches this PC now.
goto back


:firstpush
echo   This folder isn't wired to GitHub yet. Run START HERE once -
echo   it wires the folder up by itself now - then come back here.
goto back
)
echo.
echo   Didn't go through. Your work is safe either way - it's on this
echo   PC, it just hasn't been uploaded.
echo.
echo   Usually one of three things: the repo wasn't created yet, the
echo   name doesn't match, or the sign-in window was closed.
echo.
echo   There's one more: the repo already existed with files in it,
echo   from an older setup. GitHub won't let a fresh folder land on
echo   top of that. I can join the two together, keeping THIS PC's
echo   files exactly as they are - nothing here gets overwritten.
echo.
set "ANS="
set /p ANS="   Try that? Y to go ahead, anything else to skip: "
if /i not "!ANS!"=="Y" goto back

git fetch origin main
if errorlevel 1 (
  echo.
  echo   Couldn't reach GitHub - no internet, or the sign-in window
  echo   was closed. Nothing was changed.
  goto back
)
git merge -s ours origin/main --allow-unrelated-histories -q -m "keep this PC's version - it's the newer build"
git push -u origin main
if errorlevel 1 (
  echo.
  echo   Still refused. Send me exactly what's printed above - that's
  echo   a different problem to the one this fixes.
) else (
  echo.
  echo   Sorted. It's on GitHub, and this PC's files are the ones up there.
)
goto back


rem ============================================================
rem  7 - pull
rem ============================================================
:pull
cls
echo.
call :needgit || goto back
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo   This folder isn't connected to GitHub yet. Do 6 first.
  goto back
)

echo   Getting the latest...
echo.
git fetch origin main
if errorlevel 1 (
  echo   Couldn't reach GitHub. Check the internet and try again.
  goto back
)

git diff --quiet
if errorlevel 1 goto pulldirty
git diff --cached --quiet
if errorlevel 1 goto pulldirty

git pull --ff-only origin main
if errorlevel 1 (
  echo.
  echo   That wouldn't come down cleanly - GitHub and this PC have
  echo   both moved. Nothing is lost. Do 6 and say Y to the join
  echo   question, and it sorts itself out.
  goto back
)
goto pulldone

:pulldirty
echo   The files on this PC don't match GitHub. That's normal if
echo   updates used to arrive as a zip pasted over this folder -
echo   from now on THIS is the update, no more zips. The cure is to
echo   make this folder exactly match GitHub. Your keys, your day
echo   records and your trade log are NOT touched - they live
echo   outside GitHub on purpose.
echo.
set "MATCH="
set /p MATCH="   Make this folder match GitHub now? (Y = yes): "
if /i not "!MATCH!"=="Y" goto back
rem  Refuse to destroy local-only commits (8/30 lesson): if GitHub is
rem  missing anything local, this reset would erase real work.
git merge-base --is-ancestor HEAD origin/main >nul 2>&1
if errorlevel 1 (
  echo   STOP: this folder has work GitHub does NOT have yet. Push it
  echo   first ^(AUTO PUSH or SEND CHANGES^), then try again.
  goto back
)
git reset --hard origin/main
if errorlevel 1 (
  echo   That failed and nothing was changed. Send me a photo of
  echo   this screen.
  goto back
)

:pulldone
echo.
echo   Up to date. Chrome picks up the new extension on its own -
echo   straight away while the market is closed, or the moment the
echo   session ends if it's open right now. You don't touch Chrome.
echo.
rem  No question here on his word - he updates after hours, so the
rem  bridge just restarts onto the new code by itself. (A mid-session
rem  restart would start today's scorekeeping fresh, which is why
rem  updates belong in the evening.)
echo   Restarting the bridge onto the new code...
powershell -NoProfile -Command ^
  "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*bridge.py*' };" ^
  "if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host '  Old bridge stopped.' } else { Write-Host '  Bridge was not running.' }"
wscript.exe "%~dp0_run_hidden.vbs"
echo   New bridge starting, hidden. Give it a few seconds.
goto back


rem ============================================================
rem  8 - alarm off
rem ============================================================
:alarmoff
cls
echo.
schtasks /query /tn "Discord Sniper morning" >nul 2>&1
if errorlevel 1 (
  echo   The alarm isn't set, so there's nothing to turn off.
  echo   ^(START HERE sets it again next time it runs, unless Windows
  echo   asks for permission it doesn't have.^)
  goto back
)
schtasks /delete /tn "Discord Sniper morning" /f >nul 2>&1
echo   Cancelled. Nothing starts on its own now - double-click
echo   START HERE each morning instead. It will set the alarm again
echo   next run; come back here to cancel it again if you want it
echo   to stay off.
goto back


rem ============================================================
rem  9 - keys at the console, the old way
rem ============================================================
:keys
cls
echo.
echo   Your LIVE key can also go in through the extension popup. But the
echo   PAPER (sandbox) key can ONLY go in here - so for paper trading,
echo   this is the place. Press Enter on the live lines to keep them,
echo   then paste the sandbox key and secret at the Paper prompts.
echo.
call :needpython || goto back
python setup_keys.py
goto back


rem ============================================================
rem  small shared bits
rem ============================================================
:needpython
where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python isn't installed, or Windows can't find it.
  echo.
  echo   Get it from python.org/downloads and tick "Add Python to
  echo   PATH" on the very first screen of the installer. That one
  echo   tickbox is the whole thing - miss it and nothing here runs.
  exit /b 1
)
exit /b 0

:needgit
where git >nul 2>&1
if errorlevel 1 (
  echo   Git isn't installed on this PC. Get it from
  echo       https://git-scm.com/download/win
  echo   Click Next through the installer, the defaults are fine.
  exit /b 1
)
exit /b 0

:back
echo.
pause
goto menu
