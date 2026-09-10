"""chika_compare.py — HER WAY vs OUR RATCHET, on the same tape (9/10).

G: "I'd like you to read original and then compare with my ratchet to see
which would be better."

The right question, and read-only is what makes it answerable. This scores
BOTH sides of one full session from real NQ bars — not from her own claims,
because a room's self-report is not evidence.

HER SIDE
She posts her result in POINTS as she goes ("+30 safety trim", "-22 got me",
"+60 im out"). Those are used ONLY as the exit TIMES; the P&L is re-derived
from the tape at that minute, so her own claims are never taken on trust.
Where she scales out in stages the LAST exit is used, and that is CONSERVATIVE
for her, not generous: on the 14:46 long she banked a +30 trim and then flatted
the rest into a -10, and scoring only the final flat books her -10 and throws
the +30 away. So her real session is BETTER than the number below, which only
strengthens whichever way the comparison lands.

OUR SIDE
The doctrine, exactly as the machine would run it:
  * her level, expanded against the tape (she writes "230", the tape says
    29,230), then the ROUND-NUMBER WAIT: the next 25 AGAINST the trade, so a
    short fills higher and a long fills lower (webull_futures._round_entry).
  * a 10-minute window for that level to print. Never printed = NO TRADE, and
    that is counted, because a skipped trade is a real cost of the rule.
  * her stop when she posted one, our 25 points when she did not.
  * a 50-point target. One contract. No trims — ENTRIES ONLY, the resting
    stop is the only way out.

WHAT IT CANNOT SEE
One minute is one bar. If a single bar covers both the stop and the target the
row is UNKNOWN and dropped, never guessed. On 9/10's bars that needs a 75-point
minute and there was exactly one in 1,200, so it costs almost nothing here —
but the check is run and reported every time, because the coarser the bars the
more it matters. (An earlier backtest today reported a confident answer that
was pure bar-coarseness. Once was enough.)

Usage:  python3 chika_compare.py [--bars bars/NQ_bars.csv]
"""
import argparse
import csv
import datetime as dt
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Her 9/10 session, read live from the room. Times are UTC (ET + 4), taken
# from the Discord snowflake in each message id, so they are exact to the
# millisecond rather than the minute Discord renders.
#   dir, pivot digits, her stop (None = she posted none), her exit time
SESSIONS = {
  # 9/10 — 1-MINUTE bars all day. The clean session.
  "2026-09-10": [
    ("14:46", "LONG",  230, 200, "15:02"),   # "+30 safety trim" then "flat rest"
    ("15:04", "LONG",  230, None, "15:06"),  # "relonging 230 rebid" -> "+20 trim"
    ("15:12", "LONG",  250, None, "15:15"),  # "adding longs 250s" -> "flat"
    ("15:20", "LONG",  220, 200, "15:21"),   # "starter long 220s" -> "-22 got me"
    ("15:39", "SHORT", 250, None, "15:44"),  # "short 250 pivot" -> "flat at entry"
    ("16:07", "SHORT", 203, 215, "16:36"),   # "reshorting, 203" -> rode to +60/+48
    ("17:00", "SHORT", 230, 245, "18:00"),   # "got a short 230, stop 245"
    ("18:53", "SHORT", 195, None, "19:54"),  # "short 195 pivot" -> "+65 trim"
  ],
  # 9/02 and 9/03 — 15-MINUTE bars only, so a trade that lasted five minutes
  # cannot be scored at all: the exit price would be up to fifteen minutes
  # wrong on a move that took two. ONLY trades lasting >= 2x the bar are
  # listed, which is most of her sessions thrown away — 3 of ~17. Listing the
  # rest would be inventing precision the data does not have, which is the
  # mistake the Tradytics run made this morning.
  "2026-09-02": [
    ("17:14", "SHORT", 153, 165,  "17:44"),  # "am short nascock, 153 pivot" -> "flat" (30 min)
    ("19:01", "SHORT", 153, 181,  "19:44"),  # "taking a flip here pivot short 153" -> "stopped" (43 min)
  ],
  "2026-09-03": [
    ("18:51", "SHORT", 538, None, "19:52"),  # "one more attempt same bet" -> "all out +60" (61 min)
  ],
  # 9/4 — 5-MINUTE bars. Her exit times are therefore good to about five
  # minutes, which on a trade that lasts two is real slop. Reported, not hidden.
  "2026-09-04": [
    ("15:16", "SHORT", 538, None, "15:28"),  # "flippiin short 538 pivot" -> "flat shorts +40"
    ("18:10", "LONG",  465, None, "18:22"),  # "trying a long 480s fill 465 pivot" -> "+30 adds +20"
    ("18:36", "SHORT", 513, None, "18:43"),  # "starter short 513 pivot" -> "stalling, im out -3"
    ("18:47", "LONG",  523, None, "18:58"),  # "small long, 523pivot" -> "trades up +20 i've trimmed"
    ("18:59", "SHORT", 538, 555,  "19:25"),  # "starter short 538 stop 555" -> "closing the trade"
    ("19:27", "LONG",  528, 517,  "19:36"),  # "smollong 528, stop 517" -> "+15 safety trim"
    ("19:38", "SHORT", 538, 560,  "19:50"),  # "last bet short nq 538-43" -> "got me -22"
  ],
}
FUT_STOP_PTS = 25.0
FUT_TARGET_PTS = 50.0
WAIT_MIN = 10           # how long the round number gets to print
NQ_POINT = 20.0         # $ per point, E-mini NQ (Webull: size 20)


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.strptime(r["time"], "%Y-%m-%dT%H:%M:%S.%f%z")
            rows.append((t, float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"])))
    rows.sort(key=lambda x: x[0])
    return rows


def at(bars, when):
    """The bar covering this minute, or the next one after it."""
    for b in bars:
        if b[0] >= when:
            return b
    return None


def expand(pivot, ref):
    """"230" + a tape at 29,187  ->  29,230.

    The digits she writes are the tail of the price. The thousands come from
    the tape, never from a guess: take the candidate ending in those digits
    that sits nearest the last print. Ties cannot happen — the candidates are
    1,000 apart and the tape is one number."""
    base = math.floor(ref / 1000.0) * 1000.0
    best, bd = None, 1e9
    for k in (-1000.0, 0.0, 1000.0):
        cand = base + k + pivot
        d = abs(cand - ref)
        if d < bd:
            bd, best = d, cand
    return best


def round25(px, is_short):
    return math.ceil(px / 25.0) * 25.0 if is_short else math.floor(px / 25.0) * 25.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=os.path.join(HERE, "bars", "NQ_bars.csv"))
    a = ap.parse_args()
    allbars = load(a.bars)
    her_tot, our_tot, skipped, unknown, taken, n = 0.0, 0.0, 0, 0, 0, 0
    for DAY in sorted(SESSIONS):
        bars = [b for b in allbars if b[0].strftime("%Y-%m-%d") == DAY]
        if not bars:
            print("no bars for " + DAY + " — skipped")
            continue
        gaps = sorted(set(round((bars[i+1][0]-bars[i][0]).total_seconds()/60)
                          for i in range(min(40, len(bars)-1))))
        print("=" * 78)
        print("CHIKA %s — HER EXITS vs OUR RATCHET, both priced off the same tape"
              % DAY)
        print("%d NQ bars, %s to %s UTC, %s-minute resolution" %
              (len(bars), bars[0][0].strftime("%H:%M"), bars[-1][0].strftime("%H:%M"),
               "/".join(str(g) for g in gaps[:2])))
        print("=" * 78)
        print("  %-6s %-5s %-8s %-9s %8s   %8s  %s"
              % ("time", "side", "her fill", "our fill", "HERS", "OURS", "what happened to ours"))
        n += len(SESSIONS[DAY])
        her_tot, our_tot, skipped, unknown, taken = _run(
            bars, SESSIONS[DAY], DAY, her_tot, our_tot, skipped, unknown, taken)
    _summary(her_tot, our_tot, skipped, unknown, taken, n)


def _run(bars, entries, DAY, her_tot, our_tot, skipped, unknown, taken):
    for tm, side, pivot, hstop, xtm in entries:
        t0 = dt.datetime.strptime(DAY + " " + tm + "+0000", "%Y-%m-%d %H:%M%z")
        t1 = dt.datetime.strptime(DAY + " " + xtm + "+0000", "%Y-%m-%d %H:%M%z")
        b0 = at(bars, t0)
        if not b0:
            continue
        is_short = side == "SHORT"
        her_fill = expand(pivot, b0[4])

        # ---- HER SIDE: out at the tape when she said she was out ----
        bx = at(bars, t1)
        her_exit = bx[4] if bx else b0[4]
        her_pts = (her_exit - her_fill) if not is_short else (her_fill - her_exit)

        # ---- OUR SIDE: wait for the next 25 against the trade ----
        want = round25(her_fill, is_short)
        window = [b for b in bars if t0 <= b[0] <= t0 + dt.timedelta(minutes=WAIT_MIN)]
        hit = None
        for b in window:
            if (is_short and b[2] >= want) or ((not is_short) and b[3] <= want):
                hit = b
                break
        if hit is None:
            skipped += 1
            print("  %-6s %-5s %-8.0f %-9s %+8.0f   %8s  the %g never printed in %d min — NO TRADE"
                  % (tm, side, her_fill, "%.0f" % want, her_pts, "-", want, WAIT_MIN))
            her_tot += her_pts
            continue

        stop = float(hstop) if hstop else None
        if stop is not None:
            stop = expand(stop, want)
        else:
            stop = want + FUT_STOP_PTS if is_short else want - FUT_STOP_PTS
        # THE ROUND NUMBER CAN ROUND THE ENTRY INTO THE STOP (found by this
        # very run, 9/10). Her 15:20 long was "220s, stop 200"; rounding the
        # entry DOWN to the next 25 put it at 29,200 — exactly her stop. A
        # bracket whose entry IS its stop is not a trade, it is an instant
        # scratch, and the live machine must refuse it rather than send it.
        if (is_short and stop <= want) or ((not is_short) and stop >= want):
            skipped += 1
            print("  %-6s %-5s %-8.0f %-9.0f %+8.0f   %8s  the round number lands ON her stop — REFUSED"
                  % (tm, side, her_fill, want, her_pts, "-"))
            her_tot += her_pts
            continue
        target = want - FUT_TARGET_PTS if is_short else want + FUT_TARGET_PTS

        outcome, our_pts = None, None
        for b in bars:
            if b[0] < hit[0]:
                continue
            ht = (b[3] <= target) if is_short else (b[2] >= target)
            hs = (b[2] >= stop) if is_short else (b[3] <= stop)
            if ht and hs:
                outcome = "UNKNOWN"
                break
            if hs:
                outcome, our_pts = "stopped", -abs(want - stop)
                break
            if ht:
                outcome, our_pts = "target", FUT_TARGET_PTS
                break
        if outcome is None:
            last = bars[-1][4]
            our_pts = (last - want) if not is_short else (want - last)
            outcome = "still open at the close"
        if outcome == "UNKNOWN":
            unknown += 1
            print("  %-6s %-5s %-8.0f %-9.0f %+8.0f   %8s  one bar held both levels — dropped"
                  % (tm, side, her_fill, want, her_pts, "-"))
            her_tot += her_pts
            continue

        taken += 1
        her_tot += her_pts
        our_tot += our_pts
        print("  %-6s %-5s %-8.0f %-9.0f %+8.0f   %+8.0f  %s"
              % (tm, side, her_fill, want, her_pts, our_pts, outcome))

    return her_tot, our_tot, skipped, unknown, taken


def _summary(her_tot, our_tot, skipped, unknown, taken, n):
    print("=" * 78)
    print("  HER WAY    : %+.0f points  = %+.0f dollars on one NQ contract"
          % (her_tot, her_tot * NQ_POINT))
    print("  OUR RATCHET: %+.0f points  = %+.0f dollars   (%d of %d taken, %d skipped,"
          % (our_tot, our_tot * NQ_POINT, taken, n, skipped))
    print("                                          %d dropped as unreadable)" % unknown)
    print()
    print("  Difference : %+.0f points in favour of %s"
          % (abs(her_tot - our_tot), "HER" if her_tot > our_tot else "OURS"))
    print()
    print("  n=%d entries over 4 sessions. That is a story, not evidence — it says" % n)
    print("  which way to look, not what to do. read-only keeps collecting.")


if __name__ == "__main__":
    main()
