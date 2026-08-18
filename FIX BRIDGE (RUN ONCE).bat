@echo off
cd /d "%~dp0"
title FIX BRIDGE - kill the old Drive loop, start the Desktop one
echo ================================================================
echo   One-time fix (8/17): the OLD keep-alive loop from the Google
echo   Drive folder was still alive and kept resurrecting the OLD
echo   bridge - which is why popup saves seemed to vanish and new
echo   code never loaded. This kills every loop and bridge, then
echo   starts the bridge fresh from THIS folder (Desktop).
echo ================================================================
echo.
echo   [1/3] Stopping every keep-alive loop, old and new...
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*_bridge_loop*' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host ('        stopped ' + @($p).Count + ' loop(s)') } else { Write-Host '        no loop was running' }"
echo   [2/3] Stopping every bridge process...
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*bridge.py*' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host ('        stopped ' + @($p).Count + ' bridge process(es)') } else { Write-Host '        no bridge was running' }"
timeout /t 2 /nobreak >nul
echo   [3/3] Starting the bridge fresh from THIS folder, hidden...
wscript.exe "%~dp0_run_hidden.vbs"
set /a tries=0
:wait
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8787/build' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto ok
set /a tries+=1
if %tries% lss 15 (
  echo   ...still coming up ^(%tries%^)
  goto wait
)
echo   Still not answering - tell Claude, something else is wrong.
goto end
:ok
echo.
echo   Bridge is UP - and this time it is the DESKTOP one, on
echo   tonight's code and tonight's settings. You can delete this
echo   .bat file after today; RESTART BRIDGE works normally now
echo   that the old loop is dead.
:end
echo.
pause
