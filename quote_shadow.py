"""quote_shadow.py — is tastytrade's streamed quote good enough to trust?

    python quote_shadow.py                 whole tape
    python quote_shadow.py --since 1       today only
    python quote_shadow.py --occ SPY260908C00640000

WHAT THIS DECIDES (9/7/26)
--------------------------
Webull has NO option streaming. Every option bid/ask the bot owns comes from
a 1-per-second poll against a 60/min door, so with N open positions each
contract is looked at once every N seconds. That is the hard ceiling on how
fast a premium stop can react, and it is why the ratchet rungs have to be
spaced wider than our worst-case staleness.

tastytrade streams the same contracts over the socket we already hold open
for greeks. If those quotes track Webull's closely enough, promoting them
would take stop reaction from N seconds to sub-second and hand the whole
Webull request budget back to order management.

"If." That is what this tool measures, and until it has answered, the
streamed feed is taped and ignored.

WHY IT IS NOT OBVIOUSLY SAFE
----------------------------
Both feeds derive from the NBBO, but they are different snapshots taken at
different instants by different vendors. The broker actually filling you is
the one whose book should price your order. A stop that fires on a quote
your broker never saw is a stop you cannot explain afterwards.

So the question is not "are they the same" — they will not be. It is:

  * How big is the typical disagreement, in cents and in ticks?
  * How often is it big enough to move a ratchet decision?
  * Which one leads? If tastytrade sees a move first, that is the whole
    prize. If it merely sees a DIFFERENT move, that is a trap.
  * How stale is Webull's poll in practice, measured rather than assumed?

READ THE OUTPUT HONESTLY
------------------------
A small median disagreement proves nothing on its own. What matters is the
TAIL: the moments both feeds are moving fast are exactly the moments a stop
fires, and exactly when vendors diverge most. The report prints p50/p90/p99
for that reason. Judge it on p99.

MATCHING
--------
Rows are paired by nearest timestamp within a tolerance (default 1.0s).
Anything further apart is not a comparison, it is two different moments, so
it is dropped and counted rather than quietly averaged in.
"""
import argparse
import bisect
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEBULL = os.path.join(HERE, "option_tape.csv")
TASTY = os.path.join(HERE, "quote_shadow.csv")


def dx_to_occ(dx):
    """Kept as a name other code may import. Lives in occ.py since 9/7."""
    from occ import from_dx
    return from_dx(dx)


# load_webull() and load_tasty() are GONE (9/7). They each re-implemented
# reading a tape, translating a symbol format and sorting by time — the same
# job, twice, in the file that also hand-rolled the bisect join between them.
# `tape.py` does all of it once, for every source, in OCC form. See the note
# at the top of tape.py for why the READ side was consolidated and the write
# side deliberately was not.


