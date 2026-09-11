#!/usr/bin/env python3
"""
postmortem.py — EVERY exited trade gets a verdict: did it go well, what went
wrong, what we can fix.  (G, 9/9: "analyze every single trade after exiting …
be attentive to these.")

For one closed trade it rebuilds the whole story from the records we already
keep and answers, in order:
  1. THE CALL      who, room, what they said, their price vs our fill, how long
                   the round-number wait took.
  2. THE RIDE      the bid path while held: worst point (MAE), best point (MFE),
                   and what the exit was.
  3. AFTER WE LEFT the bid at +30s / +1m / +5m / +10m after the exit, the low
                   and the high in that window.  (quote_bus now keeps taping
                   a contract 10 min after its exit so this half exists.)
  4. THE STOP      which born-stop % would have survived the whole ride and
                   what each would have been worth at the after-exit high.
  5. THE MACHINE   every fault line in that window: POSTCHECK PROBLEM, 429 /
                   TOO_MANY_REQUESTS, 417, re-sent sells, "already filled",
                   EXIT-RETRY, accepted-never-filled.
  6. VERDICT       one line — NOISE CLIP / GOOD STOP / LEFT MONEY / GOOD EXIT /
                   BAD ENTRY / MACHINE FAULT — and the lesson.

Writes postmortems/<date>_<OCC>.md (the readable one) and appends one row to
master_postmortems.csv (the central file — one row per exited trade). Idempotent
per (date, occ): re-running replaces that trade's row and file.

RUN:   python3 postmortem.py                 # every closed trade today
       python3 postmortem.py --last          # the most recent exit
       python3 postmortem.py --date 2026-09-09
       python3 postmortem.py --occ META260909C00655000
Read-only over every source. Never trades. Never raises out of run().
"""
import csv
import glob
import os
import re
import sys
import threading
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger        # noqa: E402
import tape as _tape  # noqa: E402

TRADES_LOG = os.path.join(HERE, "trades.log")
OUT_DIR = os.path.join(HERE, "postmortems")
OUT_CSV = os.path.join(HERE, "master_postmortems.csv")
# F11 (9/11 audit): the CSV rewrite below is read-modify-write (read every
# row, drop this trade's old one, add the new one, write the whole file
# back) with a shared ".tmp" name and no lock — two postmortems finishing
# close together could each read the same starting file, and the second
# writer's version would silently not contain the first one's row. One
# lock around the whole read+write closes both the lost-update and the
# shared-temp-file race at once.
_CSV_LOCK = threading.Lock()
STOP_GRID = (5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0)
AFTER_MARKS = ((30, "+30s"), (60, "+1m"), (300, "+5m"), (600, "+10m"))
FAULT_PATS = (
    ("POSTCHECK PROBLEM", r"POSTCHECK .*PROBLEM"),
    ("rate-limit 429", r"TOO_MANY_REQUESTS|\b429\b"),
    ("417 rejection", r"\b417\b|OPENAPI_ORDER"),
    ("redundant sell (race)", r"re-sent the sell|order was still on this contract"),
    ("stop filled before pull", r"already filled.*before the pull|filled before it could be pulled"),
    ("exit accepted, never filled", r"EXIT-RETRY|accepted but never"),
    ("stop refused by broker", r"refused|REFUSED .*stop|STOP_PRICE"),
)
COLUMNS = ["date", "occ", "symbol", "who", "room", "fill", "exit", "pl", "pl_pct",
           "held_s", "their_price", "fill_vs_theirs_pct", "rn_wait_s",
           "mae_pct", "mfe_pct", "after_30s", "after_1m", "after_5m", "after_10m",
           "after_low", "after_high", "survive_pct", "exit_trigger", "arm_after_s",
           "faults", "verdict", "lesson", "file"]


