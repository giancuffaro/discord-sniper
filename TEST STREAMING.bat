@echo off
title Webull Streaming Test - do options come through?
cd /d "%~dp0"
echo.
echo Installing the two streaming packages if they are missing...
python -m pip install --quiet --disable-pip-version-check webull-python-sdk-mdata webull-python-sdk-quotes-core
echo.
echo Running the test. Everything it prints is ALSO saved to streaming-test.txt
echo so Claude can read it even if this window closes.
echo.
python -u "TEST_MQTT_OPTIONS.py" > "streaming-test.txt" 2>&1
type "streaming-test.txt"
echo.
echo ==========================================================
echo  Saved to streaming-test.txt. This window stays open now.
echo ==========================================================
pause
