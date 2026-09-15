#!/usr/bin/env python3
"""reports.py — the report registry, the weekly files, and the cache that
decides REUSE vs REBUILD (G, 9/15: "if I ask for a report and then another
day ask again, do not remake it — use the old one if it is the same data").

ONE FILE PER WEEK PER KIND. Every report kind lands in one weekly file named
like the DS Logs exports —

    daily-reports/REPORT week-of-Sep-14-to-Sep-20-2026.md
    daily-audits/AUDIT week-of-Sep-14-to-Sep-20-2026.txt

— with a ``===== Mon Sep 14 2026 =====`` block per day, NEWEST DAY FIRST; a
re-run for a day replaces that day's block (ds_logs.put_day). The one CSV
kind (CALLER-OUTCOMES) is one csv with a ``date`` column, replace-by-date.

THE CACHE. ``reports/INDEX.json`` remembers, per kind and day, the
fingerprint of every input the report was built from. ``build`` recomputes
the fingerprint, and when nothing changed it prints ``CURRENT <path>`` and
runs nothing. ``status`` says current or stale and WHICH input moved.
Input kinds: whole files by size+mtime (f: code, config; g: globs), dated
files by the hash of that day's lines or rows (dated: trades.log, csvdate: the
master csvs, tape: epoch-stamped tapes — the live bridge appends to them all
day, and a past day must not go stale because today grew), the day's DS Logs
blocks (dslogs), and the day's block or rows of another report (block:, csv:).

    python reports.py status [YYYY-MM-DD]      one line per kind/day
    python reports.py build <kind> <day>       skip if current, else rebuild
    python reports.py build all <day>          every buildable kind, in order
    python reports.py path <kind> <day>        the weekly file for that day
    python reports.py show <kind> <day>        that day's block, to stdout
    python reports.py kinds                    the registry

The builders are the existing scripts, run as subprocesses exactly as the
16:40 audit ran them (timeouts, captured output); this file imports none of
them, so they may import it.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

import ds_logs

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "reports", "INDEX.json")
REPORTS = "daily-reports"
AUDITS = "daily-audits"
UNDATED = "all"     # the date key of a kind that is not per-day

# What the extension's parser, rooms and symbol rules are — a change to any
# of them changes what every replay says, so they are inputs to every report.
PARSER_RULES = ("f:extension/parser.js", "f:extension/rooms.txt",
                "f:extension/optionable.txt", "f:extension/parse_batch.js")


class Kind(object):
    """One report kind. ``script`` None = made by hand or by another process
    (AUTO PUSH); registered so ``status`` and ``path`` still find it."""

    def __init__(self, name, prefix, folder, ext, script=None, inputs=(),
                 csv_name=None, dated=True, timeout=120, what=""):
        self.name = name
        self.prefix = prefix
        self.folder = folder
        self.ext = ext
        self.script = script
        self.inputs = tuple(inputs)
        self.csv_name = csv_name
        self.dated = dated
        self.timeout = timeout
        self.what = what

    def rel_path(self, day):
        if not self.dated:
            return self.prefix + "." + self.ext
        return os.path.join(self.folder,
                            ds_logs.weekly_file(self.prefix, _date(day), self.ext))

    def path(self, day):
        return os.path.join(HERE, self.rel_path(day))

    def csv_path(self):
        return os.path.join(HERE, self.folder, self.csv_name) if self.csv_name else None


DAY_INPUTS = ("dslogs", "dated:trades.log", "csvdate:master_ledger.csv",
              "csvdate:master_alerts.csv", "csvdate:master_postmortems.csv",
              "f:daily-audits/recovered-{day}.json")

KINDS = {}
for _k in (
    Kind("report", "REPORT", REPORTS, "md", "daily_report.py",
         DAY_INPUTS + PARSER_RULES + ("f:daily_report.py", "f:replay_check.py"),
         what="Daily Sniper Report: coverage, alert funnel, fills, P&L, every decision"),
    Kind("ratchet-compare", "RATCHET-COMPARE", REPORTS, "md",
         "daily_policy_compare.py",
         ("block:report", "csvdate:alert_meta.csv", "csvdate:master_ledger.csv",
          "tape:alert_tape.csv", "tape:option_tape.csv",
          "f:daily_policy_compare.py", "f:ratchet_tiers.py"),
         what="live 5/3/5 ratchet vs a fixed -5% born stop over exact-contract quote paths"),
    Kind("caller-outcomes", "CALLER-OUTCOMES", REPORTS, "md",
         "caller_outcomes.py",
         DAY_INPUTS + PARSER_RULES + ("tape:alert_tape.csv", "csvdate:alert_meta.csv",
                                      "tape:quote_shadow.csv",
                                      "f:caller_outcomes.py", "f:daily_report.py"),
         csv_name="CALLER-OUTCOMES.csv",
         what="caller entry, every trim and full exit, with the evidence basis"),
    Kind("caller-vs-ratchet", "CALLER-VS-RATCHET", REPORTS, "md",
         "caller_ratchet_compare.py",
         ("csv:caller-outcomes", "dslogs", "csvdate:master_ledger.csv",
          "f:daily-audits/recovered-{day}.json", "tape:alert_tape.csv",
          "tape:option_tape.csv", "f:caller_ratchet_compare.py",
          "f:ratchet_tiers.py", "f:tape.py"),
         what="5/3/5 ratchet replayed from the caller's own entry over tape.py"),
    Kind("futures-mirror", "FUTURES-MIRROR", REPORTS, "md",
         "futures_mirror_daily.py",
         ("csvdate:futures_mirror_shadow.csv", "csvdate:master_alerts.csv",
          "g:bars/ES_1m_*.csv", "g:bars/NQ_1m_*.csv",
          "f:futures_mirror_daily.py"), timeout=300,
         what="SPY/QQQ entries replayed as MES/MNQ on real ES/NQ 1-min bars"),
    Kind("brief", "BRIEF", REPORTS, "md", "daily_brief.py",
         ("csvdate:master_ledger.csv", "csvdate:master_broker.csv",
          "csvdate:balance_daily.csv", "dated:trades.log",
          "csv:caller-outcomes", "block:caller-vs-ratchet",
          "block:futures-mirror", "g:department-reports/extension-*.json",
          "f:HANDOFF.md", "f:daily_brief.py"),
         what="the one screen G reads: day, bot trades, callers, what broke, pending"),
    Kind("audit", "AUDIT", AUDITS, "txt", "daily_audit.py",
         DAY_INPUTS + PARSER_RULES + ("f:parser_gate.js", "g:extension/test_*.js",
                                      "g:test_*.py", "f:daily_audit.py",
                                      "f:replay_check.py"), timeout=1800,
         what="the 16:40 run: broker sync, replay, JS/Python tests, parser gate, then every report"),
    Kind("scoreboard", "SCOREBOARD", "", "html", "scoreboard.py",
         ("g:DS Logs/signal-room-chat*.txt", "f:master_ledger.csv",
          "f:extension/rooms.txt", "f:scoreboard.py"), dated=False,
         what="per-room signal/trade scoreboard -> SCOREBOARD.html"),
    Kind("alert-audit", "ALERT-AUDIT", "", "html", "audit_history.py",
         ("g:DS Logs/signal-room-chat*.txt", "f:trades.log") + PARSER_RULES
         + ("f:audit_history.py",), dated=False, timeout=900,
         what="every export since day one: traded / missed / blind / silent per room -> ALERT-AUDIT.html"),
    Kind("alert-ledger", "ALERT-LEDGER", REPORTS, "md",
         what="hand-made alert ledger (no builder); kept as a weekly file"),
    Kind("ninjago-futures-radar", "NINJAGO-FUTURES-RADAR", REPORTS, "md",
         what="hand-made caller-bracket replay (no builder)"),
    Kind("alert-history", "ALERT-HISTORY", AUDITS, "txt",
         what="hand-made all-time alert audit text (no builder; audit_history.py is the live one)"),
    Kind("parser-history", "PARSER-HISTORY", AUDITS, "txt",
         what="a frozen parser_gate run (AUTO PUSH writes PARSER-HISTORY-LATEST.txt every push)"),
):
    KINDS[_k.name] = _k

# The order the audit builds them in: each one's inputs come before it.
BUILD_ORDER = ("report", "ratchet-compare", "caller-outcomes",
               "caller-vs-ratchet", "futures-mirror", "brief")


def _date(day):
    return dt.date.fromisoformat(day) if isinstance(day, str) else day


def kind(name):
    try:
        return KINDS[name]
    except KeyError:
        raise SystemExit("unknown report kind %r — one of: %s"
                         % (name, ", ".join(sorted(KINDS))))


# ---------------------------------------------------------------- weekly IO

def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _preamble(k, day):
    mon, sun = ds_logs.week_bounds(_date(day))
    return ["# %s — week of %s to %s. Newest day first; each day under its"
            " ===== header; a re-run replaces that day's block (reports.py)."
            % (k.prefix, ds_logs.day_header(mon).strip("= "),
               ds_logs.day_header(sun).strip("= "))]


def path(name, day):
    """The weekly file holding ``day``'s report of this kind."""
    return kind(name).path(day)


