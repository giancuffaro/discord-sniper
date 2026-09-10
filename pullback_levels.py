#!/usr/bin/env python3
"""
pullback_levels.py — which PULLBACK LEVEL should the beta names use?

G, 9/9: "now that we have data to backtest — would beta names like META,
AMD, AAPL benefit from a better pullback? instead of the nearest dollar,
$2? the first price ending in 5 or 2.50? every $4 or $5 — those are prices
they like to bounce and reject from."

WHAT IT DOES
  1. ALERTS  every round-number arm the bridge ever logged for a managed
     beta name (trades.log "PULLBACK META CALL: stock at 741.23, waiting
     for a dip to $741") — the stock price the moment the room called it —
     plus the pre-8/18 refused calls on the same names (price looked up).
  2. PRICES  real 1-second stock bars (Databento XNAS.ITCH ohlcv-1s) for
     every symbol-day that has an alert. Cached in bars/stock/ so a re-run
     costs nothing. Cost is checked and printed BEFORE anything is bought.
  3. REPLAY  every alert against every level grid — take-it-now, $0.50, $1
     (today's rule), $2, $2.50, $5 — and every wait window (5/10/15 min):
       entry  = first second the stock touches the level (dip for a call,
                bounce for a put), else no trade.
       exit   = the pullback's own underlying rule for these names: stop
                $1.00 against / target $2.50 for, else 15:55 flatten.
     Measured in STOCK dollars per share — the unit the rule is written in.
     Also: the unfilled alerts' outcome (what a deeper level gave up).
  4. LEVELS  alert-free test of G's claim: on every symbol-day, how much
     does price bounce off a $5 / $2.50 / $2 / $1 / $0.50 multiple in the
     5 min after touching it, vs an arbitrary 25-cent line (control)?

RUN   python3 pullback_levels.py            # full report
      python3 pullback_levels.py --cost     # only price the pull, buy nothing
      python3 pullback_levels.py --no-fetch # replay from cache only
Read-only over every record. Never trades. Writes only bars/stock/*.csv
and reference/PULLBACK-LEVELS.md.
"""
import csv
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pullback  # noqa: E402  (the live rule — MANAGED names, exit levels)

TRADES_LOG = os.path.join(HERE, "trades.log")
SETTINGS = os.path.join(HERE, "settings.json")
BARS_DIR = os.path.join(HERE, "bars", "stock")
REPORT = os.path.join(HERE, "reference", "PULLBACK-LEVELS.md")
ET = ZoneInfo("America/New_York")
BETA = sorted(s for s in pullback.MANAGED if s not in ("SPY", "QQQ"))
GRIDS = (0.0, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0)   # 0.0 = take it at the alert
WINDOWS = (300, 600, 900)                       # seconds to wait for the touch
FLATTEN = (15, 55)                              # 0DTE flatten, ET
CONTROL = 0.25                                  # the "any old line" grid

ARM_RE = re.compile(
    r"^(\S+)\t.*PULLBACK (\w+) (CALL|PUT): stock at ([\d.]+), waiting for a "
    r"(?:dip|bounce) to \$([\d.]+) \((\d+)s window\)")
TOUCH_RE = re.compile(r"^(\S+)\t.*PULLBACK (\w+): touched \$([\d.]+) \(at ([\d.]+)\)")
MISS_RE = re.compile(r"^(\S+)\t.*PULLBACK (\w+): never touched \$([\d.]+)")
OPEN_RE = re.compile(
    r"^(\S+)\t(?:REFUSED|ERROR|TEST)\s+OPEN (\w+) \(([^)]*)'s call\) ([\d.]+)([CP]) ")


def _ep(iso):
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


