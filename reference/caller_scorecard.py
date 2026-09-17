#!/usr/bin/env python3
"""caller_scorecard.py — per caller: does he TALK, and does following him pay?

G, 9/17: "yea do that". Two facts came out of follow_the_caller.py: 41% of
alerts never get another word (the losers nobody announces), and on the ones
that do, selling at the caller's own first trim beat our ladder by a mile. Both
are properties of the CALLER, so this ranks callers on them, over EVERY alert
on file — master_alerts.csv + alert_meta.csv back to August, priced off every
quote tape (tape.py: Databento OPRA, Webull, tastytrade, alert tape) — beside
what the bot REALLY made on him (master_ledger.csv, broker truth, whatever
ladder was live that day). Rebuilt by the daily audit:

  alerts      taped option entries, instant buy at the ask, 1 contract
  silent      never got a trim / exit / stop call afterwards
  gap         median ask-vs-his-posted-price when the alert reached us
  FOLLOW HIM  exit at the bid on his FIRST follow-up call; a -20% disaster
              stop; otherwise flat at the last quote. Applied to ALL his
              alerts, silent ones included — that is the honest version.
  LADDER      the live ladder on the same alerts (ratchet_replay_tape).
  REAL        the bot's own closed trades on him in master_ledger.csv — real
              fills, real exits, not a replay. `peak` = the median best gain
              the position showed while we held it (hi_pct), where recorded.
A quote path bought for a refused alert ends 45 minutes after the alert; a
trade still open there is marked at that last bid.

UNDER 10 ALERTS IS NOT A RANKING, it is a list; those rows are marked.
MEASUREMENT ONLY — nothing here can bench, follow or trade anything.
Output: daily-reports/CALLER-SCORECARD.md (ONE file, overwritten).
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import follow_the_caller as ftc                             # noqa: E402
import ladder_grid_test as lg                               # noqa: E402
import ratchet_replay_tape as rr                            # noqa: E402
import win_rate_dig as dig                                  # noqa: E402

OUT = os.path.join(ROOT, "daily-reports", "CALLER-SCORECARD.md")
DISASTER_STOP_PCT = 20.0
MIN_N = 10


def days():
    found = set()
    for name, test in (("alert_meta.csv", lambda r: r.get("stage") == "alert"),
                       ("master_alerts.csv", lambda r: True)):
        with open(os.path.join(ROOT, name), encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if test(r) and len(r.get("date") or "") == 10:
                    found.add(r["date"])
    return sorted(found)


def logged_days():
    """Days the room chat was actually RECORDED (a day block in DS Logs). On any
    other day "he never said another word" only means we were not listening, so
    those alerts are left out of the silent / follow / ladder columns."""
    import glob
    import re
    months = {m: i + 1 for i, m in enumerate(
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
    found = set()
    for path in glob.glob(os.path.join(ROOT, "DS Logs", "signal-room-chat week-of-*.txt")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for m in re.finditer(r"^===== \w{3} (\w{3}) (\d{1,2}) (\d{4}) =====", fh.read(), flags=re.M):
                found.add("%s-%02d-%02d" % (m.group(3), months[m.group(1)], int(m.group(2))))
    return found


OWNER = ("gian",)          # G's own typed alerts — his, never a caller's
ORPHAN = "ADOPTED — no bot order before it (G's own position, or a lost link)"
_CALL_LINE = None


def bot_order_lines():
    """[(date, seconds, SYMBOL, caller)] from the bridge's own narration —
    "WORKING  META — Unraveller's call, …". The ledger lost the owner on 32
    August trades (key "?|SYM", adopted back from the account after the fill
    race of 8/10-8/20); the order line written seconds earlier still names him."""
    global _CALL_LINE
    if _CALL_LINE is None:
        import re
        pat = re.compile(r"^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d):(\d\d)\S*\t"
                         r"(?:WORKING|PULLBACK|FILLED|ORDER IN)\s+(\w+) — (.+?)'s call")
        _CALL_LINE = []
        try:
            with open(os.path.join(ROOT, "trades.log"), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = pat.match(line)
                    if m:
                        _CALL_LINE.append((m.group(1), int(m.group(2)) * 3600 + int(m.group(3)) * 60
                                           + int(m.group(4)), m.group(5).upper(), m.group(6)))
        except OSError:
            pass
    return _CALL_LINE


def owner_of(row):
    """The ledger's caller, else the caller on the bot's own order line for that
    symbol in the 15 minutes before the position opened, else ORPHAN."""
    caller, room = (row.get("caller") or "").strip(), (row.get("room") or "").strip()
    if caller not in ("", "?") or room not in ("", "?"):
        return who({"caller": caller, "room": room})
    try:
        h, m, sec = (row.get("opened") or "").split(":")
        opened = int(h) * 3600 + int(m) * 60 + int(sec)
    except ValueError:
        return ORPHAN
    near = [c for c in bot_order_lines() if c[0] == row.get("date")
            and c[2] == (row.get("symbol") or "").upper() and 0 <= opened - c[1] <= 900]
    return who({"caller": max(near, key=lambda c: c[1])[3]}) if near else ORPHAN


def real_trades():
    """{caller: [pl,...]}, {caller: [hi_pct,...]} — the bot's own closed option
    trades. Hand trades are G's, never a caller's."""
    pls, peaks = defaultdict(list), defaultdict(list)
    with open(os.path.join(ROOT, "master_ledger.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("kind") != "option" or str(r.get("manual") or "").lower() in ("true", "1"):
                continue
            if r.get("account") != "live":
                continue
            pl = rr._f(r.get("pl"))
            if pl is None:
                continue
            name = owner_of(r)
            if name.lower() in OWNER:
                name = "G's OWN typed alerts (not a caller)"
            pls[name].append(pl)
            hi = rr._f(r.get("hi_pct"))
            if hi is not None:
                peaks[name].append(hi)
    return pls, peaks


def first_calls():
    first = {}
    for (day, _clock, contract), events in ftc.load().items():
        t1 = min(ftc.ts_of(day, e["event_time"]) for e in events)
        first[(day, contract)] = min(first.get((day, contract), 1e18), t1)
    return first


def follow(row, t_call):
    entry = row["ask"]
    walk = [q for q in row["path"] if row["t0"] <= q[0] <= row["flat"]]
    for ts, bid, _ask in walk:
        if bid <= entry * (1 - DISASTER_STOP_PCT / 100.0):
            return (bid - entry) * 100.0
        if t_call and ts >= t_call:
            return (bid - entry) * 100.0
    return (walk[-1][1] - entry) * 100.0 if walk else 0.0


ALIASES = {"abtrades alert bot": "AbTrades", "elite": "EliteOptions | Brando",
           "vero-alerts": "Vero"}


def who(alert):
    """One person, one row: "Brett (Admin)", "@Brett" and "Brett" are Brett."""
    import re
    name = (alert.get("caller") or "").strip()
    if not name or name == "?":
        return "(room) " + (alert.get("room") or "?")[:28]
    name = re.sub(r"\s*\((?:admin|mod)\)\s*", "", name, flags=re.I).lstrip("@").strip()
    return ALIASES.get(name.lower(), name)


def build():
    all_days = days()
    rr.DAYS = tuple(all_days)
    first = first_calls()
    alerts, seen, heard = [], set(), logged_days()
    for a in rr.load_alerts():              # alert_meta first, master_alerts folded in
        if a["day"] not in heard:
            continue
        key = (a["day"], a["occ"], int(a["ts"] // 300))
        if key in seen:
            continue
        seen.add(key)
        alerts.append(a)
    rows = lg.rows_for(alerts)
    by = defaultdict(list)
    for r in rows:
        a = r["a"]
        t_call = first.get((a["day"], a["occ"]))
        ladder = dig.sim(r)
        gap = (r["ask"] / a["their_price"] - 1) * 100.0 if a.get("their_price") else None
        if gap is not None and not (-60 < gap < 150):
            gap = None
        name = who(a)
        if name.startswith("(room) ?"):
            # the alert row has no caller or room; the bridge's own order line
            # for that symbol within two minutes of it usually does
            clock = a["time"][:8].split(":")
            at = int(clock[0]) * 3600 + int(clock[1]) * 60 + int((clock + ["0"])[2] or 0)
            near = [c for c in bot_order_lines() if c[0] == a["day"] and c[2] == a["root"]
                    and abs(c[1] - at) <= 120]
            if near:
                name = who({"caller": min(near, key=lambda c: abs(c[1] - at))[3]})
            else:
                name = "UNATTRIBUTED alert (no caller, no room, no order line)"
        by[name].append({"silent": t_call is None, "follow": follow(r, t_call),
                           "ladder": ladder["pl"] if ladder else 0.0, "gap": gap, "day": a["day"]})
    return all_days, rows, by, len(alerts)


def render(all_days, rows, by, n_alerts):
    pls, peaks = real_trades()
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    total = [x for v in by.values() for x in v]
    used = sorted({x["day"] for v in by.values() for x in v})
    lines = ["# CALLER SCORECARD — %s .. %s (%d days with the room chat recorded · %d option alerts · %d with quotes at the alert)"
             % (used[0], used[-1], len(used), n_alerts, len(rows)),
             "",
             "Instant buy at the ask, 1 contract, our own recorded quotes. **FOLLOW HIM** = out at the bid on his first "
             "follow-up call, a -%d%% disaster stop, else flat at the last quote — on ALL his alerts, silent ones included. "
             "**LADDER** = the live ladder (%s) on the same alerts. Under %d alerts is a list, not a ranking. Measurement only."
             % (DISASTER_STOP_PCT, "/".join("%g" % x for x in (rr.BORN_PCT,) + tuple(rr.TIERS_LIVE[0][1][i] for i in (0, 2))), MIN_N),
             "",
             "ALL CALLERS: %d alerts · silent %d%% · follow him %+.0f · ladder %+.0f"
             % (len(total), round(100 * sum(1 for x in total if x["silent"]) / max(1, len(total))),
                sum(x["follow"] for x in total), sum(x["ladder"] for x in total)),
             "",
             "| caller | alerts | days | silent | entry gap | FOLLOW HIM | per alert | LADDER | per alert | better | REAL trades | REAL $ | real win | peak |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|"]
    ranked = sorted(by.items(), key=lambda kv: (len(kv[1]) < MIN_N, -sum(x["follow"] for x in kv[1]) / len(kv[1])))
    for name, part in ranked:
        n = len(part)
        gaps = [x["gap"] for x in part if x["gap"] is not None]
        f, l = sum(x["follow"] for x in part), sum(x["ladder"] for x in part)
        real = pls.get(name) or []
        pk = peaks.get(name) or []
        lines.append("| %s%s | %d | %d | %d%% | %s | %+.0f | %+.1f | %+.0f | %+.1f | %s | %s | %s | %s | %s |"
                     % (name.replace("|", "/")[:30], "" if n >= MIN_N else " *(few)*", n,
                        len({x["day"] for x in part}),
                        round(100 * sum(1 for x in part if x["silent"]) / n),
                        ("%+.0f%%" % statistics.median(gaps)) if gaps else "—",
                        f, f / n, l, l / n, "follow" if f > l else "ladder",
                        len(real) or "—", ("%+.0f" % sum(real)) if real else "—",
                        ("%d%%" % round(100 * sum(1 for x in real if x > 0) / len(real))) if real else "—",
                        ("%+.0f%%" % statistics.median(pk)) if pk else "—"))
    only_real = sorted((k for k in pls if k not in by), key=lambda k: sum(pls[k]))
    if only_real:
        lines += ["", "REAL TRADES ON CALLERS WITH NO QUOTED ALERT ABOVE (broker truth only):", ""]
        for name in only_real:
            real = pls[name]
            lines.append("- %s — %d trades %+.0f, win %d%%" % (name, len(real), sum(real),
                         round(100 * sum(1 for x in real if x > 0) / len(real))))
    lines += ["", "built from master_alerts.csv, alert_meta.csv, master_ledger.csv, daily-reports/CALLER-OUTCOMES.csv and the quote tapes · %s" % stamp, ""]
    return "\n".join(lines)


def main():
    all_days, rows, by, n_alerts = build()
    text = render(all_days, rows, by, n_alerts)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, OUT)
    print(text)


if __name__ == "__main__":
    main()
