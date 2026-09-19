"""Does the next whole-dollar level HOLD after a break? — MEASUREMENT ONLY.

G, 9/19: "in a downtrend, when breaking a level say 714, how many times has it
gone down to 713, just to bounce to 713.50 and then go to 712.5? what % does
it hold 713 and how many times does it keep going down, or vice versa."

On 1-minute stock bars (bars/stock_m1/<SYM>_<day>.csv, RTH):
  BREAK of whole dollar L (down): the prior close was at or above L and this
  close is below it (mirrored for up). The break bar is not in the first 5
  minutes. "Trend" rows keep only breaks with the close on the far side of
  the 20-minute EMA and that EMA moving the same way over the last 10 minutes.
  TOUCH: the first bar within REACH_MIN minutes whose low prints L-1 (the next
  dollar), the break bar included.
  Then, within HOLD_MIN minutes after the touch, in the order the bars come:
    through-in-touch-minute  the touch bar itself printed L-1.50 (order inside
                             the minute is unknowable -> counted as CONTINUED)
    straight through         L-1.50 printed before any L-0.50 bounce
    bounce then through      L-0.50 printed first, then L-1.50 later
    bounce then reclaim      L-0.50 printed, then L itself (the broken level)
    bounce, held             L-0.50 printed, never L-1.50 nor L in the window
    stalled                  neither L-0.50 nor L-1.50 in the window
  HOLDS = never printed L-1.50 in the window after the touch.
  CONTINUED = printed L-1.50 (straight, in the touch minute, or after a bounce).
  A bar that prints both L-0.50 and L-1.50 counts as CONTINUED (it traded at
  L-1.50 within a minute of the touch; whether the bounce came first is not
  in the data).
  CONTROL: the same machine with the "level" moved to the half dollar
  (713.50 / 712.50 / bounce 713.00 / through 712.00). If whole dollars are
  special, the whole-dollar rows differ from the control rows.

  python reference/level_hold_test.py [SPY QQQ ...]   -> reference/LEVEL-HOLD-TEST.txt
"""
import csv
import glob
import math
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M1 = os.path.join(ROOT, "bars", "stock_m1")
REACH_MIN = 60
HOLD_MIN = 30
SKIP_OPEN = 5


def days_for(sym):
    out = []
    for f in sorted(glob.glob(os.path.join(M1, sym + "_*.csv"))):
        rows = []
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append((float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])))
                except (KeyError, ValueError):
                    continue
        if len(rows) >= 200:
            out.append((os.path.basename(f)[len(sym) + 1:-4], rows))
    return out


def ema(vals, n):
    k = 2.0 / (n + 1)
    out, e = [], None
    for v in vals:
        e = v if e is None else e + k * (v - e)
        out.append(e)
    return out


def outcomes(rows, i, s, L, offset):
    """One break at bar i of level L (direction s: -1 down, +1 up). Returns
    (reached, outcome) with outcome one of the six words above or None."""
    nxt = L + s * 1.0                # the next dollar (713 for a down-break of 714)
    bounce = L + s * 0.5             # the half-dollar bounce (713.50)
    through = L + s * 1.5            # the next half dollar past it (712.50)
    n = len(rows)
    hit = lambda k, px: (rows[k][2] <= px) if s < 0 else (rows[k][1] >= px)      # low/high reached px
    back = lambda k, px: (rows[k][1] >= px) if s < 0 else (rows[k][2] <= px)     # the bounce side
    t = None
    for k in range(i, min(n, i + REACH_MIN + 1)):
        if hit(k, nxt):
            t = k
            break
    if t is None:
        return False, None
    if hit(t, through):
        return True, "through in touch minute"
    end = min(n, t + HOLD_MIN + 1)
    for k in range(t + 1, end):
        b, th = back(k, bounce), hit(k, through)
        if th:
            return True, "straight through"        # both in one bar counts here too
        if b:
            for m in range(k + 1, end):
                if hit(m, through):
                    return True, "bounce then through"
                if back(m, L):
                    return True, "bounce then reclaim"
            return True, "bounce, held"
    return True, "stalled"


