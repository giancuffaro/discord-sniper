#!/usr/bin/env python3
"""STATUS.json — the one small file that answers the everyday questions.

Written LAST by the 16:40 audit (daily_audit.py) from things the audit has
already computed or that are already on disk; no AI, no broker call. Under
4 KB. ASK-MAP.md says which field answers which question; read this before
any log.

    date                 the audit day
    balance              nlv / day_pl / bp from balance_daily.csv (that day)
    bot                  trades and realized P&L (master_ledger, live, not manual)
    rooms                per lane: rooms switched on, rooms that spoke, messages read
    audit                status / silent drops / possible missed / failed checks
    broke                the audit's unresolved review queue, newest 5
    pending              HANDOFF.md's Pending list, as the brief shows it
    bridge               last known health (department-reports/health-latest.json,
                         and a 2 s loopback probe of the running bridge)
    verified             tests, parser_gate, broker_reconciled, bridge_code_live —
                         VERIFY ONCE: trusted while their inputs are unchanged
    reports              reports.py status for the day, one line per kind

`python status_json.py [YYYY-MM-DD]` rebuilds it from disk alone (the
verified.tests / parser_gate blocks then come from the audit's last written
AUDIT block, never re-run).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "STATUS.json")


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _csv(name, day=None):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return []
    return [r for r in rows if day is None or (r.get("date") or "")[:10] == day]


def balance(day):
    row = None
    for r in _csv("balance_daily.csv"):
        if (r.get("date") or "") <= day:
            row = r
    if not row:
        return {"nlv": None, "day_pl": None, "bp": None, "as_of": None}
    return {"nlv": _num(row.get("nlv")), "day_pl": _num(row.get("day_pl")),
            "bp": _num(row.get("bp")), "as_of": row.get("date")}


def bot(day):
    """The brief's own definition of a bot trade (daily_brief.split_day):
    live, not manual, not a hand caller, not an export-only hand row."""
    import daily_brief
    rows = [r for r in _csv("master_ledger.csv", day) if r.get("account") == "live"]
    rows, _hand = daily_brief.split_day(rows, day)
    pl = [_num(r.get("pl")) for r in rows]
    pl = [x for x in pl if x is not None]
    return {"trades": len(rows), "pl": round(sum(pl), 2),
            "wins": sum(1 for x in pl if x > 0),
            "losses": sum(1 for x in pl if x < 0)}


_MSG = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}  \[(.*?) #(\S+?)(?: message_id=\S+)?\]  ")


def rooms(day):
    """Per lane: rooms switched on in rooms.txt, rooms that spoke in that
    day's DS Logs block, and how many messages were read there."""
    import ds_logs
    on = {"discord": 0, "whop": 0}
    try:
        with open(os.path.join(HERE, "extension", "rooms.txt"), encoding="utf-8") as fh:
            for line in fh:
                p = [x.strip() for x in line.split("|")]
                if line.strip() and not line.lstrip().startswith("#") \
                        and len(p) >= 5 and p[4].lower() == "on":
                    on["whop" if "whop.com" in p[1] else "discord"] += 1
    except OSError:
        pass
    out = {}
    for f in ds_logs.files_for_day(HERE, day):
        m = re.search(r"\((discord|whop)\)\.txt$", f)
        lane = m.group(1) if m else "discord"
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        block = ds_logs.get_day(text, dt.date.fromisoformat(day)) or ""
        seen, reads, sec = set(), 0, None
        for ln in block.split("\n"):
            if ln.startswith("=== "):
                sec = "raw" if ln.startswith("=== RAW MESSAGES") else "other"
                continue
            if sec != "raw":
                continue
            mm = _MSG.match(ln)
            if mm and mm.group(1) == day:
                seen.add(mm.group(3))
                reads += 1
        out[lane] = {"on": on.get(lane, 0), "spoke": len(seen), "reads": reads}
    for lane in ("discord", "whop"):
        out.setdefault(lane, {"on": on[lane], "spoke": None, "reads": None})
    return out


def broke(day, summary):
    items = []
    if summary.get("failed_checks"):
        items.append({"date": day, "failed_checks": summary["failed_checks"]})
    queue = []
    try:
        with open(os.path.join(HERE, "daily-audits", "review_queue.jsonl"),
                  encoding="utf-8") as fh:
            for line in fh:
                try:
                    queue.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    for row in reversed(queue):
        items.append({k: row.get(k) for k in
                      ("date", "silent_drops", "possible_missed",
                       "coverage_warnings", "failed_checks")})
        if len(items) >= 5:
            break
    return items


def pending():
    try:
        import daily_brief
        block = daily_brief.section_pending()
    except Exception:                                   # noqa: BLE001
        return []
    return [ln[2:].strip() for ln in block.splitlines() if ln.startswith("- ")][:8]


def bridge():
    out = {"health": None, "up": False, "buying_power": None, "probed_at": _now()}
    try:
        with open(os.path.join(HERE, "department-reports", "health-latest.json"),
                  encoding="utf-8") as fh:
            h = json.load(fh)
        out["health"] = {"issues": (h.get("issues") or [])[:5],
                         "lanes": [{"lane": ln.get("lane"), "fresh": ln.get("fresh"),
                                    "version": ln.get("version")}
                                   for ln in (h.get("lanes") or [])],
                         "checked_at": h.get("checked_at")}
    except (OSError, ValueError):
        pass
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/", timeout=2) as r:
            st = json.loads(r.read().decode("utf-8") or "{}")
        out["up"] = True
        out["buying_power"] = _num(st.get("buying_power"))
    except Exception:                                   # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------ verified block

