@echo off
setlocal
title Resume trading
rem ------------------------------------------------------------------
rem  Undoes READ ONLY - NO ORDERS.bat. Clears execution.mode back to
rem  dryrun, which means each ROOM SWITCH decides again: a room that is
rem  ON sends real orders. That is why this one asks first.
rem ------------------------------------------------------------------
echo.
echo   This turns REAL ORDERS back on.
echo   Every room still switched ON in the popup will trade real money
echo   the next time it sees an alert.
echo.
set "ANS="
set /p "ANS=   Type YES to resume trading: "
if /i not "%ANS%"=="YES" (
  echo.
  echo   Cancelled. Still READ ONLY.
  echo.
  pause
  exit /b 0
)
echo.
curl -s -m 5 -X POST -H "Content-Type: application/json" -d "{\"do\":\"read_only_off\"}" http://127.0.0.1:8787/fix > "%TEMP%\ds_rr.txt" 2>nul
if errorlevel 1 goto :nobridge
findstr /c:"\"ok\": true" "%TEMP%\ds_rr.txt" >nul 2>&1
if errorlevel 1 goto :failed
echo   [DONE] Trading is live again. Each room own toggle decides.
echo.
del /q "%TEMP%\ds_rr.txt" >nul 2>&1
pause
exit /b 0

:failed
echo   [FAILED] The bridge answered but did not switch. It said:
type "%TEMP%\ds_rr.txt"
echo.
echo   Still READ ONLY - nothing will trade.
echo.
del /q "%TEMP%\ds_rr.txt" >nul 2>&1
pause
exit /b 1

:nobridge
echo   [FAILED] No answer from the bridge on 127.0.0.1:8787.
echo   Still READ ONLY - nothing will trade.
echo.
pause
exit /b 1
