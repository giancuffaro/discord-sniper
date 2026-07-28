@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title DISCORD SNIPER

rem ===========================================================
rem  One file. Everything is a number on the menu below.
rem
rem  It can also be run with a word after it, which is how the
rem  9:25 alarm starts the morning without showing a menu:
rem      "START HERE.bat" morning
rem ===========================================================

rem  Your signal room. These two numbers are what Discord calls
rem  the server and the channel, and together they are the web
rem  address of the channel the calls come in on. Nothing here
rem  asks you for it any more - if you ever move rooms, change
rem  these two lines and that's the whole job.
set "SERVER_ID=525113944239767562"
set "CHANNEL_ID=829754942817828884"
set "DISCORD_URL=https://discord.com/channels/%SERVER_ID%/%CHANNEL_ID%"

if /i "%~1"=="morning" goto morning

:menu
cls
echo.
echo   ============================================================
echo                        D I S C O R D   S N I P E R
echo   ============================================================
echo.
echo    FIRST TIME - do these once, top to bottom
echo.
echo      1   Install everything
echo      2   Put my Webull keys in
echo      3   Check the keys actually work      ^(places no orders^)
echo      4   Set the 9:25 morning alarm
echo.
echo    EVERY DAY - or just let the alarm do it
echo.
echo      5   Start now  -  bridge + your Discord channel
echo      6   Stop the bridge
echo.
echo    CHANGE HOW IT TRADES
echo.
echo     11   The numbers  -  buying power, trades a day, averaging in
echo.
echo    IF SOMETHING LOOKS WRONG
echo.
echo      7   Show me what the bridge has been doing
echo      8   Test how it reads the room's messages
echo      9   Send my changes up to GitHub
echo     10   Get the latest down from GitHub
echo.
echo      0   Close this
echo.
set "PICK="
set /p PICK="   Number: "

if "!PICK!"=="1"  goto install
if "!PICK!"=="2"  goto keys
if "!PICK!"=="3"  goto checkkeys
if "!PICK!"=="4"  goto alarm
if "!PICK!"=="5"  goto startnow
if "!PICK!"=="6"  goto stopbridge
if "!PICK!"=="7"  goto showlog
if "!PICK!"=="8"  goto readtest
if "!PICK!"=="9"  goto push
if "!PICK!"=="10" goto pull
if "!PICK!"=="11" goto numbers
if "!PICK!"=="0"  exit /b 0
goto menu


rem ============================================================
rem  1 - install
rem ============================================================
:install
cls
echo.
echo   Installing what this needs. One or two minutes.
echo.
call :needpython || goto back

python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
python -m pip install --upgrade webull-openapi-python-sdk
if errorlevel 1 (
  echo.
  echo   That didn't finish. Almost always it's Python installed
  echo   without "Add Python to PATH" ticked. Reinstall it from
  echo   python.org with that box ticked, then come back to 1.
  goto back
)

if not exist settings.json (
  copy settings.example.json settings.json >nul
  echo.
  echo   Made you a settings.json. Don't edit it by hand - number 2
  echo   fills it in for you.
)

echo.
echo   Done. Now do 2, then 3, then 4.
goto back


rem ============================================================
rem  2 - keys
rem ============================================================
:keys
cls
call :needpython || goto back
python setup_keys.py
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
rem  4 - the 9:25 alarm
rem ============================================================
:alarm
cls
echo.
echo   ============================================================
echo     The morning alarm
echo   ============================================================
echo.
echo   Every weekday at 9:25 this PC starts the bridge hidden and
echo   opens your signal channel in Chrome. You do nothing.
echo.
echo   It does NOT arm anything and it does NOT go live. Both of
echo   those stay yours to press.
echo.

schtasks /query /tn "Discord Sniper morning" >nul 2>&1
if not errorlevel 1 (
  echo   The alarm is already set.
  echo.
  set "ANS="
  set /p ANS="   Press Enter to leave it alone, or type OFF to cancel it: "
  if /i "!ANS!"=="OFF" (
    schtasks /delete /tn "Discord Sniper morning" /f >nul 2>&1
    echo.
    echo   Cancelled. Nothing starts on its own now - use 5 each morning.
  ) else (
    echo.
    echo   Left as it is.
  )
  goto back
)