def _tests_from(output):
    m = re.search(r"Ran (\d+) tests?", output or "")
    if not m:
        return None
    ran = int(m.group(1))
    f = re.search(r"failures=(\d+)", output or "")
    e = re.search(r"errors=(\d+)", output or "")
    bad = (int(f.group(1)) if f else 0) + (int(e.group(1)) if e else 0)
    return {"passed": ran - bad, "failed": bad}


def _gate_from(output):
    o = output or ""
    msgs = re.search(r"(\d+) messages", o)
    now = re.search(r"entries fired NOW\s*:\s*(\d+)", o)
    acts = re.search(r"all actions BEFORE/NOW:\s*\d+\s*/\s*(\d+)", o)
    if not (msgs and now and acts):
        return None
    return {"messages": int(msgs.group(1)), "entries": int(now.group(1)),
            "actions": int(acts.group(1)),
            "pass": "PASS" in o and "JUNK TICKERS: 0" in o}


def _reconciled(day, summary):
    """build_ledger's own MATCH/DRIFT verdict for the day (ledger P&L equals
    the broker export to the cent), as the audit parsed it from the broker
    sync step. None = no export for the day, nothing to reconcile."""
    sync = summary.get("broker_sync") or {}
    legs = [r for r in _csv("master_broker.csv", day) if r.get("status") == "FILLED"]
    ledger = [r for r in _csv("master_ledger.csv", day) if r.get("account") == "live"]
    return {"match": sync.get("reconciled"), "sync_ok": sync.get("ok"),
            "broker_legs": len(legs),
            "ledger_pl": round(sum(_num(r.get("pl")) or 0 for r in ledger), 2),
            "at": _now()}


def _code_live():
    sha = None
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                             capture_output=True, text=True, timeout=10
                             ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        mt = dt.datetime.fromtimestamp(os.path.getmtime(
            os.path.join(HERE, "bridge.py"))).astimezone().isoformat(timespec="seconds")
    except OSError:
        mt = None
    return {"sha": sha, "bridge_py_mtime": mt, "at": _now()}


def verified(day, summary, steps, prior=None):
    """``prior`` is the last STATUS.json's verified block: a hand rebuild
    that has no fresh test/gate output keeps the recorded one, with its
    original ``at`` — VERIFY ONCE means the old check stands, not that a
    None replaces it."""
    prior = prior or {}
    by = {s.get("name"): s for s in (steps or [])}
    tests = _tests_from((by.get("Python regression suite") or {}).get("output"))
    js = [s for n, s in by.items() if n.startswith("JS ")]
    if tests and js:
        tests["passed"] += sum(1 for s in js if s.get("ok"))
        tests["failed"] += sum(1 for s in js if not s.get("ok"))
    gate = _gate_from((by.get("Historical parser corpus gate") or {}).get("output"))
    return {"tests": (dict(tests, at=_now()) if tests else
                      prior.get("tests") or {"passed": None, "failed": None, "at": None}),
            "parser_gate": ({"counts": gate, "at": _now()} if gate else
                            prior.get("parser_gate") or {"counts": None, "at": None}),
            "broker_reconciled": _reconciled(day, summary),
            "bridge_code_live": _code_live()}


def _steps_from_audit(day):
    """When rebuilt by hand: the audit's own AUDIT block carries the test and
    gate lines it wrote — read those, never re-run them (VERIFY ONCE)."""
    import reports
    text = reports.day_text("audit", day) or ""
    steps = []
    for name in ("Python regression suite", "Historical parser corpus gate"):
        m = re.search(r"^(PASS|FAIL)  %s  [\d.]+s\n(.*?)(?=^(?:PASS|FAIL)  |\Z)"
                      % re.escape(name), text, re.S | re.M)
        # The audit indents the kept count lines by four spaces.
        text_block = m.group(2) if m else ""
        m = m and (m.group(1), "\n".join(ln.strip() for ln in text_block.splitlines()))
        if m:
            steps.append({"name": name, "ok": m[0] == "PASS", "output": m[1]})
    for m in re.finditer(r"^(PASS|FAIL)  (JS \S+)", text, re.M):
        steps.append({"name": m.group(2), "ok": m.group(1) == "PASS"})
    return steps


def read(path=None):
    try:
        with open(path or PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def build(day, summary, steps, prior=None):
    import reports
    return {"date": day, "written_at": _now(), "balance": balance(day),
            "bot": bot(day), "rooms": rooms(day),
            "audit": {k: summary.get(k) for k in
                      ("status", "silent_drops", "possible_missed",
                       "coverage_warnings", "failed_checks", "generated_at")},
            "broke": broke(day, summary), "pending": pending(),
            "bridge": bridge(),
            "verified": verified(day, summary, steps,
                                 (prior or {}).get("verified")),
            "reports": [ln for ln in reports.status_lines(day)
                        if ((" %s " % day) in ln or " all " in ln)
                        and " MISSING " not in ln]}


def write(day, summary, steps, path=None):
    data = build(day, summary, steps, read(path))
    text = json.dumps(data, indent=1, sort_keys=True, default=str)
    if len(text) > 4000:      # the file stays small: trim the long lists first
        data["reports"] = data["reports"][:6]
        data["broke"] = data["broke"][:3]
        data["pending"] = data["pending"][:4]
        text = json.dumps(data, indent=1, sort_keys=True, default=str)
    path = path or PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    os.replace(tmp, path)
    return path


def main(argv):
    import eastern
    day = eastern.day_arg(argv)
    try:
        with open(os.path.join(HERE, "daily-audits", "latest.json"),
                  encoding="utf-8") as fh:
            summary = json.load(fh)
    except (OSError, ValueError):
        summary = {}
    if summary.get("date") != day:
        summary = {"date": day, "status": "no audit for this day"}
    print(write(day, summary, _steps_from_audit(day)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
