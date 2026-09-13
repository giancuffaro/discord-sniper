"""futures_mirror_daily.py — what the SPY/QQQ -> MES/MNQ mirror would have made
today, scored on real ES/NQ bars.

    python futures_mirror_daily.py             # today
    python futures_mirror_daily.py 2026-09-11  # one day

The mirror ships OFF (see index_mirror.py). This is how it earns its way on:
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

THE REPLAY RULES ARE NOT NEW. They are copied line for line from
reference/futures_mirror_replay.py, the 9/13 study that measured -$721 over 149
alerts. Live behaviour and this report have to describe the same trade or
neither number means anything.
"""

import csv
import datetime as dt
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHADOW = os.path.join(HERE, "futures_mirror_shadow.csv")
MASTER = os.path.join(HERE, "master_alerts.csv")
BARS_DIR = os.path.join(HERE, "bars")
REPORT_DIR = os.path.join(HERE, "daily-reports")
CUMULATIVE = os.path.join(HERE, "reference", "FUTURES-MIRROR-REPLAY.csv")
SEED = os.path.join(HERE, "reference", "FUTURES-MIRROR-REPLAY-2026-09-13.csv")
SETTINGS = os.path.join(HERE, "settings.json")

# Fixed -4, exactly as reference/futures_mirror_replay.py has it. The bars are
# UTC and the alerts are wall-clock ET; this is the one place they meet, and it
# has to agree with the study or the running total is two different numbers
# added together.
ET = dt.timezone(dt.timedelta(hours=-4))

MAP = {"SPY": ("ES", "MES", 5.0), "QQQ": ("NQ", "MNQ", 2.0)}
STOP, TGT = 25.0, 50.0
ARM = STOP * (5 / 7.5)          # 2/3 of the risk in profit -> breakeven
STEP = STOP * (2 / 7.5)         # then a rung every ~6.67 points
CLOSE = dt.time(15, 59)
OPEN_MINUTE, LAST_MINUTE = 9 * 60 + 30, 15 * 60 + 45
DEDUPE_SECONDS = 180
SINCE = "2026-08-03"
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
    # RTH, and early enough that there is a day left to trade.
    rows = [r for r in rows
            if OPEN_MINUTE <= r["ts"].hour * 60 + r["ts"].minute <= LAST_MINUTE]
    # Same symbol + direction inside 3 minutes is one alert, not two (relays
    # and echoes). The shadow row and the master row for the same call collapse
    # here too, which is why both sources can be read without double counting.
    rows.sort(key=lambda r: r["ts"])
    keep, last = [], {}
    for r in rows:
        k = (r["sym"], r["dirn"])
        if k in last and (r["ts"] - last[k]).total_seconds() < DEDUPE_SECONDS:
            continue
        last[k] = r["ts"]
        keep.append(r)
    return keep


# ---------------------------------------------------------------- bars

def _load_bar_file(path, root, day):
    """The rows of one cached bar file that fall on this ET trading day."""
    import pandas as pd
    b = pd.read_csv(path)
    if "ts_event" not in b.columns:
        return None
    b["ts"] = pd.to_datetime(b["ts_event"], utc=True)
    if "symbol" in b.columns:
        b = b[b["symbol"].astype(str).str.upper().str.startswith(root)]
    b = b.set_index("ts").sort_index()
    d = dt.date.fromisoformat(day)
    lo = dt.datetime.combine(d, dt.time(9, 0), tzinfo=ET)
    hi = dt.datetime.combine(d, dt.time(16, 15), tzinfo=ET)
    w = b[(b.index >= lo) & (b.index <= hi)]
    return w if len(w) >= 200 else None


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
    """One alert, one entry mode. Copied from reference/futures_mirror_replay.py
    — do not 'improve' it here without re-running the whole history."""
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
    else:                       # 25-pt snap in his favour, 10-minute window
        ref = float(w.iloc[0]["open"])
        lvl = math.floor(ref / 25) * 25 if s > 0 else math.ceil(ref / 25) * 25
        ei = None
        for i in range(min(10, len(w))):
            r = w.iloc[i]
            if (s > 0 and r["low"] <= lvl) or (s < 0 and r["high"] >= lvl):
                ei = i
                break
        if ei is None:
            return dict(status="snap never touched", lvl=lvl, ref=ref)
        e = float(lvl)
    stop = e - s * STOP
    tgt = e + s * TGT
    mfe = mae = 0.0
    for i in range(ei, len(w)):
        r = w.iloc[i]
        hi, lo = float(r["high"]), float(r["low"])
        fav = (hi - e) * s if s > 0 else (e - lo)
        adv = (e - lo) if s > 0 else (hi - e)
        # stop first (conservative), then target, then the ratchet on this
        # bar's excursion
        hit_stop = (lo <= stop) if s > 0 else (hi >= stop)
        hit_tgt = (hi >= tgt) if s > 0 else (lo <= tgt)
        if hit_stop:
            ex = stop
            why = ("STOP" if stop == e - s * STOP
                   else ("BE" if abs(stop - e) < 1e-9 else "RATCHET"))
            break
        if hit_tgt:
            ex = tgt
            why = "TARGET"
            break
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        if mfe >= ARM:
            k = math.floor((mfe - ARM) / STEP)
            new = e + s * (k * STEP)
            if (s > 0 and new > stop) or (s < 0 and new < stop):
                stop = new
    else:
        ex = float(w.iloc[-1]["close"])
        why = "CLOSE"
    pts = (ex - e) * s
    return dict(status="ok", entry=e, exit=ex, why=why, pts=pts,
                usd=pts * ppt, mfe=mfe, mae=mae, bars=i - ei + 1,
                lvl=lvl, ref=ref)


