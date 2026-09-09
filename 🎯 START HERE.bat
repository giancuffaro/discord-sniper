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
rem  Re-running this file CLOSES Chrome and reopens every room (his call 9/2).
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
rem  (8/30: Whop killed /joined/ URLs - rooms are /<biz>/exp_<hash>/app/
rem  now. These vars are legacy - rooms.txt is the real list - but they
rem  stay correct so no future copy-paste resurrects a dead link.)
set "WHOP1=https://whop.com/firststeptrading/exp_cvgzKYDmcUEDGh/app/"
set "WHOP2=https://whop.com/firststeptrading/exp_26GaLgZVMzB2PL/app/"
set "WHOP3=https://whop.com/firststeptrading/exp_hpXJymtw0yMqzB/app/"
set "WHOP4=https://whop.com/firststeptrading/exp_Yg9HGTPsXPhQ5D/app/"
set "WHOP5=https://whop.com/firststeptrading/exp_6Q7acPPpFb6CyZ/app/"
set "WHOP6=https://whop.com/firststeptrading/exp_sMzuBmyHSwKzFW/app/"
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

rem  NO PROMPTS, EVER (9/9, G: "no input from me"). If the saved GitHub
rem  credential has expired, git would pop a sign-in window and this whole
rem  run would sit behind it. With these set, git fails fast instead - and
rem  every git step below already handles failure by keeping local work and
rem  skipping the mirror. Same for the Chrome "Restore pages?" bubble
rem  (--hide-crash-restore-bubble on every launch) and the rooms: the
rem  extension opens whatever is missing on a one-shot request from this
rem  file, so a warm start never needs Chrome closed by hand.
set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=never"
set "GIT_ASKPASS=echo"

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
rem  A stale git lock (a crashed git, or the sandbox's FUSE mount) makes the
rem  save-guard silently FAIL and the reset then eats local work (23:28,
rem  8/23 — the bench and Rafita vanished). Clear it before anything git.
if exist ".git\index.lock" del /f ".git\index.lock" >nul 2>&1
if exist ".git\HEAD.lock" del /f ".git\HEAD.lock" >nul 2>&1
rem  SAVE LOCAL WORK FIRST (8/23): clicking this between auto-pushes used to
rem  hard-reset away anything Claude changed in the last half hour. Now the
rem  folder pushes ITSELF before the mirror step - and if the push fails
rem  (offline), the reset is SKIPPED so nothing local is ever thrown away.
git add -A >nul 2>&1
git commit -m "pre-start save" >nul 2>&1
set "PUSHOK=1"
git push origin main >nul 2>&1
if errorlevel 1 set "PUSHOK=0"
set "OLDREV="
for /f %%r in ('git rev-parse HEAD 2^>nul') do set "OLDREV=%%r"
git fetch origin main >nul 2>&1
if errorlevel 1 goto pastpull
if "!PUSHOK!"=="0" (
  echo         Couldn't push local work - keeping it, skipping the mirror step.
  goto pastpull
)
rem  FINAL CHECK: if ANYTHING is still uncommitted (a failed add, a locked
rem  index, whatever new way git finds), the mirror step is skipped. The
rem  reset only ever runs on a fully saved folder.
git diff-index --quiet HEAD -- >nul 2>&1
if errorlevel 1 (
  echo         Unsaved local changes detected - keeping them, skipping mirror.
  goto pastpull
)
rem  NEVER destroy local-only commits: mirror only when GitHub already has
rem  every local commit (8/30 lesson - a silent push failure + this reset
rem  erased a full day of work; recovered from the reflog, never again).
git merge-base --is-ancestor HEAD origin/main >nul 2>&1
if errorlevel 1 (
  echo         GitHub is MISSING local work - keeping it, skipping mirror.
  goto pastpull
)
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

rem ---- [4.5/5] the Fill Announcer, hidden (his ask, 9/2) --------
rem  Same launcher the Startup entry and the revive task use. Safe to
rem  fire every time: the loop stands down if a heartbeat is fresh
rem  (one announcer, never two), and a NON-EMPTY announcer.stop means
rem  "he turned it off on purpose" - we honour that and skip.
set "ANN_OFF=0"
if exist "announcer.stop" (
  for %%z in ("announcer.stop") do if %%~zz GTR 0 set "ANN_OFF=1"
)
if "!ANN_OFF!"=="1" (
  echo         Fill Announcer is switched OFF ^(STOP ANNOUNCER was used^).
  echo         Run ANNOUNCER.bat to turn it back on.
) else (
  if exist "_announcer_hidden.vbs" (
    wscript.exe "%~dp0_announcer_hidden.vbs"
    echo         Fill Announcer running in the background.
  ) else (
    echo         _announcer_hidden.vbs is missing - announcer not started.
  )
)

rem ---- [5/5] Chrome, all the rooms ----------------------------
rem  His call (8/10): NEVER touch tabs that are already open. This
rem  used to close ALL of Chrome and reopen every room on every run
rem  - so restarting the bridge "refreshed" every single tab. Now:
rem  Chrome already running -> leave it completely alone (the
rem  extension's dupe-closer still tidies any room opened twice).
rem  Only a cold start - no Chrome at all - opens the rooms fresh.
rem  "Is Chrome open?" now means "does Chrome have an actual WINDOW?" (8/18).
rem  On a fresh PC boot Chrome often starts a BACKGROUND process with no
rem  windows at all, which fooled the old tasklist check into opening
rem  nothing ("i was opening after turning on the pc, chrome shouldnt of
rem  been opened"). Visible windows = his tabs, leave them alone. Background
rem  only = kill it quietly and cold-start, so the performance flags apply.
rem  NO INPUT FROM HIM (9/9): whichever way this goes - warm or cold - drop a
rem  one-shot request. The bridge hands the token to the extension on its
rem  30s /build poll; each browser then opens every room from rooms.txt that
rem  it does not have a tab for, in its own lane, a few per tick, and marks
rem  the token done. A tab he closes by hand afterwards STAYS closed - the
rem  extension only opens rooms when this file asks. Warm start used to rely
rem  on an always-on healer that was removed; this is its replacement.
> "open-rooms.request" echo %date%-%time%-%RANDOM%%RANDOM%
powershell -NoProfile -Command "$w = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle }; if ($w) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  rem  HIS CALL 9/8 - "check which are open and open the ones that are
  rem  missing" - REVERSES the 9/2 close-everything rule. Closing Chrome to
  rem  guarantee every room is up was always a sledgehammer: it threw away
  rem  tabs that were reading fine, and this morning it shut the Brando and
  rem  Shoof tabs so a 10:44 QQQ call went unread. The extension now owns
  rem  this - openMissingRooms opens any LIVE room from rooms.txt with no
  rem  tab, oneTabPerChannel closes duplicates - together they converge on
  rem  rooms.txt without touching a tab that is already fine. So when Chrome
  rem  is already open we LEAVE IT ALONE. No kill, no countdown, no flush
  rem  risk to the extension's LevelDB - killing it mid-write is what
  rem  emptied the 9/1 and 9/4 exports. The healer opens the rest in a minute.
  rem  NOTE - keep these rem lines free of round brackets: a close bracket in a
  rem  rem inside this bracketed block ends the block early in cmd. Known trap.
  echo.
  echo   [5/5] Chrome is already open - leaving your Discord tabs as they are.
  echo         The extension opens any missing Discord rooms by itself within
  echo         a minute. Still making sure the Whop browser is up...
  rem  WARM START used to `goto chromedone` here and SKIP the Whop launch
  rem  entirely - that is why running this with Chrome already open opened
  rem  nothing for the second browser (9/8). Now it jumps to the Whop launch
  rem  instead, so the second profile comes up whether or not Chrome was
  rem  already running. The Discord side is left untouched.
  goto launch_whop
)
echo   [5/5] Chrome isn't running - cold start, opening all the rooms...
rem  Dedicated Discord profile (8/23): chrome-profile.txt holds the
rem  profile-directory name (chrome://version -> Profile Path, last part).
set "SNIPER_PROFILE=Default"
if exist "chrome-profile.txt" set /p SNIPER_PROFILE=<"chrome-profile.txt"
echo         (using Chrome profile: !SNIPER_PROFILE!)
rem  TWO-BROWSER SPLIT (9/8, his ask): the 4 Whop rooms open in a SEPARATE
rem  Chrome profile so their weight stays off the Discord browser. A separate
rem  --profile-directory is its own renderer set - Whop's memory no longer
rem  drags the Discord tabs, which is what was starving RWGates / Brando.
rem  ONE-TIME SETUP in this profile, done once and it sticks:
rem    1. it opens as a fresh Chrome profile - log into Whop in it,
rem    2. install the Discord Sniper extension in it the same way you did the
rem       main one - puzzle piece, or Load Unpacked on the extension folder.
rem  After that this launcher opens both every time. whop-profile.txt overrides
rem  the name if you want a specific one.
set "WHOP_PROFILE=Sniper Whop"
if exist "whop-profile.txt" set /p WHOP_PROFILE=<"whop-profile.txt"
echo         (Whop rooms use a second profile: !WHOP_PROFILE!)
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
  rem  message lands. (--process-per-site is GONE, 9/1: it packed every Discord
  rem  tab into ONE renderer, Discord web bloats to 0.5-2 GB per tab after
  rem  hours, and that single process hit Chrome's per-process V8 ceiling =
  rem  "Chrome ran out of memory". One renderer per tab costs more total RAM
  rem  but no single process can hit the wall; the extension's 2-hour
  rem  memory-shed reload keeps each tab's bloat in check.) Old note: all the discord
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
  rem  --hide-crash-restore-bubble (9/9): after a PC shutdown, an OOM kill or
  rem  a crash, Chrome greets the next launch with "Restore pages?" and sits
  rem  there until someone clicks. That click was his input. Gone.
  start "" "!CHROME!" --profile-directory="!SNIPER_PROFILE!" --hide-crash-restore-bubble --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion "!DISCORD_URL!"
  rem  Give Chrome itself a moment to be up before the flood.
  timeout /t 6 /nobreak >nul
  rem  THREE AT A TIME (his ask, 8/23): all ~40 rooms at once choked Chrome
  rem  and tabs sat stuck/unloaded. Open 3, breathe 10s so they actually
  rem  load, open the next 3. DISCORD rooms first, WHOP rooms LAST (8/23) -
  rem  by the time the browser is heavy with tabs, the slower Whop pages get
  rem  the tail end where the extra weight hurts least.
  rem  CLOSING THE BROWSER MUST STOP THE TABS - 9/4, his ask: if I close
  rem  the browser, tabs keep opening.. is there a way for them to stop.
  rem  start chrome with a url RELAUNCHES Chrome when it is not running, so
  rem  closing it mid-run did nothing - the loop kept reopening it, one room
  rem  at a time, for another two minutes. Now every room checks Chrome is
  rem  still alive first and the run stands down the moment it isn't.
  set "ABORTED="
  set /a TABN=0
  for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
    if not defined ABORTED (
    tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
    if errorlevel 1 (
      set "ABORTED=1"
      echo.
      echo         Chrome was closed - stopping. !TABN! room^(s^) had opened.
      echo         Nothing else will be reopened. Run this again when ready.
      echo.
    )
    )
    if not defined ABORTED (
    if not "%%A"=="" (
      set "RID=%%A"
      if /i not "!RID:~0,5!"=="whop:" (
        start "" "!CHROME!" --profile-directory="!SNIPER_PROFILE!" "%%B"
        set /a TABN+=1
        set /a TABMOD=TABN %% 3
        if !TABMOD! EQU 0 (
          echo         ...!TABN! rooms open, letting them load...
          timeout /t 10 /nobreak >nul
        )
      )
    )
    )
  )
  if not defined ABORTED echo         Discord rooms open - now the Whop rooms in the second browser...
  rem  Seed the Whop profile once with the perf flags so its Chrome starts with
  rem  background throttling off, same as the Discord one. The rest of the Whop
  rem  rooms open as tabs in this same profile below and inherit the flags.
  rem  First-ever run: this is a blank profile - log into Whop and install the
  rem  extension in it once, then it sticks.
  set "WHOP_SEEDED="
  for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
    if not defined ABORTED (
    if not defined WHOP_SEEDED (
      set "RID=%%A"
      if /i "!RID:~0,5!"=="whop:" (
        start "" "!CHROME!" --profile-directory="!WHOP_PROFILE!" --hide-crash-restore-bubble --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion "%%B"
        set "WHOP_SEEDED=1"
        set /a TABN+=1
        timeout /t 6 /nobreak >nul
      )
    )
    )
  )
  for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
    if not defined ABORTED (
    tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
    if errorlevel 1 (
      set "ABORTED=1"
      echo.
      echo         Chrome was closed - stopping. !TABN! room^(s^) had opened.
      echo.
    )
    )
    if not defined ABORTED (
    if not "%%A"=="" (
      set "RID=%%A"
      if /i "!RID:~0,5!"=="whop:" (
        rem  Whop rooms go to the SECOND profile now, not SNIPER_PROFILE. The
        rem  seed above already opened the first one; the extension's dupe
        rem  closer tidies the one repeat within 30s, same as the Discord main
        rem  room. Every Whop tab lives in its own browser - off the Discord
        rem  one's memory entirely.
        start "" "!CHROME!" --profile-directory="!WHOP_PROFILE!" "%%B"
        set /a TABN+=1
        set /a TABMOD=TABN %% 3
        if !TABMOD! EQU 0 (
          echo         ...!TABN! rooms open, letting them load...
          timeout /t 10 /nobreak >nul
        )
      )
    )
    )
  )
  if defined ABORTED (
    echo         Rooms were NOT all opened - Chrome was closed part-way.
  ) else (
    echo         All !TABN! rooms opened.
  )
  rem  Above-Normal priority for every Chrome process (8/23) - the Task
  rem  Manager bump that never survives a restart, reapplied each morning.
  rem
  rem  RETIRED 9/4 - it was the lag. G: "since then it's been really really
  rem  laggy." 26 room tabs, none of them ever discarded, all at ABOVE-NORMAL
  rem  meant Chrome outranked Windows itself, the bridge and Market Sniper.
  rem  That is a slow MACHINE, not just a slow browser.
  rem
  rem  Reading is untouched by this. What keeps a room alive is the three
  rem  launch flags - renderer-backgrounding, occluded-windows and
  rem  timer-throttling all disabled - plus autoDiscardable=false pinned in
  rem  background.js and the 30s heartbeat. Priority never read a message.
  rem  Set CHROME_PRIORITY=AboveNormal before running to put it back.
  timeout /t 5 /nobreak >nul
  if /i "%CHROME_PRIORITY%"=="AboveNormal" (
    powershell -NoProfile -Command "Get-Process chrome -ErrorAction SilentlyContinue | ForEach-Object { $_.PriorityClass = 'AboveNormal' }" >nul 2>&1
    echo         Chrome bumped to Above-Normal priority ^(CHROME_PRIORITY set^).
  ) else (
    echo         Chrome left at Normal priority - rooms stay live via the
    echo         launch flags and the heartbeat, not the priority bump.
  )
) else (
  start "" "!DISCORD_URL!"
  for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
    if not "%%A"=="" start "" "%%B"
  )
  echo         Couldn't find Chrome in the usual folders - opened your
  echo         default browser. The extension only runs in Chrome.
)
goto chromedone

