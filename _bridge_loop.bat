@echo off
rem ===========================================================
rem  _bridge_loop.bat - keeps the bridge alive.
rem
rem  Runs bridge.py and, if it ever exits (a crash, a killed
rem  process), brings it right back a couple seconds later - so a
rem  bridge that dies mid-session heals itself instead of leaving
rem  every call failing "couldn't reach the bridge" until someone
rem  notices. Launched hidden by _run_hidden.vbs; not for double-
rem  clicking.
rem
rem  Two safeties:
rem   - The STOP file (the emergency brake) stops the loop for good,
rem     same file the bot already honours. Delete it to run again.
rem   - The port is the lock: if the bridge is already answering on
rem     8787 (another copy, or a self-update re-exec in flight) this
rem     waits instead of starting a second one, and a stray second
rem     python would fail to bind and fall back to waiting anyway.
rem ===========================================================
cd /d "%~dp0"

:loop
if exist "%~dp0STOP" goto done
if exist "%~dp0STOP.txt" goto done

rem Already answering? Then something else is running it - just watch.
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  timeout /t 5 /nobreak >nul
  goto loop
)

rem Not answering - start it. This BLOCKS until the bridge exits.
echo [%date% %time%] starting bridge >> "%~dp0bridge.log"
python "%~dp0bridge.py" >> "%~dp0bridge.log" 2>&1

rem It exited. If the user pulled the STOP brake, stay down; otherwise
rem pause a beat (so a crash-loop can't spin) and bring it back.
if exist "%~dp0STOP" goto done
if exist "%~dp0STOP.txt" goto done
echo [%date% %time%] bridge exited - auto-restarting in 3s >> "%~dp0bridge.log"
timeout /t 3 /nobreak >nul
goto loop

:done
echo [%date% %time%] STOP file present - bridge loop parked >> "%~dp0bridge.log"
exit /b 0