def day_text(name, day):
    """That day's block of the weekly file, or None."""
    k = kind(name)
    if not k.dated:
        return _read(k.path(day)) or None
    return ds_logs.get_day(_read(k.path(day)), _date(day))


def write_day(name, day, text):
    """Put one day's report into its weekly file (replace that day's block).
    Returns the file path. Used by every report writer instead of a dated
    file of its own."""
    k = kind(name)
    p = k.path(day)
    _write_atomic(p, ds_logs.put_day(_read(p), _date(day), text,
                                     _preamble(k, day), newest_first=True))
    return p


def days_in(name, day):
    """Every ISO day the weekly file holding ``day`` covers, newest first."""
    return [d.isoformat() for d, _ in
            ds_logs.split_day_blocks(_read(kind(name).path(day)))]


def csv_rows(name, day):
    """The rows of the kind's one csv for ``day`` (the ``date`` column)."""
    k = kind(name)
    p = k.csv_path()
    if not p or not os.path.exists(p):
        return None
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("date") == day]


def write_csv_rows(name, day, fields, rows):
    """Replace ``day``'s rows in the kind's one csv (``date`` first column),
    keeping every other day. Returns the csv path."""
    k = kind(name)
    p = k.csv_path()
    fields = ["date"] + [f for f in fields if f != "date"]
    kept = []
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            old_fields = [f for f in (rd.fieldnames or []) if f not in fields]
            fields += old_fields
            kept = [r for r in rd if r.get("date") != day]
    new = [dict(r, date=day) for r in rows]
    out = sorted(kept + new, key=lambda r: r.get("date") or "")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    os.replace(tmp, p)
    return p


