# VERIFY WITH G — things that did not add up (newest day first)

===== Wed Sep 16 2026 =====

Each line: what happened · why it looks wrong · my guess · G's verdict (blank until he teaches it).

1. 09:55 Brando "QQQ SEPT 18 713C $3.66" — BAD-CONTRACT, Webull "lists that strike only for 9/16". 3.66 fits a 9/18 contract, not a 0DTE (0DTE 713C asked ~1.15). Guess: expiry lookup bug, not a bad call. Verdict: BUG, FIXED 9/16 — the contract is real (Webull: QQQ260918C00713000 asks 1.47 tonight). listed_expiries cached one answer per contract and reused it for a different date; now per date, only positive answers kept.
2. 10:08 Skyy "Qqq 713c at 112 target 200" — refused, price made no sense (ask 1.15). Guess: 112 = 1.12, 200 = 2.00; reader should divide by 100 when the ask matches. Verdict:
3. 09:35 Unraveller "GOOGL 347.5C @ 9.00" — contract was 3.00/3.25. Refused as thin (66 traded) so no harm, but 9.00 matches nothing. Guess: different strike/expiry than the one read, or typo. Verdict:
4. 10:10 Brett AAPL edit "@ 2.67 (edited) … 10:10 AM" — parser read the price as 10.00 (took it from the edit timestamp). Room was off so nothing fired. Guess: parser bug. Verdict: BUG, FIXED 9/16 (ext 3.8.40) — the edit datestamp is stripped. The gate showed it was worse than one price: 4 edited LOADING lines had fired as OPEN and 3 expiries were taken from the edit date.
5. 09:40 / 10:08 / 14:08 Midas "Loaded SPY 759c" / "Loaded $SPY 761c" — ignored as LOADING (heads-up). He then posted "2.32 fill on 1 contract" and a stop; caller claims +80% on 761C. Guess: for Midas "Loaded" = bought. Verdict: G: leave as is.
6. 14:09 Midas 761C edit — skipped "110 seconds old, too stale": the clock ran from the original post, the edit is what made it parseable. Guess: fine as a rule, wrong here only because #5 dropped the original. Verdict:
7. 15:50 AbTrades "$SPY 760c 30% You can risk swinging half" — read as an OPEN (it is a trim update). Blocked as duplicate/swing so no harm. Guess: parser bug. Verdict:
8. 09:41 AAPL — bought 3.40 on a 3.17 alert (+7%), 6 s before Brett trimmed +13%. By design (pullbacks cross the ask, no ceiling vs caller). Guess: needs a cap. Verdict: G, RULE 9/17 — same average as the caller or better, pullbacks included. Built: over the caller's price the pullback order rests at his price and dies unfilled.
9. 09:41 TSLA 350P add refused "costs $270, you have $258" with NLV ~$1,400 — buying power was tied up (3 bot positions + G's hand QQQ x10-17). Guess: correct, flagging because it looks odd. Verdict:
10. 09:43 Honeydrip daytrades switched OFF (popup) → META 665P (+15%), MSFT 495P (+20%), AAPL re-entry skipped "not a channel you're listening to". Back ON 13:48. Guess: G did it on purpose after 3 losers. Verdict:
11. 09:45–10:12 bridge restarted 7 times in market hours ("change on disk … safe window"). Someone was editing code live. Guess: a Claude/Codex session. Verdict:
12. 10:23–13:34 bridge log is EMPTY (3h11m). NVDA pullback watcher from 10:15 never logged an outcome. Reader also closed 10:24–13:57. Guess: G closed everything; if not, the bridge died silently and the deadman said nothing. Verdict: G: he closed it.
13. 13:48 MODE READ ONLY set and STILL ON at midnight → 21 futures-radar entries and the SPY 760C pullback (touched, +18% by close) all refused "webhook mode … no webhook_url". Guess: G's switch, forgotten. Verdict: G: he will switch it back himself 9/17.
14. 09:18–09:29 nine futures-radar entries refused "protective stop is not operational" — the futures proof gate, MGC has no proof at all. Guess: correct by design. Verdict:
15. POS-READ "no broker response (throttled)" 7 times 09:45–10:22, clustered with the restart loop. Guess: each restart re-reads positions and trips the 2-per-2s door. Verdict:
16. 09:41 POSTCHECK PROBLEM "book holds QQQ, the account doesn't"; 13:46 SPY "sold at a price I never saw", 13:49 "no sell fill found after 3 minutes". Guess: G's hand trades racing the book. Verdict:
17. Ninjago radar reposts the same MNQ call up to 12 times (29491.13, 29172.00 …) — all correctly deduped, but it is 69 skips of noise in one day. Verdict:
18. balance_daily.csv had blank day P&L / buying power 9/15–9/16 (fixed tonight); margin NLV −$465 was a $500 transfer, not a loss (fixed tonight).
