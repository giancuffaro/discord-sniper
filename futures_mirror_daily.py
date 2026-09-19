"""futures_mirror_daily.py — what the SPY/QQQ -> MES/MNQ mirror would have made
today, scored on real ES/NQ bars.

    python futures_mirror_daily.py             # today
    python futures_mirror_daily.py 2026-09-11  # one day

The mirror ships OFF (see index_mirror.py). This measures a hypothetical route:
every evening, after the audit, the day's SPY/QQQ entries are replayed against
real 1-minute index futures bars with the SAME rules the live route would use —
market entry, the house 25/50 bracket, the futures ratchet — and the running
total since 2026-08-03 is updated. If the line turns up and stays up, the
switch is worth flipping. If it keeps going down, it stays off and nobody has
to argue about it.

The alerts come from two places, both of them, deduped:
  futures_mirror_shadow.csv — written live by the bridge for EVERY SPY/QQQ
    entry it sees, whatever happened to the option order. No rebuild needed.
  master_alerts.csv — the reconciled record, for days the shadow predates or
    for entries that never reached place().

The bars come from bars/ first (already bought), then Databento GLBX.MDP3
(about a cent a day) and the answer is cached back into bars/. With no key and
no cache the report says "bars: unavailable" and stops. It never invents a
price.

THE REPLAY RULES are copied from reference/futures_mirror_replay.py, the 9/13
study that measured -$721 over 149 alerts. The current live futures route does
not enforce the simulated exits, so the switch cannot be activated yet.
"""

import csv
import datetime as dt
import glob
import json
import math
import os
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SHADOW = os.path.join(HERE, "futures_mirror_shadow.csv")
MASTER = os.path.join(HERE, "master_alerts.csv")
CHAT = os.path.join(HERE, "recovered_alerts_chat.csv")   # entries read back out of the room logs — the bot never saw most of them
GRAB = os.path.join(HERE, "grab_alerts.csv")            # a year of room history, read by the production parser (grab_to_alerts.py)
BARS_DIR = os.path.join(HERE, "bars")
CUMULATIVE = os.path.join(HERE, "reference", "FUTURES-MIRROR-REPLAY.csv")
SEED = os.path.join(HERE, "reference", "FUTURES-MIRROR-REPLAY-2026-09-13.csv")
SETTINGS = os.path.join(HERE, "settings.json")

# Fixed -4, exactly as reference/futures_mirror_replay.py has it. The bars are
# UTC and the alerts are wall-clock ET; this is the one place they meet, and it
# has to agree with the study or the running total is two different numbers
# added together.
ET = ZoneInfo('America/New_York')

MAP = {"SPY": ("ES", "MES", 5.0), "QQQ": ("NQ", "MNQ", 2.0),
       # SPX / SPXW alerts are the same bet as SPY (G, 9/18): long MES on a call, short on a put
       "SPX": ("ES", "MES", 5.0), "SPXW": ("ES", "MES", 5.0)}
STOP, TGT = 25.0, 50.0
ARM = STOP * (5 / 7.5)          # 2/3 of the risk in profit -> breakeven
STEP = STOP * (2 / 7.5)         # then a rung every ~6.67 points

# The LEVEL mode (G, 9/18, measured in reference/PULLBACK-LEVEL-ENTRY-TEST.txt
# and FUTURES-RATCHET-SWEEP.txt): the alert only picks the direction; the
# entry is a limit resting `buf` points before the first round level in the
# pullback's path (ES every 25, NQ every 50), good for LEVEL_WAIT minutes,
# else the alert is skipped. Exits per instrument: MES a 12.5 bracket (1:1,
# the ratchet added nothing); MNQ a 10-pt stop, breakeven at +5, a rung every
# 2.5, no target (every target hurt MNQ). MNQ re-measured 9/18 morning
# (reference/MNQ-ENTRY-SWEEP.txt, 10,416 rows): the 25 grid with the limit 5
# pts THROUGH the level (buf -5 = wiggle room) and a 12.5 stop is 80% / +1001
# on 46 fills, 17 of 18 days positive, vs 75% / +569 at the 50 exactly.
# Per root: (grid, buf, stop, arm, step, target) — buf > 0 rests BEFORE the
# level, buf < 0 rests THROUGH it; arm/step/target None = not used.
LEVEL = {"ES": dict(grid=25.0, buf=2.0, stop=12.5, arm=None, step=None, target=12.5),
         "NQ": dict(grid=25.0, buf=-10.0, stop=12.5, arm=5.0, step=2.5, target=None)}
