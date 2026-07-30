@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title DISCORD SNIPER

rem ===========================================================
rem  Double-click it and walk away. No menu, no numbers.
rem
rem  Every run does the whole morning by itself:
rem    - installs anything missing (first run only)
rem    - quietly pulls the latest build from GitHub
rem    - sets the 9:25 weekday alarm if it isn't set
rem    - starts the bridge, hidden
rem    - opens your signal channel in Chrome
rem
rem  Webull keys don't live here any more - they go in through the
rem  extension popup: puzzle-piece icon -> Discord Sniper ->
rem  Settings -> the two key boxes. Everything else that used to be
rem  a number on a menu lives in "EXTRAS.bat", for the rare day
rem  something needs poking.
rem
rem  The 9:25 alarm runs this same file with a word after it:
rem      "START HERE.bat" morning
rem ===========================================================

set "SERVER_ID=525113944239767562"
set "CHANNEL_ID=829754942817828884"
set "DISCORD_URL=https://discord.com/channels/%SERVER_ID%/%CHANNEL_ID%"

rem  The two extra rooms. These open in their own tabs and get RECORDED
rem  only - the extension is hard-wired to never trade off them until
rem  their wording has been learned. Capture a few days, Export chat,
rem  and the parser gets tuned on their real sentences.
set "ARISTOTLE_URL=https://discord.com/channels/%SERVER_ID%/987515353670221834"
set "MIDAS_URL=https://discord.com/channels/%SERVER_ID%/1144369893760831489"

set INTERACTIVE=1
if /i "%~1"=="morning" set INTERACTIVE=0

echo.
echo   ============================================================
echo                    D I S C O R D   S N I P E R
echo   ============================================================
echo.
echo   Starting everything. Nothing for you to press.
echo.

rem ---- [1/5] Python --------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
  echo   [1/5] Python isn't installed, or Windows can't find it.
  echo         Nothing can run without it. Get it from
  echo         python.org/downloads and tick "Add Python to PATH"
  echo         on the very first screen - that tickbox is the whole
  echo         thing. Then double-click this file again.
  goto finish
)
echo   [1/5] Python is here.

rem ---- first run: install what's missing, make settings.json ---
python -c "import webull" >nul 2>&1
if errorlevel 1 (
  echo         First run on this PC - installing what it needs.
  echo         One or two minutes, only ever happens once...
  python -m pip install --quiet --upgrade pip >nul 2>&1
  python -m pip install --quiet -r requirements.txt
  python -m pip install --quiet --upgrade webull-openapi-python-sdk
)
if not exist settings.json (
  copy settings.example.json settings.json >nul 2>&1
)

rem ---- [2/5] the latest build, all by itself -------------------
rem  This folder MIRRORS GitHub now - no more zips, no menu picks.
rem  Every morning it makes itself exactly match what's up there,
rem  which also clears any residue from the old unzip-over-the-top
rem  days. Keys, day records and logs live outside git - untouched.
rem  No internet? Fine - today runs on what's already here.
set "UPDATED=0"
where git >nul 2>&1
if errorlevel 1 goto pastpull
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 goto pastpull
set "OLDREV="
for /f %%r in ('git rev-parse HEAD 2^>nul') do set "OLDREV=%%r"
git fetch origin main >nul 2>&1
if errorlevel 1 goto pastpull
git reset --hard origin/main >nul 2>&1
set "NEWREV="
for /f %%r in ('git rev-parse HEAD 2^>nul') do set "NEWREV=%%r"
if not "!OLDREV!"=="!NEWREV!" set "UPDATED=1"
rem  Leftovers from before-git days and retired versions - gone
rem  quietly if any are still lying around. Nothing current is
rem  named any of these.
for %%f in (BRIDGE.bat KEYS.bat RUN.bat SETUP.bat TEST.bat execute.py listener.py webull_trade_sdk.log settings_quick.py "* UPDATE.bat" "* PUSH CHANGES.bat" "* FIRST PUSH TO GITHUB.bat" "* SET UP ON THIS PC.bat" "* FIX THE PUSH.bat") do del %%f >nul 2>&1
:pastpull
if "!UPDATED!"=="1" (
  echo   [2/5] A newer build just came down from GitHub.
) else (
  echo   [2/5] Checked GitHub - you're current. ^(Or offline, and
  echo         today runs on what's already here.^)
)