rem ---- does this PC's clock match New York? ------------------
for /f %%a in ('powershell -NoProfile -Command "(Get-Date).ToString('HH:mm')"') do set LOCALT=%%a
for /f %%a in ('powershell -NoProfile -Command "[System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date).ToUniversalTime(),'Eastern Standard Time').ToString('HH:mm')"') do set ETT=%%a
echo     This PC says it is:    !LOCALT!
echo     New York says it is:   !ETT!
echo.
if "!LOCALT!"=="!ETT!" (
  echo   Those match, so 9:25 here is 9:25 in New York. Good.
  set WHEN=09:25
) else (
  echo   Those DON'T match - this PC isn't on New York time, and
  echo   Windows alarms run on THIS PC's clock. Work out what time
  echo   it is here when it's 9:25 in New York and type that.
  echo.
  set "WHEN="
  set /p WHEN="   Time on THIS PC, 24 hour, like 06:25: "
  if "!WHEN!"=="" set WHEN=09:25
)

echo.
echo   Setting it for !WHEN!, Monday to Friday...
echo.

rem %~f0 is this file's own full path - safer than typing the name
rem again, because the name has a picture character in it.
schtasks /create /f /tn "Discord Sniper morning" /tr "\"%~f0\" morning" /sc weekly /d MON,TUE,WED,THU,FRI /st !WHEN!

if errorlevel 1 (
  echo.
  echo   Windows wouldn't set it. That's the permission thing - close
  echo   this, right-click the file, pick "Run as administrator", and
  echo   do 4 again.
  goto back
)

echo.
echo   Set. Two things worth knowing:
echo.
echo     - A sleeping PC runs no alarms. If it sleeps overnight,
echo       just use 5 when you sit down.
echo     - Come back to 4 any time to cancel it.
goto back


rem ============================================================
rem  5 - start now  /  the alarm's morning run
rem ============================================================
:startnow
cls
set INTERACTIVE=1
call :dostart
goto back

:morning
rem Nobody is sitting here at 9:25, so nothing in here may ask a question -
rem a hidden prompt waiting for an answer would just never start the bridge.
set INTERACTIVE=0
call :dostart
rem Close on its own - nobody's sitting here at 9:25.
timeout /t 12 >nul
exit /b 0


:dostart
echo.
echo   Starting up for the session...
echo.

set RUNNING=0
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set RUNNING=1

if "!RUNNING!"=="1" (
  echo   [1/2] The bridge is already running. Leaving it alone.
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo   [1/2] Python isn't installed, or Windows can't find it.
    echo         Nothing can trade. python.org/downloads, and tick
    echo         "Add Python to PATH" on the first screen.
    goto :dostart_discord
  )
  echo   [1/2] Starting the bridge, hidden...
  wscript.exe "%~dp0_run_hidden.vbs"

  rem Start it and check it. Not checking is how you find out at 9:31.
  set OK=0
  for /l %%i in (1,1,10) do (
    if "!OK!"=="0" (
      timeout /t 1 /nobreak >nul
      powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
      if not errorlevel 1 set OK=1
    )
  )
  if "!OK!"=="1" (
    echo         Bridge is up and answering.
  ) else (
    echo         The bridge did NOT come up. Nothing can trade.
    echo         Menu number 7 shows you why.
  )
)

:dostart_discord
echo.
echo   [2/2] Opening your signal channel in Chrome...

rem  Find Chrome. "start chrome" only works if it happens to be on the
rem  PATH, which on a lot of PCs it isn't, and then this silently opens
rem  nothing. These are the three places Windows actually puts it.
set "CHROME="
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

if defined CHROME (
  start "" "!CHROME!" "!DISCORD_URL!"
  echo         !DISCORD_URL!
) else (
  echo         Couldn't find Chrome in any of the usual folders, so I'm
  echo         opening your default browser instead. The extension only
  echo         runs in Chrome - if that wasn't Chrome, paste this in:
  echo         !DISCORD_URL!
  start "" "!DISCORD_URL!"
)

echo.
echo   ============================================================
echo     Ready. Two switches left, and only you can flip them:
echo       - the bot is OFF until you turn it ON      ^(top button^)
echo       - it's in TEST MODE until you switch it    ^(bottom button^)
echo     Both are in the extension popup, top right of Chrome.
echo     TEST MODE buys nothing. Leave it there until you mean it.
echo   ============================================================
exit /b 0