def pct(v, p):
    if not v:
        return None
    v = sorted(v)
    i = min(len(v) - 1, max(0, int(round((p / 100.0) * (len(v) - 1)))))
    return v[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=float, default=None,
                    help="only the last N days")
    ap.add_argument("--occ", default=None, help="one contract only")
    ap.add_argument("--tol", type=float, default=1.0,
                    help="max seconds between paired rows (default 1.0)")
    a = ap.parse_args()

    import tape
    since = (time.time() - a.since * 86400) if a.since else None
    tt = tape.rows(occ=a.occ, since=since, sources=["tasty_quote"])
    wb_rows = tape.rows(occ=a.occ, since=since, sources=["webull"])
    wb = {}
    for r in wb_rows:
        if r.bid and r.ask:
            wb.setdefault(r.occ, []).append((r.ts, r.bid, r.ask))
    for k in wb:
        wb[k].sort()

    if not tt:
        print("No streamed quotes yet — quote_shadow.csv is empty.")
        print()
        print("It fills while the bridge is up and holding option positions:")
        print("the stream only carries contracts the greeks bus is watching,")
        print("and it only watches what we hold. Come back after a session.")
        return 0
    if not wb:
        print("No Webull quotes in option_tape.csv for that window — nothing")
        print("to compare against.")
        return 1

    d_bid, d_ask, d_mid, ticks, ages = [], [], [], [], []
    lead_tt = lead_wb = same = 0
    paired, unpaired, seen = 0, 0, {}

    for _r in tt:
        ts, occ, tb, ta = _r.ts, _r.occ, _r.bid, _r.ask
        if tb is None or ta is None:
            continue
        series = wb.get(occ)
        if not series:
            unpaired += 1
            continue
        times = [x[0] for x in series]
        i = bisect.bisect_left(times, ts)
        best, bestd = None, None
        for j in (i - 1, i):
            if 0 <= j < len(series):
                dd = abs(series[j][0] - ts)
                if bestd is None or dd < bestd:
                    best, bestd = series[j], dd
        if best is None or bestd > a.tol:
            unpaired += 1
            continue
        paired += 1
        seen[occ] = seen.get(occ, 0) + 1
        wts, wbid, wask = best
        ages.append(bestd)
        d_bid.append(abs(tb - wbid))
        d_ask.append(abs(ta - wask))
        tmid, wmid = (tb + ta) / 2.0, (wbid + wask) / 2.0
        d_mid.append(abs(tmid - wmid))
        # In ticks, because cents mean different things on a $0.20 contract
        # and a $12 one. SPY/QQQ are penny-quoted; everything else uses the
        # coarse grid, so this is approximate by design.
        step = 0.01 if wmid < 3.0 else 0.05
        ticks.append(abs(tmid - wmid) / step)
        if abs(tmid - wmid) < 1e-9:
            same += 1
        elif tmid > wmid:
            lead_tt += 1
        else:
            lead_wb += 1

    if not paired:
        print("Nothing paired inside %.1fs. Streamed rows: %d, Webull "
              "contracts: %d." % (a.tol, len(tt), len(wb)))
        print("If both tapes have data, the feeds never watched the same")
        print("contract at the same time — check the window with --since.")
        return 1

    print("QUOTE SHADOW — tastytrade stream vs Webull poll")
    print("=" * 62)
    print("  paired quotes      : %d across %d contract(s)" % (paired, len(seen)))
    print("  unpaired (dropped) : %d  (no Webull row inside %.1fs)"
          % (unpaired, a.tol))
    print("  median pair gap    : %.2fs" % (pct(ages, 50) or 0))
    print()
    print("  DISAGREEMENT        p50       p90       p99       max")
    for name, v in (("bid", d_bid), ("ask", d_ask), ("mid", d_mid)):
        print("    %-6s        %8s  %8s  %8s  %8s"
              % (name,
                 "$%.3f" % (pct(v, 50) or 0), "$%.3f" % (pct(v, 90) or 0),
                 "$%.3f" % (pct(v, 99) or 0), "$%.3f" % (max(v) if v else 0)))
    print("    ticks       %8s  %8s  %8s  %8s"
          % ("%.1f" % (pct(ticks, 50) or 0), "%.1f" % (pct(ticks, 90) or 0),
             "%.1f" % (pct(ticks, 99) or 0), "%.1f" % (max(ticks) if ticks else 0)))
    print()
    print("  WHO IS HIGHER      tastytrade %d · webull %d · identical %d"
          % (lead_tt, lead_wb, same))
    print()
    print("  READ p99, NOT p50. The moments both feeds move fastest are the")
    print("  moments a stop fires, and the moments vendors diverge most. A")
    print("  tight median with a wide tail is the dangerous shape.")
    print()
    print("  This says nothing about WHO IS RIGHT. Neither tape is the NBBO;")
    print("  they are two vendors' views. What it can prove is whether they")
    print("  are close enough that swapping would not change our exits — and")
    print("  a 'higher' count that is roughly even is what you want to see.")
    print("  A persistent one-sided bias means one feed is systematically")
    print("  stale, and promoting it would move every stop in one direction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
