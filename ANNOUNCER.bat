@echo off
rem ============================================================
rem  FILL ANNOUNCER - posts every real Webull fill (margin +
rem  futures), milestones, stop-outs, and the scoreboard to
rem  Discord. Read-only - never places or cancels anything.
rem
rem  Double-click ONCE. It then:
rem    1. starts the announcer hidden (no window - output goes
rem       to announcer.log)
rem    2. installs a Startup entry so it comes back at every logon
rem    3. installs a 30-min revive task in case it ever dies
rem  To turn it off: STOP ANNOUNCER.bat. To restart: this file.
rem ============================================================
cd /d "%~dp0"
title FILL ANNOUNCER
del /q "announcer.stop" >nul 2>&1

rem --- 2. Startup folder entry (runs at every logon, no admin needed)
set "SU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\fill-announcer.vbs"
rem  60s head start: at logon the Desktop folder (OneDrive / disk) isn't
rem  always ready yet - firing instantly threw "Can not find script file"
rem  (9/2). START HERE launches it too, so this is just the safety net.
> "%SU%" echo WScript.Sleep 60000
>> "%SU%" echo If CreateObject("Scripting.FileSystemObject").FileExists("%~dp0_announcer_hidden.vbs") Then CreateObject("WScript.Shell").Run "wscript.exe ""%~dp0_announcer_hidden.vbs""", 0, False

rem --- 3. revive task: every 30 min, the heartbeat makes extras stand down
schtasks /query /tn "Fill Announcer revive" >nul 2>&1
if errorlevel 1 (
  schtasks /create /tn "Fill Announcer revive" /sc minute /mo 30 /tr "wscript.exe \"%~dp0_announcer_hidden.vbs\"" /f >nul 2>&1
)

rem --- 1. start it now, hidden
wscript.exe "%~dp0_announcer_hidden.vbs"

echo.
echo  Fill Announcer is running in the BACKGROUND (no window).
echo  It auto-starts at logon and revives itself if it dies.
echo  Watch it live: announcer.log   Off switch: STOP ANNOUNCER.bat
echo.
timeout /t 6 >nul
