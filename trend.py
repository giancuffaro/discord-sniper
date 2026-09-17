#!/usr/bin/env python3
"""trend.py — is the stock STAIR-STEPPING, and which way?

G, 9/17: "if I traded SPY I need something detecting movement in trend like
711 to 712, pull back to 711.50, jump to 712.5, pullback to 712, push to 713 …
I need something that will detect that."

That picture is a SWING STRUCTURE: legs and pullbacks. An UPTREND is a run of
HIGHER HIGHS and HIGHER LOWS (712 -> 712.5 -> 713 with 711.5 -> 712 under
them); a DOWNTREND is lower lows and lower highs; anything else is CHOP. So
this file does one thing: turn a price path into its swing points, then read
the last two highs and the last two lows.

WHAT COUNTS AS A PULLBACK. A wiggle is not a swing. A leg ends only when price
comes back against it by at least REVERSAL — sized to the stock, not typed in:
    reversal = max(MIN_PCT of price, ATR_MULT x the median 1-minute range)
over the bars given. On a quiet SPY that is about 30-45 cents, which is the
size of the pullbacks in his own example; on TSLA it is dollars. One number
for every symbol would be wrong for all of them.

LABEL
    UP      last two swing highs rising AND last two swing lows rising
    DOWN    both falling
    CHOP    anything else, or fewer than two of each yet
The leg still in progress counts the moment it breaks the prior extreme (the
push to 713 is a higher high when it prints, not when it later pulls back).

MEASUREMENT ONLY. Nothing here can place, block or size an order. The bridge
writes the label beside each alert (alert_trend.csv) so the question "do
with-trend alerts pay better" is answered by data before it becomes a rule.
"""
from __future__ import annotations

import statistics

MIN_PCT = 0.04          # reversal floor, % of price
ATR_MULT = 2.5          # x median 1-minute high-low range
LOOKBACK_BARS = 90      # minutes of structure that still describe "now"


def reversal_size(bars):
    """bars: [(ts, open, high, low, close)] oldest first."""
    if not bars:
        return 0.0
    last = bars[-1][4]
    ranges = [b[2] - b[3] for b in bars if b[2] >= b[3]]
    typical = statistics.median(ranges) if ranges else 0.0
    return max(last * MIN_PCT / 100.0, ATR_MULT * typical)


def swings(bars, reversal):
    """Zigzag pivots -> [(ts, price, 'H'|'L')], confirmed ones only, plus the
    live leg's extreme as the last element flagged 'h'/'l' (unconfirmed).

    Inside one bar the order of its high and low is unknown. The leg's own
    extreme is updated first and the opposite end is what may confirm a
    reversal — the conservative read: it finds a pullback a bar late rather
    than inventing one that did not happen."""
    if not bars or reversal <= 0:
        return []
    pivots = []
    ts0, _o, hi, lo, _c = bars[0]
    direction = 0                       # +1 leg up, -1 leg down, 0 unknown
    ext_hi, ext_hi_ts, ext_lo, ext_lo_ts = hi, ts0, lo, ts0
    for ts, _o, h, l, _c in bars[1:]:
        if direction >= 0 and h > ext_hi:
            ext_hi, ext_hi_ts = h, ts
        if direction <= 0 and l < ext_lo:
            ext_lo, ext_lo_ts = l, ts
        if direction == 0:
            if ext_hi - l >= reversal and ext_hi_ts <= ts:
                direction = -1
                pivots.append((ext_hi_ts, ext_hi, "H"))
                ext_lo, ext_lo_ts = l, ts
            elif h - ext_lo >= reversal:
                direction = 1
                pivots.append((ext_lo_ts, ext_lo, "L"))
                ext_hi, ext_hi_ts = h, ts
        elif direction == 1 and ext_hi - l >= reversal:
            pivots.append((ext_hi_ts, ext_hi, "H"))
            direction, ext_lo, ext_lo_ts = -1, l, ts
        elif direction == -1 and h - ext_lo >= reversal:
            pivots.append((ext_lo_ts, ext_lo, "L"))
            direction, ext_hi, ext_hi_ts = 1, h, ts
    if direction == 1:
        pivots.append((ext_hi_ts, ext_hi, "h"))
    elif direction == -1:
        pivots.append((ext_lo_ts, ext_lo, "l"))
    return pivots


def read(bars):
    """-> {"label", "reversal", "pivots", "legs", "highs", "lows"}."""
    bars = list(bars or [])[-LOOKBACK_BARS:]
    rev = reversal_size(bars)
    piv = swings(bars, rev)
    highs = [p for p in piv if p[2] in ("H", "h")]
    lows = [p for p in piv if p[2] in ("L", "l")]
    # The live leg counts only once it has BROKEN the prior extreme.
    if highs and highs[-1][2] == "h" and len(highs) >= 2 and highs[-1][1] <= highs[-2][1]:
        highs = highs[:-1]
    if lows and lows[-1][2] == "l" and len(lows) >= 2 and lows[-1][1] >= lows[-2][1]:
        lows = lows[:-1]
    label = "CHOP"
    if len(highs) >= 2 and len(lows) >= 2:
        hh, hl = highs[-1][1] > highs[-2][1], lows[-1][1] > lows[-2][1]
        lh, ll = highs[-1][1] < highs[-2][1], lows[-1][1] < lows[-2][1]
        if hh and hl:
            label = "UP"
        elif lh and ll:
            label = "DOWN"
    legs = " > ".join("%.2f" % p[1] for p in piv[-7:])
    return {"label": label, "reversal": round(rev, 4), "pivots": piv,
            "legs": legs, "highs": [p[1] for p in highs[-2:]],
            "lows": [p[1] for p in lows[-2:]]}


def with_or_counter(label, side):
    """A call in an UP tape or a put in a DOWN tape is WITH it."""
    if label not in ("UP", "DOWN"):
        return "CHOP"
    is_call = str(side or "").upper().startswith("C")
    return "WITH" if (label == "UP") == is_call else "COUNTER"


def minute_bars(path, until_ts, minutes=LOOKBACK_BARS):
    """[(ts, price)] (any cadence) -> 1-minute OHLC bars ending at until_ts."""
    start = until_ts - minutes * 60
    buckets = {}
    for ts, px in path:
        if ts < start or ts > until_ts:
            continue
        b = int(ts // 60)
        if b not in buckets:
            buckets[b] = [b * 60, px, px, px, px]
        else:
            row = buckets[b]
            row[2], row[3], row[4] = max(row[2], px), min(row[3], px), px
    return [tuple(buckets[b]) for b in sorted(buckets)]
