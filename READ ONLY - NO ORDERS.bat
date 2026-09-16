@echo off
setlocal
title READ ONLY - no orders
rem ------------------------------------------------------------------
rem  G, 2026-09-16: "make me a read only no execute button".
rem  Sets execution.mode = webhook at the running bridge: every room
rem  keeps reading, every alert is still parsed, judged and logged,
rem  and live_order is forced False at the dispatch boundary - so
rem  NOTHING reaches the broker. It is written to settings.json, so it
rem  survives a bridge restart.
rem  IT DOES NOT touch positions you already hold: their resting stops
rem  stay at Webull. This stops NEW orders.
rem  To trade again: RESUME TRADING.bat
rem ------------------------------------------------------------------
echo.
curl -s -m 5 -X POST -H "Content-Type: application/json" -d "{\"do\":\"read_only_on\"}" http://127.0.0.1:8787/fix > "%TEMP%\ds_ro.txt" 2>nul
if errorlevel 1 goto :nobridge
findstr /c:"\"ok\": true" "%TEMP%\ds_ro.txt" >nul 2>&1
if errorlevel 1 goto :failed
echo   ############################################################
echo   #                                                          #
echo   #                 R E A D   O N L Y                        #
echo   #         rooms still read - NO orders are sent            #
echo   #                                                          #
echo   ############################################################
echo.
echo   Open positions keep their resting stops at Webull.
echo   To trade again, run:  RESUME TRADING.bat
echo.
del /q "%TEMP%\ds_ro.txt" >nul 2>&1
pause
exit /b 0

:failed
echo   [FAILED] The bridge answered but did not switch. It said:
type "%TEMP%\ds_ro.txt"
echo.
echo   NOTHING CHANGED - assume the bot can still trade.
echo   Fall back: turn the rooms OFF in the popup.
echo.
del /q "%TEMP%\ds_ro.txt" >nul 2>&1
pause
exit /b 1

:nobridge
echo   [FAILED] No answer from the bridge on 127.0.0.1:8787.
echo.
echo   If the bridge is DOWN it is not trading anyway.
echo   If it is UP and just did not answer, NOTHING CHANGED -
echo   turn the rooms OFF in the popup instead.
echo.
pause
exit /b 1
