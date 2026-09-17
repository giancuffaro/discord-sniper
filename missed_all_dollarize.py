"""missed_all_dollarize.py — every alert the bot did NOT take, priced at the
CALLER'S posted price, run through the LIVE ratchet. What would it have made?

missed_dollarize.py only covers ROUND-NUMBER PULLBACK timeouts (ledger state
"nofill"). Most misses never reach the ledger at all — BUYING POWER refusals,
NO-OTM/thin/other refusals — because no order was ever attempted, so there is
no days/*.json row for databento_backfill.py to price. This reads the wider
net master_alerts.csv already recovered (every REFUSED/PULLBACK line in
trades.log, tier-scored by build_alerts.py) and prices what that script never
had a source for.

    python3 missed_all_dollarize.py            full run (buys missing bars,
                                                 cost printed and capped)
    python3 missed_all_dollarize.py --cost      quote only, buys nothing
    python3 missed_all_dollarize.py --no-fetch  existing tapes only

Cost is quoted BEFORE any purchase and the run stops if it exceeds
COST_CAP_USD — never silently spends real money. Writes only
missed_all_tape.csv (its own cache, separate from databento_tape.csv so this
never disturbs databento_backfill.py's own state). Read-only over everything
else. Never trades.
"""
import csv
import collections
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import occ                                                    # noqa: E402
import ratchet_sweep as rs                                    # noqa: E402
import tape as _tape                                          # noqa: E402
from ratchet_tiers import live_spacing                        # noqa: E402
from ratchet_sweep_fine import sim                             # noqa: E402
from databento_backfill import downsample                       # noqa: E402  (~1 row/sec — the raw feed is not usable as-is)

SETTINGS = os.path.join(HERE, "settings.json")
OUT_CSV = os.path.join(HERE, "missed_all_tape.csv")
COST_CAP_USD = 5.00           # stop and ask rather than spend past this
PAD_SECONDS = 60
WINDOW_SECONDS = 30 * 60       # same shape databento_backfill uses for nofill
ET = datetime.timezone(datetime.timedelta(hours=-4))          # EDT; good enough for a 30-min window

MISS_OUTCOMES = {"BUYING POWER too small", "PULLBACK never hit", "OTHER refusal",
                  "THIN / no open interest", "NO buying connection"}


