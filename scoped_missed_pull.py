"""scoped_missed_pull.py — pull WIDE price windows for the skipped (nofill) calls.

The normal backfill pulled only the ~90-second pullback-wait window for skipped
calls, so illiquid ones came back empty and we can't backtest them. This re-pulls
each skipped contract from its alert time to end of day (a real path to run the
ratchet over), into missed_tape.csv (kept separate from the main tape). Spends a
little Databento credit — G asked for it ("pull price history to backtest the
missed").

    python3 scoped_missed_pull.py
"""
import csv
import glob
import json
import os

import occ
import databento as db
import databento_backfill as bf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "missed_tape.csv")
DAY_SECONDS = 6.5 * 3600


def main():
    key = bf.load_key()
    client = db.Historical(key)

    targets = {}
    for fn in sorted(glob.glob(os.path.join(HERE, "days", "*.json"))):
        try:
            d = json.load(open(fn, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        for r in d.get("table", []):
            if r.get("kind") != "option" or r.get("state") != "nofill":
                continue
            sym, side = r.get("symbol"), r.get("side")
            strike, expiry = r.get("strike"), r.get("expiry")
            opened = r.get("opened")
            if not (sym and side and strike and expiry and opened):
                continue
            try:
                o = occ.build(sym, expiry, side, strike)
                raw = occ.to_tasty(sym, expiry, side, strike)
            except ValueError:
                continue
            start = float(opened) - 60
            end = float(opened) + DAY_SECONDS
            if raw in targets:
                targets[raw]["start"] = min(targets[raw]["start"], start)
                targets[raw]["end"] = max(targets[raw]["end"], end)
            else:
                targets[raw] = {"occ": o, "raw": raw, "start": start, "end": end}

    print("skipped contracts to pull (wide window): %d\n" % len(targets))
    fh = open(OUT, "w", newline="", encoding="utf-8")
    w = csv.writer(fh)
    w.writerow(["ts", "occ", "bid", "ask"])
    got = empty = err = 0
    for i, (raw, t) in enumerate(targets.items(), 1):
        try:
            df = client.timeseries.get_range(
                dataset="OPRA.PILLAR", schema="cmbp-1", stype_in="raw_symbol",
                symbols=[raw], start=bf.iso(t["start"]), end=bf.iso(t["end"]),
            ).to_df()
        except Exception as e:                              # noqa: BLE001
            err += 1
            print("[%d/%d] ERROR %s: %s" % (i, len(targets), t["occ"], str(e)[:100]))
            continue
        rows = bf.downsample(df, t["start"], t["end"])
        if not rows:
            empty += 1
            print("[%d/%d] empty %s" % (i, len(targets), t["occ"]))
            continue
        for ts, bid, ask in rows:
            w.writerow(["%.3f" % ts, t["occ"], bid, ask])
        fh.flush()
        got += 1
        print("[%d/%d] %-20s %d rows" % (i, len(targets), t["occ"], len(rows)))
    fh.close()
    print("\ndone: %d pulled, %d empty, %d errors -> %s"
          % (got, empty, err, os.path.basename(OUT)))


if __name__ == "__main__":
    main()
