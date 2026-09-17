#!/usr/bin/env python3
"""ladder_grid_test.py — which born stop / arm / step would have paid?

G, 9/17: "what ladder would have been beneficial today? test". Every taped
option alert, INSTANT entry at the ask on the first quote after the alert,
one contract, exits by ratchet_replay_tape.simulate on recorded bids, flat
15:59. The grid runs on ONE DAY and on ALL HISTORY side by side, because the
best cell of one day is a fitted number, not a finding. MEASUREMENT ONLY.
    python reference/ladder_grid_test.py 2026-09-17
"""
from __future__ import annotations

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import caller_price_window_replay as rp                     # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402
import win_rate_dig as dig                                  # noqa: E402

BORN = (5, 10, 15, 20, 30, 50)
ARM = (3, 5, 10, 20, 30)
STEP = (5, 10, 20)


def day_alerts(day):
    out, seen = [], set()
    with open(os.path.join(ROOT, "alert_meta.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("stage") != "alert" or r.get("date") != day or not r.get("occ"):
                continue
            if (r.get("side") or "").upper() not in ("CALLS", "PUTS"):
                continue
            k = (r["occ"], r["time"][:4])
            if k in seen:
                continue
            seen.add(k)
            out.append({"day": day, "time": r["time"], "ts": float(r["ts"]), "occ": r["occ"],
                        "root": (r.get("symbol") or "").upper(), "side": r["side"],
                        "their_price": rr._f(r.get("their_price")),
                        "caller": r.get("caller") or r.get("room") or ""})
    return out


def rows_for(alerts):
    paths = rp.option_paths({a["occ"] for a in alerts})
    rows = []
    for a in alerts:
        p = paths.get((a["day"], a["occ"]))
        after = [q for q in (p or []) if q[0] >= a["ts"] - 2]
        if not after or after[0][0] - a["ts"] > 30:
            continue
        rows.append({"a": a, "path": p, "t0": after[0][0], "ask": after[0][2],
                     "bid": after[0][1], "flat": rr._flat_ts(a["day"])})
    return rows


def grid(rows):
    res = {}
    for b in BORN:
        for arm in ARM:
            for st in STEP:
                tiers = ((None, (float(arm), 0.0, float(st))),)
                sims = [dig.sim(r, born=float(b), tiers=tiers) for r in rows]
                pls = [s["pl"] for s in sims if s]
                res[(b, arm, st)] = (sum(pls), sum(1 for x in pls if x > 2), len(pls))
    return res


def show(title, res):
    print("\n" + title)
    ranked = sorted(res.items(), key=lambda kv: -kv[1][0])
    print("  best 6:  " + "   ".join("%d/%d/%d %+.0f (%d%%)" % (k + (v[0], 100 * v[1] // max(1, v[2])))
                                     for k, v in ranked[:6]))
    print("  worst 3: " + "   ".join("%d/%d/%d %+.0f" % (k + (v[0],)) for k, v in ranked[-3:]))
    print("  born stop alone (average over every arm/step):")
    for b in BORN:
        vals = [v[0] for k, v in res.items() if k[0] == b]
        print("    born -%2d%%  %+7.0f" % (b, sum(vals) / len(vals)))
    print("  arm alone:   " + "  ".join("+%d%% %+.0f" % (a, sum(v[0] for k, v in res.items() if k[1] == a)
                                        / len([1 for k in res if k[1] == a])) for a in ARM))
    print("  step alone:  " + "  ".join("+%d%% %+.0f" % (s, sum(v[0] for k, v in res.items() if k[2] == s)
                                        / len([1 for k in res if k[2] == s])) for s in STEP))


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-09-17"
    today = rows_for(day_alerts(day))
    hist = rows_for([a for a in rp.alerts() if a["day"] != day])
    live = (int(rr.BORN_PCT),) + tuple(int(x) for x in (rr.TIERS_LIVE[0][1][0], rr.TIERS_LIVE[0][1][2]))
    print("LADDER GRID — instant entry at the ask, 1 contract. LIVE = %d/%d/%d (born/arm/step)" % live)
    print("%s: %d taped alerts   |   history (all other days): %d alerts" % (day, len(today), len(hist)))
    rt, rh = grid(today), grid(hist)
    print("\nLIVE ladder: %s %+.0f   |   history %+.0f" % (day, rt.get(live, (0,))[0], rh.get(live, (0,))[0]))
    hold = [(r["path"][-1][1] if r["path"][-1][0] <= r["flat"] else
             [q for q in r["path"] if q[0] <= r["flat"]][-1][1]) - r["ask"] for r in today]
    print("NO LADDER AT ALL (hold to the last quote of the day): %s %+.0f" % (day, sum(hold) * 100))
    show("== %s ==" % day, rt)
    show("== HISTORY (the check: does today's winner hold anywhere else?) ==", rh)
    best_today = sorted(rt.items(), key=lambda kv: -kv[1][0])[:3]
    print("\nTODAY'S TOP 3 ON HISTORY: " + "   ".join("%d/%d/%d today %+.0f -> history %+.0f"
          % (k + (v[0], rh[k][0])) for k, v in best_today))
    best_hist = sorted(rh.items(), key=lambda kv: -kv[1][0])[:3]
    print("HISTORY'S TOP 3 TODAY:    " + "   ".join("%d/%d/%d history %+.0f -> today %+.0f"
          % (k + (v[0], rt[k][0])) for k, v in best_hist))


if __name__ == "__main__":
    main()
