#!/usr/bin/env python3
"""edge_lab.py — the honest research bench for the index-futures mirror.

G, 9/19: "backtest every single one of your ideas and more ... if something
starts elevating the % keep going that route." The bench that keeps that
honest:
  - the HONEST simulator (fill bar earns nothing; the stop/target tested on a
    bar are the ones that existed at its open; ratchet moves after; stops
    fill one tick through; limits need a trade-through of one tick; $1.50 RT)
  - IN-SAMPLE / OUT-OF-SAMPLE: everything is reported on the first half of
    the year (before SPLIT) and the second half separately. A result that
    holds only in-sample is curve-fit and is said so.
  - a RANDOM-DIRECTION control on the same fills, so "the callers" can be
    told apart from "the tape went up".
Alerts: every SPY/SPX/QQQ entry the bot saw, the room logs, and the grabbed
year (futures_mirror_daily.alerts_for). Bars: bars/*.csv. MEASUREMENT ONLY.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import pickle
import random
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import futures_mirror_daily as fm                          # noqa: E402

ET = fm.ET
RT = 1.5
TICK = 0.25
SLIP_TICKS = 1                      # a stop fills one tick through
SPLIT = dt.date(2026, 3, 16)        # in-sample before, out-of-sample from
CACHE = "/tmp/edge_lab.pkl"
CLOSE_MIN = 15 * 60 + 59


# ------------------------------------------------------------------ data

def _day_arrays(b):
    idx = b.index.tz_convert(ET)
    mins = (idx.hour * 60 + idx.minute).to_numpy()
    o = b["open"].astype(float).to_numpy(); h = b["high"].astype(float).to_numpy()
    l = b["low"].astype(float).to_numpy(); c = b["close"].astype(float).to_numpy()
    v = b["volume"].astype(float).to_numpy() if "volume" in b.columns else None
    return dict(mins=mins, o=o, h=h, l=l, c=c, v=v)


def load(force=False):
    """The bench's alerts and bars. ALERTS ARE RE-READ EVERY TIME (a new grab
    lands in grab_alerts.csv and must count); the day-bar arrays are the slow
    part, so they come from the cache and only days the cache has never seen
    are parsed. --reload throws the cache away and parses every day again."""
    cached = {}
    if not force and os.path.exists(CACHE):
        try:
            cached = pickle.load(open(CACHE, "rb")).get("bars") or {}
        except Exception:                                   # noqa: BLE001
            cached = {}
    days = set()
    for src, col in ((fm.MASTER, "symbol"), (fm.SHADOW, "sym"), (fm.CHAT, "symbol"), (fm.GRAB, "symbol")):
        for r in fm._read_csv(src):
            if str(r.get(col) or "").upper() in fm.MAP and len(str(r.get("date") or "")) == 10:
                days.add(r["date"][:10])
    bars, alerts = {}, []
    for day in sorted(d for d in days if d >= "2025-09-18"):
        ok = True
        for root in ("ES", "NQ"):
            if (root, day) in cached:
                bars[(root, day)] = cached[(root, day)]
                continue
            b, _ = fm.cached_bars(root, day)
            if b is None:
                ok = False
                break
            bars[(root, day)] = _day_arrays(b)
        if not ok:
            continue
        for a in fm.alerts_for(day):
            root, _m, ppt = fm.MAP[a["sym"]]
            alerts.append(dict(day=day, ts=a["ts"], mins=a["ts"].hour * 60 + a["ts"].minute,
                               sym=a["sym"], grp="SPY" if root == "ES" else "QQQ", root=root, ppt=ppt,
                               s=1 if a["dirn"] == "L" else -1, caller=a["caller"] or a["room"] or "?",
                               src=a["src"]))
    data = dict(alerts=alerts, bars=bars)
    pickle.dump(data, open(CACHE, "wb"))
    return data


# --------------------------------------------------------------- features

def features(D, a, root=None):
    """What was knowable at the alert minute, from that root's bars."""
    root = root or a["root"]
    B = D["bars"][(root, a["day"])]
    m = a["mins"]
    i0 = int((B["mins"] > m).argmax()) if (B["mins"] > m).any() else None   # first bar after the alert
    if i0 is None or i0 == 0:
        return None
    rth = (B["mins"] >= 9 * 60 + 30) & (B["mins"] <= m)
    if rth.sum() < 3:
        return None
    px = B["o"][i0]
    tp = (B["h"] + B["l"] + B["c"]) / 3
    if B["v"] is not None and B["v"][rth].sum() > 0:
        vwap = float((tp[rth] * B["v"][rth]).sum() / B["v"][rth].sum())
    else:
        vwap = float(tp[rth].mean())
    c = B["c"]
    ema = lambda n: _ema(c[:i0], n)
    e20, e50 = ema(20), ema(50)
    or_h = float(B["h"][(B["mins"] >= 570) & (B["mins"] < 585)].max()) if ((B["mins"] >= 570) & (B["mins"] < 585)).any() else None
    or_l = float(B["l"][(B["mins"] >= 570) & (B["mins"] < 585)].min()) if ((B["mins"] >= 570) & (B["mins"] < 585)).any() else None
    day_h = float(B["h"][rth].max()); day_l = float(B["l"][rth].min())
    opn = float(B["o"][(B["mins"] >= 570)][0]) if (B["mins"] >= 570).any() else px
    mom20 = float(px - c[max(0, i0 - 21)])
    rng = float((B["h"][max(0, i0 - 30):i0] - B["l"][max(0, i0 - 30):i0]).mean()) if i0 > 5 else 1.0
    return dict(i0=i0, px=px, vwap=vwap, e20=e20, e50=e50, or_h=or_h, or_l=or_l, day_h=day_h, day_l=day_l,
                opn=opn, mom20=mom20, rng=rng, pos=(px - day_l) / max(0.25, day_h - day_l))


