"""orb_backtest.py — Opening Range Breakout backtest on real NQ 1-minute bars.

Built 2026-09-15 to answer Gian's ask for "a strategy that could be
profitable most days" as a testable, wireable systematic play (as opposed
to depending entirely on what a Discord room calls). READ-ONLY: loads
bars\\NQ_1m_2026-08-03_2026-09-12.csv, simulates trades, writes a report.
Does not import bridge.py/positions.py, does not touch settings.json, does
not place anything anywhere.

THE STRATEGY (classic ORB, adapted for NQ/MNQ futures)
--------------------------------------------------------
1. Mark the high/low of the first N minutes after the 9:30 ET stock-market
   open (index futures move on the same open even though they trade nearly
   24h) -- the "opening range."
2. Long if price breaks above the range high; short if it breaks below the
   range low. Skip the day if price never breaks either side by the cutoff
   time.
3. Stop: the OPPOSITE side of the opening range (a full round-trip through
   the range invalidates the breakout).
4. Profit: ride it with the SAME ratchet shape already proven in this repo
   (ratchet_tiers.py's arm/lock/step, expressed in points instead of %),
   so the exit logic that already works for options gets reused here
   almost unchanged.
5. Hard flatten at the daily cutoff (16:00 ET) -- no overnight futures risk
   from this strategy, ever.

This is a WELL-KNOWN, decades-old setup (Toby Crabel and others formalized
it in the 90s) -- the honest pitch is "well-studied and easy to systematize
cleanly," not "a secret edge." Whether it's actually profitable on THIS
instrument in THIS regime is exactly what this backtest checks, on the
~5.5 weeks of real 1-minute NQ data already sitting in bars\\.

USAGE
-----
  python orb_backtest.py --or-minutes 15 --stop-mode range --arm-pts 40 --step-pts 40
  python orb_backtest.py --sweep     # tries a grid of OR windows and reports the best

HONEST LIMITS (read before trusting any number this prints)
-------------------------------------------------------------
- ~5.5 weeks of one instrument, one regime. This is a screening backtest,
  not a verdict -- exactly the same caveat ratchet_sweep_fine.py gives itself.
- 1-minute bars, not tick data: this can't model getting stopped out and
  re-triggering within the same bar, and open==prior close is assumed for
  gap handling (fine for continuous futures, not literally true).
- No commissions/slippage modeled beyond a fixed --slippage-pts assumption
  (defaults to 1 tick = 0.25pt for NQ). Real fills will be a bit worse.
- The data file only spans one calendar stretch (early Aug - mid Sept), so
  this cannot see how ORB behaves across different volatility regimes
  (e.g. earnings weeks, FOMC weeks, holidays) beyond whatever occurred in
  that window.
"""
import argparse
import csv
import os
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.join(HERE, "bars", "NQ_1m_2026-08-03_2026-09-12.csv")

TICK = 0.25          # NQ tick size, points
MULT = 20.0          # $ per point per contract (NQ full-size; MNQ = 2.0)


def load_bars(path):
    """Load 1-min bars, convert UTC timestamps to US/Eastern wall time."""
    from eastern import ET
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                ts_utc = datetime.strptime(r["ts_event"][:19], "%Y-%m-%d %H:%M:%S")
            except (KeyError, ValueError):
                continue
            # ts_event carries +00:00 (UTC). Convert to ET wall clock.
            from datetime import timezone
            ts_utc = ts_utc.replace(tzinfo=timezone.utc)
            ts_et = ts_utc.astimezone(ET)
            try:
                rows.append({
                    "t": ts_et,
                    "o": float(r["open"]), "h": float(r["high"]),
                    "l": float(r["low"]), "c": float(r["close"]),
                    "v": float(r.get("volume") or 0),
                })
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: r["t"])
    return rows


def group_by_session_day(rows):
    """Bucket bars into trading days by ET calendar date. Futures bars can
    span into the prior evening (the overnight session); we only look at
    RTH-anchored bars (>= 09:30 ET) per day for this strategy, so evening
    bars naturally get filtered out downstream, not here."""
    days = {}
    for r in rows:
        key = r["t"].date()
        days.setdefault(key, []).append(r)
    return days


