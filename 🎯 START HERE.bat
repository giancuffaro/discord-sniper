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

rem  The extra rooms. Each opens in its own tab and trades in TEST
rem  like the main room - pretend money for everyone until HE flips
rem  REAL in the popup. Their wording keeps getting tuned from the
rem  Export chat captures.
set "ARISTOTLE_URL=https://discord.com/channels/%SERVER_ID%/987515353670221834"
set "MIDAS_URL=https://discord.com/channels/%SERVER_ID%/1144369893760831489"
rem  Aristotle again, but his small-account challenge room.
set "ARISTOTLE_SMALL_URL=https://discord.com/channels/%SERVER_ID%/1433933203302776852"
rem  Felony's Whop rooms - the reader only sees what's open in a tab.
set "WHOP1=https://whop.com/joined/firststeptrading/day-trades-cvgzKYDmcUEDGh/app/"
set "WHOP2=https://whop.com/joined/firststeptrading/futures-26GaLgZVMzB2PL/app/"
set "WHOP3=https://whop.com/joined/firststeptrading/high-risk-hpXJymtw0yMqzB/app/"
set "WHOP4=https://whop.com/joined/firststeptrading/fst-2-k-challenge-Yg9HGTPsXPhQ5D/app/"
set "WHOP5=https://whop.com/joined/firststeptrading/swing-trades-6Q7acPPpFb6CyZ/app/"
set "WHOP6=https://whop.com/joined/firststeptrading/long-term-sMzuBmyHSwKzFW/app/"
rem  z trades (ZTRADEZ) - the free-trial week. Different Discord server.
set "ZT_SERVER=496871546963492874"
set "ZT1=https://discord.com/channels/%ZT_SERVER%/829352738239414332"
set "ZT2=https://discord.com/channels/%ZT_SERVER%/721821717328298066"
set "ZT3=https://discord.com/channels/%ZT_SERVER%/1504469469844738158"
set "ZT4=https://discord.com/channels/%ZT_SERVER%/1174393224253681674"
set "ZT5=https://discord.com/channels/%ZT_SERVER%/748266924122570882"
set "ZT6=https://discord.com/channels/%ZT_SERVER%/1343408561803362374"
set "ZT7=https://discord.com/channels/%ZT_SERVER%/1151897689185861632"

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
if not errorlevel 1 goto haverepo
rem  An unzipped or copied folder has no .git - his laptop's did not. Wire
rem  it up right here instead of printing instructions at him. Windows may
rem  pop a GitHub sign-in once; keys/days/logs are untracked and untouched.
echo         This folder isn't wired to GitHub yet - wiring it now...
git init >nul 2>&1
git remote remove origin >nul 2>&1
git remote add origin https://github.com/giancuffaro/discord-sniper.git >nul 2>&1
git fetch origin main
if errorlevel 1 (
  echo         Couldn't reach GitHub to wire it - running what's here.
  goto pastpull
)
git checkout -B main >nul 2>&1
:haverepo
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

