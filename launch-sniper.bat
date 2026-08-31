@echo off
rem ASCII-named launcher: the desktop shortcut points here, because the
rem shortcut system can't stomach the emoji in "START HERE.bat". This
rem finds it by wildcard and hands over.
cd /d "%~dp0"
rem breadcrumb (8/29, "icon does nothing"): proves a click reached this far
>> "launcher-probe.log" echo launcher hit %date% %time%
for %%f in ("*START HERE.bat") do (
  call "%%~f"
  goto :eof
)
echo START HERE.bat not found next to this launcher.
pause
