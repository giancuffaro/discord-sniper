# FUTURES MIRROR — --help

SPY/QQQ room entries replayed as one-contract MES/MNQ, market entry, 25-pt stop / 50-pt target, futures ratchet.
The switch is OFF: this is a measurement, not a trade.

**No SPY/QQQ entries on this date.** Nothing to replay.


### What this number is not

- No slippage and no spread: entries fill at the next bar's OPEN, exits at
  the exact stop/target price. A real market order does neither.
- 1-minute bars, so a bar that touched the stop AND the target is scored as
  a stop. Conservative, but it is a guess about which came first.
- Commission is an assumption: $1.50 round turn per contract, shown net.
- The mirror is OFF. This is hypothetical: the current live futures route
  records stop/target levels but does not enforce those exits at the broker.
  Activation is blocked until protective exits are operational and tested.
- New-day alert coverage is limited to bridge shadow rows and master_alerts;
  a post missed before those stages is absent from this report.