def _ema(x, n):
    if len(x) < n:
        return float(x.mean()) if len(x) else 0.0
    k = 2.0 / (n + 1)
    e = float(x[:n].mean())
    for val in x[n:]:
        e = e + k * (float(val) - e)
    return e


# ---------------------------------------------------------------- entries

def bars_after(D, a, root=None):
    root = root or a["root"]
    B = D["bars"][(root, a["day"])]
    f = features(D, a, root)
    if f is None:
        return None, None, None
    i0 = f["i0"]
    sel = (B["mins"] <= CLOSE_MIN)
    hi, lo, cl = B["h"][i0:][sel[i0:]], B["l"][i0:][sel[i0:]], B["c"][i0:][sel[i0:]]
    if len(hi) == 0:
        return None, None, None
    return list(zip(hi, lo, cl)), float(B["o"][i0]), f


def fill_level(rows, e, s, grid, wait, buf):
    lvl = math.floor(e / grid) * grid if s > 0 else math.ceil(e / grid) * grid
    limit = lvl + s * buf
    if (limit >= e) if s > 0 else (limit <= e):
        return 0, e
    n = len(rows) if wait is None else min(len(rows), wait)
    for i in range(n):
        h, l, _c = rows[i]
        if (l <= limit - TICK) if s > 0 else (h >= limit + TICK):
            return i, limit
    return None, limit


def fill_pullback_pts(rows, e, s, pts, wait):
    limit = e - s * pts
    n = len(rows) if wait is None else min(len(rows), wait)
    for i in range(n):
        h, l, _c = rows[i]
        if (l <= limit - TICK) if s > 0 else (h >= limit + TICK):
            return i, limit
    return None, limit


def fill_breakout(rows, e, s, wait):
    """Enter when price takes out the alert bar's extreme in the alert's direction."""
    h0, l0, _ = rows[0]
    trig = h0 + TICK if s > 0 else l0 - TICK
    n = len(rows) if wait is None else min(len(rows), wait)
    for i in range(1, n):
        h, l, _c = rows[i]
        if (h >= trig) if s > 0 else (l <= trig):
            return i, trig
    return None, trig


# -------------------------------------------------------------------- sim

def sim(s, e, rows, ppt, stop, arm=None, rung=None, tgt=None, time_stop=None, be_at=None):
    """rows[0] is the fill bar (earns nothing, cannot stop us). Returns $ net."""
    st = e - s * stop
    target = e + s * tgt if tgt else None
    mfe = 0.0
    slip = SLIP_TICKS * TICK * ppt
    # The fill bar earns nothing, but if it CLOSES through the initial stop we
    # were stopped inside it — at the close, not at the stop (9/19 fix #2).
    c0 = rows[0][2]
    if (c0 <= st) if s > 0 else (c0 >= st):
        return (c0 - e) * s * ppt - slip - RT
    for k in range(1, len(rows)):
        h, l, c = rows[k]
        if (l <= st) if s > 0 else (h >= st):
            return (st - e) * s * ppt - slip - RT
        if target is not None and ((h >= target) if s > 0 else (l <= target)):
            return (target - e) * s * ppt - RT
        if time_stop and k >= time_stop:
            return (c - e) * s * ppt - RT
        fav = (h - e) if s > 0 else (e - l)
        if fav > mfe:
            mfe = fav
            if be_at is not None and mfe >= be_at:
                new = e
                if (s > 0 and new > st) or (s < 0 and new < st):
                    st = new
            if arm is not None and mfe >= arm:
                new = e + s * (math.floor((mfe - arm) / rung) * rung)
                if (s > 0 and new > st) or (s < 0 and new < st):
                    st = new
        # A stop moved on this bar that the bar has ALREADY closed through
        # is not a resting stop at that price — the trade is out at the
        # close (the next bar opens there or worse). The old rule let the
        # next bar "fill" at a stop it had gapped past (9/19 fix #2).
        if (c <= st) if s > 0 else (c >= st):
            return (c - e) * s * ppt - slip - RT
    return (rows[-1][2] - e) * s * ppt - RT


# ------------------------------------------------------------------ shapes

