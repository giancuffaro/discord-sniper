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

    if cost_only:
        # Pricing costs a round-trip PER DAY-WINDOW and takes minutes on a big
        # pull, so it belongs to --cost alone. Price first, then buy.
        total = 0.0
        for day in sorted(byday):
            syms = [x[0] for x in byday[day]]
            lo = min(x[2] for x in byday[day]).astimezone(timezone.utc)
            hi = max(x[3] for x in byday[day]).astimezone(timezone.utc)
            try:
                total += client.metadata.get_cost(
                    dataset="OPRA.PILLAR", symbols=syms, schema="cmbp-1",
                    stype_in="raw_symbol", start=lo, end=hi) or 0.0
            except Exception as e:                          # noqa: BLE001
                print("  cost check failed %s: %s" % (day, str(e)[:110]))
        print("DATABENTO QUOTE: $%.2f" % total)
        return

    # ONE PULL PER CONTRACT-WINDOW, not per day. A day-wide union window over
    # every contract that day is the whole session for each of them — millions
    # of OPRA book rows, minutes per day, and a run that gets killed before it
    # writes anything. Each contract only needs its own hold window.
    budget = 0.0
    for i, a in enumerate(sys.argv):
        if a == "--minutes" and i + 1 < len(sys.argv):
            budget = float(sys.argv[i + 1]) * 60
    started = datetime.now(timezone.utc).timestamp()

    print("downloading %d contract-windows across %d days%s"
          % (len(win), len(byday), "  (stop after %g min)" % (budget / 60) if budget else ""),
          flush=True)
    new = not os.path.exists(OUT_CSV)
    fh = open(OUT_CSV, "a", newline="", encoding="utf-8")
    w = csv.writer(fh)
    if new:
        w.writerow(["ts", "occ", "bid", "ask"])
    wrote = done_n = 0
    order = sorted(win.items(), key=lambda kv: (kv[0][2], kv[0][0]))

    def fetch(item):
        """Download ONE window and reduce it to tape rows. Runs on a worker."""
        (raw, occ_s, day), (a, b) = item
        try:
            df = client.timeseries.get_range(
                dataset="OPRA.PILLAR", symbols=[raw], schema="cmbp-1",
                stype_in="raw_symbol",
                start=a.astimezone(timezone.utc),
                end=b.astimezone(timezone.utc)).to_df()
        except Exception as e:                              # noqa: BLE001
            return occ_s, day, None, str(e)[:120]
        last = None
        buf = []                # a window is written ALL-OR-NOTHING: a run
                                # killed mid-window must not leave a half
                                # window the next run then skips as taped
        for ts, row in df.iterrows():
            sec = int(ts.timestamp())
            if last == sec:                     # ~1 row a second, like option_tape
                continue
            last = sec
            try:
                bid = float(row.get("bid_px_00")); ask = float(row.get("ask_px_00"))
            except (TypeError, ValueError):
                continue
            if bid <= 0 and ask <= 0:
                continue
            buf.append([sec, occ_s, round(bid, 4), round(ask, 4)])
        return occ_s, day, buf, None

    # The wall clock is the whole cost here — one window is a second of compute
    # and ten of waiting on Databento. Four in flight, one writer.
    # Submit only a few at a time: pool.map would queue all 400 and the pool
    # would refuse to shut down until every one of them came back, so the time
    # budget could never stop it.
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=4)
    queue, nxt, stop = [], 0, False
    while (queue or nxt < len(order)) and not stop:
        while len(queue) < 4 and nxt < len(order) and not stop:
            queue.append(pool.submit(fetch, order[nxt])); nxt += 1
        occ_s, day, buf, err = queue.pop(0).result()
        if err is not None:
            print("  %s %s failed: %s" % (day, occ_s, err), flush=True)
        else:
            w.writerows(buf)
            fh.flush()
            os.fsync(fh.fileno())
            wrote += len(buf)
            done_n += 1
            print("  %s %-22s %6d rows   (%d/%d)"
                  % (day, occ_s, len(buf), done_n, len(win)), flush=True)
        if budget and datetime.now(timezone.utc).timestamp() - started > budget:
            stop = True
    for f in queue:                 # drain what is already paid for
        try:
            occ_s, day, buf, err = f.result(timeout=45)
        except Exception:                                   # noqa: BLE001
            continue
        if err is None:
            w.writerows(buf); wrote += len(buf); done_n += 1
    fh.flush()
    os.fsync(fh.fileno())
    pool.shutdown(wait=False)
    if stop:
        print("  time budget spent — %d of %d done, re-run to continue"
              % (done_n, len(win)), flush=True)
    fh.close()
    print("wrote %d tape rows to %s" % (wrote, os.path.basename(OUT_CSV)))


if __name__ == "__main__":
    main()