rem ==== THE WHOP BROWSER (its own profile) =====================
rem  Reached on a WARM start - Chrome was already open, so the block above
rem  left the Discord tabs alone and jumped straight here. Self-contained: it
rem  sets its own CHROME + WHOP_PROFILE because the warm path skipped where the
rem  cold path sets them. Opens the 4 Whop rooms into the second profile so
rem  Whop's weight stays off the Discord browser. ONE-TIME on the very first
rem  run of this profile: log into Whop and install the Discord Sniper
rem  extension in it - a script cannot do either. After that it just works.
:launch_whop
set "WHOP_PROFILE=Sniper Whop"
if exist "whop-profile.txt" set /p WHOP_PROFILE=<"whop-profile.txt"
set "CHROME="
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME (
  echo         Couldn't find Chrome - can't open the Whop browser.
  goto chromedone
)
echo         Opening the Whop rooms in the second profile: !WHOP_PROFILE!
set "WHOP_SEEDED="
for /f "usebackq eol=# tokens=1,2 delims=|" %%A in ("extension\rooms.txt") do (
  set "RID=%%A"
  if /i "!RID:~0,5!"=="whop:" (
    if not defined WHOP_SEEDED (
      start "" "!CHROME!" --profile-directory="!WHOP_PROFILE!" --hide-crash-restore-bubble --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-background-timer-throttling --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion "%%B"
      set "WHOP_SEEDED=1"
      timeout /t 6 /nobreak >nul
    ) else (
      start "" "!CHROME!" --profile-directory="!WHOP_PROFILE!" "%%B"
      timeout /t 2 /nobreak >nul
    )
  )
)
if not defined WHOP_SEEDED echo         No live Whop rooms in rooms.txt - nothing to open.
if defined WHOP_SEEDED echo         Whop browser up. First run only: log into Whop + install the extension in it.
goto chromedone

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
