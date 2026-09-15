# RATCHET AND EXITS — mechanics

The mechanics behind the rules in HANDOFF.md, moved here 9/15 so HANDOFF stays a
rules core (under 30 KB). The rule is in HANDOFF; the HOW, the numbers and the
history-with-numbers are here. REPLACE, DON'T STACK applies: edit in place.

Owner code: ratchet_tiers.py (the one implementation; live_spacing() is the one
configuration reader), positions.py (Book: watchdog, stop arm, rearm_overnight_stops,
_sell_confirmed), bridge.py (EXIT-IGNORED gate). Studies: reference/ANTI-CLIP.txt,
reference/RATCHET-REPLAY-TAPE-2026-09-14.md, reference/STOCK-STOP-REPLAY-2026-09-14.md,
ratchet_sweep_fine.py, ratchet_backtest.py.

## The doctrine and its mechanics (verbatim from HANDOFF, 9/15)

EXITS — THE DOCTRINE: THEIR TRIGGER → OUR ENTRY → THE RATCHET'S EXIT
- ENTRIES ONLY (G, 9/3; verified live 9/8): the bot follows room ENTRIES
  (and adds) only. EVERY room-side exit — trim, stop-move, "all out",
  "stopped out", "closed everything" — is logged "EXIT-IGNORED … entries
  only" and NEVER traded. The ratchet's resting stop at Webull is the ONLY
  exit (plus the bridge's own pullback stock-stop / underlying hard-stop).
  ONE EXCEPTION, and it is not a room exit: an EDIT that changes the CONTRACT
  we already bought (see ENTRIES). A bot SELL that traces to a room's own exit
  call is still a BUG: check bridge.py do_POST's
  EXIT-IGNORED gate, background.js's TRIM/STOPMOVE/CLOSE gate, and that
  settings execution.exit_policy is absent (default entries_only; "full" is
  the one-line way back).
- THE RATCHET (10/10/10 since 9/15, flat — G: "go back to 10", the August spacing): born stop −10%; +10% moves the stop to breakeven; each further +10% locks another +10%; `ratchet_tiers.py` is the one implementation, `live_spacing()` the one reader (born from settings strategy.stop_loss_pct, arm/step from TIERS); stops never loosen; anti-clip off. The 9/8 sweep ranked this 30/50 and 5/3/5 first — G's call against that evidence, on the two days it made money. Re-measure as the sample grows: `ratchet_sweep_fine.py`, `reference/ratchet_replay_tape.py`.
- FUTURES RATCHET (9/9): derived from the trade's own risk — arm at
  ⅔ of the stop distance in profit → BE, then a rung every ~27% of it
  (FUT_ARM_FRACTION = 5/7.5, FUT_STEP_FRACTION = 2/7.5). 30-pt NQ stop →
  30/20/8. Anchor: QQQ↔NQ ≈ 41 pts per $1.
- SWINGS: 14+ DTE = swing (auto-tagged). Their stock-level stop runs it; no
  level = wide −25%. Option SELL orders are DAY-only at Webull, so
  Book.rearm_overnight_stops re-arms every open swing at 9:31. Scalps
  excluded on purpose.
- CLOSE path: every bot sell waits for FILLED (_sell_confirmed) — an
  ACCEPTED sell is never booked as filled; a never-filled sell releases the
  key and logs EXIT-RETRY; late/partial fills found during cancel reduce the
  remaining quantity before any retry.
- A CLOSE for a contract the book does not hold is REFUSED, never sent
  (his 12-lot scalps live in the same account).
- NO PRE-CLOSE FLATTEN (G, 9/15). There is no timed close-out path and none
  is to be written. ETFs trade to 16:15; a 0DTE left $0.01 ITM auto-exercises
  into 100 shares. G was shown that risk and chose to run it — closing an
  expiring position by hand is his call, and the ratchet's resting stop stays
  the only exit the bot has.
