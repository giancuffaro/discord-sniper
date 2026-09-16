@echo off
cd /d "%~dp0"
title PROVE FUTURES STOPS
echo.
echo  ================================================================
echo    PROVE FUTURES STOPS  -  the two real trades that open futures
echo  ================================================================
echo.
echo    Your futures alerts do not trade. Every Webull futures OPEN is
echo    refused on purpose: Webull has no OCO for futures, so the stop is
echo    a SEPARATE GTC order placed AFTER the fill - and nobody has ever
echo    watched that second leg work on the real account.
echo.
echo    This proves it, once per micro, on ONE contract:
echo      buy 1 at market  -^>  confirm the fill AT THE BROKER
echo      -^>  place a GTC stop under it  -^>  read it back and match it
echo      -^>  cancel it  -^>  confirm the cancel  -^>  flatten  -^>  confirm flat
echo.
echo    EACH MICRO IS PROVEN ON ITS OWN. MES ^($5 a point^) and MNQ ^($2 a
echo    point^) get their own trade and their own block in
echo    futures_protection_proof.json. Proving MES does NOT let an MNQ
echo    alert trade, and proving MNQ does not touch the MES proof.
echo.
echo    THAT IS A REAL ONE-LOT ORDER ON YOUR REAL FUTURES ACCOUNT.
echo    Normal cost is a few dollars of spread and commission. Between the
echo    fill and the confirmed stop you are long with no stop - seconds,
echo    but real. If anything cannot be verified it STOPS and tells you
echo    exactly what to close by hand.
echo.
echo    RIGHT NOW THIS IS THE DRY RUN, FOR BOTH MICROS. It sends nothing.
echo    It checks the market is open, the money is there, the contract
echo    resolves and the account is clear, then prints each plan.
echo.
python futures_protection_proof.py --symbol all
echo.
echo  ----------------------------------------------------------------
echo    Nothing was sent. If the plans above are what you want, YOU run
echo    them - one micro at a time, watching the Webull futures screen:
echo.
echo        python futures_protection_proof.py --symbol MES --live
echo            1 MES, 10-point stop = $50 of intended risk
echo.
echo        python futures_protection_proof.py --symbol MNQ --live
echo            1 MNQ, 10-point stop = $20 of intended risk
echo.
echo    Each asks you to type YES before anything goes out. A clean pass
echo    writes that micro's block of futures_protection_proof.json and its
echo    entries start working; editing webull_futures.py kills BOTH proofs
echo    and shuts them again.
echo  ----------------------------------------------------------------
pause
