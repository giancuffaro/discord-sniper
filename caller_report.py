"""caller_report.py — which callers are actually worth following.

    python caller_report.py                 all time
    python caller_report.py --since 30      last 30 days
    python caller_report.py --room "vero-trades"

WHY (9/6/26)
------------
`scoreboard.py` loads rooms, exports and trades and stops there. Nothing in
this project has ever grouped results BY CALLER, which means the question G
has asked in three different ways — "which rooms are worth it" — has never
had an answer computed from his own money.

The one serious open-source project in this niche does have this, and the
part worth copying is not the grouping. It is the THREE-WAY SPLIT:

    claimed   what the caller says he got
    ours      what WE got, after our entry and our ratchet

Only the second is real. When they disagree it is not necessarily dishonesty
— his fill, his size and his exits are all different from ours — but the gap
is the number that decides whether a subscription pays for itself, and it is
invisible in any per-trade view.

(The competitor has a third column, the market price at the alert timestamp,
which separates "the caller lied" from "we executed badly". We cannot build
that column from history — Webull has no historical option prices and our
tape only covers contracts we held. It fills in going forward from
`alert_decay.csv`, which telemetry.py starts recording today. Until there is
data, this report does not pretend to have that column.)

THE SAMPLE-SIZE RULE — the reason this file has an opinion
----------------------------------------------------------
20 trades at a 65% win rate is not significant (p > 0.2). ~100 trades is the
minimum that should move real money. A report that ranks a 3-trade caller
above a 90-trade caller is worse than no report, because it looks like data.

So every line carries N, and callers under the floor are printed in a
separate block marked NOT ENOUGH DATA. They are never ranked against the
others and never sorted to the top on a lucky week.

Also worth knowing when you read this: a profit factor above ~4.0 in a small
sample is a red flag for cherry-picking, not a sign of excellence.

WHAT IT MEASURES
----------------
expectancy  average $ per trade. THE number. A 40% win rate with 2:1 payoff
            beats a 70% win rate with 1:3, and only expectancy shows it.
win rate    reported, but never ranked on. It is the most misleading number
            in trading.
profit factor  gross wins / gross losses.
max drawdown %  the worst a trade went against us before it worked. This is
            the column that tells you if a caller's winners are comfortable
            or terrifying.
"""
import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(HERE, "journal.csv")

MIN_N = 20          # below this, do not rank at all
GOOD_N = 100        # at or above this, the number can move real money


