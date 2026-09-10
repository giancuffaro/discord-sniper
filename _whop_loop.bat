@echo off
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
rem  This loop checks every 60s whether a Chrome window is running
rem  under that profile. If not, it starts one - blank tab is enough,
rem  background.js's whopSelfHeal (added 9/10, whop lane only) opens
rem  the actual room tabs itself from rooms.txt the moment the
rem  extension loads, no request token needed for that lane.
rem
rem  Two safeties, same as the bridge loop:
rem   - The STOP file (the emergency brake) stops this loop too.
rem   - Never touches the Discord profile, its tabs, or the "a tab he
rem     closes by hand stays closed" rule (9/8) - that's untouched.
rem     He doesn't hand-manage the Whop profile day to day, which is
rem     exactly why nobody noticed it going dark for a month.
rem
rem  Launched hidden by _whop_hidden.vbs; not for double-clicking.
rem ===========================================================
cd /d "%~dp0"

:loop
if exist "%~dp0STOP" goto done
if exist "%~dp0STOP.txt" goto done

set "WHOP_PROFILE=Sniper Whop"
if exist "whop-profile.txt" set /p WHOP_PROFILE=<"whop-profile.txt"

rem  Already running? Just watch. Match on the profile-directory flag in
rem  the process command line - the only reliable way to tell Chrome
rem  windows/profiles apart from outside.
powershell -NoProfile -Command "$p = '--profile-directory=\"' + $env:WHOP_PROFILE + '\"'; $w = Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($p) }; if ($w) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
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

echo [%date% %time%] Sniper Whop Chrome isn't running - starting it >> "%~dp0whop-loop.log"
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