# ---------- 1. the alerts ----------
def load_alerts():
    """[{ts, date, symbol, side, px0, target, window, logged}] — one per
    call. Arms carry the live stock price; refused pre-arm calls get px0
    from the tape later. Twins (same name+side within 60 s) collapse."""
    out, arms = [], {}
    if not os.path.exists(TRADES_LOG):
        return out
    with open(TRADES_LOG, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            m = ARM_RE.match(ln)
            if m:
                ts = _ep(m.group(1))
                sym = m.group(2).upper()
                if ts and sym in BETA:
                    a = {"ts": ts, "date": m.group(1)[:10], "symbol": sym,
                         "side": "CALLS" if m.group(3) == "CALL" else "PUTS",
                         "px0": float(m.group(4)), "target": float(m.group(5)),
                         "window": int(m.group(6)), "logged": None, "src": "arm"}
                    out.append(a)
                    arms[(sym, round(a["target"]))] = a
                continue
            m = TOUCH_RE.match(ln)
            if m:
                a = arms.get((m.group(2).upper(), round(float(m.group(3)))))
                if a and a["logged"] is None:
                    a["logged"] = ("touched", _ep(m.group(1)), float(m.group(4)))
                continue
            m = MISS_RE.match(ln)
            if m:
                a = arms.get((m.group(2).upper(), round(float(m.group(3)))))
                if a and a["logged"] is None:
                    a["logged"] = ("missed", _ep(m.group(1)), None)
                continue
            m = OPEN_RE.match(ln)
            if m:
                ts = _ep(m.group(1))
                sym = m.group(2).upper()
                if ts and sym in BETA:
                    out.append({"ts": ts, "date": m.group(1)[:10], "symbol": sym,
                                "side": "CALLS" if m.group(5) == "C" else "PUTS",
                                "px0": None, "target": None, "window": None,
                                "logged": None, "src": "open"})
    out.sort(key=lambda a: a["ts"])
    dedup = []
    for a in out:
        twin = next((b for b in dedup if b["symbol"] == a["symbol"] and b["side"] == a["side"]
                     and abs(b["ts"] - a["ts"]) <= 60), None)
        if twin:
            if twin["px0"] is None and a["px0"] is not None:
                twin.update({k: a[k] for k in ("px0", "target", "window", "logged", "src")})
            continue
        dedup.append(a)
    return dedup


# ---------- 2. the prices ----------
def _bars_path(sym, date):
    return os.path.join(BARS_DIR, "%s_%s_1s.csv" % (sym, date))


def load_bars(sym, date):
    """[(epoch, o, h, l, c)] for the regular session, or [] if not cached."""
    p = _bars_path(sym, date)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, newline="") as fh:
        for r in csv.reader(fh):
            if r and r[0] != "ts":
                out.append((float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return out


def _session(date):
    d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ET)
    return (d.replace(hour=9, minute=30).astimezone(timezone.utc),
            d.replace(hour=16, minute=0).astimezone(timezone.utc))


def fetch_bars(need, cost_only=False):
    """need = {(sym, date)}. Prices the pull first, prints it, then buys
    only what isn't cached. Returns the dollar cost quoted by Databento."""
    missing = sorted(k for k in need if not os.path.exists(_bars_path(*k)))
    if not missing:
        print("  bars: every symbol-day already cached — nothing to buy")
        return 0.0
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            key = ((json.load(fh).get("execution") or {}).get("databento") or {}).get("api_key", "")
    except (OSError, ValueError):
        key = ""
    if not key:
        print("  bars: no Databento key in settings.json — replaying from cache only")
        return 0.0
    import databento as db
    client = db.Historical(key)
    by_day = defaultdict(list)
    for sym, date in missing:
        by_day[date].append(sym)
    total = 0.0
    quotes = []
    for date, syms in sorted(by_day.items()):
        s, e = _session(date)
        try:
            c = client.metadata.get_cost(dataset="XNAS.ITCH", symbols=syms,
                                         schema="ohlcv-1s", start=s, end=e)
        except Exception as ex:                      # noqa: BLE001
            print("  cost check failed for %s %s: %s" % (date, syms, str(ex)[:120]))
            c = None
        quotes.append((date, syms, c))
        total += c or 0.0
    print("  bars to buy: %d symbol-days over %d days; Databento quote $%.4f"
          % (len(missing), len(by_day), total))
    if cost_only:
        for date, syms, c in quotes:
            print("    %s  %-40s  $%s" % (date, ",".join(syms), "?" if c is None else "%.4f" % c))
        return total
    os.makedirs(BARS_DIR, exist_ok=True)
    for date, syms, c in quotes:
        s, e = _session(date)
        try:
            data = client.timeseries.get_range(dataset="XNAS.ITCH", symbols=syms,
                                               schema="ohlcv-1s", start=s, end=e)
            df = data.to_df()
        except Exception as ex:                      # noqa: BLE001
            print("  %s: pull failed — %s" % (date, str(ex)[:160]))
            continue
        got = defaultdict(list)
        for ts, row in df.iterrows():
            got[str(row["symbol"]).upper()].append(
                (ts.timestamp(), float(row["open"]), float(row["high"]),
                 float(row["low"]), float(row["close"])))
        for sym in syms:
            rows = sorted(got.get(sym, []))
            with open(_bars_path(sym, date), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["ts", "o", "h", "l", "c"])
                for r in rows:
                    w.writerow(["%.0f" % r[0]] + ["%.4f" % v for v in r[1:]])
            print("  %s %-5s %6d one-second bars" % (date, sym, len(rows)))
    return total


# ---------- 3. the replay ----------
def level_for(px, side, grid):
    """The grid line the stock must come back to. grid 0 = no waiting."""
    if not grid:
        return px
    call = pullback.is_call(side)
    n = px / grid
    if abs(n - round(n)) * grid < 0.01:          # already standing on one
        return round(n) * grid
    return (math.floor(n) if call else math.ceil(n)) * grid


def _px_at(bars, ts):
    for b in bars:
        if b[0] >= ts:
            return b[4]
    return None


# ---------- the exit that actually binds: the option ratchet, in stock $ ----------
# The bridge's real exit on these trades is the RATCHET on the OPTION
# (born -7.5%, arm to breakeven at +5%, +2% rungs) — it fires long before
# the pullback's own $1 stock stop does. To compare grids under the exit
# that really decides P&L, each alert's ratchet is translated into stock
# dollars through its premium P and delta Δ:  a $m stock move ≈ Δ·m on the
# option, so -7.5% of P is a stock move of 0.075·P/Δ.  P = the caller's
# premium from the log; Δ from Black-Scholes with a per-name IV guess.
# It is a proxy (no gamma, no spread) — good enough to RANK grids, not to
# quote dollars to the cent.
BORN_PCT, ARM_PCT, RUNG_PCT = 7.5, 5.0, 2.0
IV_GUESS = {"TSLA": 0.60, "NVDA": 0.50, "AMD": 0.55, "META": 0.40, "AMZN": 0.38,
            "GOOGL": 0.35, "GOOG": 0.35, "AAPL": 0.32, "MSFT": 0.26}
PREM_RE = re.compile(r"\$?(\d{2,4}(?:\.\d+)?)\s*([CP])\b[^@\n]{0,60}@\s*\$?(\d+(?:\.\d+)?)")
EXP_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|([0-9])DTE)\b")
_LOG_BY_SYM = None