def run_one_day(bars, or_minutes, stop_mode, arm_pts, step_pts,
                 flatten_hour=16, flatten_minute=0, slippage_pts=0.25):
    """Simulate ORB on one day's bars. Returns a dict or None if skipped."""
    rth = [b for b in bars if b["t"].hour >= 9 and
           (b["t"].hour, b["t"].minute) >= (9, 30)]
    if len(rth) < or_minutes + 5:
        return None

    or_bars = rth[:or_minutes]
    or_high = max(b["h"] for b in or_bars)
    or_low = min(b["l"] for b in or_bars)
    or_range = or_high - or_low
    if or_range <= 0:
        return None

    rest = rth[or_minutes:]
    direction = None
    entry = None
    entry_t = None
    for b in rest:
        if b["h"] > or_high:
            direction, entry, entry_t = "long", or_high + slippage_pts, b["t"]
            break
        if b["l"] < or_low:
            direction, entry, entry_t = "short", or_low - slippage_pts, b["t"]
            break
    if direction is None:
        return {"date": bars[0]["t"].date(), "traded": False, "pnl_pts": 0.0,
                "reason": "no breakout"}

    sign = 1.0 if direction == "long" else -1.0
    if stop_mode == "range":
        stop = or_low if direction == "long" else or_high
    else:
        stop = entry - sign * or_range  # 1x range as stop distance fallback

    armed = False
    peak = entry
    exit_price, reason = None, None
    after_entry = [b for b in rest if b["t"] >= entry_t]
    for b in after_entry:
        # use close as the reference price (bar-close granularity, see docstring)
        price = b["c"]
        gain_pts = (price - entry) * sign
        if direction == "long":
            peak = max(peak, b["h"])
        else:
            peak = min(peak, b["l"])

        if arm_pts is not None and gain_pts >= arm_pts:
            armed = True
        if armed and step_pts:
            rungs = int((gain_pts - arm_pts) // step_pts) + 1
            locked = rungs * step_pts * 0.5  # locks half of each rung, conservative
            candidate = entry + sign * locked
            stop = max(stop, candidate) if direction == "long" else min(stop, candidate)

        hit_stop = (b["l"] <= stop) if direction == "long" else (b["h"] >= stop)
        if hit_stop:
            exit_price, reason = stop, "stop"
            break

        if (b["t"].hour, b["t"].minute) >= (flatten_hour, flatten_minute):
            exit_price, reason = price, "flatten"
            break

    if exit_price is None:
        exit_price, reason = after_entry[-1]["c"], "data ended"

    pnl_pts = (exit_price - entry) * sign - slippage_pts  # exit slippage too
    return {
        "date": bars[0]["t"].date(), "traded": True, "direction": direction,
        "entry": entry, "exit": exit_price, "pnl_pts": pnl_pts, "reason": reason,
        "or_range": or_range,
    }


def backtest(path, or_minutes=15, stop_mode="range", arm_pts=40.0,
             step_pts=40.0, slippage_pts=0.25, qty=1, mult=MULT):
    rows = load_bars(path)
    days = group_by_session_day(rows)
    results = []
    for _date, bars in sorted(days.items()):
        r = run_one_day(bars, or_minutes, stop_mode, arm_pts, step_pts,
                         slippage_pts=slippage_pts)
        if r:
            results.append(r)
    return results


def summarize(results, qty=1, mult=MULT):
    traded = [r for r in results if r.get("traded")]
    total_days = len(results)
    n = len(traded)
    wins = [r for r in traded if r["pnl_pts"] > 0]
    losses = [r for r in traded if r["pnl_pts"] <= 0]
    total_pts = sum(r["pnl_pts"] for r in traded)
    total_dollars = total_pts * mult * qty
    win_rate = (len(wins) / n * 100.0) if n else 0.0
    avg_win = (sum(r["pnl_pts"] for r in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(r["pnl_pts"] for r in losses) / len(losses)) if losses else 0.0
    return {
        "calendar_days": total_days, "days_traded": n,
        "no_breakout_days": total_days - n,
        "win_rate_pct": win_rate, "total_pts": total_pts,
        "total_dollars": total_dollars, "avg_win_pts": avg_win,
        "avg_loss_pts": avg_loss,
        "avg_dollars_per_traded_day": (total_dollars / n) if n else 0.0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=DEFAULT_DATA)
    p.add_argument("--or-minutes", type=int, default=15)
    p.add_argument("--stop-mode", choices=["range", "1x"], default="range")
    p.add_argument("--arm-pts", type=float, default=40.0)
    p.add_argument("--step-pts", type=float, default=40.0)
    p.add_argument("--slippage-pts", type=float, default=0.25)
    p.add_argument("--qty", type=int, default=1)
    p.add_argument("--mult", type=float, default=MULT)
    p.add_argument("--sweep", action="store_true",
                   help="try a grid of OR windows / arm-step combos, print the top 10")
    p.add_argument("--csv-out")
    args = p.parse_args()

    if args.sweep:
        grid = []
        for orm in (5, 10, 15, 20, 30):
            for arm in (20.0, 30.0, 40.0, 60.0):
                for step in (20.0, 40.0, 60.0):
                    res = backtest(args.data, or_minutes=orm, stop_mode=args.stop_mode,
                                    arm_pts=arm, step_pts=step,
                                    slippage_pts=args.slippage_pts,
                                    qty=args.qty, mult=args.mult)
                    s = summarize(res, qty=args.qty, mult=args.mult)
                    grid.append((orm, arm, step, s))
        grid.sort(key=lambda x: x[3]["total_dollars"], reverse=True)
        print("%-6s %-6s %-6s %8s %8s %10s %10s" %
              ("OR-min", "arm", "step", "days", "win%", "$total", "$/day"))
        for orm, arm, step, s in grid[:10]:
            print("%-6d %-6.0f %-6.0f %8d %7.1f%% %10.2f %10.2f" %
                  (orm, arm, step, s["days_traded"], s["win_rate_pct"],
                   s["total_dollars"], s["avg_dollars_per_traded_day"]))
        return

    results = backtest(args.data, or_minutes=args.or_minutes, stop_mode=args.stop_mode,
                        arm_pts=args.arm_pts, step_pts=args.step_pts,
                        slippage_pts=args.slippage_pts, qty=args.qty, mult=args.mult)
    s = summarize(results, qty=args.qty, mult=args.mult)
    print("Opening Range Breakout — %s" % os.path.basename(args.data))
    print("OR window: %d min   stop: %s   arm: %.0fpt   step: %.0fpt   qty: %d"
          % (args.or_minutes, args.stop_mode, args.arm_pts, args.step_pts, args.qty))
    print("-" * 60)
    print("calendar days seen:     %d" % s["calendar_days"])
    print("days with a breakout:   %d" % s["days_traded"])
    print("no-breakout days:       %d" % s["no_breakout_days"])
    print("win rate (traded days): %.1f%%" % s["win_rate_pct"])
    print("avg win:                %+.2f pts" % s["avg_win_pts"])
    print("avg loss:               %+.2f pts" % s["avg_loss_pts"])
    print("TOTAL P&L:              $%+.2f  (%.2f pts)" % (s["total_dollars"], s["total_pts"]))
    print("avg $ per traded day:   $%+.2f" % s["avg_dollars_per_traded_day"])

    if args.csv_out:
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "traded", "direction", "entry", "exit", "pnl_pts", "reason"])
            for r in results:
                w.writerow([r.get("date"), r.get("traded"), r.get("direction"),
                            r.get("entry"), r.get("exit"), r.get("pnl_pts"), r.get("reason")])
        print("per-day detail written to %s" % args.csv_out)


if __name__ == "__main__":
    main()
