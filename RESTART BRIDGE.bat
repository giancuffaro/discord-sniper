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
