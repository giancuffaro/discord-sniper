"""
databento_backfill.py — real OPRA option prices for every call in days/*.json.

WHY (9/7/26, G: "find out now then later and slow")
-----------------------------------------------------
option_tape.csv only has prices for contracts the bot itself quoted, starting
9/2. It has NOTHING for calls that were refused, missed, or never filled —
which is exactly where "was that gate/tier the right call" lives. days/*.json
already carries symbol, side, strike and expiry for every call the bot ever
tracked, filled or not (state: filled/closed/stopped/nofill/failed), with
opened/closed unix timestamps. This script prices every one of them for real,
off OPRA, and writes them in the SAME SHAPE tape.py already reads.

WHAT IT DOES NOT DO
--------------------
Nothing live. No order, no broker, no setting changed. It only reads
days/*.json and settings.json (for the key) and writes databento_tape.csv.
Safe to re-run — it skips (occ, day) pairs already written, so nothing is
double-fetched or double-billed.

COST
----
Billed by Databento per uncompressed byte actually streamed, against the
$125 signup credit. A test pull (one contract, ~3.5 min window) came back
at 2,823 quote updates for a few hundred KB — this script downsamples to
~1 row/second (matching option_tape's own polling cadence) before writing,
so the CSV stays small and the credit goes a long way. Expect low
single-digit dollars for the whole backfill, nowhere near $125.

SETUP
-----
    pip install databento
Then run:
    python databento_backfill.py
"""

import csv
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger  # noqa: E402
import occ  # noqa: E402  (project's one place that knows contract symbols)

SETTINGS = os.path.join(HERE, "settings.json")
OUT_CSV = os.path.join(HERE, "databento_tape.csv")
# Every (occ, day) ever ATTEMPTED, success or empty — separate from the CSV
# because a contract with no OPRA quotes in its window (illiquid moment, or
# the window landed outside real trading hours) writes zero rows, and would
# otherwise look "not done" forever and get re-fetched — and re-billed —
# every single run.
STATE_FILE = os.path.join(HERE, "databento_backfill_state.json")

# How far past a call with no fill we still look, to see what the contract
# actually did (state: nofill/failed never got a closed timestamp).
NOFILL_WINDOW_SECONDS = 30 * 60
# Buffer around a real fill/close so the entry and exit prices both land
# inside the window, not right at its edge.
PAD_SECONDS = 60
# Never ask for more than this in one query, whatever the day file says —
# a bad timestamp should cost a few dollars at worst, never the whole credit.
MAX_WINDOW_SECONDS = 4 * 3600
# Collapse to about one row per this many seconds. option_tape.csv itself
# polls at ~1/sec; there is no analysis here that needs sub-second ticks,
# and keeping every NBBO update would make the file (and the bill) far
# bigger than the ratchet study needs.
DOWNSAMPLE_SECONDS = 1.0


def load_key():
    cfg = json.load(open(SETTINGS, encoding="utf-8"))
    key = (cfg.get("execution", {}).get("databento", {}) or {}).get("api_key", "")
    if not key:
        sys.exit("No Databento key in settings.json execution.databento.api_key "
                  "— run setup_databento.py first.")
    return key


def worklist():
    """One entry per (contract, day), windows merged if it appears more than
    once that day (an add, or a partial fill logged twice)."""
    work = {}
    # 9/9: reads master_ledger.csv via ledger.py — days/*.json table truncates.
    for day, day_rows in sorted(ledger.by_day().items()):
        for r in day_rows:
            if r.get("kind") != "option":
                continue
            sym, side, strike, expiry = (r.get("symbol"), r.get("side"),
                                          r.get("strike"), r.get("expiry"))
            if not (sym and side and strike and expiry):
                continue
            try:
                occ_sym = occ.build(sym, expiry, side, strike)
                raw_sym = occ.to_tasty(sym, expiry, side, strike)  # OSI-padded
            except ValueError:
                continue  # a bad contract here would be a bad symbol, not a guess

            opened = r.get("opened")
            if not opened:
                continue
            closed = r.get("closed")
            start = opened - PAD_SECONDS
            end = (closed + PAD_SECONDS) if closed else (opened + NOFILL_WINDOW_SECONDS)
            end = min(end, start + MAX_WINDOW_SECONDS)

            key = (raw_sym, day)
            if key in work:
                w = work[key]
                w["start"] = min(w["start"], start)
                w["end"] = max(w["end"], end)
            else:
                work[key] = {"occ": occ_sym, "raw": raw_sym, "day": day,
                             "start": start, "end": end, "state": r.get("state")}
    return sorted(work.values(), key=lambda w: (w["day"], w["raw"]))