# NQ buf -10 (G, 9/19: "I prefer a higher percentage of winning"): 10 pts
# through the 25 = 44 fills, +$1,012, 91% win, worst day -$8, both halves
# positive, vs -5 = 47 fills, +$1,010, 81%. Same money, fewer and cleaner fills.
LEVEL_WAIT = 30                 # minutes the resting entry lives
CLOSE = dt.time(15, 59)
OPEN_MINUTE, LAST_MINUTE = 9 * 60 + 30, 15 * 60 + 45
DEDUPE_SECONDS = 180
SINCE = "2026-09-17"                   # the running total counts from the honest simulator (9/19); the year lives in reference/edge_lab.py
RT_FEE = 1.50                   # round-turn commission assumption, per contract

FIELDS = ["status", "entry", "exit", "why", "pts", "usd", "mfe", "mae", "bars",
          "mode", "ts", "sym", "dirn", "room", "caller", "src", "lvl", "ref"]


# ---------------------------------------------------------------- alerts

def _parse_time(day, t):
    import re
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?", str(t).strip())
    if not m:
        return None
    return dt.datetime.strptime(str(day)[:10], "%Y-%m-%d").replace(
        hour=int(m[1]), minute=int(m[2]), second=int(m[3] or 0), tzinfo=ET)


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def alerts_for(day):
    """Every SPY/QQQ entry on this date, from the shadow file and the master
    record, RTH-filtered and deduped. Same selection as
    reference/futures_mirror_alerts.py."""
    rows = []
    for r in _read_csv(SHADOW):
        if str(r.get("date") or "")[:10] != day:
            continue
        sym = str(r.get("sym") or "").upper()
        dirn = str(r.get("dirn") or "").upper()
        if sym not in MAP or dirn not in ("L", "S"):
            continue
        ts = _parse_time(day, r.get("time_et"))
        if ts is None:
            continue
        rows.append(dict(ts=ts, sym=sym, dirn=dirn, room=r.get("room") or "",
                         caller=r.get("caller") or "", src="shadow"))
    for r in _read_csv(MASTER):
        if str(r.get("date") or "")[:10] != day:
            continue
        sym = str(r.get("symbol") or "").upper()
        if sym not in MAP:
            continue
        side = str(r.get("side") or "").upper()
        if not side.startswith(("C", "P")):
            continue
        ts = _parse_time(day, r.get("time"))
        if ts is None:
            continue
        rows.append(dict(ts=ts, sym=sym, dirn="L" if side.startswith("C") else "S",
                         room=r.get("room") or "", caller=r.get("caller") or "",
                         src="bot"))
    # G, 9/18: "run this by all the alerts we have, even the ones skipped and not
    # taken" — every SPY/QQQ ENTRY recovered from the room logs, whether or not
    # the bot ever parsed it. The 3-minute dedupe below folds the ones it did.
    for r in _read_csv(CHAT):
        if str(r.get("date") or "")[:10] != day or str(r.get("msg_type") or "") != "entry":
            continue
        sym = str(r.get("symbol") or "").upper()
        side = str(r.get("side") or "").upper()
        if sym not in MAP or not side.startswith(("C", "P")):
            continue
        ts = _parse_time(day, r.get("time"))
        if ts is None:
            continue
        rows.append(dict(ts=ts, sym=sym, dirn="L" if side.startswith("C") else "S",
                         room=r.get("room") or "", caller=r.get("caller") or "",
                         src="chat"))
    # 9/19: the year of grabbed room history, parsed by parse_batch.js.
    for r in _read_csv(GRAB):
        if str(r.get("date") or "")[:10] != day:
            continue
        sym = str(r.get("symbol") or "").upper()
        side = str(r.get("side") or "").upper()
        if sym not in MAP or not side.startswith(("C", "P")):
            continue
        ts = _parse_time(day, r.get("time"))
        if ts is None:
            continue
        rows.append(dict(ts=ts, sym=sym, dirn="L" if side.startswith("C") else "S",
                         room=r.get("room") or "", caller=r.get("caller") or "",
                         src="grab"))
    # RTH, and early enough that there is a day left to trade.
    rows = [r for r in rows
            if OPEN_MINUTE <= r["ts"].hour * 60 + r["ts"].minute <= LAST_MINUTE]
    # Same symbol + direction inside 3 minutes is one alert, not two (relays
    # and echoes). The shadow row and the master row for the same call collapse
    # here too, which is why both sources can be read without double counting.
    rows.sort(key=lambda r: r["ts"])
    keep, last = [], {}
    for r in rows:
        k = (MAP[r["sym"]][0], r["dirn"])        # SPY and SPX relays of one move are one alert
        if k in last and (r["ts"] - last[k]).total_seconds() < DEDUPE_SECONDS:
            continue
        last[k] = r["ts"]
        keep.append(r)
    return keep


