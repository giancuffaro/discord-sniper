@echo off
setlocal enabledelayedexpansion
rem ===========================================================
rem  _whop_loop.bat - keeps the Sniper Whop browser alive.
rem
rem  The 4 Whop rooms (Day Trades, Futures, High Risk, 2K Challenge)
rem  live in their own Chrome profile ("Sniper Whop") so their weight
rem  stays off the Discord browser (9/8 split). Nothing used to notice
rem  if that whole profile's Chrome window closed, crashed, or never
rem  started - Day Trades caught exactly 1 alert in the month since
rem  8/13 because of it (found 9/10 checking a live NQ short call that
rem  never reached trades.log).
rem
rem  VERSION 2 (9/10, same afternoon): v1 guessed whether Chrome was
rem  running by matching --profile-directory in the process list -
rem  Chrome's shared-process/single-instance behavior made that
rem  unreliable and it was caught relaunching Chrome every ~60-70s in
rem  whop-loop.log. Now it asks the bridge instead: background.js's
rem  whopSelfHeal() pings POST /whopalive every watch-build tick
rem  (~30s) ONLY when it's actually running in the whop lane, and this
rem  loop reads GET /whopalive's ago_sec - a fact, not a guess. Two
rem  safety nets on top so a bad read can never spam again: a launch
rem  is never attempted twice within 5 minutes (marker file), and the
rem  STOP file stops the loop entirely, same as everything else.
rem
rem  Never touches the Discord profile, its tabs, or the "a tab he
rem  closes by hand stays closed" rule (9/8) - that's untouched. He
rem  doesn't hand-manage the Whop profile day to day, which is exactly
rem  why nobody noticed it going dark for a month.
rem
rem  Launched hidden by _whop_hidden.vbs; not for double-clicking.
rem ===========================================================
cd /d "%~dp0"

:loop
if exist "%~dp0STOP" goto done
if exist "%~dp0STOP.txt" goto done

rem  RATE LIMIT (the safety net): never even consider launching Chrome
rem  again within 5 minutes of the last attempt, no matter what the
rem  alive-check below says. A marker file's own age is the timer -
rem  cheap, survives this script restarting, needs no math.
set "MARKER=%~dp0whop-loop-last-launch.marker"
set "MARKER_AGE="
if exist "%MARKER%" (
  for /f %%A in ('powershell -NoProfile -Command "try { [int](New-TimeSpan -Start (Get-Item '%MARKER%').LastWriteTime -End (Get-Date)).TotalSeconds } catch { '' }" 2^>nul') do set "MARKER_AGE=%%A"
)
if defined MARKER_AGE if not "!MARKER_AGE!"=="" if !MARKER_AGE! LSS 300 (
  timeout /t 60 /nobreak >nul
  goto loop
)

rem  Ask the bridge how long since the whop lane last checked in. Any
rem  failure (bridge down, endpoint missing on an older build, bad
rem  JSON) is treated as "can't confirm it's alive" - same branch as a
rem  stale heartbeat, not a crash.
set "AGO="
for /f %%A in ('powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/whopalive' -TimeoutSec 5; if ($null -eq $r.ago_sec) { '' } else { [int]$r.ago_sec } } catch { '' }" 2^>nul') do set "AGO=%%A"

rem  Alive if the bridge answered a number under 180s (~6 missed ticks
rem  of the ~30s watch-build alarm - generous margin, no flapping).
set "ALIVE=0"
if defined AGO if not "!AGO!"=="" if !AGO! LSS 180 set "ALIVE=1"

if "!ALIVE!"=="1" (
  timeout /t 60 /nobreak >nul
  goto loop
)

set "CHROME="
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME (
  echo [%date% %time%] Chrome not found - can't start the Whop profile >> "%~dp0whop-loop.log"
  timeout /t 60 /nobreak >nul
  goto loop
)

set "WHOP_PROFILE=Sniper Whop"
if exist "whop-profile.txt" set /p WHOP_PROFILE=<"whop-profile.txt"

echo [%date% %time%] whop lane heartbeat is !AGO!s old (or missing) - starting Sniper Whop Chrome, next attempt no sooner than 5 min from now >> "%~dp0whop-loop.log"
> "%MARKER%" echo %date% %time%
start "" "%CHROME%" --profile-directory="%WHOP_PROFILE%" --hide-crash-restore-bubble --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion
rem  Give Chrome a moment to actually come up, then ask the extension to
rem  fill in any rooms missing a tab (belt-and-suspenders - the whop lane
rem  self-heals on its own every watch-build tick regardless of this token).
timeout /t 8 /nobreak >nul
> "%~dp0open-rooms.request" echo %date%-%time%-%RANDOM%%RANDOM%

timeout /t 60 /nobreak >nul
goto loop

:done
echo [%date% %time%] STOP file present - whop loop parked >> "%~dp0whop-loop.log"
exit /b 0
