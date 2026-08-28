@echo off
rem ============================================================
rem  MAKE DESKTOP ICON - run me ONCE. Puts a "Discord Sniper"
rem  shortcut on your Desktop with the crosshair icon; double-
rem  clicking it does exactly what START HERE does. (8/28, his
rem  ask.) Safe to run again - it just rewrites the shortcut.
rem ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$here = (Get-Location).Path;" ^
 "$bat = (Get-ChildItem -LiteralPath $here -Filter '*START HERE.bat' | Select-Object -First 1).FullName;" ^
 "if (-not $bat) { Write-Host 'START HERE.bat not found - nothing made.'; exit 1 };" ^
 "$ico = Join-Path $here 'sniper.ico';" ^
 "$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Discord Sniper.lnk';" ^
 "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
 "$s.TargetPath = $bat;" ^
 "$s.WorkingDirectory = $here;" ^
 "$s.Description = 'Launch the Discord Sniper - bridge, Chrome profile, all the rooms';" ^
 "if (Test-Path $ico) { $s.IconLocation = ($ico + ',0') };" ^
 "$s.Save();" ^
 "Write-Host ('Done - look at your Desktop for Discord Sniper.')"
echo.
pause