def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _hms(t):
    try:
        return datetime.fromtimestamp(float(t)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "?"


# ---------- the raw materials ----------
def _tape_rows(occ, t0, t1):
    """(ts, bid, ask) for occ between t0 and t1 from every tape we have."""
    out = []
    try:
        for r in _tape.rows(occ=occ, since=t0, until=t1):
            if r.bid is not None and r.bid > 0:
                out.append((float(r.ts), float(r.bid), float(r.ask or 0)))
    except Exception:                                   # noqa: BLE001
        pass
    out.sort()
    return out


def _log_lines(symbol, t0, t1):
    """trades.log lines mentioning the symbol inside [t0, t1]."""
    if not os.path.exists(TRADES_LOG):
        return []
    sym = re.compile(r"\b%s\b" % re.escape(symbol.upper()))
    out = []
    with open(TRADES_LOG, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            iso = ln[:25]
            try:
                ts = datetime.fromisoformat(iso).timestamp()
            except ValueError:
                continue
            if ts < t0 or ts > t1:
                continue
            if sym.search(ln):
                out.append((ts, ln.rstrip("\n")))
    return out


def _at(rows, t):
    """Bid at or just after time t (None if the tape ends first)."""
    for ts, b, _a in rows:
        if ts >= t:
            return b
    return None


# ---------- one trade ----------
def analyze(r):
    """r = a ledger row (day-JSON shape). Returns a dict for the CSV + the md."""
    occ = r.get("occ") or ""
    sym = (r.get("symbol") or "").upper()
    fill = _f(r.get("fill")) or _f(r.get("avg"))
    opened = _f(r.get("opened"))
    closed = _f(r.get("closed"))
    exits = r.get("exits") or []
    exit_px = _f(exits[-1].get("price")) if exits else None
    if closed is None and exits:
        closed = _f(exits[-1].get("t"))
    pl = _f(r.get("pl"))
    pl_pct = _f(r.get("pl_pct"))
    if pl_pct is None and pl is not None and fill and r.get("qty"):
        try:
            pl_pct = round(pl / (fill * float(r["qty"]) * 100.0) * 100.0, 1)
        except (TypeError, ZeroDivisionError):
            pl_pct = None
    their = _f(r.get("their_avg"))
    who = r.get("who") or "?"
    room = r.get("room") or "?"

    res = {"date": r.get("date"), "occ": occ, "symbol": sym, "who": who, "room": room,
           "_opened": opened,
           "fill": fill, "exit": exit_px, "pl": pl, "pl_pct": pl_pct,
           "held_s": round(closed - opened) if (opened and closed) else None,
           "their_price": their,
           "fill_vs_theirs_pct": (round((fill - their) / their * 100.0, 1)
                                  if (fill and their) else None)}

    # timeline from the log: alert -> touch -> fill -> exit
    t0 = (opened or closed or 0) - 180
    t1 = (closed or opened or 0) + 660
    lines = _log_lines(sym, t0, t1) if sym else []
    rn_call = next((ts for ts, ln in lines if "PULLBACK" in ln and "CALL:" in ln), None)
    res["rn_wait_s"] = round(opened - rn_call) if (rn_call and opened) else None

    # WHICH stop pulled the trigger? (9/9, SPY 764P: the ratchet armed to
    # breakeven 9 s after the fill and a one-tick flicker took it out — a
    # different fault from META's born stop, and the decision depends on
    # telling them apart.)
    trig, arm_after = "", None
    arm_ts = next((ts for ts, ln in lines if "ratchet moved your stop" in ln), None)
    if arm_ts and opened:
        arm_after = round(arm_ts - opened)
    # 9/10 fix: "resting stop had already filled at X before the pull landed"
    # (broker's own stop beat the bridge's poll — 6+ of these a day) was
    # falling through this whole ladder to "hand close" or "other/unknown",
    # because only the "at or under your Y stop" phrasing was recognized.
    # Both mean the same thing (the ratchet's resting stop did its job); the
    # filled price is used as the level proxy for the born/breakeven/rung
    # split when the threshold itself wasn't logged.
    stop_ln = next(((ts, ln) for ts, ln in lines
                    if re.search(r"STOPPED\s.*at or under your ([\d.]+) stop", ln)), None)
    stop_lvl_pat = r"at or under your ([\d.]+) stop"
    if not stop_ln:
        stop_ln = next(((ts, ln) for ts, ln in lines
                        if re.search(r"STOPPED\s.*resting stop had already filled at ([\d.]+)", ln)), None)
        stop_lvl_pat = r"resting stop had already filled at ([\d.]+)"
    stk_ln = next((ts for ts, ln in lines
                   if "PULLBACK" in ln and "stock hit the" in ln and "stop" in ln), None)
    # "ADOPT"/"ADOPTED" mark picking up a position at OPEN, not closing one —
    # matching bare "ADOPT" here grabbed any same-ticker adoption line inside
    # the lookback window (e.g. a same-day SPY ADOPT notice for an unrelated
    # hold) and mislabeled a clean ratchet-stop exit as "hand close" (9/10,
    # SPY 757P). Only match actual close phrasing.
    hand_ln = next((ts for ts, ln in lines
                    if re.search(r"you closed it yourself|didn't send this sell", ln)), None)
    if stop_ln and fill:
        lvl = float(re.search(stop_lvl_pat, stop_ln[1]).group(1))
        if abs(lvl - fill) <= 0.011:
            trig = "breakeven stop (ratchet arm)"
        elif lvl < fill:
            trig = "born stop"
        else:
            trig = "ratchet rung (+%.0f%%)" % ((lvl - fill) / fill * 100.0)
    elif stk_ln:
        trig = "stock stop (pullback)"
    elif hand_ln:
        trig = "hand close"
    elif closed:
        trig = "other/unknown"
    res["exit_trigger"], res["arm_after_s"] = trig, arm_after

    # the ride
    ride = _tape_rows(occ, (opened or 0) - 5, closed or (opened or 0) + 1) if occ else []
    mae = mfe = None
    if ride and fill:
        lo = min(b for _t, b, _a in ride)
        hi = max(b for _t, b, _a in ride)
        mae = round((lo - fill) / fill * 100.0, 1)
        mfe = round((hi - fill) / fill * 100.0, 1)
    res["mae_pct"], res["mfe_pct"] = mae, mfe

    # after we left
    after = _tape_rows(occ, closed, closed + 605) if (occ and closed) else []
    for secs, name in AFTER_MARKS:
        b = _at(after, closed + secs) if closed else None
        res["after_" + name.strip("+")] = b
    res["after_low"] = min((b for _t, b, _a in after), default=None)
    res["after_high"] = max((b for _t, b, _a in after), default=None)

    # the stop: what born-stop % survives the WHOLE window (ride + after)?
    whole = ride + after
    survive = None
    if whole and fill:
        low_all = min(b for _t, b, _a in whole)
        for s in STOP_GRID:
            if low_all > fill * (1 - s / 100.0):
                survive = s
                break
    res["survive_pct"] = survive

    # machine faults
    faults = []
    for label, pat in FAULT_PATS:
        n = sum(1 for _ts, ln in lines if re.search(pat, ln))
        if n:
            faults.append("%s x%d" % (label, n))
    res["faults"] = "; ".join(faults)

    # verdict
    v, lesson = _verdict(res, fill, exit_px, pl, after)
    res["verdict"], res["lesson"] = v, lesson
    res["_lines"] = lines
    res["_ride"] = ride
    res["_after"] = after
    return res


def _verdict(res, fill, exit_px, pl, after):
    ah, al = res.get("after_high"), res.get("after_low")
    mfe, survive = res.get("mfe_pct"), res.get("survive_pct")
    faults = res.get("faults") or ""
    if pl is None or fill is None:
        return "NO VERDICT", "no priced exit in the ledger — check the row"
    if pl < 0 or (pl == 0 and (res.get("exit_trigger") or "").startswith("breakeven")):
        if ah is not None and ah >= fill and (res.get("exit_trigger") or "").startswith("breakeven"):
            return "ARM CLIP", ("the ratchet armed to breakeven %ss after the fill on a real +5%% "
                                "move that reversed; the bid then reached %.2f (%+.0f%%). Counted, "
                                "not acted on: on 90 contract-days (9/9) the INSTANT arm beat every "
                                "alternative — a 30 s dwell lost $170 vs today's rule, 5 min lost "
                                "$640, and a spread-aware arm changed 3 old trades by $25. This is "
                                "the known cost of a rule that wins on the sample. Ratchet values "
                                "stay G's call."
                                % (res.get("arm_after_s") if res.get("arm_after_s") is not None else "?",
                                   ah, (ah - fill) / fill * 100.0))
        if ah is not None and ah >= fill:
            back = next((n for s, n in AFTER_MARKS
                         if (res.get("after_" + n.strip("+")) or 0) >= fill), "+10m")
            les = ("stopped, then the bid was back above the entry by %s. " % back)
            les += ("Only a %g%%+ born stop survives this one" % survive if survive
                    else "no stop in the 5-25%% grid survives this one")
            les += ("; the 80-fill sweep still prefers 7.5 on average — count "
                    "these clips; if they pile up on 0DTE ATM, that is the "
                    "case for a wider 0DTE stop.")
            return "NOISE CLIP", les
        if al is not None and exit_px and al < exit_px:
            return "GOOD STOP", ("it kept falling to %.2f after we left (%.0f%% "
                                 "under the exit) — the stop saved money."
                                 % (al, (al - exit_px) / exit_px * 100.0))
        return "LOSS, FLAT AFTER", "no recovery and no further drop on tape in 10 min — a dead call."
    # winner
    if ah is not None and exit_px and ah > exit_px * 1.2:
        return "LEFT MONEY", ("exited at %.2f, ran to %.2f within 10 min (%.0f%% more). "
                              "The ratchet's rung is the lever if this repeats."
                              % (exit_px, ah, (ah - exit_px) / exit_px * 100.0))
    if mfe is not None and res.get("pl_pct") is not None and mfe - res["pl_pct"] > 15:
        return "GAVE BACK", ("peaked +%.0f%% but banked +%.0f%% — the ratchet let %.0f "
                             "points slip." % (mfe, res["pl_pct"], mfe - res["pl_pct"]))
    return "GOOD EXIT", "took what was there; nothing to change."


# ---------- output ----------
def _md(res):
    L = []
    L.append("# %s %s — %s (%s)" % (res["date"], res["symbol"], res["verdict"], res["occ"]))
    L.append("")
    L.append("**Caller:** %s · **Room:** %s" % (res["who"], res["room"]))
    if res.get("their_price") and res.get("fill"):
        L.append("**Their price:** %.2f · **Our fill:** %.2f (%+.1f%%)"
                 % (res["their_price"], res["fill"], res["fill_vs_theirs_pct"]))
    elif res.get("fill"):
        L.append("**Our fill:** %.2f" % res["fill"])
    if res.get("rn_wait_s") is not None:
        L.append("**Round-number wait:** %ds from the call to the touch" % res["rn_wait_s"])
    L.append("**Exit:** %s · **P&L:** %s (%s) · **Held:** %ss"
             % (("%.2f" % res["exit"]) if res.get("exit") else "?",
                ("%+.0f$" % res["pl"]) if res.get("pl") is not None else "?",
                ("%+.1f%%" % res["pl_pct"]) if res.get("pl_pct") is not None else "?",
                res.get("held_s") if res.get("held_s") is not None else "?"))
    L.append("")
    L.append("## The ride (bid)")
    L.append("- worst point (MAE): %s · best point (MFE): %s"
             % (("%+.1f%%" % res["mae_pct"]) if res.get("mae_pct") is not None else "no tape",
                ("%+.1f%%" % res["mfe_pct"]) if res.get("mfe_pct") is not None else "no tape"))
    L.append("")
    L.append("## After we left (bid)")
    parts = []
    for _s, n in AFTER_MARKS:
        b = res.get("after_" + n.strip("+"))
        parts.append("%s %s" % (n, ("%.2f" % b) if b is not None else "—"))
    L.append("- " + " · ".join(parts))
    if res.get("after_low") is not None:
        L.append("- low %.2f · high %.2f in the 10 min after the exit"
                 % (res["after_low"], res["after_high"]))
    else:
        L.append("- no after-exit tape (the linger starts with the next bridge restart)")
    L.append("")
    L.append("## The stop")
    if res.get("exit_trigger"):
        L.append("- exit trigger: **%s**%s" % (res["exit_trigger"],
                 (" · armed %ss after the fill" % res["arm_after_s"]) if res.get("arm_after_s") is not None else ""))
    if res.get("survive_pct") is not None:
        L.append("- widest that would have survived the whole window: **%g%%** born stop"
                 % res["survive_pct"])
    elif res.get("fill"):
        L.append("- nothing in the 5–25%% grid survives this ride")
    if res.get("fill") and res.get("after_high"):
        L.append("- at the after-exit high (%.2f) each stop is worth: %s" % (
            res["after_high"],
            ", ".join("%g%%→%+.0f$" % (s, (res["after_high"] - res["fill"]) * 100.0)
                      if (res.get("survive_pct") is not None and s >= res["survive_pct"])
                      else "%g%%→stopped" % s for s in STOP_GRID)))
    L.append("")
    L.append("## The machine")
    L.append("- " + (res["faults"] if res.get("faults") else "clean — no fault lines in the window"))
    L.append("")
    L.append("## Verdict: %s" % res["verdict"])
    L.append(res["lesson"])
    L.append("")
    L.append("## Timeline (trades.log)")
    for ts, ln in (res.get("_lines") or [])[:40]:
        L.append("- `%s` %s" % (_hms(ts), ln[26:].strip()[:150]))
    return "\n".join(L) + "\n"


def _write(res):
    os.makedirs(OUT_DIR, exist_ok=True)
    base = "%s_%s" % (res["date"], res["occ"] or res["symbol"])
    # SAME CONTRACT, SAME DAY, TWO ROUND TRIPS (9/10 — SPY 758C traded twice
    # in one morning, ~90s apart): the filename is the trade's RANK among
    # that day's closed trades on the OCC, ordered by entry time — first
    # trade = base.md, second = base-2.md — so it is stable across re-runs.
    # (The first fix keyed "is this a re-run" on fill+exit, which named BOTH
    # trades base.md once both rows existed in the csv, and the 16:39 --date
    # run overwrote trade 1 with trade 2 again.) The csv row is replaced by
    # (date, occ, fill, exit), so a re-run of the same trade never piles up.
    idx = _trade_index(res)
    fn = "%s.md" % base if idx == 0 else "%s-%d.md" % (base, idx + 1)
    path = os.path.join(OUT_DIR, fn)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_md(res))
    res["file"] = "postmortems/" + fn
    # central csv: replace THIS trade's row (date, occ, fill, exit) if
    # present; a different trade on the same (date, occ) is kept, not lost.
    # F11 (9/11 audit): read, modify and write all happen under one lock
    # now — two postmortems finishing close together used to be able to
    # both read the file before either wrote it back, so the loser's write
    # silently erased the winner's row.
    with _CSV_LOCK:
        rows = [x for x in _read_postmortems_csv()
                if not (x.get("date") == res["date"] and x.get("occ") == res["occ"]
                        and _f(x.get("fill")) == res.get("fill")
                        and _f(x.get("exit")) == res.get("exit"))]
        rows.append({c: ("" if res.get(c) is None else res.get(c)) for c in COLUMNS})
        rows.sort(key=lambda x: (x.get("date") or "", x.get("occ") or ""))
        tmp = "%s.tmp.%d" % (OUT_CSV, threading.get_ident())
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            for x in rows:
                w.writerow({c: x.get(c, "") for c in COLUMNS})
        os.replace(tmp, OUT_CSV)
    return path


def _trade_index(res):
    """0 for the day's first closed trade on this OCC, 1 for the second ..."""
    try:
        same = [r for _d, r in ledger.rows(real_only=True, since=res["date"], until=res["date"])
                if (r.get("occ") or "") == (res.get("occ") or "")
                and r.get("state") in ("closed", "stopped")
                and not r.get("manual")
                and str(r.get("who") or "").strip().lower() != "gian"]   # graded trades only
        same.sort(key=lambda r: _f(r.get("opened")) or 0)
        for i, r in enumerate(same):
            if _f(r.get("opened")) == res.get("_opened"):
                return i
    except Exception:                                   # noqa: BLE001
        pass
    return 0


def _read_postmortems_csv():
    if not os.path.exists(OUT_CSV):
        return []
    with open(OUT_CSV, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------- entry points ----------
def run(date=None, occ=None, last=False, quiet=False):
    """Analyze closed trades. Never raises."""
    done = []
    try:
        cands = [r for _d, r in ledger.rows(real_only=True, since=date, until=date)
                 if r.get("state") in ("closed", "stopped") and r.get("pl") is not None
                 and not r.get("manual")
                 and str(r.get("who") or "").strip().lower() != "gian"]   # his hand trades: not the bot's to grade
        if occ:
            cands = [r for r in cands if (r.get("occ") or "") == occ]
        if last and cands:
            cands = [max(cands, key=lambda r: _f(r.get("closed")) or _f(r.get("opened")) or 0)]
        for r in cands:
            try:
                res = analyze(r)
                path = _write(res)
                done.append(res)
                if not quiet:
                    print("%s %-6s %-11s %+6.0f$  %s  ->  %s" % (
                        res["date"], res["symbol"], res["verdict"],
                        res["pl"] or 0, (res["faults"] or "clean")[:40], res["file"]))
            except Exception as e:                      # noqa: BLE001
                if not quiet:
                    print("postmortem failed for", r.get("occ"), "->", str(e)[:80])
    except Exception as e:                              # noqa: BLE001
        if not quiet:
            print("postmortem run failed:", str(e)[:100])
    return done


def run_for_key_later(symbol, delay_s=630):
    """Bridge hook: a thread that waits for the after-exit tape, then writes
    the post-mortem for every trade of that symbol closed today. Never raises."""
    import threading

    def _go():
        try:
            import time as _t
            _t.sleep(delay_s)
            today = datetime.now().strftime("%Y-%m-%d")
            for r in [x for _d, x in ledger.rows(real_only=True, since=today, until=today)
                      if (x.get("symbol") or "").upper() == symbol.upper()
                      and x.get("state") in ("closed", "stopped")
                      and x.get("pl") is not None and not x.get("manual")
                      and str(x.get("who") or "").strip().lower() != "gian"]:
                try:
                    _write(analyze(r))
                except Exception:                       # noqa: BLE001
                    pass
        except Exception:                               # noqa: BLE001
            pass
    try:
        threading.Thread(target=_go, daemon=True, name="postmortem:" + symbol).start()
    except Exception:                                   # noqa: BLE001
        pass


if __name__ == "__main__":
    a = sys.argv[1:]
    date = None
    occ = None
    last = "--last" in a
    if "--date" in a:
        date = a[a.index("--date") + 1]
    if "--occ" in a:
        occ = a[a.index("--occ") + 1]
    if date is None and not occ:
        date = datetime.now().strftime("%Y-%m-%d")
    out = run(date=date, occ=occ, last=last)
    if not out:
        print("no closed, priced, non-manual trades to analyze for", date or occ)
