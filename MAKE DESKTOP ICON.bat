@echo off
rem ============================================================
rem  MAKE DESKTOP ICON - run me ONCE (again after updates; it
rem  just rewrites the shortcut). Puts "Discord Sniper" on the
rem  Desktop with the crosshair icon. The shortcut targets
rem  cmd.exe /c launch-sniper.bat - a real EXE target, so
rem  Windows allows Pin to taskbar (a bare .bat shortcut
rem  can't be pinned; that was the 8/28 complaint).
rem ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$here = (Get-Location).Path;" ^
 "$bat = Join-Path $here 'launch-sniper.bat';" ^
 "if (-not (Test-Path $bat)) { Write-Host 'launch-sniper.bat is missing - nothing made.'; exit 1 };" ^
 "$ico = Join-Path $here 'sniper.ico';" ^
 "$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Discord Sniper.lnk';" ^
 "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
 "$s.TargetPath = \"$env:ComSpec\";" ^
 "$s.Arguments = ('/c \"\"' + $bat + '\"\"');" ^
 "$s.WorkingDirectory = $here;" ^
 "$s.Description = 'Launch the Discord Sniper - bridge, Chrome profile, all the rooms';" ^
 "if (Test-Path $ico) { $s.IconLocation = ($ico + ',0') };" ^
 "$s.Save();" ^
 "Write-Host 'Done. Desktop icon refreshed - right-click it, Pin to taskbar.'"
echo.
pause