def run(sym, offset=0.0):
    """offset 0 = whole dollars; 0.5 = the half-dollar control."""
    res = {}
    for key in ("down", "down trend", "up", "up trend"):
        res[key] = dict(breaks=0, reached=0, out=Counter())
    for _day, rows in days_for(sym):
        closes = [r[3] for r in rows]
        e20 = ema(closes, 20)
        for i in range(SKIP_OPEN + 1, len(rows) - 2):
            c0, c1 = closes[i - 1], closes[i]
            for s, key in ((-1, "down"), (1, "up")):
                if s < 0:
                    L = math.floor(c0 - offset) + offset
                    if not (c0 >= L and c1 < L):
                        continue
                else:
                    L = math.ceil(c0 - offset) + offset
                    if not (c0 <= L and c1 > L):
                        continue
                trend = (c1 < e20[i] and e20[i] < e20[i - 10]) if s < 0 else (c1 > e20[i] and e20[i] > e20[i - 10])
                reached, out = outcomes(rows, i, s, L, offset)
                for k in ((key, key + " trend") if trend else (key,)):
                    r = res[k]
                    r["breaks"] += 1
                    if reached:
                        r["reached"] += 1
                        r["out"][out] += 1
    return res


ORDER = ["through in touch minute", "straight through", "bounce then through",
         "bounce then reclaim", "bounce, held", "stalled"]
CONT = ("through in touch minute", "straight through", "bounce then through")


def fmt(sym, label, r):
    n = r["reached"]
    if not r["breaks"]:
        return "  %-14s no breaks" % label
    cont = sum(r["out"][k] for k in CONT)
    held = n - cont
    bounced = r["out"]["bounce then through"] + r["out"]["bounce then reclaim"] + r["out"]["bounce, held"]
    pct = lambda a, b: ("%3.0f%%" % (100.0 * a / b)) if b else "  --"
    line = ("  %-14s breaks %4d  reached next $ %4d (%s)  | HOLDS %s  CONTINUES %s  | "
            % (label, r["breaks"], n, pct(n, r["breaks"]), pct(held, n), pct(cont, n)))
    line += "  ".join("%s %s" % (k.replace("through in touch minute", "thru@touch").replace("straight through", "straight")
                                  .replace("bounce then through", "bounce->thru").replace("bounce then reclaim", "bounce->reclaim")
                                  .replace("bounce, held", "bounce,held"), pct(r["out"][k], n)) for k in ORDER)
    if bounced:
        line += "  | of the bounces: %s went on through, %s reclaimed the broken $" % (
            pct(r["out"]["bounce then through"], bounced), pct(r["out"]["bounce then reclaim"], bounced))
    return line


def main():
    syms = sys.argv[1:] or ["SPY", "QQQ"]
    out = []
    P = out.append
    P("NEXT-DOLLAR HOLD TEST — 1-minute RTH bars; a break of whole dollar L, the touch of the next dollar within %d min, "
      "the outcome within %d min of the touch (definitions in the file header)" % (REACH_MIN, HOLD_MIN))
    P("HOLDS = never printed the next half dollar past the level (L-1.50 down / L+1.50 up) after touching it; "
      "CONTINUES = did. 'bounce->thru' is G's exact case: to 713, up to 713.50, then 712.50.")
    P("CONTROL rows do the same on half-dollar levels — if whole dollars are special, the two differ.")
    for sym in syms:
        days = days_for(sym)
        P("")
        P("== %s — %d days (%s .. %s)" % (sym, len(days), days[0][0] if days else "-", days[-1][0] if days else "-"))
        for offset, tag in ((0.0, "whole $"), (0.5, "CONTROL half $")):
            r = run(sym, offset)
            P(" %s" % tag)
            for key in ("down", "down trend", "up", "up trend"):
                P(fmt(sym, key, r[key]))
    text = "\n".join(out)
    with open(os.path.join(HERE, "LEVEL-HOLD-TEST.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
