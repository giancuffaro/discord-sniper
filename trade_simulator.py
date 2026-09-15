"""trade_simulator.py — quick "what if" stop/trailing-take-profit simulator.

Built 2026-09-15 at Gian's request: a standalone, READ-ONLY tool to try out
made-up stop-loss and trailing-take-profit rules against either real
historical data already sitting in this folder (option tick tape, futures
1-minute bars) or a fully made-up price path — without touching the live
bridge, the ledger, or any broker connection. Nothing in here places an
order, imports bridge.py/positions.py, or writes to any file the live bot
reads. It only reads CSVs you point it at and prints/writes a result.

This is DELIBERATELY simpler than ratchet_sweep_fine.py (which does careful
per-second replay across every rule in this codebase, tick-floors, spread
floors, and real fills). Use ratchet_sweep_fine.py when you want a rigorous
answer about the LIVE ratchet. Use this when you want a fast answer to an
arbitrary "what if I'd used a 12% stop and a 4% trail" question, on real or
made-up data, for either options or futures.

THREE MODES
-----------
  options    — replay a real option tick tape (ts,occ,bid,ask), e.g.
               option_tape.csv or databento_tape.csv in this folder.
  futures    — replay real 1-minute futures bars from bars/*.csv
               (auto-detects the two header shapes already in this repo).
  synthetic  — a price path you type in, or a quick random-walk generator,
               for pure "does this rule even make sense" sanity checks.

EXIT RULE KNOBS (mix and match; all optional except one stop)
---------------------------------------------------------------
  --stop-pct N        born stop, N% under entry (long) / over entry (short)
  --stop-dollar N     born stop, N points/dollars away instead of a percent
  --arm-pct N         gain%% at which the ratchet switches on (else the born
                      stop never moves)
  --lock-pct N        what the stop locks to the moment it arms (0 = breakeven)
  --step-pct N        DISCRETE ratchet: every further N%% of gain locks
                      another N%% of profit (mirrors ratchet_tiers.py's style)
  --trail-pct N       CONTINUOUS trailing stop: once armed, stop always sits
                      N%% below the best price seen so far (true trailing
                      take-profit; use this OR --step-pct, not both)
  --trail-dollar N    same as --trail-pct but a flat point/dollar distance
  --take-profit-pct N hard ceiling: close the WHOLE position the instant
                      gain reaches N%%, no matter what the ratchet is doing
  --qty N             contracts (options) or contracts/lots (futures)
  --mult N            $ per 1.0 of price move per contract (options default
                      100; futures: looked up by --symbol, override here)

EXAMPLES
--------
  # Real SPY option tape, try a 25% stop / arm at 8% / trail 6% continuously
  python trade_simulator.py options --data option_tape.csv \\
      --occ SPY260902C00767000 --stop-pct 25 --arm-pct 8 --trail-pct 6

  # Real NQ futures bars, long from the first bar's open, 20pt stop,
  # arm at 15pt, then trail 10pt behind the high
  python trade_simulator.py futures --data bars\\NQ_1m_2026-08-03_2026-09-12.csv \\
      --direction long --stop-dollar 20 --arm-pct 0.35 --trail-dollar 10

  # Fully made-up price path, no data file needed
  python trade_simulator.py synthetic --prices 100,103,101,108,106,115,112 \\
      --stop-pct 5 --arm-pct 4 --step-pct 3

  # Made-up random walk, 200 one-minute steps, quick gut check
  python trade_simulator.py synthetic --random-walk --start 5.00 --steps 200 \\
      --vol 0.05 --drift 0.002 --stop-pct 20 --arm-pct 10 --trail-pct 8
"""
import argparse
import csv
import glob
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BARS_DIR = os.path.join(HERE, "bars")

# $ per 1.0 point of price move, per contract/lot. Micro contracts use the
# "M" prefix. Extend this table as needed -- it's just a convenience lookup
# for --mult; you can always pass --mult directly and skip --symbol.
FUTURES_MULT = {
    "ES": 50.0, "MES": 5.0,
    "NQ": 20.0, "MNQ": 2.0,
    "RTY": 50.0, "M2K": 5.0,
    "YM": 5.0, "MYM": 0.5,
    "GC": 100.0, "MGC": 10.0,
    "SI": 5000.0, "SIL": 1000.0,
    "CL": 1000.0, "MCL": 100.0,
}


# --------------------------------------------------------------------------
# Data loaders — all return a plain list of (timestamp, price) tuples.
# One price per tick is a deliberate simplification (see module docstring):
# for options that's the bid (what you'd actually get filled at on exit),
# for futures bars that's the close. If you need intrabar high/low
# precision, use ratchet_sweep_fine.py instead.
# --------------------------------------------------------------------------