def already_done():
    """(occ, day) pairs already in databento_tape.csv — skip on re-run."""
    done = set()
    if not os.path.exists(OUT_CSV):
        return done
    with open(OUT_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row.get("ts")
            occ_v = row.get("occ")
            if ts and occ_v:
                day = datetime.datetime.fromtimestamp(
                    float(ts), tz=datetime.timezone.utc).strftime("%Y-%m-%d")
                done.add((occ_v, day))
    return done


def load_state():
    """(occ, day) pairs already ATTEMPTED (empty or fetched) - not just the
    ones that happened to write a row."""
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        return {tuple(pair) for pair in json.load(open(STATE_FILE, encoding="utf-8"))}
    except (OSError, ValueError):
        return set()


def save_state(state):
    json.dump(sorted(state), open(STATE_FILE, "w", encoding="utf-8"))


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()


def downsample(df, win_start=None, win_end=None):
    """~1 row/sec: keep the first quote in each DOWNSAMPLE_SECONDS bucket.

    9/8: one row in the first full backfill came back timestamped in the
    year 2343 — a single corrupted record out of 329,431 real ones, cause
    unconfirmed (a bad message, a pandas Timestamp artifact, who knows).
    Whatever produced it, nothing here should ever trust a timestamp outside
    the window it actually asked for, so anything more than an hour past
    either edge is dropped rather than silently written into a tape that
    ratchet/anti-clip math will treat as real."""
    if df is None or len(df) == 0:
        return []
    out = []
    last_bucket = None
    for ts_recv, bid, ask in zip(df.index, df["bid_px_00"], df["ask_px_00"]):
        t = ts_recv.timestamp()
        if win_start is not None and t < win_start - 3600:
            continue
        if win_end is not None and t > win_end + 3600:
            continue
        bucket = int(t // DOWNSAMPLE_SECONDS)
        if bucket == last_bucket:
            continue
        last_bucket = bucket
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            continue
        out.append((t, float(bid), float(ask)))
    return out


def main():
    import databento as db

    key = load_key()
    client = db.Historical(key)

    work = worklist()
    state = load_state() | already_done()
    todo = [w for w in work if (w["occ"], w["day"]) not in state]

    print("=" * 62)
    print("  DATABENTO BACKFILL — real OPRA prices for days/*.json calls")
    print("=" * 62)
    print("%d contract-days found, %d already attempted, %d to fetch"
          % (len(work), len(work) - len(todo), len(todo)))
    print()

    new_file = not os.path.exists(OUT_CSV)
    fh = open(OUT_CSV, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    if new_file:
        writer.writerow(["ts", "occ", "bid", "ask"])

    done_n = err_n = empty_n = 0
    rows_n = 0
    for i, w in enumerate(todo, 1):
        label = "%s (%s, %s)" % (w["occ"], w["day"], w["state"])
        try:
            data = client.timeseries.get_range(
                dataset="OPRA.PILLAR",
                schema="cmbp-1",
                stype_in="raw_symbol",
                symbols=[w["raw"]],
                start=iso(w["start"]),
                end=iso(w["end"]),
            )
            df = data.to_df()
        except Exception as e:                                 # noqa: BLE001
            err_n += 1
            print("[%d/%d] ERROR  %s -> %s: %s"
                  % (i, len(todo), label, type(e).__name__, str(e)[:160]))
            continue

        rows = downsample(df, win_start=w["start"], win_end=w["end"])
        if not rows:
            empty_n += 1
            state.add((w["occ"], w["day"]))
            save_state(state)
            print("[%d/%d] empty  %s (no OPRA quotes in that window)"
                  % (i, len(todo), label))
            continue

        for t, bid, ask in rows:
            writer.writerow([t, w["occ"], bid, ask])
        fh.flush()
        rows_n += len(rows)
        done_n += 1
        state.add((w["occ"], w["day"]))
        save_state(state)
        print("[%d/%d] %-40s %4d rows" % (i, len(todo), label, len(rows)))

    fh.close()
    print()
    print("Done. %d contract-days fetched, %d empty, %d errors, %d rows written to %s"
          % (done_n, empty_n, err_n, rows_n, os.path.basename(OUT_CSV)))
    print("Re-run any time — already-fetched (occ, day) pairs are skipped.")


if __name__ == "__main__":
    main()