def load_candidates():
    rows = list(csv.DictReader(open(os.path.join(HERE, "master_alerts.csv"),
                                    encoding="utf-8", errors="replace")))
    out = []
    for r in rows:
        if r.get("outcome") not in MISS_OUTCOMES:
            continue
        if not (r.get("strike") and r.get("expiry") and r.get("their_price")):
            continue
        if str(r.get("caller") or "").strip().lower() == "gian":
            continue
        try:
            price = float(r["their_price"])
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        try:
            o = occ.build(r["symbol"], r["expiry"], r["side"], r["strike"])
            raw = occ.to_tasty(r["symbol"], r["expiry"], r["side"], r["strike"])
        except ValueError:
            continue
        try:
            when = datetime.datetime.strptime(
                r["date"] + " " + r["time"][:5], "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        except ValueError:
            continue
        out.append({"row": r, "occ": o, "raw": raw, "ts": when.timestamp(),
                    "price": price})
    return out


def load_existing_tape():
    tape = rs.load_tape()
    mp = _tape.path("missed")
    if os.path.exists(mp):
        add = collections.defaultdict(list)
        for row in csv.DictReader(open(mp, encoding="utf-8")):
            try:
                add[row["occ"]].append((float(row["ts"]), float(row["bid"]), float(row["ask"])))
            except (TypeError, ValueError, KeyError):
                continue
        for k, v in add.items():
            v.sort()
            tape[k] = v
    if os.path.exists(OUT_CSV):
        add = collections.defaultdict(list)
        for row in csv.DictReader(open(OUT_CSV, encoding="utf-8")):
            try:
                add[row["occ"]].append((float(row["ts"]), float(row["bid"]), float(row["ask"])))
            except (TypeError, ValueError, KeyError):
                continue
        for k, v in add.items():
            v.sort()
            tape[k] = v
    return tape


def fetch_missing(missing, cost_only=False):
    """missing = list of candidate dicts with no tape coverage yet.
    Quotes cost FIRST, prints it, stops (returns 0 bought) if over cap or
    cost_only. Appends fetched rows to missed_all_tape.csv."""
    if not missing:
        return 0
    try:
        key = (json.load(open(SETTINGS, encoding="utf-8")).get("execution", {})
               .get("databento", {}) or {}).get("api_key", "")
    except (OSError, ValueError):
        key = ""
    if not key:
        print("  no Databento key in settings.json — replaying from cache only")
        return 0
    import databento as db
    client = db.Historical(key)

    total = 0.0
    quotes = []
    for c in missing:
        start = c["ts"] - PAD_SECONDS
        end = c["ts"] + WINDOW_SECONDS
        try:
            cost = client.metadata.get_cost(dataset="OPRA.PILLAR", schema="cmbp-1",
                                            symbols=[c["raw"]], stype_in="raw_symbol",
                                            start=datetime.datetime.fromtimestamp(start, tz=datetime.timezone.utc).isoformat(),
                                            end=datetime.datetime.fromtimestamp(end, tz=datetime.timezone.utc).isoformat())
        except Exception as e:                                # noqa: BLE001
            print("  cost check failed for %s: %s" % (c["occ"], str(e)[:100]))
            cost = None
        quotes.append((c, start, end, cost))
        total += cost or 0.0

    print("  %d contract-windows to price; Databento quote $%.4f" % (len(missing), total))
    if cost_only:
        return 0
    if total > COST_CAP_USD:
        print("  OVER the $%.2f cap — stopping, nothing bought. Raise COST_CAP_USD "
              "in the script to proceed." % COST_CAP_USD)
        return 0

    new_file = not os.path.exists(OUT_CSV)
    fh = open(OUT_CSV, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    if new_file:
        writer.writerow(["ts", "occ", "bid", "ask"])
    bought = 0
    for c, start, end, cost in quotes:
        try:
            data = client.timeseries.get_range(
                dataset="OPRA.PILLAR", schema="cmbp-1", stype_in="raw_symbol",
                symbols=[c["raw"]],
                start=datetime.datetime.fromtimestamp(start, tz=datetime.timezone.utc).isoformat(),
                end=datetime.datetime.fromtimestamp(end, tz=datetime.timezone.utc).isoformat())
            df = data.to_df()
        except Exception as e:                                # noqa: BLE001
            print("  %s: pull failed — %s" % (c["occ"], str(e)[:140]))
            continue
        rows_ds = downsample(df, win_start=start, win_end=end)
        n = 0
        for t, bid, ask in rows_ds:
            try:
                writer.writerow(["%.3f" % t, c["occ"], "%.4f" % bid, "%.4f" % ask])
                n += 1
            except (TypeError, ValueError):
                continue
        print("  %-20s %5d quotes (downsampled from %d raw)" % (c["occ"], n, len(df)))
        if n:
            bought += 1
    fh.close()
    return bought


def main():
    cost_only = "--cost" in sys.argv
    no_fetch = "--no-fetch" in sys.argv

    cands = load_candidates()
    print("candidate misses (real callers, full contract+price): %d" % len(cands))
    print(collections.Counter(c["row"]["outcome"] for c in cands).most_common())
    print()

    tape = load_existing_tape()
    covered, missing = [], []
    for c in cands:
        q = [x for x in tape.get(c["occ"], []) if x[0] >= c["ts"] - 2]
        (covered if q else missing).append(c)

    print("already covered by existing tapes: %d   need pricing: %d\n"
          % (len(covered), len(missing)))

    if missing and not no_fetch:
        fetch_missing(missing, cost_only=cost_only)
        if not cost_only:
            tape = load_existing_tape()
            still_missing = []
            for c in missing:
                q = [x for x in tape.get(c["occ"], []) if x[0] >= c["ts"] - 2]
                (covered if q else still_missing).append(c)
            missing = still_missing

    if cost_only:
        return

    print("priceable: %d   still uncovered: %d\n" % (len(covered), len(missing)))
    if not covered:
        print("nothing to simulate.")
        return

    born, arm, step = live_spacing()
    tot, wins, det = 0.0, 0, []
    by_outcome = collections.defaultdict(lambda: [0.0, 0])
    for c in covered:
        q = [x for x in tape.get(c["occ"], []) if x[0] >= c["ts"] - 2]
        rp, _ = sim({"entry": c["price"], "quotes": q}, born, arm, step)
        dollars = rp / 100.0 * c["price"] * rs.CONTRACT_MULT
        tot += dollars
        outc = c["row"]["outcome"]
        by_outcome[outc][0] += dollars
        by_outcome[outc][1] += 1
        if dollars > 0:
            wins += 1
        det.append((dollars, c["occ"], c["price"], rp, outc,
                    c["row"].get("caller") or "?"))

    det.sort(reverse=True)
    print("if we'd taken the CALLER'S price on every miss (%g/%g/%g — the LIVE "
          "ladder, read from ratchet_tiers):" % (born, arm, step))
    print("  total: $%.2f   win %d/%d   avg $%.2f/call\n"
          % (tot, wins, len(covered), tot / len(covered)))

    print("  by refusal reason:")
    for outc, (d, n) in sorted(by_outcome.items(), key=lambda kv: -kv[1][0]):
        print("    %-28s n=%-4d total $%-9.2f avg $%.2f"
              % (outc, n, d, d / n))
    print()

    print("  %-20s in$    result   $P&L   reason                       caller"
          % "contract")
    for dollars, o, e, rp, outc, who in det[:40]:
        print("  %-20s %5.2f  %+5.0f%%  %+7.0f   %-28s %s"
              % (o[:20], e, rp, dollars, outc[:28], who))
    if len(det) > 40:
        print("  ... %d more rows" % (len(det) - 40))

    print("\nread: POSITIVE total = these refusals LEFT money on the table;")
    print("NEGATIVE = the refusal SAVED you. BUYING POWER rows are an account-")
    print("sizing question, not a strategy one — read that bucket separately.")


if __name__ == "__main__":
    main()
