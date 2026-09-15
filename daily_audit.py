#!/usr/bin/env python3
"""After-close parser audit and regression gate.

The trading parser never rewrites itself from chat.  Instead, every day's
exact parser inputs are replayed, gaps are put in a durable review queue, and
the accumulated regression suite must pass before the report can be green.
That keeps learning measurable without letting untrusted Discord text modify
live trading code.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "daily-audits")


def _run(label, command, timeout=240):
    started = time.time()
    try:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        p = subprocess.run(command, cwd=HERE, env=env,
                           text=True, encoding="utf-8",
                           errors="replace", capture_output=True,
                           timeout=timeout)
        output = (p.stdout or "") + (p.stderr or "")
        return {"name": label, "ok": p.returncode == 0,
                "seconds": round(time.time() - started, 2),
                "output": output.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": label, "ok": False,
                "seconds": round(time.time() - started, 2),
                "output": str(exc)}


def summarize_replay(output):
    def number(pattern):
        m = re.search(pattern, output)
        return int(m.group(1)) if m else 0
    return {
        "silent_drops": number(r"TOTAL silent drops:\s*(\d+)"),
        "possible_missed": number(r"POSSIBLE MISSED ENTRIES:\s*(\d+)"),
        "coverage_warnings": len(re.findall(r"^COVERAGE WARNING:", output,
                                             flags=re.MULTILINE)),
    }


_KEY_LINE = re.compile(r"^(Ran \d+ tests?|OK\b|FAILED \(|\d+ messages, |\s*entries fired "
                       r"(?:BEFORE|NOW)|\s*all actions BEFORE/NOW|\s*JUNK TICKERS)")


def _key_lines(output):
    return ["    " + ln.strip() for ln in (output or "").splitlines()
            if _KEY_LINE.match(ln)]


def _reconciled(day, output):
    """True/False from build_ledger's RECONCILIATION line for ``day``, None
    when the day had no export to reconcile against."""
    m = re.search(r"^\s*%s\s+export\s+\S+\s+ledger\s+\S+\s+(MATCH|DRIFT)"
                  % re.escape(day), output or "", re.M)
    return (m.group(1) == "MATCH") if m else None


def _write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _queue_attention(day, summary, report_path):
    path = os.path.join(OUT_DIR, "review_queue.jsonl")
    # generated_at changes on every manual rerun; fingerprint only the issue
    # shape so the same day's unchanged evidence is one review item.
    issue = {k: summary.get(k) for k in
             ("status", "silent_drops", "possible_missed",
              "coverage_warnings", "failed_checks")}
    fingerprint = hashlib.sha256(json.dumps(issue, sort_keys=True)
                                 .encode("utf-8")).hexdigest()[:16]
    existing = set()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    existing.add((row.get("date"), row.get("fingerprint")))
                except ValueError:
                    continue
    except OSError:
        pass
    if (day, fingerprint) in existing:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"date": day, "fingerprint": fingerprint,
                             "status": "attention", **summary,
                             "report": os.path.relpath(report_path, HERE),
                             "created_at": dt.datetime.now().astimezone().isoformat()},
                            sort_keys=True) + "\n")


def run(day):
    import reports
    import status_json
    os.makedirs(OUT_DIR, exist_ok=True)
    # BROKER TRUTH FIRST (9/15). Nothing in this repo ever pulled the account's
    # order history — `absorb_exports()` only folds a file a Claude session had
    # written by hand, and the last one was 9/11, so 9/12-9/14 reported
    # "broker export missing" and every hand trade was invisible. broker_sync
    # does the pull (and one balance read) BEFORE the reports, so they see the
    # day's real fills. Wrapped: a broker that will not answer must not stop
    # the parser audit, which needs no broker at all.
    broker_step = _run("broker truth sync",
                       [sys.executable, os.path.join(HERE, "broker_sync.py"),
                        day], 180)
    steps_note = broker_step["output"].strip().splitlines()
    print("BROKER SYNC %s — %s" % ("ok" if broker_step["ok"] else "FAILED",
                                   steps_note[-1] if steps_note else ""))
    steps = []
    replay = _run("daily message replay",
                  [sys.executable, os.path.join(HERE, "replay_check.py"), day])
    steps.append(replay)

    node = os.environ.get("NODE", "node")
    js_files = sorted(glob.glob(os.path.join(HERE, "extension", "test_*.js")))
    js_files.append(os.path.join(HERE, "test_resolve.js"))
    for path in js_files:
        steps.append(_run("JS " + os.path.basename(path), [node, path], 90))
    steps.append(_run("Historical parser corpus gate",
                      [node, os.path.join(HERE, "parser_gate.js"), "--show", "40"],
                      180))
    steps.append(_run("Python regression suite",
                      [sys.executable, "-m", "unittest", "discover",
                       "-p", "test_*.py", "-v"], 300))

    counts = summarize_replay(replay["output"])
    failed = [s["name"] for s in steps if not s["ok"]]
    attention = bool(failed or counts["silent_drops"]
                     or counts["possible_missed"]
                     or counts["coverage_warnings"])
    status = "attention" if attention else "pass"
    generated = dt.datetime.now().astimezone().isoformat()

    lines = ["DISCORD SNIPER DAILY AUDIT — %s" % day,
             "generated: %s" % generated,
             "status: %s" % status.upper(),
             "silent drops: %d" % counts["silent_drops"],
             "possible missed entries: %d" % counts["possible_missed"],
             "coverage warnings: %d" % counts["coverage_warnings"],
             "failed checks: %s" % (", ".join(failed) if failed else "none"),
             "", "MESSAGE REPLAY", replay["output"], "", "REGRESSION CHECKS"]
    for step in steps[1:]:
        lines.append("%s  %s  %.2fs" %
                     ("PASS" if step["ok"] else "FAIL", step["name"],
                      step["seconds"]))
        # The counts a passing gate / suite printed stay in the record, so
        # STATUS.json.verified can be rebuilt from this block without
        # re-running either (VERIFY ONCE).
        lines.extend(_key_lines(step["output"]))
        if not step["ok"] and step["output"]:
            lines.append(step["output"][-4000:])
    # ONE FILE PER WEEK (9/15): this day's block in AUDIT week-of-….txt,
    # newest day first; a re-run replaces the block.
    report_path = reports.write_day("audit", day,
                                    "\n".join(lines).rstrip() + "\n")

    summary = {"date": day, "generated_at": generated, "status": status,
               **counts, "failed_checks": failed,
               "broker_sync": {"ok": broker_step["ok"],
                               "note": (steps_note[-1] if steps_note
                                        else "")[:200],
                               # build_ledger's own MATCH/DRIFT line for the
                               # day (ledger == broker export to the cent)
                               "reconciled": _reconciled(day, broker_step["output"])},
               "report": os.path.relpath(report_path, HERE)}
    _write_atomic(os.path.join(OUT_DIR, "latest.json"),
                  json.dumps(summary, indent=2, sort_keys=True) + "\n")

    # THE REPORTS go through reports.py (REUSE, DON'T REBUILD, 9/15): each
    # kind is rebuilt only when its inputs moved since reports/INDEX.json
    # last saw them, and every build is recorded there so the index is
    # always populated by this run. Order matters — each one reads the ones
    # before it. A failure marks the day "attention" exactly as before.
    kinds = (("daily operating report", "report", "daily_report"),
             ("ratchet policy comparison", "ratchet-compare", "ratchet_comparison"),
             ("caller outcome ledger", "caller-outcomes", "caller_outcomes"),
             ("caller versus ratchet comparison", "caller-vs-ratchet",
              "caller_ratchet_comparison"))
    for label, kind, key in kinds:
        res = reports.build(kind, day, quiet=True)
        print("%s %s — %s" % (res["status"].upper(), res["path"], label))
        if res["status"] in ("failed", "partial"):
            attention = True
            summary["failed_checks"].append(label)
            print(res["output"][-2000:])
        else:
            summary[key] = res["path"]
        summary["status"] = "attention" if attention else "pass"
        _write_atomic(os.path.join(OUT_DIR, "latest.json"),
                      json.dumps(summary, indent=2, sort_keys=True) + "\n")
    # INDEX MIRROR (9/13) — score the SPY/QQQ -> MES/MNQ idea on today's real
    # ES/NQ bars and update the running total. It runs AFTER the audit and can
    # never fail it: the mirror is a measurement of a switch that is off, and
    # the audit is the day's books.
    res = reports.build("futures-mirror", day, quiet=True)
    if res["status"] == "failed":
        summary["index_mirror"] = {"status": "failed",
                                   "why": res["output"][-200:]}
        print("INDEX MIRROR replay failed: %s" % res["output"][-200:])
    else:
        summary["index_mirror"] = res["path"]

    try:
        import departments
        summary["daily_analyst"] = departments.daily(day)
    except Exception:
        summary["daily_analyst"] = {"status": "failed"}
    # THE BRIEF (9/15) — the one screen G reads on his phone, built from every
    # report above and posted to Sniper HQ through the Fill Announcer webhook.
    # It runs after the reports it summarises, and a brief that cannot be
    # built must never cost him the audit. A CURRENT brief (nothing above
    # changed since it was posted) is not posted twice.
    res = reports.build("brief", day, extra=("--post",), quiet=True)
    if res["status"] == "failed":
        summary["brief"] = {"status": "failed", "why": res["output"][-200:]}
        print("DAILY BRIEF failed: %s" % res["output"][-200:])
    else:
        summary["brief"] = res["path"]
    _write_atomic(os.path.join(OUT_DIR, "latest.json"), json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if attention:
        _queue_attention(day, summary, report_path)
    # The audit's own record in the report index, then STATUS.json LAST: the
    # one small file that answers "how did we do / what broke / is it
    # verified" without reading a log (ASK-MAP.md).
    try:
        reports.record("audit", day)
    except Exception as _index_error:                   # noqa: BLE001
        print("reports index not updated: %s" % str(_index_error)[:200])
    try:
        status_json.write(day, summary, steps)
    except Exception as _status_error:                  # noqa: BLE001
        print("STATUS.json not written: %s" % str(_status_error)[:200])
    print("DAILY AUDIT %s — %s; silent=%d possible=%d coverage=%d failed=%d"
          % (day, summary["status"].upper(), counts["silent_drops"],
             counts["possible_missed"], counts["coverage_warnings"],
             len(summary["failed_checks"])))
    print(report_path)
    return 1 if attention else 0


if __name__ == "__main__":
    import eastern
    raise SystemExit(run(eastern.day_arg()))
