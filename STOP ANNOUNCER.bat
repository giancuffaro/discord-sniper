@echo off
rem ============================================================
rem  STOP ANNOUNCER - the off switch. Drops announcer.stop; the
rem  announcer sees it within a second and signs off, the keep-
rem  alive loop exits, and the revive task's copies stand down
rem  too (they see the stop file before relaunching).
rem  It will NOT come back until you run ANNOUNCER.bat again -
rem  not even after a reboot (the Startup entry checks too).
rem ============================================================
cd /d "%~dp0"
title STOP ANNOUNCER
echo stop> "announcer.stop"
echo.
echo  Stop signal sent. The announcer signs off within a second.
echo  Run ANNOUNCER.bat whenever you want it back.
echo.
timeout /t 5 >nul