rem ---- [3/5] the 9:25 alarm, set once, no questions ------------
schtasks /query /tn "Discord Sniper morning" >nul 2>&1
if not errorlevel 1 (
  echo   [3/5] The 9:25 weekday alarm is already set.
  goto alarmdone
)
rem  9:25 New York, converted to THIS PC's clock - worked out here
rem  so nobody has to do timezone arithmetic at a prompt.
set "WHEN=09:25"
for /f "usebackq" %%a in (`powershell -NoProfile -Command "$et=[System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time');$d=[datetime]::SpecifyKind((Get-Date -Hour 9 -Minute 25 -Second 0),'Unspecified');[System.TimeZoneInfo]::ConvertTimeToUtc($d,$et).ToLocalTime().ToString('HH:mm')" 2^>nul`) do set "WHEN=%%a"
schtasks /create /f /tn "Discord Sniper morning" /tr "\"%~f0\" morning" /sc weekly /d MON,TUE,WED,THU,FRI /st !WHEN! >nul 2>&1
if errorlevel 1 (
  echo   [3/5] Windows wouldn't set the 9:25 alarm without permission.
  echo         Not a problem - double-clicking this file does the same
  echo         job. To set it: right-click this file, "Run as
  echo         administrator", once.
) else (
  echo   [3/5] Set the alarm: weekdays at !WHEN! on this PC's clock,
  echo         which is 9:25 in New York. It starts all of this by
  echo         itself - a sleeping PC runs no alarms, though.
)
:alarmdone

rem ---- [4/5] the bridge, hidden --------------------------------
set RUNNING=0
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set RUNNING=1

set "NEEDSTART=0"
if "!RUNNING!"=="0" set "NEEDSTART=1"
if "!RUNNING!"=="1" if "!UPDATED!"=="1" (
  echo   [4/5] New build - moving the bridge onto it...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*bridge.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  set "NEEDSTART=1"
)
if "!NEEDSTART!"=="0" (
  echo   [4/5] The bridge is already running. Leaving it alone.
) else (
  echo   [4/5] Starting the bridge, hidden...
  wscript.exe "%~dp0_run_hidden.vbs"
  set OK=0
  for /l %%i in (1,1,10) do (
    if "!OK!"=="0" (
      timeout /t 1 /nobreak >nul
      powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
      if not errorlevel 1 set OK=1
    )
  )
  if "!OK!"=="1" (
    echo         Up and answering.
  ) else (
    echo         The bridge did NOT come up, so nothing can trade.
    echo         EXTRAS.bat, "show me the bridge log", says why.
  )
)

rem ---- [5/5] Chrome, all three rooms ---------------------------
echo   [5/5] Opening your three rooms in Chrome - main trades,
echo         Aristotle's and Midas are recorded only...
set "CHROME="
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if defined CHROME (
  start "" "!CHROME!" "!DISCORD_URL!" "!ARISTOTLE_URL!" "!MIDAS_URL!"
) else (
  start "" "!DISCORD_URL!"
  start "" "!ARISTOTLE_URL!"
  start "" "!MIDAS_URL!"
  echo         Couldn't find Chrome in the usual folders - opened your
  echo         default browser. The extension only runs in Chrome.
)

rem ---- anything left for a human? ------------------------------
set HASKEYS=1
powershell -NoProfile -Command "try { if ((Invoke-RestMethod -Uri 'http://127.0.0.1:8787/mode' -TimeoutSec 3).has_keys) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 set HASKEYS=0

echo.
echo   ============================================================
if "!HASKEYS!"=="0" (
  echo     One thing only you can do: your Webull keys aren't in
  echo     yet. In Chrome: puzzle-piece icon, Discord Sniper,
  echo     Settings, paste the App Key and App Secret, hit save.
  echo     They stay on this PC. Until then it reads and pretends
  echo     but can't touch Webull.
  echo   ============================================================
  echo.
)
echo     Ready. It's ON and reading, 24/7 - the market-hours
echo     guard does the timekeeping. The one switch that's yours:
echo       - TEST or REAL                             ^(bottom button^)
echo     It stays in TEST until YOU flip it. TEST buys nothing.
echo     OFF up top is the emergency brake.
echo.
echo     This window closes itself. You're done here.
echo   ============================================================

:finish
if "%INTERACTIVE%"=="0" (
  timeout /t 12 >nul
) else (
  timeout /t 30 >nul
)
exit /b 0
