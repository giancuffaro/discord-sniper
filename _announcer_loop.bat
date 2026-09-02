@echo off
rem ============================================================
rem  ANNOUNCER keep-alive loop (not meant to be double-clicked -
rem  ANNOUNCER.bat / _announcer_hidden.vbs run it for you).
rem  If the announcer ever crashes it comes back in 10 seconds.
rem  Honours a NON-EMPTY announcer.stop (an empty one is inert - the
rem  sandbox can truncate but not delete); heartbeat = single instance.
rem ============================================================
cd /d "%~dp0"

rem single instance: a fresh heartbeat means an announcer is
rem already alive somewhere; this copy stands down.
powershell -nop -c "$f='.announcer.alive'; if(Test-Path $f){$a=(Get-Date)-(Get-Item $f).LastWriteTime; if($a.TotalSeconds -lt 120){exit 1}}; exit 0" >nul 2>&1
if errorlevel 1 exit /b 0

:loop
for %%z in ("announcer.stop") do if %%~zz GTR 0 exit /b 0
python -u announcer.py >> announcer.log 2>&1
for %%z in ("announcer.stop") do if %%~zz GTR 0 exit /b 0
timeout /t 10 /nobreak >nul
goto loop
