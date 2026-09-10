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

rem  NEVER-PINGED IS NOT THE SAME AS DIED (9/10). /whopalive returns
rem  ago_sec=null until the whop lane's extension has pinged even once,
rem  and this script read that empty answer as "dead" and relaunched
rem  Chrome every 5 minutes forever - 13:21, 13:27, 13:32, 13:37, 13:42 -
rem  each time opening a blank tab and writing a new open-rooms token that
rem  made EVERY profile reopen rooms. That is a tab storm, not a heal.
rem  An empty answer means the extension there is old or not installed;
rem  restarting Chrome cannot fix either. Try a few times, then say so
rem  plainly and stop, instead of flapping until someone notices.
set "STRIKES=0"
if exist "%~dp0whop-loop-strikes.txt" set /p STRIKES=<"%~dp0whop-loop-strikes.txt"
if "!ALIVE!"=="1" (
  > "%~dp0whop-loop-strikes.txt" echo 0
) else (
  if not defined AGO set /a STRIKES+=1
  if "!AGO!"=="" set /a STRIKES+=1
  > "%~dp0whop-loop-strikes.txt" echo !STRIKES!
  if !STRIKES! GEQ 4 (
    echo [%date% %time%] GIVING UP: /whopalive has never returned a number after !STRIKES! tries. The Whop profile's extension is old or not installed - reload it there (chrome://extensions) and delete whop-loop-strikes.txt to re-arm. No more relaunches. >> "%~dp0whop-loop.log"
    timeout /t 300 /nobreak >nul
    goto loop
  )
)

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
call :resolve_profile "!WHOP_PROFILE!" WHOP_PROFILE


echo [%date% %time%] whop lane heartbeat is !AGO!s old (or missing) - starting Sniper Whop Chrome, next attempt no sooner than 5 min from now >> "%~dp0whop-loop.log"
> "%MARKER%" echo %date% %time%
rem  SEED IT ON A ROOM, not on nothing (9/10). Launching bare left an empty
rem  new tab behind on every single revive - G saw them piling up. START
rem  HERE seeds with the first ON whop room; do the same here.
set "WHOP_SEED_URL="
for /f "usebackq eol=# tokens=1,2,5 delims=|" %%A in ("%~dp0extension\rooms.txt") do (
  if not defined WHOP_SEED_URL (
    set "RID=%%A"
    set "RST=%%C"
    if /i "!RID:~0,5!"=="whop:" if /i "!RST!"=="on" set "WHOP_SEED_URL=%%B"
  )
)
start "" "%CHROME%" --profile-directory="%WHOP_PROFILE%" --hide-crash-restore-bubble --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion "!WHOP_SEED_URL!"
rem  Give Chrome a moment to actually come up, then ask the extension to
rem  fill in any rooms missing a tab (belt-and-suspenders - the whop lane
rem  self-heals on its own every watch-build tick regardless of this token).
rem  NO TOKEN FROM HERE (9/10). open-rooms.request is GLOBAL - every profile
rem  running the extension acts on it, so a whop revive was making the
rem  DISCORD browser reopen its rooms too, every 5 minutes. The comment
rem  below already said the whop lane self-heals on its own watch-build
rem  tick, which makes the token pure downside. START HERE is the only
rem  thing that writes it now.
timeout /t 8 /nobreak >nul

timeout /t 60 /nobreak >nul
goto loop

:done
echo [%date% %time%] STOP file present - whop loop parked >> "%~dp0whop-loop.log"
exit /b 0

rem  ---- resolve a Chrome profile DISPLAY name to its FOLDER name ----------
rem  9/10: --profile-directory takes the FOLDER ("Profile 3"), never the name
rem  you see in Chrome ("Sniper Whop"). Give it a display name and Chrome
rem  silently falls back to Default — no error, no clue. That is exactly how
rem  the Whop rooms opened in the wrong profile. Chrome's own Local State
rem  file maps folder -> display name, so ask it rather than guess. If the
rem  lookup finds nothing the value is passed through unchanged, so a real
rem  folder name still works and this can only ever help.
:resolve_profile
setlocal enabledelayedexpansion
set "WANT=%~1"
set "FOUND="
for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command ^
  "$p=Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data\Local State';" ^
  "if(Test-Path $p){try{$j=Get-Content $p -Raw ^| ConvertFrom-Json;" ^
  "$m=$j.profile.info_cache.PSObject.Properties ^| Where-Object { $_.Value.name -eq '%~1' } ^| Select-Object -First 1;" ^
  "if($m){$m.Name}}catch{}}" 2^>nul`) do set "FOUND=%%R"
if defined FOUND if not "!FOUND!"=="" (
  endlocal & set "%~2=%FOUND%" & goto :eof
)
endlocal & set "%~2=%~1" & goto :eof