# ---------------------------------------------------------------- bars

def _load_bar_file(path, root, day):
    """The rows of one cached bar file that fall on this ET trading day."""
    b = _bar_frame(path, root)
    if b is None:
        return None
    d = dt.date.fromisoformat(day)
    lo = dt.datetime.combine(d, dt.time(9, 0), tzinfo=ET)
    hi = dt.datetime.combine(d, dt.time(16, 15), tzinfo=ET)
    w = b[(b.index >= lo) & (b.index <= hi)]
    return w if len(w) >= 200 else None


_FRAMES = {}


def _bar_frame(path, root):
    """One parsed frame per bar file, kept for the process — a year file is
    360k rows and the replays ask for 200 days out of it (9/19)."""
    key = (path, root, os.path.getmtime(path))
    if key not in _FRAMES:
        import pandas as pd
        b = pd.read_csv(path)
        if "ts_event" not in b.columns:
            _FRAMES[key] = None
        else:
            b["ts"] = pd.to_datetime(b["ts_event"], utc=True)
            if "symbol" in b.columns:
                b = b[b["symbol"].astype(str).str.upper().str.startswith(root)]
            _FRAMES[key] = b.set_index("ts").sort_index()
    return _FRAMES[key]


def cached_bars(root, day):
    exact = os.path.join(BARS_DIR, "%s_1m_%s.csv" % (root, day))
    for path in ([exact] if os.path.exists(exact) else []) + sorted(
            glob.glob(os.path.join(BARS_DIR, "%s_1m_*.csv" % root)), reverse=True):
        try:
            w = _load_bar_file(path, root, day)
        except Exception:                               # noqa: BLE001
            continue
        if w is not None:
            return w, os.path.basename(path)
    return None, None


def databento_bars(day):
    """Buy the day's ES and NQ 1-minute bars and cache them. Returns
    {root: frame} or raises with a sentence. About a cent."""
    with open(SETTINGS, encoding="utf-8") as f:
        cfg = json.load(f)
    key = ((cfg.get("execution", {}).get("databento") or {}).get("api_key") or "").strip()
    if not key:
        raise RuntimeError("no Databento key in settings.json "
                           "execution.databento.api_key")
    import databento as db
    import pandas as pd
    client = db.Historical(key)
    d = dt.date.fromisoformat(day)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3", schema="ohlcv-1m", stype_in="continuous",
        symbols=["ES.c.0", "NQ.c.0"],
        start=d.isoformat(), end=(d + dt.timedelta(days=1)).isoformat())
    df = data.to_df().reset_index()
    if df.empty:
        raise RuntimeError("Databento returned no bars for %s" % day)
    out = {}
    os.makedirs(BARS_DIR, exist_ok=True)
    for root in ("ES", "NQ"):
        part = df[df["symbol"].astype(str).str.upper().str.startswith(root)].copy()
        if part.empty:
            raise RuntimeError("Databento returned no %s bars for %s" % (root, day))
        part = part.rename(columns={"ts_recv": "ts_event"})
        cols = ["ts_event", "symbol", "open", "high", "low", "close", "volume"]
        part = part[[c for c in cols if c in part.columns]]
        part.to_csv(os.path.join(BARS_DIR, "%s_1m_%s.csv" % (root, day)),
                    index=False)
        part["ts"] = pd.to_datetime(part["ts_event"], utc=True)
        out[root] = part.set_index("ts").sort_index()
    return out