def _log_index():
    """symbol -> [(ts, line)] once, for premium look-ups."""
    global _LOG_BY_SYM
    if _LOG_BY_SYM is not None:
        return _LOG_BY_SYM
    idx = defaultdict(list)
    if os.path.exists(TRADES_LOG):
        with open(TRADES_LOG, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ts = _ep(ln.split("\t", 1)[0])
                if ts is None:
                    continue
                for sym in BETA:
                    if re.search(r"\b%s\b" % sym, ln):
                        idx[sym].append((ts, ln))
    _LOG_BY_SYM = idx
    return idx


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs(S, K, T, iv, call):
    """(price, delta) — r = 0, good enough for a 0-3 DTE proxy."""
    T = max(T, 0.3 / 252.0)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if call:
        return (S * _norm_cdf(d1) - K * _norm_cdf(d2), _norm_cdf(d1))
    return (K * _norm_cdf(-d2) - S * _norm_cdf(-d1), -_norm_cdf(-d1))


def contract_for(alert):
    """(premium, delta, strike, dte) for the alert's contract — premium from
    the caller's own line in the log when it's there, else Black-Scholes."""
    sym, ts0, px0, side = alert["symbol"], alert["ts"], alert["px0"], alert["side"]
    call = pullback.is_call(side)
    strike = prem = None
    dte = 1.0
    for ts, ln in _log_index().get(sym, ()):
        if abs(ts - ts0) > 180:
            continue
        m = PREM_RE.search(ln)
        if not m or (m.group(2) == "C") != call:
            continue
        strike, prem = float(m.group(1)), float(m.group(3))
        e = EXP_RE.search(ln[m.end(2):])
        if e:
            if e.group(2):
                dte = float(e.group(2))
            else:
                try:
                    txt = e.group(1)
                    if "-" in txt:
                        exp = datetime.strptime(txt, "%Y-%m-%d")
                    else:
                        parts = txt.split("/")
                        yr = int(parts[2]) if len(parts) == 3 else datetime.fromtimestamp(ts0).year
                        yr = yr + 2000 if yr < 100 else yr
                        exp = datetime(yr, int(parts[0]), int(parts[1]))
                    dte = max(0.0, (exp - datetime.fromtimestamp(ts0)).total_seconds() / 86400.0)
                except (ValueError, IndexError):
                    pass
        break
    if strike is None or px0 is None:
        return None
    iv = IV_GUESS.get(sym, 0.40)
    bs_px, delta = _bs(px0, strike, (dte + 0.5) / 365.0, iv, call)
    delta = min(0.75, max(0.15, abs(delta)))
    if prem is None or prem <= 0:
        prem = max(0.05, bs_px)
    return {"premium": prem, "delta": delta, "strike": strike, "dte": dte}


def replay_ratchet(alert, bars, grid, window, con):
    """Same entry as replay(); exit = the option ratchet expressed in stock $.
    Returns option-$ per contract (Δ-scaled), % of premium, armed flag."""
    base = replay(alert, bars, grid, window)
    if not base or not base["entered"] or not con:
        return base
    call = pullback.is_call(alert["side"])
    e, entry_ts = base["entry"], base["entry_ts"]
    unit = con["premium"] / con["delta"] / 100.0       # stock $ per 1% of premium
    born, arm, rung = BORN_PCT * unit, ARM_PCT * unit, RUNG_PCT * unit
    stop = e - born if call else e + born
    armed, mfe = False, 0.0
    day = datetime.fromtimestamp(entry_ts, ET)
    flat_ts = day.replace(hour=FLATTEN[0], minute=FLATTEN[1], second=0).timestamp()
    exit_px, why, last = None, "", e
    for b in bars:
        if b[0] <= entry_ts:
            continue
        if b[0] >= flat_ts:
            break
        hi, lo = b[2], b[3]
        # stop checked with LAST bar's level — a spike-and-drop inside one
        # second earns no arm
        if (call and lo <= stop) or (not call and hi >= stop):
            exit_px, why = stop, ("ratchet" if armed else "born stop")
            break
        fav = (hi - e) if call else (e - lo)
        if fav > mfe:
            mfe = fav
            if mfe >= arm:
                armed = True
                k = math.floor((mfe - arm) / rung)
                stop = (e + k * rung) if call else (e - k * rung)
        last = b[4]
    if exit_px is None:
        exit_px, why = last, "flatten"
    m = (exit_px - e) if call else (e - exit_px)
    pct = con["delta"] * m / con["premium"] * 100.0
    base.update({"r_pnl": round(m, 2), "r_why": why, "r_armed": armed,
                 "r_pct": round(pct, 1), "r_opt": round(con["delta"] * m * 100.0, 2),
                 "r_born_$": round(born, 2), "r_arm_$": round(arm, 2)})
    return base


def replay(alert, bars, grid, window):
    """One alert, one grid, one window → dict(entered, entry_ts, entry,
    exit, exit_why, pnl, mfe, mae) in stock $/share, or None w/o data."""
    px0, side, ts0 = alert["px0"], alert["side"], alert["ts"]
    if px0 is None or not bars:
        return None
    call = pullback.is_call(side)
    lvl = level_for(px0, side, grid)
    entry_ts, entry = None, None
    if not grid:
        entry_ts, entry = ts0, px0
    else:
        for b in bars:
            if b[0] < ts0:
                continue
            if b[0] > ts0 + window:
                break
            if (call and b[3] <= lvl + 1e-9) or (not call and b[2] >= lvl - 1e-9):
                entry_ts, entry = b[0], lvl
                break
    if entry is None:
        return {"entered": False, "level": lvl}
    stop_d, tgt_d = pullback.exit_levels(alert["symbol"])
    stop = entry - stop_d if call else entry + stop_d
    tgt = entry + tgt_d if call else entry - tgt_d
    day = datetime.fromtimestamp(entry_ts, ET)
    flat_ts = day.replace(hour=FLATTEN[0], minute=FLATTEN[1], second=0).timestamp()
    mfe = mae = 0.0
    last = entry
    exit_px, why, exit_ts = None, "", None
    for b in bars:
        if b[0] <= entry_ts:
            continue
        if b[0] >= flat_ts:
            break
        hi, lo = b[2], b[3]
        fav = (hi - entry) if call else (entry - lo)
        adv = (entry - lo) if call else (hi - entry)
        mfe, mae = max(mfe, fav), max(mae, adv)
        hit_stop = lo <= stop if call else hi >= stop
        hit_tgt = hi >= tgt if call else lo <= tgt
        if hit_stop:                                 # same second: stop wins (conservative)
            exit_px, why, exit_ts = stop, "stop", b[0]
            break
        if hit_tgt:
            exit_px, why, exit_ts = tgt, "target", b[0]
            break
        last = b[4]
    if exit_px is None:
        exit_px, why, exit_ts = last, "flatten", flat_ts
    pnl = (exit_px - entry) if call else (entry - exit_px)
    return {"entered": True, "level": lvl, "entry_ts": entry_ts, "entry": entry,
            "wait_s": entry_ts - ts0, "exit": exit_px, "exit_why": why,
            "exit_ts": exit_ts, "pnl": round(pnl, 2), "mfe": round(mfe, 2),
            "mae": round(mae, 2), "improve": round((px0 - entry) if call else (entry - px0), 2)}


# ---------- 4. do the levels themselves bounce? ----------
def level_reactions(bars, grid, lookahead=300, lookback=120):
    """Every FIRST touch of a grid line from above (support test) or below
    (resistance test): how far did price bounce back within `lookahead` s?
    Returns list of bounce sizes in $ (positive = reacted away from the line)."""
    if not bars:
        return []
    out = []
    seen = set()
    n = len(bars)
    for i in range(1, n):
        ts, o, h, l, c = bars[i]
        prev_c = bars[i - 1][4]
        # lines crossed/touched by this bar
        lo_n, hi_n = math.floor(l / grid + 1e-9), math.floor(h / grid + 1e-9)
        for k in range(lo_n, hi_n + 1):
            lvl = k * grid
            if lvl < l - 1e-9 or lvl > h + 1e-9:
                continue
            key = (k, "sup" if prev_c > lvl else "res")
            if key in seen:
                continue
            if grid == CONTROL and abs(lvl * 2 - round(lvl * 2)) < 1e-6:
                continue                             # control = x.25 / x.75 lines ONLY
            # must be the first touch after having been >= 0.25 away
            back = [b for b in bars[max(0, i - 200):i] if b[0] >= ts - lookback]
            if prev_c > lvl:                         # coming down onto support
                if not back or min(b[3] for b in back) < lvl + 0.10:
                    continue
                ahead = [b for b in bars[i + 1:i + 400] if b[0] <= ts + lookahead]
                if not ahead:
                    continue
                bounce = max(b[2] for b in ahead) - lvl
                fail = lvl - min(b[3] for b in ahead)
            elif prev_c < lvl:                       # coming up into resistance
                if not back or max(b[2] for b in back) > lvl - 0.10:
                    continue
                ahead = [b for b in bars[i + 1:i + 400] if b[0] <= ts + lookahead]
                if not ahead:
                    continue
                bounce = lvl - min(b[3] for b in ahead)
                fail = max(b[2] for b in ahead) - lvl
            else:
                continue
            seen.add(key)
            out.append((round(bounce, 2), round(fail, 2)))
    return out


# ---------- report ----------
def main():
    cost_only = "--cost" in sys.argv
    no_fetch = "--no-fetch" in sys.argv
    alerts = load_alerts()
    need = {(a["symbol"], a["date"]) for a in alerts}
    print("PULLBACK LEVELS — %d alerts on %s over %d symbol-days"
          % (len(alerts), "/".join(BETA), len(need)))
    if not no_fetch:
        fetch_bars(need, cost_only=cost_only)
        if cost_only:
            return
    bars = {k: load_bars(*k) for k in need}
    have = {k for k, v in bars.items() if v}
    print("  symbol-days with prices: %d/%d" % (len(have), len(need)))
    # price the pre-arm alerts off the tape
    for a in alerts:
        if a["px0"] is None:
            a["px0"] = _px_at(bars.get((a["symbol"], a["date"]), []), a["ts"])
    usable = [a for a in alerts if a["px0"] is not None and (a["symbol"], a["date"]) in have]
    print("  alerts with a price and a tape: %d" % len(usable))

    # sanity: does the $1 replay agree with what the bridge logged?
    agree = total = 0
    for a in usable:
        if a["src"] != "arm" or not a["logged"]:
            continue
        r = replay(a, bars[(a["symbol"], a["date"])], 1.0, a["window"] or 300)
        if r is None:
            continue
        total += 1
        if (r["entered"] and a["logged"][0] == "touched") or \
           (not r["entered"] and a["logged"][0] == "missed"):
            agree += 1
    lines = []
    lines.append("# Pullback levels — beta names (%s)" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("")
    lines.append("%d alerts, %d symbol-days with real 1-second prices. "
                 "The $1 replay agrees with the bridge's own touched/missed log on %d/%d arms."
                 % (len(usable), len(have), agree, total))
    lines.append("")
    # ---- A. under the exit that really fires: the option ratchet ----
    cons = {id(a): contract_for(a) for a in usable}
    with_con = [a for a in usable if cons[id(a)]]
    lines.append("## A. Under the real exit — the %g/%g/%g option ratchet (proxy in stock $)"
                 % _rt.live_spacing())
    lines.append("")
    lines.append("%d of %d alerts carry a premium in the log (the rest are priced by "
                 "Black-Scholes). Option $ = per ONE contract, Δ-scaled. 'per alert' counts "
                 "skipped alerts as 0. Born stop on these names works out to about $%.2f of "
                 "stock, arm at $%.2f (medians)."
                 % (len([a for a in with_con if True]), len(usable),
                    sorted(BORN_PCT * cons[id(a)]["premium"] / cons[id(a)]["delta"] / 100.0
                           for a in with_con)[len(with_con) // 2] if with_con else 0,
                    sorted(ARM_PCT * cons[id(a)]["premium"] / cons[id(a)]["delta"] / 100.0
                           for a in with_con)[len(with_con) // 2] if with_con else 0))
    lines.append("")
    lines.append("| grid | wait | entered | of %d | better entry | armed (reached +5%%) | born-stopped | "
                 "option $ total | per alert | avg %% of premium |" % len(with_con))
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    best_r = {}
    for grid in GRIDS:
        for window in (WINDOWS if grid else (WINDOWS[0],)):
            res = [replay_ratchet(a, bars[(a["symbol"], a["date"])], grid, window, cons[id(a)])
                   for a in with_con]
            ent = [r for r in res if r and r["entered"] and "r_opt" in r]
            if not ent:
                continue
            tot = sum(r["r_opt"] for r in ent)
            armed = sum(1 for r in ent if r["r_armed"])
            born = sum(1 for r in ent if r["r_why"] == "born stop")
            lines.append("| %s | %s | %d | %d%% | $%.2f | %d%% | %d%% | %+.0f | %+.2f | %+.1f%% |"
                         % ("take it" if not grid else "$%g" % grid,
                            "—" if not grid else "%d min" % (window // 60),
                            len(ent), round(100.0 * len(ent) / len(with_con)),
                            sum(r["improve"] for r in ent) / len(ent),
                            round(100.0 * armed / len(ent)), round(100.0 * born / len(ent)),
                            tot, tot / len(with_con),
                            sum(r["r_pct"] for r in ent) / len(ent)))
            best_r[(grid, window)] = (tot, len(ent))
    lines.append("")
    lines.append("Per symbol, ratchet exit, 10-minute wait (option $ total, entered/alerts):")
    lines.append("")
    lines.append("| symbol | alerts | " + " | ".join("take it" if not g else "$%g" % g for g in GRIDS) + " |")
    lines.append("|---|---|" + "---|" * len(GRIDS))
    for sym in BETA:
        al = [a for a in with_con if a["symbol"] == sym]
        if not al:
            continue
        cells = []
        for grid in GRIDS:
            res = [replay_ratchet(a, bars[(a["symbol"], a["date"])], grid, 600, cons[id(a)]) for a in al]
            ent = [r for r in res if r and r["entered"] and "r_opt" in r]
            cells.append("%+.0f (%d/%d)" % (sum(r["r_opt"] for r in ent), len(ent), len(al)))
        lines.append("| %s | %d | %s |" % (sym, len(al), " | ".join(cells)))
    lines.append("")
    # PAIRED — the only fair grid-vs-grid test: same alert, both grids fill,
    # what changed? Removes the "deeper grid only fills the easy ones" bias.
    lines.append("Paired, same alert, both grids filled (ratchet exit, 10-min wait). "
                 "Mean = option $ per contract the other grid made OVER $1; SE = noise band. "
                 "Ties = the trade ended the same way whichever level bought it.")
    lines.append("")
    lines.append("| compare | pairs | mean diff | SE | better | worse | ties |")
    lines.append("|---|---|---|---|---|---|---|")

    def _paired(ga, wa, gb, wb):
        d = []
        for a in with_con:
            b = bars[(a["symbol"], a["date"])]
            ra = replay_ratchet(a, b, ga, wa, cons[id(a)])
            rb = replay_ratchet(a, b, gb, wb, cons[id(a)])
            if ra and rb and ra.get("entered") and rb.get("entered") \
                    and "r_opt" in ra and "r_opt" in rb:
                d.append(rb["r_opt"] - ra["r_opt"])
        if not d:
            return None
        mean = sum(d) / len(d)
        sd = (sum((x - mean) ** 2 for x in d) / len(d)) ** 0.5
        return (len(d), mean, sd / len(d) ** 0.5, sum(1 for x in d if x > 0.5),
                sum(1 for x in d if x < -0.5), sum(1 for x in d if abs(x) <= 0.5))
    for label, args in (("$1 vs take-it", (0.0, 300, 1.0, 600)),
                        ("$0.50 vs $1", (1.0, 600, 0.5, 600)),
                        ("$2 vs $1", (1.0, 600, 2.0, 600)),
                        ("$2.50 vs $1", (1.0, 600, 2.5, 600)),
                        ("$5 vs $1", (1.0, 600, 5.0, 600)),
                        ("$1 15-min vs 10-min", (1.0, 600, 1.0, 900))):
        p = _paired(*args)
        if p:
            lines.append("| %s | %d | %+.1f | %.1f | %d | %d | %d |" % ((label,) + p))
    lines.append("")
    lines.append("## B. Under the pullback's own stock rule (stop $1.00 / target $2.50)")
    lines.append("")
    lines.append("Stock $/share; else 15:55 flatten. 'per alert' counts the skipped ones as 0.")
    lines.append("")
    lines.append("| grid | wait | entered | of %d | avg better entry | wins | losses | flat | "
                 "total $/sh | per alert | avg MFE | avg MAE |" % len(usable))
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    best = {}
    for grid in GRIDS:
        for window in (WINDOWS if grid else (WINDOWS[0],)):
            res = [replay(a, bars[(a["symbol"], a["date"])], grid, window) for a in usable]
            ent = [r for r in res if r and r["entered"]]
            if not ent:
                continue
            tot = sum(r["pnl"] for r in ent)
            wins = sum(1 for r in ent if r["exit_why"] == "target")
            loss = sum(1 for r in ent if r["exit_why"] == "stop")
            flat = len(ent) - wins - loss
            lines.append("| %s | %s | %d | %d%% | $%.2f | %d | %d | %d | %+.2f | %+.3f | %.2f | %.2f |"
                         % ("take it" if not grid else "$%g" % grid,
                            "—" if not grid else "%d min" % (window // 60),
                            len(ent), round(100.0 * len(ent) / len(usable)),
                            sum(r["improve"] for r in ent) / len(ent),
                            wins, loss, flat, tot, tot / len(usable),
                            sum(r["mfe"] for r in ent) / len(ent),
                            sum(r["mae"] for r in ent) / len(ent)))
            best[(grid, window)] = (tot, tot / len(usable), len(ent))
    lines.append("")
    # per symbol at the 10-min window
    lines.append("## Per symbol, 10-minute wait (total $/share, entered/alerts)")
    lines.append("")
    lines.append("| symbol | alerts | " + " | ".join("take it" if not g else "$%g" % g for g in GRIDS) + " |")
    lines.append("|---|---|" + "---|" * len(GRIDS))
    for sym in BETA:
        al = [a for a in usable if a["symbol"] == sym]
        if not al:
            continue
        cells = []
        for grid in GRIDS:
            res = [replay(a, bars[(a["symbol"], a["date"])], grid, 600) for a in al]
            ent = [r for r in res if r and r["entered"]]
            cells.append("%+.2f (%d/%d)" % (sum(r["pnl"] for r in ent), len(ent), len(al)))
        lines.append("| %s | %d | %s |" % (sym, len(al), " | ".join(cells)))
    lines.append("")
    # what the deeper grids gave up
    lines.append("## What a deeper level skips (10-minute wait)")
    lines.append("")
    lines.append("Alerts that fill at $1 but NOT at the deeper grid — and what the $1 entry made on them.")
    lines.append("")
    lines.append("| grid | skipped vs $1 | those trades at $1 made | wins | losses |")
    lines.append("|---|---|---|---|---|")
    for grid in (2.0, 2.5, 5.0):
        skipped, made, w, l = 0, 0.0, 0, 0
        for a in usable:
            b = bars[(a["symbol"], a["date"])]
            r1 = replay(a, b, 1.0, 600)
            rg = replay(a, b, grid, 600)
            if r1 and r1["entered"] and rg and not rg["entered"]:
                skipped += 1
                made += r1["pnl"]
                w += r1["exit_why"] == "target"
                l += r1["exit_why"] == "stop"
        lines.append("| $%g | %d | %+.2f | %d | %d |" % (grid, skipped, made, w, l))
    lines.append("")
    # level reactions
    lines.append("## Do these names actually bounce off round levels? (alert-free)")
    lines.append("")
    lines.append("Every first touch of a line on every symbol-day we hold. "
                 "Bounce = how far price moved back off the line within 5 min; "
                 "fail = how far it pushed through. Control = x.25/x.75 lines only (never round).")
    lines.append("")
    lines.append("| grid | touches | avg bounce | avg push-through | held (bounce ≥ 2× push) |")
    lines.append("|---|---|---|---|---|")
    for grid in (5.0, 2.5, 2.0, 1.0, 0.5, CONTROL):
        rx = []
        for k in have:
            rx.extend(level_reactions(bars[k], grid))
        if not rx:
            continue
        held = sum(1 for b, f in rx if b >= 2 * f and b >= 0.25)
        lines.append("| %s | %d | $%.2f | $%.2f | %d%% |"
                     % ("$%g" % grid if grid != CONTROL else "25¢ control", len(rx),
                        sum(b for b, _ in rx) / len(rx), sum(f for _, f in rx) / len(rx),
                        round(100.0 * held / len(rx))))
    lines.append("")
    per_sym = defaultdict(list)
    for (sym, date) in have:
        for grid in (5.0, 2.5, 1.0, CONTROL):
            per_sym[(sym, grid)].extend(level_reactions(bars[(sym, date)], grid))
    lines.append("| symbol | $5 held | $2.50 held | $1 held | 25¢ control |")
    lines.append("|---|---|---|---|---|")
    for sym in BETA:
        cells = []
        for grid in (5.0, 2.5, 1.0, CONTROL):
            rx = per_sym.get((sym, grid), [])
            if not rx:
                cells.append("—")
                continue
            held = sum(1 for b, f in rx if b >= 2 * f and b >= 0.25)
            cells.append("%d%% (%d)" % (round(100.0 * held / len(rx)), len(rx)))
        if any(c != "—" for c in cells):
            lines.append("| %s | %s |" % (sym, " | ".join(cells)))
    lines.append("")
    top = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:3]
    lines.append("Best by total: " + "; ".join(
        "%s/%s %+.2f (%d entries)" % ("take it" if not g else "$%g" % g, "%dm" % (w // 60), t, n)
        for (g, w), (t, _pa, n) in top))
    text = "\n".join(lines) + "\n"
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print()
    print(text)


if __name__ == "__main__":
    main()
