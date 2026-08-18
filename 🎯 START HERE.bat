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
rem    - removes the old 9:25 weekday alarm if Windows still has it
rem    - starts the bridge, hidden
rem    - opens your signal channel in Chrome
rem
rem  Webull keys don't live here any more - they go in through the
rem  extension popup: puzzle-piece icon -> Discord Sniper ->
rem  Settings -> the two key boxes. Everything else that used to be
rem  a number on a menu lives in "EXTRAS.bat", for the rare day
rem  something needs poking.
rem
rem  The 9:25 alarm is GONE (his call, 8/10) - mornings are his.
rem  Re-running this file never touches tabs that are already open.
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
set "ZT4=https://discord.com/channels/%ZT_SERVER%/1174393224253681674"
set "ZT5=https://discord.com/channels/%ZT_SERVER%/748266924122570882"
set "ZT8=https://discord.com/channels/%ZT_SERVER%/1471700027662405712"
set "ZT9=https://discord.com/channels/%ZT_SERVER%/499045647580921887"
set "ZT10=https://discord.com/channels/%ZT_SERVER%/1135947475912495216"
rem  Summit / $STS alert channels (option, spread, lotto, stock, futures,
rem  member, trade-log, RWGates, watchlist). SUMMIT_SERVER is the server id
rem  from the address bar - paste it once and all nine tabs open themselves.
set "SUMMIT_SERVER=588137369409159208"
rem  Trading The Trend - proven by his own URL 8/11: option-alerts lives at
rem  discord.com/channels/769790224921395200/769797179992571914. The whole
rem  alert family (created the same day the server was) opens from here;
rem  RWGates is older than this server and stays on SUMMIT above.
set "TTT_SERVER=769790224921395200"
rem  Vero rooms + Options Insider - same deal, one server id each.
set "VERO_SERVER=725117609275555851"
set "INSIDER_SERVER=719580371997556737"
rem  Platinum Trading - his URL 8/11.
set "PLATINUM_SERVER=911385966864896081"

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

rem ---- [3/5] the 9:25 alarm - REMOVED, his call (8/10) ---------
rem  It used to run this whole file at 9:25 every weekday, which
rem  closed ALL of Chrome and reopened every room - every tab
rem  "refreshed" out from under him. He runs his own mornings now.
rem  This step only CLEANS UP: if the old alarm is still in
rem  Windows, delete it. It is never created again.
schtasks /query /tn "Discord Sniper morning" >nul 2>&1
if not errorlevel 1 (
  schtasks /delete /tn "Discord Sniper morning" /f >nul 2>&1
  if errorlevel 1 (
    echo   [3/5] The old 9:25 alarm is still set and Windows wouldn't
    echo         drop it without permission. Right-click this file,
    echo         "Run as administrator", once - or EXTRAS option 8.
  ) else (
    echo   [3/5] Removed the old 9:25 alarm. Mornings are yours now.
  )
) else (
  echo   [3/5] No 9:25 alarm - as it should be.
)

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
rem  His call (8/10): NEVER touch tabs that are already open. This
rem  used to close ALL of Chrome and reopen every room on every run
rem  - so restarting the bridge "refreshed" every single tab. Now:
rem  Chrome already running -> leave it completely alone (the
rem  extension's dupe-closer still tidies any room opened twice).
rem  Only a cold start - no Chrome at all - opens the rooms fresh.
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 (
  echo   [5/5] Chrome is already open - leaving every tab exactly as
  echo         it is. Open any missing rooms yourself.
  goto chromedone
)
echo   [5/5] Chrome isn't running - opening all the rooms fresh...
set "CHROME="
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
rem  Every room now comes from ONE file - extension\rooms.txt (his ask,
rem  8/17). That file is also what background.js reads its trading list
rem  from, so a room deleted from rooms.txt stops opening AND stops
rem  trading in the same edit - nothing here to keep in sync by hand any
rem  more. Format per line: channel_id|url|label|group - this loop only
rem  needs the url (2nd field).
if defined CHROME (
  rem  The flags do two jobs. The first three stop Chrome throttling background
  rem  tabs - a room you're not looking at still gets read the instant a
  rem  message lands. --process-per-site is the big RAM saver: all the discord
  rem  tabs (same site) share ONE renderer process instead of one each, and the
  rem  Whop tabs share another - it cuts memory hard with this many rooms open.
  rem  --disable-features drops translate, casting and the occlusion check that
  rem  would otherwise pause a window you can't see. These apply to the whole
  rem  Chrome instance because we closed it first above, so this launch is what
  rem  starts it - the later tabs inherit them. The main room opens here by
  rem  itself so SOMETHING starts Chrome with the flags on; it's also in
  rem  rooms.txt and would open a second time in the loop below, but the
  rem  extension's own dupe-closer (oneTabPerChannel) tidies that up within
  rem  30 seconds - harmless.
  start "" "!CHROME!" --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling --process-per-site --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion "!DISCORD_URL!"
  for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
    if not "%%A"=="" start "" "!CHROME!" "%%B"
  )
) else (
  start "" "!DISCORD_URL!"
  for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
    if not "%%A"=="" start "" "%%B"
  )
  echo         Couldn't find Chrome in the usual folders - opened your
  echo         default browser. The extension only runs in Chrome.
)

:chromedone

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