rem ---- [5/5] Chrome, all the rooms ----------------------------
echo   [5/5] Closing any open Chrome first, so re-running this ^(or the
echo         9:25 alarm^) doesn't stack a SECOND copy of every room on
echo         top of the ones already open. Then reopening them fresh...
rem  Graceful close (no /F) so Chrome saves its session and never shows
rem  the "restore pages?" bar. A short wait lets it actually finish before
rem  we reopen, otherwise the new window lands before the old ones are gone.
taskkill /IM chrome.exe >nul 2>&1
timeout /t 3 /nobreak >nul
rem  If anything stubbornly hung on, one firm nudge - by now the session is
rem  already saved from the graceful try above.
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 (
  taskkill /F /IM chrome.exe >nul 2>&1
  timeout /t 1 /nobreak >nul
)
set "CHROME="
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if defined CHROME (
  rem  The flags stop Chrome throttling background tabs - a room you're
  rem  not looking at still gets read the instant a message lands.
  start "" "!CHROME!" --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling "!DISCORD_URL!" "!ARISTOTLE_URL!" "!MIDAS_URL!" "!ARISTOTLE_SMALL_URL!" "!WHOP1!" "!WHOP2!" "!WHOP3!" "!WHOP4!" "!WHOP5!" "!WHOP6!" "!ZT1!" "!ZT2!" "!ZT3!" "!ZT4!" "!ZT5!" "!ZT6!" "!ZT7!"
  rem  z trades batch two opens as its own window - 25 more rooms
  start "" "!CHROME!" "https://discord.com/channels/496871546963492874/1356793611420958732" "https://discord.com/channels/496871546963492874/1248264554886991893" "https://discord.com/channels/496871546963492874/1470409110288601282" "https://discord.com/channels/496871546963492874/694197721430491266" "https://discord.com/channels/496871546963492874/777750637613416479" "https://discord.com/channels/496871546963492874/1331631786068938813" "https://discord.com/channels/496871546963492874/1239624229583061052" "https://discord.com/channels/496871546963492874/1209181195406024744" "https://discord.com/channels/496871546963492874/1332090335005900800" "https://discord.com/channels/496871546963492874/874280313038192670" "https://discord.com/channels/496871546963492874/1389300087829827745" "https://discord.com/channels/496871546963492874/862419656382873650" "https://discord.com/channels/496871546963492874/1061980561293443152" "https://discord.com/channels/496871546963492874/1179200811650252850" "https://discord.com/channels/496871546963492874/918665915103584327" "https://discord.com/channels/496871546963492874/1255279667489931325" "https://discord.com/channels/496871546963492874/1294812275668160613" "https://discord.com/channels/496871546963492874/1121391020148543631" "https://discord.com/channels/496871546963492874/1239561137914122240" "https://discord.com/channels/496871546963492874/552885275676639243" "https://discord.com/channels/496871546963492874/1525120298075029554" "https://discord.com/channels/496871546963492874/1251181965252755517" "https://discord.com/channels/496871546963492874/1472793065646325904" "https://discord.com/channels/496871546963492874/1213977047479754783" "https://discord.com/channels/496871546963492874/1375454591755489341"
  rem  boka trading opens as its own window
  start "" "!CHROME!" "https://discord.com/channels/1156381060108664884/1288291150083653652" "https://discord.com/channels/1156381060108664884/1499190814482632825" "https://discord.com/channels/1156381060108664884/1395159239164432515" "https://discord.com/channels/1156381060108664884/1387459050505240597"
) else (
  start "" "!DISCORD_URL!"
  start "" "!ARISTOTLE_URL!"
  start "" "!MIDAS_URL!"
  start "" "!ARISTOTLE_SMALL_URL!"
  start "" "!WHOP1!"
  start "" "!WHOP2!"
  start "" "!WHOP3!"
  start "" "!WHOP4!"
  start "" "!WHOP5!"
  start "" "!WHOP6!"
  start "" "!ZT1!"
  start "" "!ZT2!"
  start "" "!ZT3!"
  start "" "!ZT4!"
  start "" "!ZT5!"
  start "" "!ZT6!"
  start "" "!ZT7!"
  rem  boka trading
  start "" "https://discord.com/channels/1156381060108664884/1288291150083653652" "https://discord.com/channels/1156381060108664884/1499190814482632825" "https://discord.com/channels/1156381060108664884/1395159239164432515" "https://discord.com/channels/1156381060108664884/1387459050505240597"
  rem  z trades batch two - one more window's worth
  start "" "https://discord.com/channels/496871546963492874/1356793611420958732" "https://discord.com/channels/496871546963492874/1248264554886991893" "https://discord.com/channels/496871546963492874/1470409110288601282" "https://discord.com/channels/496871546963492874/694197721430491266" "https://discord.com/channels/496871546963492874/777750637613416479" "https://discord.com/channels/496871546963492874/1331631786068938813" "https://discord.com/channels/496871546963492874/1239624229583061052" "https://discord.com/channels/496871546963492874/1209181195406024744" "https://discord.com/channels/496871546963492874/1332090335005900800" "https://discord.com/channels/496871546963492874/874280313038192670" "https://discord.com/channels/496871546963492874/1389300087829827745" "https://discord.com/channels/496871546963492874/862419656382873650" "https://discord.com/channels/496871546963492874/1061980561293443152" "https://discord.com/channels/496871546963492874/1179200811650252850" "https://discord.com/channels/496871546963492874/918665915103584327" "https://discord.com/channels/496871546963492874/1255279667489931325" "https://discord.com/channels/496871546963492874/1294812275668160613" "https://discord.com/channels/496871546963492874/1121391020148543631" "https://discord.com/channels/496871546963492874/1239561137914122240" "https://discord.com/channels/496871546963492874/552885275676639243" "https://discord.com/channels/496871546963492874/1525120298075029554" "https://discord.com/channels/496871546963492874/1251181965252755517" "https://discord.com/channels/496871546963492874/1472793065646325904" "https://discord.com/channels/496871546963492874/1213977047479754783" "https://discord.com/channels/496871546963492874/1375454591755489341"
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
