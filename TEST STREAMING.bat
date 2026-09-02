@echo off
title Webull Streaming Test - do options come through?
cd /d "%~dp0"
echo.
echo Installing the two streaming packages if they are missing...
python -m pip install --quiet --disable-pip-version-check webull-python-sdk-mdata webull-python-sdk-quotes-core
echo.
python "TEST_MQTT_OPTIONS.py"
