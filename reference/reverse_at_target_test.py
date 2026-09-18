#!/usr/bin/env python3
"""reverse_at_target_test.py — at the take-profit, flip and trade the other way.

G, 9/18: "instead of taking profits at the final level, what about reversing
and going the opposite way? how many would have been profitable or losers?"

Base = the pullback-level entry that held up (pullback_level_entry_test.py):
  MES  limit 2 pts before the ES 25 below (puts: above), 30-min wait, 12.5 stop, 1:1 target
  MNQ  limit at the NQ 50, 30-min wait, 10 stop / BE at 5 / 2.5 rungs (no target),
       so its "final level" is taken as the next NQ 50 in the trade's favour.
When the first trade reaches its target / final level, the reverse trade opens
THERE, the opposite way, with the same exit rules, and runs to its own stop /
target / the close. The base trade is counted once; the reverse is the add-on.
Also shown: reverse at the NEXT ES 25 (instead of +12.5) for MES. MEASUREMENT
ONLY. Output: reference/REVERSE-AT-TARGET-TEST.txt
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import futures_ratchet_sweep as rs                          # noqa: E402
import pullback_level_entry_test as pt                     # noqa: E402


def first_hit(rows, s, level):
    for i, (hi, lo, _c) in enumerate(rows):
        if (hi >= level) if s > 0 else (lo <= level):
            return i
    return None


def main():
    W = rs.windows()
    out = []
    p = out.append
    p("REVERSE AT THE TARGET — flip at the take-profit and trade back the other way (same exit rules)")
    cases = (
        ("SPY", "MES · limit 2 before the 25 · 12.5 1:1 · reverse at +12.5 (the target)", 25.0, 2.0, (12.5, None, 1.0, 1.0), "target"),
        ("SPY", "MES · limit 2 before the 25 · 12.5 1:1 · reverse at the NEXT 25 level", 25.0, 2.0, (12.5, None, 1.0, 1.0), "level"),
        ("QQQ", "MNQ · limit at the 50 · 10/BE5/2.5 · reverse at the NEXT 50 level", 50.0, 0.0, (10.0, 0.5, 0.25, None), "level"),
    )
    for sym, name, grid, buf, (st, ar, ru, tg), where in cases:
        tr = [x for x in W if x[0]["sym"] == sym]
        base, rev, reached = [], [], 0
        for a, ppt, rows, e in tr:
            s = 1 if a["dirn"] == "L" else -1
            i, fill = pt.pullback_fill(rows, e, s, grid, 30, buf)
            if i is None:
                continue
            rest = rows[i:]
            base.append(rs.sim(s, fill, rest, ppt, st, ar, ru, tg))
            if where == "target":
                flip_at = fill + s * st * tg
            else:
                flip_at = (math.floor(fill / grid) + 1) * grid if s > 0 else (math.ceil(fill / grid) - 1) * grid
            # the base trade has to get there before its own stop
            j = first_hit(rest, s, flip_at)
            if j is None:
                continue
            stop0 = fill - s * st
            k = first_hit(rest, -s, stop0)
            if k is not None and k < j:
                continue
            reached += 1
            after = rest[j + 1:]
            if not after:
                continue
            rev.append(rs.sim(-s, flip_at, after, ppt, st, ar, ru, tg))
        p("\n%s" % name)
        p("  base trades %d -> %+.0f (win %.0f%%)" % (len(base), sum(base), 100 * sum(1 for v in base if v > 0) / len(base)))
        p("  reached the flip point %d; reverse trades %d -> %+.0f  winners %d  losers %d  (win %.0f%%)"
          % (reached, len(rev), sum(rev), sum(1 for v in rev if v > 0), sum(1 for v in rev if v <= 0),
             100 * sum(1 for v in rev if v > 0) / max(1, len(rev))))
        p("  base + reverse = %+.0f" % (sum(base) + sum(rev)))
    txt = "\n".join(out)
    with open(os.path.join(HERE, "REVERSE-AT-TARGET-TEST.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
