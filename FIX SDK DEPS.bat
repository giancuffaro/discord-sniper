@echo off
title FIX SDK DEPS - put the bridge's SDK pins back
cd /d "%~dp0"
echo.
echo  The streaming test (9/2 01:03) upgraded four packages past what the
echo  bridge's Webull SDK (webull-openapi-python-sdk 2.0.16) allows. The
echo  running bridge is fine, but the NEXT restart would fail to import.
echo  This puts the exact compatible versions back. Takes ~30 seconds.
echo.
python -m pip install --disable-pip-version-check "cachetools<6,>=5.2.0" "jmespath<1.0.0,>=0.9.3" "paho-mqtt<2,>=1.6.1" "protobuf<6,>=4.25.0"
echo.
echo  --- verifying the bridge's SDK imports cleanly ---
python -c "import webull; from webull.trade.trade_client import TradeClient; print('  bridge SDK import: OK')" 2>&1
python -m pip check 2>&1 | findstr /i "webull-openapi" && echo  (see conflicts above) || echo   pip check: no webull-openapi conflicts
echo.
echo  Done. Safe to restart the bridge again.
pause