# ---------------------------------------------------------------- cumulative

def _key(r):
    return (r.get("mode"), str(r.get("ts")), r.get("sym"), r.get("dirn"))


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

def _money(x):
    return "%s$%.0f" % ("-" if x < 0 else "+", abs(x))


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out


def write_report(day, lines):
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, "FUTURES-MIRROR-%s.md" % day)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return path


CAVEATS = [
    "",
    "### What this number is not",
    "",
    "- No slippage and no spread: entries fill at the next bar's OPEN, exits at",
    "  the exact stop/target price. A real market order does neither.",
    "- 1-minute bars, so a bar that touched the stop AND the target is scored as",
    "  a stop. Conservative, but it is a guess about which came first.",
    "- Commission is an assumption: $%.2f round turn per contract, shown net." % RT_FEE,
    "- The mirror is OFF. Nothing here was traded; no money moved.",
]


def main(day):
    alerts = alerts_for(day)
    lines = ["# FUTURES MIRROR — %s" % day, "",
             "SPY/QQQ room entries replayed as one-contract MES/MNQ, "
             "market entry, 25-pt stop / 50-pt target, futures ratchet.",
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
    for mode in ("market", "snap"):
        for a in alerts:
            r = run(a, mode, bars)
            r.update(mode=mode, ts=a["ts"].isoformat(), sym=a["sym"],
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
    snap = [r for r in results if r["mode"] == "snap"]
    snap_ok = [r for r in snap if r["status"] == "ok"]
    day_usd = sum(float(r["usd"]) for r in mkt_ok)
    snap_usd = sum(float(r["usd"]) for r in snap_ok)

    hist = [r for r in allrows
            if r.get("mode") == "market" and r.get("status") == "ok"
            and str(r.get("ts", ""))[:10] >= SINCE]
    run_usd = sum(float(r["usd"]) for r in hist)
    run_wins = sum(1 for r in hist if float(r["usd"]) > 0)

    lines += ["**Bars:** %s" % where,
              "**Alerts:** %d (after RTH filter and 3-minute dedupe)" % len(alerts),
              ""]
    lines += ["## The day", ""]
    lines += _table(
        ["time ET", "sym", "dir", "micro", "room", "caller", "entry", "exit",
         "why", "pts", "$ market", "$ snap*"],
        [[r["ts"][11:19], r["sym"], "long" if r["dirn"] == "L" else "short",
          MAP[r["sym"]][1], (r["room"] or "")[:34], (r["caller"] or "")[:22],
          ("%.2f" % r["entry"]) if r["status"] == "ok" else "—",
          ("%.2f" % r["exit"]) if r["status"] == "ok" else "—",
          r["why"] if r["status"] == "ok" else r["status"],
          ("%+.2f" % r["pts"]) if r["status"] == "ok" else "—",
          _money(r["usd"]) if r["status"] == "ok" else "—",
          next((_money(s["usd"]) if s["status"] == "ok" else s["status"]
                for s in snap if s["ts"] == r["ts"] and s["sym"] == r["sym"]
                and s["dirn"] == r["dirn"]), "—")]
         for r in mkt])
    lines += ["",
              "\\* the 25-pt-snap entry variant. **Selection-biased** — it only "
              "trades the alerts whose level happened to get touched inside ten "
              "minutes, which is a filter you cannot apply live. Shown for "
              "comparison, never as the headline.", ""]

    lines += ["## Totals", ""]
    lines += _table(
        ["", "trades", "gross", "net after $%.2f RT" % RT_FEE, "win rate"],
        [["Today (market)", len(mkt_ok), _money(day_usd),
          _money(day_usd - RT_FEE * len(mkt_ok)),
          "%.0f%%" % (100.0 * sum(1 for r in mkt_ok if float(r["usd"]) > 0)
                      / len(mkt_ok)) if mkt_ok else "—"],
         ["Today (snap*)", len(snap_ok), _money(snap_usd),
          _money(snap_usd - RT_FEE * len(snap_ok)),
          "%.0f%%" % (100.0 * sum(1 for r in snap_ok if float(r["usd"]) > 0)
                      / len(snap_ok)) if snap_ok else "—"],
         ["**Since %s (market)**" % SINCE, len(hist), "**%s**" % _money(run_usd),
          _money(run_usd - RT_FEE * len(hist)),
          "%.0f%%" % (100.0 * run_wins / len(hist)) if hist else "—"]])
    lines += ["", "The running total is the market column only — the snap "
              "column has no seeded history and is biased anyway.", ""]

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
    _d = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    raise SystemExit(main(_d))
