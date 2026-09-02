@echo off
title Webull Streaming Test - do options come through?
cd /d "%~dp0"
echo.
echo Installing the streaming SDK packages (a different family than the
echo bridge's SDK) - this may take a minute. Output is saved too.
echo.
> "streaming-test.txt" echo === pip install ===
python -m pip install --disable-pip-version-check webull-python-sdk-core webull-python-sdk-mdata webull-python-sdk-quotes-core >> "streaming-test.txt" 2>&1
type "streaming-test.txt"
echo.
echo === test === >> "streaming-test.txt"
python -u "TEST_MQTT_OPTIONS.py" >> "streaming-test.txt" 2>&1
python -u "TEST_MQTT_OPTIONS.py" 2>&1 | more
echo.
echo ==========================================================
echo  Saved to streaming-test.txt. This window stays open now.
echo ==========================================================
pause
