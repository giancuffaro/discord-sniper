"""Per-caller edge on the index mirror — MEASUREMENT ONLY (G, 9/19: "what about
following Brett that had a good %, what was Mike's %?").

Same honest simulator, same in-sample / out-of-sample split and the same
random-direction control as edge_lab.py. Honeydrip's relay bot posts as
"HoneyDrip (Scribe)"; the trader is the @name inside the text, so those
alerts are re-labelled Unraveller / Mike / Brett from grab_alerts.csv before
counting. A caller "beats random" only when his win% is above the control
on BOTH halves and the sample is not tiny — read the n before the %.

  python reference/caller_edge.py            -> reference/CALLER-EDGE.txt
"""
import csv
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import edge_lab as el  # noqa: E402

MIN_N = 20


def honeydrip_names():
    m = {}
    with open(os.path.join(ROOT, "grab_alerts.csv"), encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if "HoneyDrip" not in (r.get("caller") or ""):
                continue
            x = re.search(r"@(Unraveller|Mike|Brett)\b", r.get("text") or "")
            if x:
                m[(r["date"], (r["time"] or "")[:5], (r["symbol"] or "").upper(),
                   (r["side"] or "")[:1].upper())] = x.group(1)
    return m


def relabel(alerts):
    names = honeydrip_names()
    for a in alerts:
        if str(a["caller"]).startswith("HoneyDrip"):
            k = (a["day"], a["ts"].strftime("%H:%M"), a["sym"], "C" if a["s"] > 0 else "P")
            a["caller"] = names.get(k, "HoneyDrip relay (no @name)")
    return alerts


def main():
    D = el.load()
    alerts = relabel(D["alerts"])
    out = []
    P = out.append
    P("PER-CALLER EDGE — honest sim (edge_lab), %d index alerts, IS before %s / OOS from it, "
      "random-direction control on the same fills" % (len(alerts), el.SPLIT))
    P("exits: MES 12.5-pt stop 1:1 · MNQ 12.5-pt stop, BE at 5, 2.5 rungs (edge_lab defaults). "
      "instant = trade the alert at the next minute's open; level = the 25-level pullback shape.")
    P("A caller counts as above random only if win%% > rnd on BOTH halves — and n under ~150 proves nothing either way.")
    P("")
    counts = Counter(a["caller"] for a in alerts)
    callers = [c for c, n in counts.most_common() if n >= MIN_N]
    for caller in callers:
        mine = [a for a in alerts if a["caller"] == caller]
        by = Counter(a["grp"] for a in mine)
        P("== %s — %d alerts (%s), %d calls / %d puts" % (
            caller, len(mine), ", ".join("%s %d" % kv for kv in by.most_common()),
            sum(1 for a in mine if a["s"] > 0), sum(1 for a in mine if a["s"] < 0)))
        for entry in ("instant", "level"):
            for label, sub in (("all", mine),
                               ("QQQ->MNQ", [a for a in mine if a["grp"] == "QQQ"]),
                               ("SPY/SPX->MES", [a for a in mine if a["grp"] == "SPY"]),
                               ("calls only", [a for a in mine if a["s"] > 0]),
                               ("puts only", [a for a in mine if a["s"] < 0])):
                if len(sub) < MIN_N:
                    continue
                _pairs, ln = el.run_set(D, sub, "  %-8s %-13s" % (entry, label), entry=entry)
                P(ln)
        P("")
    text = "\n".join(out)
    with open(os.path.join(HERE, "CALLER-EDGE.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