rem ============================================================
rem  6 - stop the bridge
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
rem  7 - the bridge's log
rem ============================================================
:showlog
cls
echo.
if not exist bridge.log (
  echo   There's no log yet. That means the bridge has never been
  echo   started hidden on this PC - do 5 first.
  goto back
)
echo   The last 40 lines of what the bridge has been saying. The
echo   reason for anything going wrong is usually the bottom line.
echo.
powershell -NoProfile -Command "Get-Content -Path 'bridge.log' -Tail 40"
goto back


rem ============================================================
rem  11 - the numbers
rem ============================================================
:numbers
cls
echo.
echo   Nothing here can place a trade, and nothing here goes live.
echo   It only changes the numbers it trades by.
echo.
call :needpython || goto back
python settings_quick.py
goto back


rem ============================================================
rem  8 - read test
rem ============================================================
:readtest
cls
echo.
echo   Nothing here can place a trade. This only shows you how it
echo   reads the lines in samples.txt.
echo.
call :needpython || goto back
python tune.py
goto back


rem ============================================================
rem  9 - push
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
echo   This folder isn't connected to GitHub yet.
echo.
echo   Do this in your browser first:
echo.
echo     1. Go to  https://github.com/new
echo     2. Repository name:  discord-sniper
echo     3. Set it to PRIVATE
echo     4. Leave every tickbox empty - no README
echo     5. Click "Create repository"
echo.
pause
git init >nul 2>&1
git branch -M main >nul 2>&1
git add -A
git commit -q -m "Discord Sniper"
git remote remove origin >nul 2>&1
git remote add origin https://github.com/giancuffaro/discord-sniper.git
echo.
echo   Pushing. A GitHub sign-in window may pop up - finish it and
echo   this carries on by itself.
echo.
git push -u origin main
if not errorlevel 1 (
  echo.
  echo   Done. It's on GitHub.
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
rem  10 - pull
rem ============================================================
:pull
cls
echo.
call :needgit || goto back
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo   This folder isn't connected to GitHub yet. Do 9 first.
  goto back
)

git diff --quiet
if errorlevel 1 goto dirty
git diff --cached --quiet
if errorlevel 1 goto dirty

echo   Getting the latest...
echo.
git pull --ff-only origin main
if errorlevel 1 (
  echo.
  echo   That wouldn't come down cleanly - GitHub and this PC have
  echo   both moved. Nothing is lost. Do 9 and say Y to the join
  echo   question, and it sorts itself out.
  goto back
)
echo.
echo   Up to date. If any extension files changed, Chrome picks it
echo   up on its own within about half a minute - you don't touch it.
echo.
set "ANS="
set /p ANS="   Keep watching for more changes every 2 min? Y/N: "
if /i not "!ANS!"=="Y" goto back

echo.
echo   Watching. Leave this window open. Close it to stop.
echo.
:watchloop
timeout /t 120 /nobreak >nul
git diff --quiet || goto watchdirty
git diff --cached --quiet || goto watchdirty
git fetch origin main --quiet
if errorlevel 1 (
  echo   [!time:~0,8!] can't reach GitHub. Trying again in 2 minutes.
  goto watchloop
)
for /f %%i in ('git rev-parse HEAD') do set LOCALH=%%i
for /f %%i in ('git rev-parse origin/main') do set REMOTEH=%%i
if "!LOCALH!"=="!REMOTEH!" (
  echo   [!time:~0,8!] up to date
  goto watchloop
)
echo   [!time:~0,8!] something changed - pulling it down...
git pull --ff-only origin main
if errorlevel 1 (
  echo   The pull wouldn't go through cleanly. Stopping rather than
  echo   guessing. Do 9 and say Y to the join question.
  goto back
)
echo   Done. Chrome picks it up within about half a minute.
goto watchloop

:watchdirty
echo.
echo   You've got changes on this PC that aren't on GitHub. Not
echo   pulling over the top of them. Do 9 first.
goto back

:dirty
echo   You've got changes on this PC that aren't on GitHub yet, and
echo   pulling would go over the top of them. Do 9 first, then come
echo   back to 10.
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
