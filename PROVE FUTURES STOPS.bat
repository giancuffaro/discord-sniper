@echo off
cd /d "%~dp0"
title PROVE FUTURES STOPS
echo.
echo  ================================================================
echo    PROVE FUTURES STOPS  -  the one real trade that opens futures
echo  ================================================================
echo.
echo    Your futures alerts do not trade. Every Webull futures OPEN is
echo    refused on purpose: Webull has no OCO for futures, so the stop is
echo    a SEPARATE GTC order placed AFTER the fill - and nobody has ever
echo    watched that second leg work on the real account.
echo.
echo    This proves it, once, on ONE MES contract ^($5 a point^):
echo      buy 1 MES at market  -^>  confirm the fill AT THE BROKER
echo      -^>  place a GTC stop under it  -^>  read it back and match it
echo      -^>  cancel it  -^>  confirm the cancel  -^>  flatten  -^>  confirm flat
echo.
echo    THAT IS A REAL ONE-LOT ORDER ON YOUR REAL FUTURES ACCOUNT.
echo    Normal cost is a few dollars of spread and commission. Between the
echo    fill and the confirmed stop you are long with no stop - seconds,
echo    but real. If anything cannot be verified it STOPS and tells you
echo    exactly what to close by hand.
echo.
echo    RIGHT NOW THIS IS THE DRY RUN. It sends nothing. It checks the
echo    market is open, the money is there, the contract resolves and the
echo    account is clear, then prints the plan.
echo.
python futures_protection_proof.py
echo.
echo  ----------------------------------------------------------------
echo    Nothing was sent. If the plan above is what you want, YOU run it:
echo.
echo        python futures_protection_proof.py --live
echo.
echo    It asks you to type YES before anything goes out. Watch the
echo    Webull futures screen while it runs. A clean pass writes
echo    futures_protection_proof.json and futures entries start working;
echo    editing webull_futures.py kills that proof and shuts them again.
echo  ----------------------------------------------------------------
pause