# ------------------------------------------------------------- fingerprints

def _h(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def _stat_sig(p):
    try:
        st = os.stat(p)
    except OSError:
        return "missing"
    return "%d:%d" % (st.st_size, int(st.st_mtime))


def _dated_lines_sig(p, day):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return _h("".join(ln for ln in fh if ln.startswith(day)))
    except OSError:
        return "missing"


def _tape_day_sig(p, day):
    """Rows of an epoch-stamped tape (ts first column) that fall on ``day``
    in New York. Append-only files, so a past day only moves on a backfill."""
    import eastern
    d = _date(day)
    lo = dt.datetime(d.year, d.month, d.day, tzinfo=eastern.ET).timestamp()
    hi = lo + 36 * 3600      # generous: covers the DST day too
    h = hashlib.sha256()
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                head = ln.split(",", 1)[0]
                try:
                    ts = float(head)
                except ValueError:
                    continue
                if lo <= ts < hi:
                    h.update(ln.encode("utf-8", "replace"))
    except OSError:
        return "missing"
    return h.hexdigest()[:16]


def _csv_date_sig(p, day):
    try:
        with open(p, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            rows = [r for r in rd if str(r.get("date") or "")[:10] == day]
    except (OSError, csv.Error):
        return "missing"
    return _h(json.dumps(rows, sort_keys=True, default=str))


def _dslogs_sig(day):
    sig = {}
    for f in ds_logs.files_for_day(HERE, day):
        text = _read(f)
        block = ds_logs.get_day(text, _date(day))
        sig[os.path.basename(f)] = _h(block) if block is not None else _stat_sig(f)
    return sig


def input_signatures(name, day):
    """{input name: signature} for every declared input of the kind."""
    k = kind(name)
    sig = {}
    for spec in k.inputs:
        tag, _, arg = spec.partition(":")
        arg = arg.replace("{day}", day)
        if tag == "f":
            sig[arg] = _stat_sig(os.path.join(HERE, arg))
        elif tag == "g":
            for p in sorted(glob.glob(os.path.join(HERE, arg))):
                sig[os.path.relpath(p, HERE)] = _stat_sig(p)
        elif tag == "dated":
            sig[arg + " (day lines)"] = _dated_lines_sig(os.path.join(HERE, arg), day)
        elif tag == "csvdate":
            sig[arg + " (day rows)"] = _csv_date_sig(os.path.join(HERE, arg), day)
        elif tag == "tape":
            sig[arg + " (day rows)"] = _tape_day_sig(os.path.join(HERE, arg), day)
        elif tag == "dslogs":
            for f, s in _dslogs_sig(day).items():
                sig["DS Logs/" + f + " (day block)"] = s
        elif tag == "block":
            other = day_text(arg, day)
            sig[kind(arg).rel_path(day) + " (day block)"] = (
                _h(other) if other is not None else "missing")
        elif tag == "csv":
            rows = csv_rows(arg, day)
            sig[kind(arg).csv_name + " (day rows)"] = (
                _h(json.dumps(rows, sort_keys=True)) if rows is not None
                else "missing")
    return sig


def fingerprint(sigs):
    return _h(json.dumps(sigs, sort_keys=True))


# ------------------------------------------------------------------ the index

def load_index():
    try:
        with open(INDEX, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_index(index):
    _write_atomic(INDEX, json.dumps(index, indent=1, sort_keys=True) + "\n")


def _day_key(k, day):
    return day if k.dated else UNDATED


def _output_present(k, day):
    if not k.dated:
        return os.path.exists(k.path(day))
    return day_text(k.name, day) is not None


def check(name, day):
    """(state, why, path): state is 'current', 'stale', 'missing' (never
    built or output gone) or 'manual' (no builder). ``why`` names the inputs
    that moved."""
    k = kind(name)
    p = k.rel_path(day)
    present = _output_present(k, day)
    if not k.script:
        return ("manual" if present else "missing",
                "no builder; hand-made" if present else "no such file", p)
    entry = (load_index().get(name) or {}).get(_day_key(k, day))
    if not present:
        return "missing", "output not on disk", p
    if not entry:
        return "stale", "never recorded in reports/INDEX.json", p
    sigs = input_signatures(name, day)
    if fingerprint(sigs) == entry.get("fingerprint"):
        return "current", "built %s" % entry.get("built_at", "?"), p
    old = entry.get("inputs") or {}
    moved = sorted(n for n in set(sigs) | set(old) if sigs.get(n) != old.get(n))
    return "stale", "changed: " + ", ".join(moved[:6]) + (
        " (+%d more)" % (len(moved) - 6) if len(moved) > 6 else ""), p


def record(name, day, sigs=None):
    """Remember that ``name``/``day`` was just built from ``sigs``."""
    k = kind(name)
    sigs = input_signatures(name, day) if sigs is None else sigs
    index = load_index()
    index.setdefault(name, {})[_day_key(k, day)] = {
        "fingerprint": fingerprint(sigs), "inputs": sigs,
        "output": k.rel_path(day).replace("\\", "/"),
        "built_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    save_index(index)


def run_script(k, day, extra=()):
    """Run the kind's script the way the audit does: subprocess, captured
    output, a timeout. Returns {ok, seconds, output}."""
    cmd = [sys.executable, os.path.join(HERE, k.script)]
    if k.dated:
        cmd.append(day)
    cmd.extend(extra)
    started = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run(cmd, cwd=HERE, env=env, text=True, encoding="utf-8",
                           errors="replace", capture_output=True,
                           timeout=k.timeout)
        return {"ok": p.returncode == 0, "seconds": round(time.time() - started, 2),
                "output": ((p.stdout or "") + (p.stderr or "")).strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "seconds": round(time.time() - started, 2),
                "output": str(exc)}


def build(name, day, force=False, extra=(), quiet=False):
    """REUSE, DON'T REBUILD. Returns {status: current|built|partial|failed|
    manual, path, why, seconds, output}. ``partial`` = the script wrote the
    day's block but exited non-zero; nothing is recorded, so it is retried."""
    k = kind(name)
    state, why, rel = check(name, day)
    if state == "manual":
        return {"status": "manual", "path": rel, "why": why, "seconds": 0, "output": ""}
    if not k.script:
        return {"status": "failed", "path": rel, "why": why, "seconds": 0, "output": ""}
    if state == "current" and not force:
        if not quiet:
            print("CURRENT %s" % rel)
        return {"status": "current", "path": rel, "why": why, "seconds": 0, "output": ""}
    sigs = input_signatures(name, day)
    started = time.time() - 1
    res = run_script(k, day, extra)
    present = _output_present(k, day)
    if res["ok"] and present:
        record(name, day, sigs)
        status = "built"
    elif present and os.path.getmtime(k.path(day)) >= started:
        # The script wrote its block but exited non-zero (the futures mirror
        # says "bars unavailable" that way): the file is real, the index is
        # NOT updated, so the next call tries again.
        status = "partial"
    else:
        status = "failed"
    if not quiet:
        print("%s %s (%s, %.1fs)" % (status.upper(), rel, why, res["seconds"]))
    return dict(res, status=status, path=rel, why=why)


def status_lines(day=None):
    """One line per kind/day: everything the index knows, plus ``day`` (today
    by default) for every kind."""
    index = load_index()
    days = {}
    for name, k in KINDS.items():
        keys = set((index.get(name) or {}).keys())
        keys.add(_day_key(k, day) if day else (UNDATED if not k.dated else None))
        keys.discard(None)
        days[name] = keys
    out = []
    for name in sorted(KINDS):
        k = KINDS[name]
        for d in sorted(days[name], reverse=True):
            probe = d if d != UNDATED else (day or dt.date.today().isoformat())
            state, why, rel = check(name, probe)
            out.append("%-22s %-10s %-8s %s  [%s]" % (name, d, state.upper(), rel, why))
    return out


# ------------------------------------------------------------------- CLI

def main(argv):
    import eastern
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd == "kinds":
        for name in sorted(KINDS):
            k = KINDS[name]
            print("%-22s %-60s %s" % (name, k.rel_path(eastern.now().date().isoformat()),
                                      k.what))
        return 0
    if cmd == "status":
        day = eastern.day_arg([argv[0]] + argv[2:3])
        print("\n".join(status_lines(day)))
        return 0
    if cmd in ("build", "path", "show"):
        if len(argv) < 3:
            raise SystemExit("usage: reports.py %s <kind|all> [YYYY-MM-DD]" % cmd)
        day = eastern.day_arg([argv[0]] + argv[3:4])
        names = BUILD_ORDER if argv[2] == "all" else (argv[2],)
        rc = 0
        for name in names:
            if cmd == "path":
                print(kind(name).rel_path(day))
            elif cmd == "show":
                text = day_text(name, day)
                print(text if text is not None else
                      "no %s for %s (%s)" % (name, day, kind(name).rel_path(day)))
                rc = rc or (0 if text is not None else 1)
            else:
                res = build(name, day, force="--force" in argv)
                if res["status"] in ("failed", "partial"):
                    rc = 1
                    print(res["output"][-3000:])
        return rc
    raise SystemExit("unknown command %r — status | build | path | show | kinds" % cmd)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
