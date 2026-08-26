@echo off
cd /d "%~dp0"
title RESTART BRIDGE
echo ================================================
echo   Restarting the bridge onto the latest code...
echo ================================================
echo.
if exist "%~dp0STOP" echo   NOTE: STOP brake is on - remove it or the bridge stays down.
if exist "%~dp0STOP.txt" echo   NOTE: STOP brake is on - remove it or the bridge stays down.
echo.
rem --- PRE-FLIGHT (8/26, his ask): ask the running bridge what a restart
rem --- would interrupt. Held positions are SAFE (stops rest at Webull and
rem --- the book restores). A WORKING bid loses its 90-second puller, and an
rem --- armed pullback hunt dies silently - so those get a real warning and
rem --- a choice before anything is killed.
powershell -NoProfile -Command ^
  "try { $s = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/status' -TimeoutSec 3 } catch { exit 0 };" ^
  "$rc = $s.restart_check; if (-not $rc) { exit 0 };" ^
  "if ($rc.held.Count)   { Write-Host ('  SAFE to restart: holding ' + ($rc.held -join ', ') + ' - stops rest at Webull, the book restores them.') };" ^
  "if ($rc.working.Count -or $rc.armed_pullbacks.Count) {" ^
  "  if ($rc.working.Count) { Write-Host ('  !! RESTING BID in flight: ' + ($rc.working -join ', ') + ' - a restart kills its 90s puller (cancel it in Webull if you proceed).') -ForegroundColor Yellow };" ^
  "  if ($rc.armed_pullbacks.Count) { Write-Host ('  !! PULLBACK HUNT armed: ' + $rc.armed_pullbacks.Count + ' waiting for a touch - a restart drops the hunt (missed entry, not a loss).') -ForegroundColor Yellow };" ^
  "  exit 2 } else { exit 0 }"
if errorlevel 2 (
  echo.
  choice /c YN /m "  Something is mid-flight. Restart anyway"
  if errorlevel 2 (
    echo   Smart. Wait for it to resolve and run this again.
    pause
    exit /b 0
  )
)
echo.
rem --- stop the hidden python bridge process(es); the keep-alive loop revives it ---
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*bridge.py*' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host ('  Stopped ' + @($p).Count + ' bridge process(es). The keep-alive loop is bringing it back...') } else { Write-Host '  Bridge was not running.' }"
echo.
set /a tries=0
:wait
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto ok
set /a tries+=1
if %tries% lss 12 (
  echo   ...still coming up ^(%tries%^)
  goto wait
)
rem --- 36s and still down: no loop was running, so start one hidden ---
echo   No keep-alive loop found - starting the bridge hidden...
wscript.exe "%~dp0_run_hidden.vbs"
timeout /t 8 /nobreak >nul
:ok
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; Write-Host '  Bridge is UP on the new code. AI reader is reading (no more HTTP 404).' } catch { Write-Host '  Still not answering - double-click START HERE instead.' }"
echo.
pause