def bars_for(day):
    """({root: frame}, where_from) or (None, why_not)."""
    got, where = {}, []
    for root in ("ES", "NQ"):
        w, src = cached_bars(root, day)
        if w is None:
            got = None
            break
        got[root] = w
        where.append(src)
    if got:
        return got, "cache (%s)" % ", ".join(sorted(set(where)))
    try:
        return databento_bars(day), "Databento GLBX.MDP3 (cached into bars/)"
    except Exception as e:                              # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, str(e)[:200])


# ---------------------------------------------------------------- the replay

def run(a, mode, bars):
    """One alert, one entry mode. The market branch is copied from
    reference/futures_mirror_replay.py — do not 'improve' it here without
    re-running the whole history. The level branch is the 9/18 shape."""
    root, _micro, ppt = MAP[a["sym"]]
    b = bars[root]
    s = 1 if a["dirn"] == "L" else -1
    t0 = (a["ts"] + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    day_end = a["ts"].replace(hour=CLOSE.hour, minute=CLOSE.minute,
                              second=0, microsecond=0)
    w = b[(b.index >= t0) & (b.index <= day_end)]
    if w.empty:
        return dict(status="no bars")
    if mode == "market":
        e = float(w.iloc[0]["open"])
        ei = 0
        lvl = ref = ""
        stop_pts, tgt_pts, arm, step = STOP, TGT, ARM, STEP
    else:                       # level: resting limit before the round number
        L = LEVEL[root]
        ref = float(w.iloc[0]["open"])
        lvl = (math.floor(ref / L["grid"]) * L["grid"] if s > 0
               else math.ceil(ref / L["grid"]) * L["grid"])
        limit = lvl + s * L["buf"]
        if (limit >= ref) if s > 0 else (limit <= ref):
            ei, e = 0, ref                                 # already there
        else:
            ei = None
            for i in range(min(LEVEL_WAIT, len(w))):
                r = w.iloc[i]
                if (s > 0 and r["low"] <= limit) or (s < 0 and r["high"] >= limit):
                    ei = i
                    break
            if ei is None:
                return dict(status="level never touched", lvl=lvl, ref=ref)
            e = float(limit)
        stop_pts, tgt_pts, arm, step = L["stop"], L["target"], L["arm"], L["step"]
    stop = e - s * stop_pts
    tgt = e + s * tgt_pts if tgt_pts else None
    mfe = mae = 0.0
    # HONEST ORDER (9/19): the fill bar (ei) earns nothing and cannot stop us
    # — its other side's timing is unknown; on every later bar the stop and
    # target tested are the ones that existed at the bar's open, and the
    # ratchet moves AFTER, protecting from the next bar. The old loop
    # credited the fill bar's high and ratcheted on it; random direction
    # scored 71% under it.
    i = ei
    slip = 2 * 0.25                                  # a stop fills two ticks through (points)
    c0 = float(w.iloc[ei]["close"])
    if (c0 <= stop) if s > 0 else (c0 >= stop):     # the fill bar closed through the stop
        pts = (c0 - e) * s - slip
        return dict(status="ok", entry=e, exit=c0, why="STOP", pts=pts, usd=pts * ppt, mfe=0.0,
                    mae=abs(c0 - e), bars=1, lvl=lvl, ref=ref)
    for i in range(ei + 1, len(w)):
        r = w.iloc[i]
        hi, lo = float(r["high"]), float(r["low"])
        fav = (hi - e) * s if s > 0 else (e - lo)
        adv = (e - lo) if s > 0 else (hi - e)
        hit_stop = (lo <= stop) if s > 0 else (hi >= stop)
        hit_tgt = tgt is not None and ((hi >= tgt) if s > 0 else (lo <= tgt))
        if hit_stop:
            ex = stop - s * slip
            why = ("STOP" if stop == e - s * stop_pts
                   else ("BE" if abs(stop - e) < 1e-9 else "RATCHET"))
            break
        if hit_tgt:
            ex = tgt
            why = "TARGET"
            break
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        if arm is not None and mfe >= arm:
            k = math.floor((mfe - arm) / step)
            new = e + s * (k * step)
            if (s > 0 and new > stop) or (s < 0 and new < stop):
                stop = new
        cl = float(r["close"])
        if (cl <= stop) if s > 0 else (cl >= stop):   # (fix #2) closed through a moved stop: out at the close
            ex, why = cl - s * slip, "RATCHET"
            break
    else:
        ex = float(w.iloc[-1]["close"])
        why = "CLOSE"
    pts = (ex - e) * s
    return dict(status="ok", entry=e, exit=ex, why=why, pts=pts,
                usd=pts * ppt, mfe=mfe, mae=mae, bars=max(1, i - ei + 1),
                lvl=lvl, ref=ref)


# ---------------------------------------------------------------- cumulative

def _norm_ts(ts):
    """One spelling for a timestamp. The 9/13 seed was written by pandas with a
    space ("2026-09-11 11:21:00-04:00") and datetime.isoformat() writes a "T".
    Left alone, the same alert lands in the file twice and the running total
    counts the six-week history twice over."""
    return str(ts).replace("T", " ").strip()


def _key(r):
    return (r.get("mode"), _norm_ts(r.get("ts")), r.get("sym"), r.get("dirn"))


def load_cumulative():
    if not os.path.exists(CUMULATIVE):
        seed = [r for r in _read_csv(SEED) if r.get("mode") == "market"]
        os.makedirs(os.path.dirname(CUMULATIVE), exist_ok=True)
        with open(CUMULATIVE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in seed:
                w.writerow(r)
        return seed
    return _read_csv(CUMULATIVE)


def append_cumulative(existing, rows):
    """Only rows this file has never seen. A re-run of the same day adds
    nothing, so the running total cannot be inflated by running it twice."""
    seen = {_key(r) for r in existing}
    fresh = [r for r in rows if _key(r) not in seen]
    if fresh:
        with open(CUMULATIVE, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            for r in fresh:
                w.writerow(r)
    return fresh


# ---------------------------------------------------------------- the report

def _level_text():
    """The level shape, read from LEVEL so the report can never drift from it."""
    parts = []
    for root, L in LEVEL.items():
        ex = ("%g-pt 1:1 bracket" % L["stop"] if L["target"] and L["arm"] is None
              else "%g stop, BE at +%g, rungs %g%s" % (L["stop"], L["arm"], L["step"],
                                                         ", target %g" % L["target"] if L["target"] else ""))
        parts.append("%s: limit %s the %g, %s" % (
            MAP["SPY" if root == "ES" else "QQQ"][1],
            ("%g before" % L["buf"] if L["buf"] > 0 else "%g through" % -L["buf"]) if L["buf"] else "at",
            L["grid"], ex))
    return "; ".join(parts) + "; %d-min wait" % LEVEL_WAIT


def _money(x):
    return "%s$%.0f" % ("-" if x < 0 else "+", abs(x))


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out


def write_report(day, lines):
    import reports
    return reports.write_day("futures-mirror", day,
                             "\n".join(lines).rstrip() + "\n")


CAVEATS = [
    "",
    "### What this number is not",
    "",
    "- No slippage and no spread: entries fill at the next bar's OPEN, exits at",
    "  the exact stop/target price. A real market order does neither.",
    "- 1-minute bars, so a bar that touched the stop AND the target is scored as",
    "  a stop. Conservative, but it is a guess about which came first.",
    "- Commission is an assumption: $%.2f round turn per contract, shown net." % RT_FEE,
    "- The mirror is OFF. This is hypothetical: the current live futures route",
    "  records stop/target levels but does not enforce those exits at the broker.",
    "  Activation is blocked until protective exits are operational and tested.",
    "- New-day alert coverage is limited to bridge shadow rows and master_alerts;",
    "  a post missed before those stages is absent from this report.",
]


def main(day):
    alerts = alerts_for(day)
    lines = ["# FUTURES MIRROR — %s" % day, "",
             "SPY/QQQ room entries replayed as one-contract MES/MNQ two ways: "
             "market entry with a %g-pt stop / %g-pt target and the futures "
             "ratchet, and the LEVEL entry (%s)." % (STOP, TGT, _level_text()),
             "The switch is OFF: this is a measurement, not a trade.", ""]
    if not alerts:
        lines += ["**No SPY/QQQ entries on this date.** Nothing to replay.", ""]
        print(write_report(day, lines + CAVEATS))
        return 0

    bars, where = bars_for(day)
    if bars is None:
        lines += ["**bars: unavailable** — %s" % where, "",
                  "%d SPY/QQQ alert(s) were found for this date and are NOT "
                  "scored. Nothing is guessed and nothing is written to the "
                  "cumulative file; re-run once bars are available." % len(alerts),
                  ""]
        print(write_report(day, lines + CAVEATS))
        return 1

    results = []
    for mode in ("market", "level"):
        for a in alerts:
            r = run(a, mode, bars)
            r.update(mode=mode, ts=_norm_ts(a["ts"].isoformat()), sym=a["sym"],
                     dirn=a["dirn"], room=a["room"], caller=a["caller"],
                     src=a["src"])
            r.setdefault("lvl", "")
            r.setdefault("ref", "")
            results.append(r)

    existing = load_cumulative()
    fresh = append_cumulative(existing, results)
    allrows = existing + fresh

    mkt = [r for r in results if r["mode"] == "market"]
    mkt_ok = [r for r in mkt if r["status"] == "ok"]
    lvl_rows = [r for r in results if r["mode"] == "level"]
    lvl_ok = [r for r in lvl_rows if r["status"] == "ok"]
    day_usd = sum(float(r["usd"]) for r in mkt_ok)
    lvl_usd = sum(float(r["usd"]) for r in lvl_ok)

    def _hist(mode):
        return [r for r in allrows
                if r.get("mode") == mode and r.get("status") == "ok"
                and str(r.get("ts", ""))[:10] >= SINCE]
    hist = _hist("market")
    run_usd = sum(float(r["usd"]) for r in hist)
    run_wins = sum(1 for r in hist if float(r["usd"]) > 0)
    lhist = _hist("level")
    lrun_usd = sum(float(r["usd"]) for r in lhist)
    lrun_wins = sum(1 for r in lhist if float(r["usd"]) > 0)

    lines += ["**Bars:** %s" % where,
              "**Alerts:** %d (after RTH filter and 3-minute dedupe)" % len(alerts),
              ""]
    lines += ["## The day", ""]
    lines += _table(
        ["time ET", "sym", "dir", "micro", "room", "caller", "entry", "exit",
         "why", "pts", "$ market", "$ level"],
        [[r["ts"][11:19], r["sym"], "long" if r["dirn"] == "L" else "short",
          MAP[r["sym"]][1], (r["room"] or "")[:34], (r["caller"] or "")[:22],
          ("%.2f" % r["entry"]) if r["status"] == "ok" else "—",
          ("%.2f" % r["exit"]) if r["status"] == "ok" else "—",
          r["why"] if r["status"] == "ok" else r["status"],
          ("%+.2f" % r["pts"]) if r["status"] == "ok" else "—",
          _money(r["usd"]) if r["status"] == "ok" else "—",
          next((_money(s["usd"]) if s["status"] == "ok" else s["status"]
                for s in lvl_rows if s["ts"] == r["ts"] and s["sym"] == r["sym"]
                and s["dirn"] == r["dirn"]), "—")]
         for r in mkt])
    lines += ["",
              "$ level = the resting-limit entry (%s) with its own exits; "
              "\"level never touched\" = the alert was skipped, not lost." % _level_text(), ""]

    lines += ["## Totals", ""]
    lines += _table(
        ["", "trades", "gross", "net after $%.2f RT" % RT_FEE, "win rate"],
        [["Today (market)", len(mkt_ok), _money(day_usd),
          _money(day_usd - RT_FEE * len(mkt_ok)),
          "%.0f%%" % (100.0 * sum(1 for r in mkt_ok if float(r["usd"]) > 0)
                      / len(mkt_ok)) if mkt_ok else "—"],
         ["Today (level)", len(lvl_ok), _money(lvl_usd),
          _money(lvl_usd - RT_FEE * len(lvl_ok)),
          "%.0f%%" % (100.0 * sum(1 for r in lvl_ok if float(r["usd"]) > 0)
                      / len(lvl_ok)) if lvl_ok else "—"],
         ["**Since %s (market)**" % SINCE, len(hist), "**%s**" % _money(run_usd),
          _money(run_usd - RT_FEE * len(hist)),
          "%.0f%%" % (100.0 * run_wins / len(hist)) if hist else "—"],
         ["**Level, fills so far**", len(lhist), "**%s**" % _money(lrun_usd),
          _money(lrun_usd - RT_FEE * len(lhist)),
          "%.0f%%" % (100.0 * lrun_wins / len(lhist)) if lhist else "—"]])
    lines += ["", "The level row counts from the day it was added to this file "
              "(9/18); the history behind it is reference/PULLBACK-LEVEL-ENTRY-TEST.txt. "
              "It goes to G for a real-money decision at 30 fills per micro.", ""]

    def _group(rows, keyf, label):
        agg = {}
        for r in rows:
            k = keyf(r)
            a = agg.setdefault(k, [0, 0.0, 0])
            a[0] += 1
            a[1] += float(r["usd"])
            a[2] += 1 if float(r["usd"]) > 0 else 0
        body = ["## %s" % label, ""]
        body += _table([label.split(" ")[-1], "trades", "gross", "wins"],
                       [[k or "—", v[0], _money(v[1]), v[2]]
                        for k, v in sorted(agg.items(),
                                           key=lambda kv: kv[1][1])])
        return body + [""]

    if mkt_ok:
        lines += _group(mkt_ok, lambda r: (r["room"] or "")[:44], "By room")
        lines += _group(mkt_ok,
                        lambda r: "%s %s" % (r["sym"],
                                             "long" if r["dirn"] == "L" else "short"),
                        "By symbol and direction")
        exits = {}
        for r in mkt_ok:
            e = exits.setdefault(r["why"], [0, 0.0])
            e[0] += 1
            e[1] += float(r["usd"])
        lines += ["## How they ended", ""]
        lines += _table(["exit", "trades", "gross"],
                        [[k, v[0], _money(v[1])]
                         for k, v in sorted(exits.items(),
                                            key=lambda kv: -kv[1][0])])
        lines += [""]
    skipped = [r for r in mkt if r["status"] != "ok"]
    if skipped:
        lines += ["%d alert(s) could not be replayed: %s"
                  % (len(skipped), ", ".join(sorted({r["status"] for r in skipped}))),
                  ""]

    path = write_report(day, lines + CAVEATS)
    print("FUTURES MIRROR %s — %d alerts, day %s, running %s since %s (%d new "
          "rows in %s)"
          % (day, len(alerts), _money(day_usd), _money(run_usd), SINCE,
             len(fresh), os.path.basename(CUMULATIVE)))
    print(path)
    return 0


if __name__ == "__main__":
    import eastern
    raise SystemExit(main(eastern.day_arg()))
