"""ai_scalps_backtest.py — DID THE TRADYTICS "AI SCALPS" FEED MAKE MONEY? (9/10)

G found two bot channels in Low Key Stonks and asked the only question that
matters about a signal feed: "run some of these alerts and see if they actually
made money or not."

WHAT THE FEED IS
Tradytics posts a fully specified stock trade — direction, entry, target and
stoploss:
    "Scalp Trade Idea | Bearish Continuation on 1 Day | Symbol ENPH |
     Entry 45.9 | Position Short | Target 44.4464 | Stoploss 48.6"
That is rare and welcome: nothing is left to interpretation, so it can be
scored exactly rather than argued about.

HOW THIS SCORES IT
For each idea, pull 1-minute bars from the alert forward and walk them in
order, asking which came first — the target or the stop. No modelling, no
assumptions about slippage beyond the note below:

  * ENTRY IS AT THEIR PRICE. Their entry is usually the price at the moment
    they posted, so this is generous to them: a real follower is seconds late.
  * BOTH IN ONE BAR = A LOSS. If a single minute's range covers the target AND
    the stop, this counts it a stop-out. We cannot see the order inside the
    bar and the pessimistic read is the honest one.
  * A HORIZON. A "scalp" that has not resolved in a day is not a scalp; the
    default is one trading day, and whatever the position is worth at that
    point is the result. --days changes it.

WHAT IT REPORTS
Hit rate is NOT the answer and is deliberately not the headline. These setups
have wildly different reward:risk — some risk $13 to make $8, others risk $2
to make $5 — so a 60% win rate can still lose money. The headline is the
EXPECTANCY: average dollars per $1 risked, which is the only number that says
whether following the feed pays.

Usage:  python3 ai_scalps_backtest.py [--days 1] [--in /tmp/scalps.json]
Needs execution.tradier.access_token in settings.json (read-only market data).
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://api.tradier.com/v1"


def _token():
    with open(os.path.join(HERE, "settings.json"), "r", encoding="utf-8") as fh:
        s = json.load(fh)
    tok = (((s.get("execution") or {}).get("tradier") or {}).get("access_token") or "")
    if not tok:
        sys.exit("No Tradier token in settings.json (execution.tradier.access_token).")
    return tok


def bars(symbol, start, end, token):
    """1-minute OHLC between two datetimes. [] when the API has nothing."""
    q = urllib.parse.urlencode({
        "symbol": symbol, "interval": "1min",
        "start": start.strftime("%Y-%m-%d %H:%M"),
        "end": end.strftime("%Y-%m-%d %H:%M"),
        "session_filter": "open",
    })
    req = urllib.request.Request(
        BASE + "/markets/timesales?" + q,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except Exception as e:                                   # noqa: BLE001
        print("  ! %s: %s" % (symbol, e))
        return []
    series = (d.get("series") or {}).get("data") or []
    if isinstance(series, dict):
        series = [series]
    return series


def daily(symbol, start, end, token):
    """DAILY OHLC — the fallback, and why it exists.

    Tradier only keeps 1-minute history for about the last three weeks, and 35
    of these 48 ideas are older than that. Scoring only the recent 13 would
    have meant reporting n=11, which answers nothing.

    Daily bars cost resolution: inside one day we cannot see whether the target
    or the stop came first, so a day whose range covers BOTH is scored a STOP.
    That is pessimistic by construction and it is the right way round — a
    backtest that resolves its own ambiguity in the strategy's favour is
    worthless. Every row scored this way is marked "d" in the output.
    """
    q = urllib.parse.urlencode({
        "symbol": symbol, "interval": "daily",
        "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")})
    req = urllib.request.Request(
        BASE + "/markets/history?" + q,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except Exception as e:                                   # noqa: BLE001
        print("  ! %s daily: %s" % (symbol, e))
        return []
    day = (d.get("history") or {}).get("day") or []
    if isinstance(day, dict):
        day = [day]
    return day


def walk(rows, entry, target, stop, is_long):
    """Which came first. -> (outcome, exit_price, minutes_taken)."""
    for i, b in enumerate(rows):
        hi, lo = float(b.get("high", 0)), float(b.get("low", 0))
        if is_long:
            hit_t, hit_s = hi >= target, lo <= stop
        else:
            hit_t, hit_s = lo <= target, hi >= stop
        # BOTH IN ONE BAR -> the loss. We cannot see the order within a
        # minute, and assuming the good one is how a backtest lies.
        if hit_s:
            return ("STOP", stop, i)
        if hit_t:
            return ("TARGET", target, i)
    if not rows:
        return ("NO DATA", None, 0)
    return ("OPEN", float(rows[-1].get("close", entry)), len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1,
                    help="trading-day horizon before giving up (default 1)")
    ap.add_argument("--in", dest="src", default="/tmp/scalps.json")
    a = ap.parse_args()
    token = _token()
    with open(a.src, "r", encoding="utf-8") as fh:
        ideas = json.load(fh)

    out, skipped = [], 0
    for when, sym, pos, entry, target, stop in ideas:
        try:
            t0 = dt.datetime.strptime(when, "%m/%d/%y %H:%M")
        except ValueError:
            skipped += 1
            continue
        is_long = pos.lower() == "long"
        # THE FEED'S OWN BROKEN ROWS. Two of 48 put the TARGET on the wrong
        # side of the entry (SPOT Long 496 -> target 494.52). Those are not
        # tradeable instructions at all; counted and excluded, not silently
        # scored as losers, because the fault is the publisher's not the idea's.
        if (is_long and target <= entry) or ((not is_long) and target >= entry):
            out.append((when, sym, pos, "BROKEN", 0.0, 0.0, 0, "-"))
            continue
        risk = abs(entry - stop)
        if risk <= 0:
            skipped += 1
            continue
        rows = bars(sym, t0, t0 + dt.timedelta(days=a.days + 3), token)
        rows = [b for b in rows if b.get("time", "") >= t0.strftime("%Y-%m-%dT%H:%M")]
        # a trading day is ~390 minutes
        rows = rows[:390 * a.days]
        res = "m"
        if not rows:
            # Older than Tradier's intraday window — fall back to daily bars.
            d = daily(sym, t0.date(), t0.date() + dt.timedelta(days=a.days + 6), token)
            d = [b for b in d if b.get("date", "") >= t0.strftime("%Y-%m-%d")]
            rows = d[:a.days + 1]
            res = "d"
        outcome, px, mins = walk(rows, entry, target, stop, is_long)
        if res == "d":
            mins = 0
        if outcome == "NO DATA":
            out.append((when, sym, pos, "NO DATA", 0.0, 0.0, 0, "-"))
            continue
        pnl = (px - entry) if is_long else (entry - px)
        out.append((when, sym, pos, outcome, pnl, pnl / risk, mins, res))

    real = [r for r in out if r[3] in ("TARGET", "STOP", "OPEN")]
    print("=" * 74)
    print("TRADYTICS AI-SCALPS — %d ideas, %d scoreable, horizon %d trading day(s)"
          % (len(ideas), len(real), a.days))
    print("=" * 74)
    for when, sym, pos, outcome, pnl, r_mult, mins, res in out:
        print("  %-15s %-6s %-5s %-7s %8s  %6s R  %s%s"
              % (when, sym, pos, outcome,
                 ("%+.2f" % pnl) if outcome in ("TARGET", "STOP", "OPEN") else "-",
                 ("%+.2f" % r_mult) if outcome in ("TARGET", "STOP", "OPEN") else "-",
                 ("%dm" % mins) if mins else "",
                 "  [daily bars]" if res == "d" and outcome != "NO DATA" else ""))
    if not real:
        print("\nNothing scoreable.")
        return
    wins = [r for r in real if r[3] == "TARGET"]
    losses = [r for r in real if r[3] == "STOP"]
    rs = [r[5] for r in real]
    exp = sum(rs) / len(rs)
    print("-" * 74)
    print("  target first : %d" % len(wins))
    print("  stopped out  : %d" % len(losses))
    print("  unresolved   : %d  (marked to the close of the horizon)"
          % len([r for r in real if r[3] == "OPEN"]))
    print("  broken rows  : %d  (target on the wrong side of the entry)"
          % len([r for r in out if r[3] == "BROKEN"]))
    print("  no data      : %d" % len([r for r in out if r[3] == "NO DATA"]))
    print("  hit rate     : %.0f%%   <- NOT the answer, see below"
          % (100.0 * len(wins) / len(real)))
    print()
    print("  EXPECTANCY   : %+.3f R per trade" % exp)
    print("     (R = one unit of the risk THEY defined, entry to their stop.)")
    # The honest error bar: standard error of the mean R.
    if len(rs) > 1:
        mean = exp
        var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)
        se = (var / len(rs)) ** 0.5
        print("  std error    : %.3f R   ->  %+.3f to %+.3f at 2 SE"
              % (se, exp - 2 * se, exp + 2 * se))
        print()
        if exp - 2 * se > 0:
            print("  VERDICT: positive, and clear of its own error bar.")
        elif exp + 2 * se < 0:
            print("  VERDICT: NEGATIVE, and clear of its own error bar. Following")
            print("           this feed loses money.")
        else:
            print("  VERDICT: INSIDE THE NOISE. At n=%d this feed cannot be shown"
                  % len(real))
            print("           to make or lose money. Not a reason to trade it —")
            print("           a reason not to bet on it yet.")


if __name__ == "__main__":
    main()
