@echo off
title Webull Streaming Test - ANSWERED BY THE DOCS
cd /d "%~dp0"
echo.
echo  ANSWERED 9/2 without running (v3.5.0\OPTIONS-BROKER-REFERENCE.md):
echo.
echo    Webull's streaming (MQTT) carries STOCKS, ETFs, FUTURES, CRYPTO
echo    and EVENT CONTRACTS only. The Subscribe endpoint's category enum
echo    is US_STOCK / US_ETF. There is NO option streaming on Webull.
echo    (developer.webull.com/apis/docs/reference/subscribe.md)
echo.
echo    Option bid/ask exists ONLY via the polled snapshot endpoint:
echo    60 calls/min, 20 contracts per call = 1,200 contract-quotes/min
echo    per app key. That is what the quote bus does, at 1 call/second.
echo.
echo    What Webull DOES push: ORDER FILL EVENTS over gRPC
echo    (TradeEventsClient in the same SDK the bridge uses). That is the
echo    next announcer upgrade - fills the instant they happen, no polling.
echo.
echo  Nothing to run. No Python 3.12 needed.
pause
