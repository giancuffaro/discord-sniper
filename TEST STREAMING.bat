@echo off
title Webull Streaming Test - do options come through?
cd /d "%~dp0"
echo.
echo Installing the streaming SDK. Python 3.14 has no prebuilt wheel for
echo the OLD grpcio the SDK pins, so: newest grpcio/protobuf/paho as
echo prebuilt wheels FIRST, then the SDK without re-resolving its pins.
echo Everything is saved to streaming-test.txt so Claude can read it.
echo.
> "streaming-test.txt" echo === pip install (wheels only) ===
python -m pip install --disable-pip-version-check --only-binary=:all: --upgrade grpcio grpcio-tools protobuf paho-mqtt cachetools cryptography jmespath >> "streaming-test.txt" 2>&1
echo === pip install (sdk, no deps) === >> "streaming-test.txt"
python -m pip install --disable-pip-version-check --no-deps webull-python-sdk-core webull-python-sdk-mdata webull-python-sdk-quotes-core >> "streaming-test.txt" 2>&1
type "streaming-test.txt" | findstr /i "error successfully failed"
echo.
echo === test === >> "streaming-test.txt"
echo Running the test now (about a minute)...
rem the HTTP contract hunt answers INVALID_SYMBOL on this SDK family, so
rem hand it a contract we KNOW is real (his open FLR 57.5C 9/18 swing)
set "TEST_OCC=FLR260918C00057500"
python -u "TEST_MQTT_OPTIONS.py" >> "streaming-test.txt" 2>&1
echo.
type "streaming-test.txt" | more
echo.
echo ==========================================================
echo  Saved to streaming-test.txt. This window stays open now.
echo ==========================================================
pause