def _f(v):
    try:
        if v in ("", None):
            return None
        return float(str(v).replace("$", "").replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def load(path=JOURNAL, since_days=None, room=None):
    try:
        fh = open(path, encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    rows = []
    cut = (time.time() - since_days * 86400) if since_days else None
    for r in csv.DictReader(fh):
        if room and (r.get("room") or "").strip().lower() != room.strip().lower():
            continue
        if cut:
            try:
                t = time.mktime(time.strptime((r.get("date") or "")[:10],
                                              "%Y-%m-%d"))
                if t < cut:
                    continue
            except (ValueError, OverflowError):
                pass
        if _f(r.get("P&L")) is None:
            continue                    # still open, or never priced
        rows.append(r)
    return rows


def split_own(rows):
    """Separate G's OWN hand trades from room calls.

    Found the moment this report first ran: 87 of 258 journal rows had
    caller "?" — and every one of them had a BLANK room AND a BLANK signal.
    Those are adopted positions, i.e. trades he placed himself at Webull
    that the book picked up off the account. They are not a parsing failure
    and they are not anybody's alerts.

    Left in, they were a third of the sample and they dragged the house
    numbers toward zero (65 of the 87 carry P&L 0.00). A caller scorecard
    that silently includes the user's own trades is not a scorecard.

    The test is deliberately narrow — no room AND no signal text. A room
    call that merely lost its author is a PARSING bug and must stay in the
    report as "?", loudly, instead of being quietly reclassified as his.
    """
    mine, theirs = [], []
    for r in rows:
        caller = (r.get("caller") or "").strip()
        no_room = not (r.get("room") or "").strip()
        no_sig = not (r.get("signal") or "").strip()
        if (caller in ("", "?") and no_room and no_sig) or caller == "Gian":
            mine.append(r)
        else:
            theirs.append(r)
    return mine, theirs


def score(rows):
    by = {}
    for r in rows:
        c = (r.get("caller") or "?").strip() or "?"
        b = by.setdefault(c, {"pl": [], "pct": [], "dd": [], "run": [],
                              "rooms": set(), "wins": 0, "losses": 0,
                              "gross_win": 0.0, "gross_loss": 0.0})
        pl = _f(r.get("P&L")) or 0.0
        b["pl"].append(pl)
        if r.get("room"):
            b["rooms"].add(r["room"])
        for src, dst in (("P&L %", "pct"), ("max drawdown %", "dd"),
                         ("max run-up %", "run")):
            v = _f(r.get(src))
            if v is not None:
                b[dst].append(v)
        if pl > 0:
            b["wins"] += 1
            b["gross_win"] += pl
        elif pl < 0:
            b["losses"] += 1
            b["gross_loss"] += abs(pl)

    out = {}
    for c, b in by.items():
        n = len(b["pl"])
        if not n:
            continue
        total = sum(b["pl"])
        pf = (b["gross_win"] / b["gross_loss"]) if b["gross_loss"] else None
        out[c] = {
            "n": n,
            "rooms": sorted(b["rooms"]),
            "total": round(total, 2),
            "expectancy": round(total / n, 2),
            "win_rate": round(100.0 * b["wins"] / n, 1),
            "wins": b["wins"], "losses": b["losses"],
            "profit_factor": (round(pf, 2) if pf is not None else None),
            "avg_pct": (round(sum(b["pct"]) / len(b["pct"]), 1)
                        if b["pct"] else None),
            "worst_dd": (round(min(b["dd"]), 1) if b["dd"] else None),
            "best_run": (round(max(b["run"]), 1) if b["run"] else None),
            "enough": n >= MIN_N,
            "solid": n >= GOOD_N,
        }
    return out


def _latency():
    try:
        import telemetry
        return telemetry.summary()
    except Exception:                                       # noqa: BLE001
        return {}


def render(sc, lat, title):
    hdr = ("%-20s %5s %10s %11s %7s %7s %8s %9s"
           % ("CALLER", "N", "total $", "expectancy", "win%", "PF",
              "worst dd", "fill ms"))
    print(title)
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))

    ranked = sorted([(c, v) for c, v in sc.items() if v["enough"]],
                    key=lambda kv: kv[1]["expectancy"], reverse=True)
    thin = sorted([(c, v) for c, v in sc.items() if not v["enough"]],
                  key=lambda kv: kv[1]["n"], reverse=True)

    def line(c, v):
        lt = lat.get(c) or {}
        ms = lt.get("median_total_ms")
        print("%-20s %5d %10.2f %11.2f %7.1f %7s %8s %9s%s"
              % (c[:20], v["n"], v["total"], v["expectancy"], v["win_rate"],
                 ("%.2f" % v["profit_factor"])
                 if v["profit_factor"] is not None else "-",
                 ("%.1f%%" % v["worst_dd"]) if v["worst_dd"] is not None
                 else "-",
                 ("%.0f" % ms) if ms is not None else "-",
                 "" if v["solid"] else "   <- under %d trades" % GOOD_N))

    if ranked:
        for c, v in ranked:
            line(c, v)
    else:
        print("  (nobody has %d+ closed trades yet)" % MIN_N)

    if thin:
        print()
        print("NOT ENOUGH DATA — under %d closed trades. NOT RANKED, and not"
              % MIN_N)
        print("comparable to the block above. A hot streak of six lives here.")
        print("-" * len(hdr))
        for c, v in thin:
            line(c, v)

    print()
    tot = sum(v["total"] for v in sc.values())
    n = sum(v["n"] for v in sc.values())
    print("ALL CALLERS: %d closed trades, %s$%.2f, expectancy %s$%.2f/trade"
          % (n, "+" if tot >= 0 else "-", abs(tot),
             "+" if tot >= 0 else "-", abs(tot / n) if n else 0.0))
    if not lat:
        print()
        print("No fill-latency column yet — telemetry.csv fills up as trades")
        print("fill from here on. That column is what separates 'this caller")
        print("is bad' from 'we are slow reading this room'.")


def main():
    global MIN_N
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=None,
                    help="only the last N days")
    ap.add_argument("--room", default=None, help="one room only")
    ap.add_argument("--min", type=int, default=None,
                    help="override the %d-trade ranking floor" % MIN_N)
    a = ap.parse_args()
    if a.min:
        MIN_N = a.min

    rows = load(since_days=a.since, room=a.room)
    if not rows:
        print("No closed, priced trades found in journal.csv"
              + (" for that filter." if (a.since or a.room) else "."))
        return 1
    mine, theirs = split_own(rows)
    if not theirs:
        print("No room calls in that slice — all %d rows are your own "
              "hand trades." % len(mine))
        return 1
    sc = score(theirs)
    title = "CALLER SCORECARD — %d room calls%s%s" % (
        len(theirs),
        (", last %d days" % a.since) if a.since else "",
        (", room %s" % a.room) if a.room else "")
    render(sc, _latency(), title)
    if mine:
        m = score(mine)
        tot = sum(v["total"] for v in m.values())
        n = sum(v["n"] for v in m.values())
        print()
        print("YOUR OWN TRADES, held out of the scorecard above: %d trades, "
              "%s$%.2f" % (n, "+" if tot >= 0 else "-", abs(tot)))
        print("  (adopted off the Webull account — no room, no caller, not "
              "anybody's alert)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