def load_option_tape(path, occ=None):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if occ and r.get("occ") != occ:
                continue
            try:
                rows.append((float(r["ts"]), float(r["bid"])))
            except (KeyError, TypeError, ValueError):
                continue
    rows.sort(key=lambda x: x[0])
    if not rows:
        raise SystemExit(
            "No rows found in %s%s. Check the path and --occ filter."
            % (path, (" for occ=%s" % occ) if occ else "")
        )
    return rows


def load_futures_bars(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = [c.lower() for c in (reader.fieldnames or [])]
        # This repo has two bar header shapes in the wild:
        #   time,open,high,low,close,volume   (NQ_bars.csv style)
        #   ts,o,h,l,c                         (bars/stock/*.csv style)
        close_key = "close" if "close" in fieldnames else "c"
        time_key = "time" if "time" in fieldnames else "ts"
        for i, r in enumerate(reader):
            lr = {k.lower(): v for k, v in r.items()}
            try:
                price = float(lr[close_key])
            except (KeyError, TypeError, ValueError):
                continue
            t = lr.get(time_key, i)
            try:
                t = float(t)
            except (TypeError, ValueError):
                t = i  # ISO timestamp string -> just use row order
            rows.append((t, price))
    if not rows:
        raise SystemExit("No usable rows found in %s" % path)
    return rows


def resolve_futures_path(data_arg, symbol_arg):
    if data_arg:
        return data_arg
    if not symbol_arg:
        raise SystemExit("futures mode needs --data <path> or --symbol <e.g. NQ>")
    hits = sorted(glob.glob(os.path.join(BARS_DIR, "%s_*.csv" % symbol_arg.upper())))
    hits += sorted(glob.glob(os.path.join(BARS_DIR, "%s.csv" % symbol_arg.upper())))
    if not hits:
        raise SystemExit(
            "No bars\\%s*.csv found. Pass --data <path> to point at a file directly."
            % symbol_arg.upper()
        )
    return hits[-1]  # most recent by name (files are date-stamped)


def make_synthetic(prices_arg, random_walk, start, steps, vol, drift, seed):
    if prices_arg:
        vals = [float(x) for x in prices_arg.split(",") if x.strip()]
        if len(vals) < 2:
            raise SystemExit("--prices needs at least 2 comma-separated numbers")
        return [(i, v) for i, v in enumerate(vals)]
    if random_walk:
        rng = random.Random(seed)
        price = start
        rows = [(0, price)]
        for i in range(1, steps + 1):
            price = max(0.01, price + rng.gauss(drift, vol))
            rows.append((i, price))
        return rows
    raise SystemExit("synthetic mode needs --prices \"a,b,c\" or --random-walk")


# --------------------------------------------------------------------------
# The simulator itself.
# --------------------------------------------------------------------------

def simulate(ticks, direction, entry, stop_pct=None, stop_dollar=None,
             arm_pct=None, lock_pct=0.0, step_pct=None, trail_pct=None,
             trail_dollar=None, take_profit_pct=None):
    if stop_pct is None and stop_dollar is None:
        raise SystemExit("need at least --stop-pct or --stop-dollar")
    if step_pct and trail_pct:
        raise SystemExit("use --step-pct OR --trail-pct, not both")
    if step_pct and trail_dollar:
        raise SystemExit("use --step-pct OR --trail-dollar, not both")

    long = (direction == "long")
    sign = 1.0 if long else -1.0

    if stop_dollar is not None:
        stop = entry - sign * stop_dollar
    else:
        stop = entry * (1.0 - sign * stop_pct / 100.0)

    armed = False
    peak = entry  # best price seen so far (highest for long, lowest for short)
    trace = []

    for t, price in ticks:
        gain_pct = (price - entry) / entry * 100.0 * sign
        if long:
            peak = max(peak, price)
        else:
            peak = min(peak, price)

        # 1. hard take-profit ceiling, checked first — closes everything
        if take_profit_pct is not None and gain_pct >= take_profit_pct:
            trace.append((t, price, gain_pct, stop, "take-profit"))
            return _result(entry, price, gain_pct, "take-profit", t, trace)

        # 2. arm the ratchet once gain clears arm_pct
        if arm_pct is not None and gain_pct >= arm_pct:
            armed = True

        # 3. move the stop, never backwards
        if armed:
            if step_pct:
                rungs = int((gain_pct - arm_pct + 1e-9) // step_pct)
                locked_pct = lock_pct + step_pct * max(rungs, 0)
                candidate = entry * (1.0 + sign * locked_pct / 100.0)
            elif trail_pct:
                candidate = peak * (1.0 - sign * trail_pct / 100.0)
            elif trail_dollar:
                candidate = peak - sign * trail_dollar
            else:
                candidate = entry * (1.0 + sign * lock_pct / 100.0)
            stop = max(stop, candidate) if long else min(stop, candidate)

        trace.append((t, price, gain_pct, stop, ""))

        # 4. stop check, last — a stop that was just moved can still be hit
        #    by this same tick, which is the conservative/correct order.
        hit = (price <= stop) if long else (price >= stop)
        if hit:
            exit_gain = (stop - entry) / entry * 100.0 * sign
            trace[-1] = (t, price, gain_pct, stop, "stopped")
            return _result(entry, stop, exit_gain, "stop", t, trace)

    # ran off the end of the data with the position still open
    last_t, last_price = ticks[-1]
    last_gain = (last_price - entry) / entry * 100.0 * sign
    return _result(entry, last_price, last_gain, "mark-to-market (data ran out)",
                    last_t, trace)


def _result(entry, exit_price, gain_pct, reason, exit_t, trace):
    return {
        "entry": entry, "exit": exit_price, "gain_pct": gain_pct,
        "reason": reason, "exit_t": exit_t, "trace": trace,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    def add_common(p):
        p.add_argument("--direction", choices=["long", "short"], default="long")
        p.add_argument("--entry-price", type=float)
        p.add_argument("--entry-index", type=int, default=0)
        p.add_argument("--qty", type=int, default=1)
        p.add_argument("--mult", type=float)
        p.add_argument("--stop-pct", type=float)
        p.add_argument("--stop-dollar", type=float)
        p.add_argument("--arm-pct", type=float)
        p.add_argument("--lock-pct", type=float, default=0.0)
        p.add_argument("--step-pct", type=float)
        p.add_argument("--trail-pct", type=float)
        p.add_argument("--trail-dollar", type=float)
        p.add_argument("--take-profit-pct", type=float)
        p.add_argument("--csv-out", help="optional path to dump the tick-by-tick trace")

    p_opt = sub.add_parser("options", help="replay a real option tick tape")
    p_opt.add_argument("--data", required=True)
    p_opt.add_argument("--occ", help="filter the tape to one contract, e.g. SPY260902C00767000")
    add_common(p_opt)

    p_fut = sub.add_parser("futures", help="replay real 1-minute futures bars")
    p_fut.add_argument("--data")
    p_fut.add_argument("--symbol", help="e.g. NQ, ES, MGC -- auto-finds the file in bars\\")
    add_common(p_fut)

    p_syn = sub.add_parser("synthetic", help="a made-up price path, no data file needed")
    p_syn.add_argument("--prices", help="comma-separated price list, e.g. 100,102,98,105")
    p_syn.add_argument("--random-walk", action="store_true")
    p_syn.add_argument("--steps", type=int, default=100)
    p_syn.add_argument("--start", type=float, default=100.0)
    p_syn.add_argument("--vol", type=float, default=1.0, help="stddev per step, price units")
    p_syn.add_argument("--drift", type=float, default=0.0, help="mean per step, price units")
    p_syn.add_argument("--seed", type=int)
    add_common(p_syn)

    args = parser.parse_args()

    if args.mode == "options":
        ticks = load_option_tape(args.data, occ=args.occ)
        default_mult = 100.0
    elif args.mode == "futures":
        path = resolve_futures_path(args.data, args.symbol)
        ticks = load_futures_bars(path)
        sym = (args.symbol or os.path.basename(path).split("_")[0]).upper()
        default_mult = FUTURES_MULT.get(sym, 1.0)
        if args.mult is None and sym not in FUTURES_MULT:
            print("! unknown symbol '%s' for --mult lookup, defaulting to 1.0 "
                  "$/point -- pass --mult to fix this." % sym, file=sys.stderr)
    else:
        ticks = make_synthetic(args.prices, args.random_walk, args.start,
                                args.steps, args.vol, args.drift, args.seed)
        default_mult = 1.0

    entry_idx = max(0, min(args.entry_index, len(ticks) - 1))
    entry = args.entry_price if args.entry_price is not None else ticks[entry_idx][1]
    ticks = ticks[entry_idx:]
    mult = args.mult if args.mult is not None else default_mult

    result = simulate(
        ticks, args.direction, entry,
        stop_pct=args.stop_pct, stop_dollar=args.stop_dollar,
        arm_pct=args.arm_pct, lock_pct=args.lock_pct,
        step_pct=args.step_pct, trail_pct=args.trail_pct,
        trail_dollar=args.trail_dollar, take_profit_pct=args.take_profit_pct,
    )

    dollars = (result["gain_pct"] / 100.0) * entry * mult * args.qty

    print("mode:      %s" % args.mode)
    print("direction: %s   qty: %d   mult: $%.2f/pt" % (args.direction, args.qty, mult))
    print("entry:     %.4f" % result["entry"])
    print("exit:      %.4f   (%s)" % (result["exit"], result["reason"]))
    print("gain:      %+.2f%%" % result["gain_pct"])
    print("P&L:       $%+.2f" % dollars)
    print("ticks used: %d" % len(result["trace"]))

    if args.csv_out:
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "price", "gain_pct", "stop", "event"])
            w.writerows(result["trace"])
        print("trace written to %s" % args.csv_out)


if __name__ == "__main__":
    main()
