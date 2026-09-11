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
rem
rem  9/9 (G: "delete old stale batch files"): six options went -
rem  the retired parser tuner, the drill (drill.py is gone), send/
rem  get GitHub (AUTO PUSH commits every 45s and START HERE mirrors
rem  on every run), the 9:25 alarm switch (alarm retired 8/10, START
rem  HERE removes it if it ever reappears) and the sandbox-key entry
rem  (sandbox retired 8/29 - paper is local, keys go in the popup).
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
echo      3   Check the keys work  ^(places no orders^)
echo      4   What did the reader miss today  ^(replay_check.py^)
echo.
echo      0   Close this
echo.
set "PICK="
set /p PICK="   Number: "

if "!PICK!"=="1"  goto stopbridge
if "!PICK!"=="2"  goto showlog
if "!PICK!"=="3"  goto checkkeys
if "!PICK!"=="4"  goto misses
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

> "%~dp0STOP" echo stopped from EXTRAS on %date% %time%

powershell -NoProfile -Command ^
  "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*bridge.py*' };" ^
  "if (-not $p) { Write-Host '  It wasn''t running. The STOP brake is now set.'; exit 0 };" ^
  "$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force };" ^
  "Write-Host ('  Stopped ' + @($p).Count + ' bridge process(es).')"

echo.
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; Write-Host '  Something is STILL answering on port 8787. Restart the PC if it will not go.' } catch { Write-Host '  Confirmed: nothing is listening. The STOP brake keeps it down.' }"
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
rem  4 - what did the reader miss today
rem ============================================================
:misses
cls
echo.
echo   Nothing here can place a trade. This replays today's captured
echo   room messages through the same reader that trades and lists
echo   every alert it did NOT act on, with the reason. Read-only.
echo.
call :needpython || goto back
python replay_check.py
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

:back
echo.
pause
goto menu
