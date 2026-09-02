@echo off
title Webull Streaming Test - do options come through?
cd /d "%~dp0"
echo.
echo  PARKED (9/2 01:10). The streaming SDK (webull-python-sdk-*) and the
echo  bridge's SDK (webull-openapi-python-sdk) can NOT share one Python:
echo  they pin protobuf/paho/cachetools/jmespath to incompatible ranges.
echo  Installing this test into the bridge's Python broke the bridge's
echo  pins on 9/2 (FIX SDK DEPS.bat repairs that).
echo.
echo  The right way is a SEPARATE Python just for streaming. If you have
echo  Python 3.12 installed, this will build one in .venv-stream and run
echo  the test there. Otherwise it stops here without touching anything.
echo.
py -3.12 -c "print('python 3.12 found')" >nul 2>&1
if errorlevel 1 (
  echo  No Python 3.12 on this PC - nothing done. Install 3.12 from
  echo  python.org side by side ^(it will not replace 3.14^), then rerun.
  pause
  exit /b 0
)
if not exist ".venv-stream\Scripts\python.exe" py -3.12 -m venv .venv-stream
> "streaming-test.txt" echo === venv pip install ===
".venv-stream\Scripts\python.exe" -m pip install --disable-pip-version-check -q webull-python-sdk-core webull-python-sdk-mdata webull-python-sdk-quotes-core >> "streaming-test.txt" 2>&1
echo === test === >> "streaming-test.txt"
set "TEST_OCC=FLR260918C00057500"
".venv-stream\Scripts\python.exe" -u "TEST_MQTT_OPTIONS.py" >> "streaming-test.txt" 2>&1
type "streaming-test.txt" | more
echo.
echo  Saved to streaming-test.txt.
pause
