#!/usr/bin/env python3
"""
option_tape_pull.py — buy the REAL per-second price path for every trade we
took, so a different stop can be replayed against what actually happened.

WHY (9/10, G: "run the ratchet scenarios now on all")
-----------------------------------------------------
An order record holds two points — what we paid and what we sold for. A
ratchet question ("would a 5% stop have done better than 7.5%?") needs the
whole path in between: how far the bid fell before it recovered, how high it
got before it came back. That is the option TAPE, and Webull has no history
for it. Databento's OPRA feed does.

WHAT IT DOES
  1. Reads master_broker.csv (the broker's own record) and builds one window
     per contract-day: first buy -> last sell + 10 minutes.
  2. Prices the whole pull with metadata.get_cost and PRINTS IT before
     spending anything. --cost stops there.
  3. Downloads cmbp-1 (top of book) from OPRA.PILLAR, downsamples to ~1 row
     a second, and appends to databento_tape.csv in the exact shape tape.py
     already reads (ts, occ, bid, ask).
  4. Skips (occ, day) pairs already in the tape, so a re-run costs nothing.

SYMBOLS: Databento wants the OSI form with the root padded to 6 ("SPY   260909P00764000"),
which occ.to_tasty() produces. The bare OCC is rejected — that cost a first
attempt with a confusing "symbology_invalid_symbol" error.

RUN   python3 option_tape_pull.py --cost     price it, buy nothing
      python3 option_tape_pull.py            buy and write the tape
      python3 option_tape_pull.py --bot      only contracts the BOT traded
Read-only over every record. Never trades.
"""
import collections
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ledger as bl   # noqa: E402
import occ as OCC           # noqa: E402

ET = ZoneInfo("America/New_York")
SETTINGS = os.path.join(HERE, "settings.json")
OUT_CSV = os.path.join(HERE, "databento_tape.csv")
AFTER_EXIT_MIN = 10          # keep taping past the exit — that is the
                             # "what did we leave behind" half of a post-mortem


def bot_contracts():
    """OCCs the BOT traded (a real caller, not G's own, not adopted)."""
    out = set()
    p = os.path.join(HERE, "master_ledger.csv")
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("caller") or "").strip() in ("", "?"):
                continue
            if r.get("source") == "webull-export-only" or r.get("manual") == "True":
                continue
            if r.get("occ"):
                out.add(r["occ"])
    return out


def windows(bot_only=False):
    """{(raw_osi, occ, day): (start, end)} — one per contract-day held."""
    keep = bot_contracts() if bot_only else None
    win = {}
    for t in bl.load_broker_exports():
        if t.get("sell") is None:
            continue
        if keep is not None and t["occ"] not in keep:
            continue
        try:
            raw = OCC.to_tasty(t["symbol"], t["expiry"],
                               "CALLS" if t["cp"] == "C" else "PUTS", t["strike"])
        except Exception:                                   # noqa: BLE001
            continue
        a = datetime.fromtimestamp(t["buy_ts"], ET)
        b = datetime.fromtimestamp(t["sell_ts"], ET) + timedelta(minutes=AFTER_EXIT_MIN)
        k = (raw, t["occ"], t["date"])
        if k in win:
            a = min(a, win[k][0])
            b = max(b, win[k][1])
        win[k] = (a, b)
    return win


def already_taped():
    done = set()
    if not os.path.exists(OUT_CSV):
        return done
    try:
        with open(OUT_CSV, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ts, o = row.get("ts"), row.get("occ")
                if ts and o:
                    day = datetime.fromtimestamp(float(ts), tz=timezone.utc)\
                        .astimezone(ET).strftime("%Y-%m-%d")
                    done.add((o, day))
    except (OSError, ValueError):
        pass
    return done


def main():
    cost_only = "--cost" in sys.argv
    bot_only = "--bot" in sys.argv
    win = windows(bot_only)
    done = already_taped()
    win = {k: v for k, v in win.items() if (k[1], k[2]) not in done}
    print("contract-days to pull: %d%s" % (len(win), "  (bot only)" if bot_only else ""))
    if not win:
        print("nothing new — the tape already covers every one.")
        return
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            key = ((json.load(fh).get("execution") or {}).get("databento") or {}).get("api_key", "")
    except (OSError, ValueError):
        key = ""
    if not key:
        sys.exit("no Databento key in settings.json execution.databento.api_key")
    import databento as db
    client = db.Historical(key)

    byday = collections.defaultdict(list)
    for (raw, occ_s, day), (a, b) in win.items():
        byday[day].append((raw, occ_s, a, b))

    total = 0.0
    for day in sorted(byday):
        syms = [x[0] for x in byday[day]]
        lo = min(x[2] for x in byday[day]).astimezone(timezone.utc)
        hi = max(x[3] for x in byday[day]).astimezone(timezone.utc)
        try:
            total += client.metadata.get_cost(
                dataset="OPRA.PILLAR", symbols=syms, schema="cmbp-1",
                stype_in="raw_symbol", start=lo, end=hi) or 0.0
        except Exception as e:                              # noqa: BLE001
            print("  cost check failed %s: %s" % (day, str(e)[:110]))
    print("DATABENTO QUOTE: $%.2f" % total)
    if cost_only:
        return

    new = not os.path.exists(OUT_CSV)
    fh = open(OUT_CSV, "a", newline="", encoding="utf-8")
    w = csv.writer(fh)
    if new:
        w.writerow(["ts", "occ", "bid", "ask"])
    wrote = 0
    for day in sorted(byday):
        syms = [x[0] for x in byday[day]]
        raw2occ = {x[0]: x[1] for x in byday[day]}
        lo = min(x[2] for x in byday[day]).astimezone(timezone.utc)
        hi = max(x[3] for x in byday[day]).astimezone(timezone.utc)
        try:
            data = client.timeseries.get_range(
                dataset="OPRA.PILLAR", symbols=syms, schema="cmbp-1",
                stype_in="raw_symbol", start=lo, end=hi)
            df = data.to_df()
        except Exception as e:                              # noqa: BLE001
            print("  %s pull failed: %s" % (day, str(e)[:140]))
            continue
        last = {}
        n = 0
        for ts, row in df.iterrows():
            raw = str(row.get("symbol") or "")
            o = raw2occ.get(raw)
            if not o:
                continue
            sec = int(ts.timestamp())
            if last.get(o) == sec:              # ~1 row a second, like option_tape
                continue
            last[o] = sec
            bid = row.get("bid_px_00")
            ask = row.get("ask_px_00")
            try:
                bid = float(bid); ask = float(ask)
            except (TypeError, ValueError):
                continue
            if bid <= 0 and ask <= 0:
                continue
            w.writerow([sec, o, round(bid, 4), round(ask, 4)])
            n += 1
        wrote += n
        print("  %s  %2d contracts  %6d rows" % (day, len(syms), n))
    fh.close()
    print("wrote %d tape rows to %s" % (wrote, os.path.basename(OUT_CSV)))


if __name__ == "__main__":
    main()