EXITS = {
    "MES 12.5 1:1": dict(stop=12.5, tgt=12.5),
    "MNQ 12.5/BE5/2.5": dict(stop=12.5, arm=5.0, rung=2.5),
}
ENTRY = {
    "ES": dict(grid=25.0, buf=2.0),
    "NQ": dict(grid=25.0, buf=-10.0),
}


def trade(D, a, entry="level", exitk=None, wait=30, root=None, force_s=None, **ov):
    """One alert -> $ or None (no fill). entry: instant | level | pb10 | pb20 | breakout."""
    root = root or a["root"]
    rows, e, f = bars_after(D, a, root)
    if rows is None:
        return None
    s = force_s if force_s is not None else a["s"]
    ppt = 5.0 if root == "ES" else 2.0
    if entry == "instant":
        i, fill = 0, e
    elif entry == "level":
        g = dict(ENTRY[root]); g.update({k: v for k, v in ov.items() if k in ("grid", "buf")})
        i, fill = fill_level(rows, e, s, g["grid"], wait, g["buf"])
    elif entry.startswith("pb"):
        i, fill = fill_pullback_pts(rows, e, s, float(entry[2:]), wait)
    elif entry == "breakout":
        i, fill = fill_breakout(rows, e, s, wait)
    else:
        raise ValueError(entry)
    if i is None:
        return None
    ex = dict(EXITS[exitk or ("MES 12.5 1:1" if root == "ES" else "MNQ 12.5/BE5/2.5")])
    ex.update({k: v for k, v in ov.items() if k in ("stop", "arm", "rung", "tgt", "time_stop", "be_at")})
    if "tgt" in ov and ov["tgt"] is None:
        ex.pop("tgt", None)
    return sim(s, fill, rows[i:], ppt, **ex)


# ----------------------------------------------------------------- report

def stats(pairs):
    """pairs: [(alert, $)]. -> dict with n, usd, per, win, dd."""
    if not pairs:
        return dict(n=0, usd=0.0, per=0.0, win=0.0, dd=0.0)
    vals = [v for _a, v in sorted(pairs, key=lambda x: x[0]["ts"])]
    peak = cum = dd = 0.0
    for v in vals:
        cum += v; peak = max(peak, cum); dd = min(dd, cum - peak)
    return dict(n=len(vals), usd=sum(vals), per=sum(vals) / len(vals), win=100.0 * sum(1 for v in vals if v > 0) / len(vals), dd=dd)


def line(label, pairs, control=None):
    IS = [p for p in pairs if p[0]["ts"].date() < SPLIT]
    OS = [p for p in pairs if p[0]["ts"].date() >= SPLIT]
    A, I, O = stats(pairs), stats(IS), stats(OS)
    months = defaultdict(float)
    for a, v in pairs:
        months[a["ts"].strftime("%y-%m")] += v
    mp = "%d/%d" % (sum(1 for v in months.values() if v > 0), len(months))
    # The control's own win% swings hard between IS and OOS (a regime shift in
    # the random baseline itself, not the caller) -- one overall "rnd" number
    # hides that and can make a caller look like he beats it on both halves
    # when he only beats an average of two very different baselines (9/19,
    # G: "double check Mike" -- his SPY instant looked ~50/50 against one rnd
    # number; split, IS was 59% vs a 35% control and OOS was 42% vs a 61%
    # control -- a flip, not an edge). ctl now always carries its own IS/OOS.
    ctl = ""
    if control is not None:
        CI = [p for p in control if p[0]["ts"].date() < SPLIT]
        CO = [p for p in control if p[0]["ts"].date() >= SPLIT]
        C, CIs, COs = stats(control), stats(CI), stats(CO)
        ctl = (" | rnd %3.0f%% %+6.0f (IS %3.0f%% %+6.0f / OOS %3.0f%% %+6.0f)"
               % (C["win"], C["usd"], CIs["win"], CIs["usd"], COs["win"], COs["usd"]))
    return ("%-46s n %4d  $%+7.0f  per %+5.1f  win %3.0f%%  dd %+6.0f  m+ %5s | IS n %3d %3.0f%% %+6.0f | OOS n %3d %3.0f%% %+6.0f%s"
            % (label, A["n"], A["usd"], A["per"], A["win"], A["dd"], mp, I["n"], I["win"], I["usd"], O["n"], O["win"], O["usd"], ctl))


def run_set(D, alerts, label, control=True, **kw):
    pairs = []
    for a in alerts:
        v = trade(D, a, **kw)
        if v is not None:
            pairs.append((a, v))
    ctl = None
    if control:
        ctl = []
        rnd = random.Random(11)
        for a in alerts:
            v = trade(D, a, force_s=rnd.choice((1, -1)), **kw)
            if v is not None:
                ctl.append((a, v))
    return pairs, line(label, pairs, ctl)


if __name__ == "__main__":
    D = load(force="--reload" in sys.argv)
    print("alerts", len(D["alerts"]), "days", len({a["day"] for a in D["alerts"]}), "split", SPLIT)
