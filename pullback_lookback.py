"""pullback_lookback.py — did the pullback ALREADY HAPPEN before we started waiting?

G's question (9/15): "what if it has touched it in the last minute? we could
probably still enter because maybe we missed it by a second."

The round-number rule arms a wait at the moment the alert lands and then watches
FORWARD only. If the underlying tagged that level in the seconds BEFORE the
alert reached us — the caller saw the touch, typed it, we read it a beat late —
then we are waiting for a second touch that has no reason to come, and the
entry the caller actually got is the one we are refusing.

This reads every armed pullback out of trades.log, keeps the ones that timed
out ("never touched"), and asks the 1-second stock bars in bars/stock whether
that exact level was traded through in the N seconds BEFORE the arm.

    python3 pullback_lookback.py              90s lookback (default)
    python3 pullback_lookback.py --secs 30

Read-only. Touches no order path and sends nothing.
"""
import csv, datetime as dt, glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARM = re.compile(r"PULLBACK (\w+) (CALL|PUT): stock at ([\d.]+), "
                 r"waiting for a (dip|bounce) to \$([\d.]+)")
DEAD = re.compile(r"PULLBACK (\w+): never touched \$([\d.]+)")
LIVE = re.compile(r"PULLBACK (\w+): touched \$")

secs = 90
if "--secs" in sys.argv:
    secs = int(sys.argv[sys.argv.index("--secs") + 1])


def bars(sym, day):
    p = os.path.join(HERE, "bars", "stock", "%s_%s_1s.csv" % (sym, day))
    if not os.path.exists(p):
        return None
    out = []
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                out.append((int(r["ts"]), float(r["l"]), float(r["h"])))
            except (TypeError, ValueError, KeyError):
                continue
    return out


armed, resolved = [], {}
with open(os.path.join(HERE, "trades.log"), encoding="utf-8", errors="replace") as f:
    for line in f:
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        stamp, msg = parts
        try:
            when = dt.datetime.fromisoformat(stamp.strip())
        except ValueError:
            continue
        m = ARM.search(msg)
        if m:
            armed.append({"t": when, "sym": m.group(1), "side": m.group(2),
                          "spot": float(m.group(3)), "dir": m.group(4),
                          "level": float(m.group(5))})
            continue
        d = DEAD.search(msg)
        if d:
            resolved.setdefault((d.group(1), d.group(2)), []).append(("dead", when))
        elif LIVE.search(msg):
            s = LIVE.search(msg).group(1)
            resolved.setdefault((s, None), []).append(("live", when))

dead = []
for a in armed:
    key = (a["sym"], ("%g" % a["level"]))
    hits = [h for h in resolved.get(key, []) if h[1] >= a["t"]]
    if hits and hits[0][0] == "dead":
        dead.append(a)

print("armed pullbacks in trades.log: %d   timed out (never touched): %d"
      % (len(armed), len(dead)))
print("asking the 1s bars: was that level traded in the %ds BEFORE the arm?\n" % secs)

already, clean, nodata = [], 0, 0
for a in dead:
    day = a["t"].date().isoformat()
    b = bars(a["sym"], day)
    if not b:
        nodata += 1
        continue
    end = int(a["t"].timestamp())
    win = [x for x in b if end - secs <= x[0] <= end]
    if not win:
        nodata += 1
        continue
    lo = min(x[1] for x in win)
    hi = max(x[2] for x in win)
    if lo <= a["level"] <= hi:
        already.append((a, lo, hi))
    else:
        clean += 1

checkable = len(already) + clean
print("  checkable with bars on hand : %d  (no bars for %d)" % (checkable, nodata))
if checkable:
    print("  level ALREADY tagged first  : %d  (%.0f%% of checkable)"
          % (len(already), 100.0 * len(already) / checkable))
    print("  genuinely never near it     : %d\n" % clean)
for a, lo, hi in already:
    print("  %s  %-5s %-4s  level $%-8g  spot at arm %-9g  prior %ds range %g-%g"
          % (a["t"].strftime("%m/%d %H:%M:%S"), a["sym"], a["side"],
             a["level"], a["spot"], secs, lo, hi))
