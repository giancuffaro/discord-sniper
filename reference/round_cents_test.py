"""Do nickel/dime price endings mark trend reversals more than chance? -- MEASUREMENT ONLY.

G, 9/19: "in general is there a 1 dollar drop or bounce, then a .50 pullback,
how often does it keep going" (answered by LEVEL-HOLD-TEST.txt, which already
aggregates every whole-dollar break all year -- not just 714) AND "how many
times have levels ending in 10 20 30 and 05 15 25 turned trends around."

This is a DIFFERENT question from the hold test: not "does a broken level
hold," but "do prices ending in a round nickel/dime print more turning points
than chance." Method (standard round-number-effect test):

  1. ZIGZAG the 1-minute closes: a pivot is registered every time price moves
     at least THRESH ($0.15) from the last pivot in the opposite direction.
     That is every real swing high/low in the series, full year, RTH only.
  2. Take each pivot's price, keep its cents (price*100 mod 100, 0-99).
  3. TARGET = {05,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,00}
     (every nickel). DIME = the subset {00,10,20,30,40,...}. FIVE-ONLY = the
     rest of TARGET ({05,15,25,...}). CONTROL = every other cent value.
  4. BASELINE: the same cent histogram over EVERY 1-minute close in the same
     bars (not just pivots). If nickels are just common prices (they are --
     market makers quote in nickels a lot) the baseline is already nickel-
     heavy; the real test is PIVOT SHARE vs BASELINE SHARE at nickel cents.
     A ratio > 1 means pivots cluster at nickels MORE than prices do anyway.

  python reference/round_cents_test.py [SPY QQQ ...] -> reference/ROUND-CENTS-TEST.txt
"""
import csv
import glob
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M1 = os.path.join(ROOT, "bars", "stock_m1")
THRESH = 0.15


def days_for(sym):
    out = []
    for f in sorted(glob.glob(os.path.join(M1, sym + "_*.csv"))):
        closes = []
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    closes.append(float(r["c"]))
                except (KeyError, ValueError):
                    continue
        if len(closes) >= 200:
            out.append((os.path.basename(f)[len(sym) + 1:-4], closes))
    return out


def cents(px):
    return int(round(px * 100)) % 100


def zigzag(closes, thresh):
    """Every swing high/low at least `thresh` from the last one. Returns a
    list of (index, price, direction) where direction is the swing that just
    ENDED there (-1 a low after a decline, +1 a high after an advance)."""
    pivots = []
    if len(closes) < 3:
        return pivots
    last_piv_i, last_piv_px = 0, closes[0]
    direction = 0  # unknown until the first thresh move
    ext_i, ext_px = 0, closes[0]
    for i in range(1, len(closes)):
        px = closes[i]
        if direction >= 0 and px > ext_px:
            ext_i, ext_px = i, px
        if direction <= 0 and px < ext_px:
            ext_i, ext_px = i, px
        if direction <= 0 and px - last_piv_px >= thresh:
            # confirmed an up-leg from the prior low; that low is a pivot
            if direction == -1:
                pivots.append((last_piv_i, last_piv_px, -1))
            direction = 1
            last_piv_i, last_piv_px = ext_i, ext_px
            ext_i, ext_px = i, px
        elif direction >= 0 and last_piv_px - px >= thresh:
            if direction == 1:
                pivots.append((last_piv_i, last_piv_px, 1))
            direction = -1
            last_piv_i, last_piv_px = ext_i, ext_px
            ext_i, ext_px = i, px
    return pivots


DIME = set(range(0, 100, 10))
FIVE = set(range(5, 100, 10))
NICKEL = DIME | FIVE


def run(sym):
    piv_cents = Counter()
    base_cents = Counter()
    n_days = 0
    total_closes = 0
    total_pivots = 0
    for _day, closes in days_for(sym):
        n_days += 1
        for c in closes:
            base_cents[cents(c)] += 1
        total_closes += len(closes)
        for _i, px, _d in zigzag(closes, THRESH):
            piv_cents[cents(px)] += 1
            total_pivots += 1
    return dict(n_days=n_days, total_closes=total_closes, total_pivots=total_pivots,
                piv_cents=piv_cents, base_cents=base_cents)


def share(counter, keys, total):
    return 100.0 * sum(counter[k] for k in keys) / total if total else 0.0


def fmt_group(name, keys, r):
    piv_pct = share(r["piv_cents"], keys, r["total_pivots"])
    base_pct = share(r["base_cents"], keys, r["total_closes"])
    ratio = piv_pct / base_pct if base_pct else float("nan")
    return "  %-18s pivots %5.1f%%  of-all-prices %5.1f%%  ratio %5.2fx" % (name, piv_pct, base_pct, ratio)


def main():
    syms = sys.argv[1:] or ["SPY", "QQQ"]
    out = []
    P = out.append
    P("ROUND-CENTS REVERSAL TEST -- 1-minute RTH closes, zigzag pivots at >= $%.2f swings" % THRESH)
    P("PIVOTS % = share of all swing highs/lows that print at that cent ending.")
    P("OF-ALL-PRICES % = share of every 1-minute close at that cent ending (the baseline --")
    P("  nickels are already common quoted prices, so this is what a 'no effect' pivot rate looks like).")
    P("RATIO > 1x = that ending turns up as a pivot MORE than it turns up as a price at all (a real level effect).")
    P("RATIO ~= 1x = pivots just follow where price already sits most of the time -- no level effect.")
    for sym in syms:
        r = run(sym)
        P("")
        P("== %s -- %d days, %d one-minute closes, %d pivots (avg %.1f/day)"
          % (sym, r["n_days"], r["total_closes"], r["total_pivots"],
             r["total_pivots"] / r["n_days"] if r["n_days"] else 0))
        P(fmt_group("dimes (00,10,20..)", DIME, r))
        P(fmt_group("fives (05,15,25..)", FIVE, r))
        P(fmt_group("all nickels", NICKEL, r))
        P(fmt_group("G's set (05,10,15,20,25,30)", {5, 10, 15, 20, 25, 30}, r))
        P(fmt_group("CONTROL (non-nickel cents)", set(range(100)) - NICKEL, r))
        # per-decile breakdown so a single strong cent (e.g. .00 or .50) can't hide in "all nickels"
        P("  by cent (pivot% / baseline% / ratio):")
        line = "    "
        for k in sorted(NICKEL):
            piv_pct = share(r["piv_cents"], {k}, r["total_pivots"])
            base_pct = share(r["base_cents"], {k}, r["total_closes"])
            ratio = piv_pct / base_pct if base_pct else float("nan")
            line += ".%02d %4.1f/%4.1f/%4.2fx  " % (k, piv_pct, base_pct, ratio)
            if k % 5 == 0 and k % 50 == 45:
                pass
        P(line)
    text = "\n".join(out)
    with open(os.path.join(HERE, "ROUND-CENTS-TEST.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
