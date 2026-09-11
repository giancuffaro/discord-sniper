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
    os.makedirs(OUT_DIR, exist_ok=True)
    steps = []
    replay = _run("daily message replay",
                  [sys.executable, os.path.join(HERE, "replay_check.py"), day])
    steps.append(replay)

    node = os.environ.get("NODE", "node")
    js_files = sorted(glob.glob(os.path.join(HERE, "extension", "test_*.js")))
    js_files.append(os.path.join(HERE, "test_resolve.js"))
    for path in js_files:
        steps.append(_run("JS " + os.path.basename(path), [node, path], 90))
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
    report_path = os.path.join(OUT_DIR, "AUDIT-%s.txt" % day)

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
        if not step["ok"] and step["output"]:
            lines.append(step["output"][-4000:])
    _write_atomic(report_path, "\n".join(lines).rstrip() + "\n")

    summary = {"date": day, "generated_at": generated, "status": status,
               **counts, "failed_checks": failed,
               "report": os.path.relpath(report_path, HERE)}
    _write_atomic(os.path.join(OUT_DIR, "latest.json"),
                  json.dumps(summary, indent=2, sort_keys=True) + "\n")
    report_step = _run("daily operating report",
                       [sys.executable, os.path.join(HERE, "daily_report.py"), day],
                       120)
    if not report_step["ok"]:
        attention = True
        summary["status"] = "attention"
        summary["failed_checks"].append(report_step["name"])
        _write_atomic(os.path.join(OUT_DIR, "latest.json"),
                      json.dumps(summary, indent=2, sort_keys=True) + "\n")
    else:
        summary["daily_report"] = os.path.relpath(
            os.path.join(HERE, "daily-reports", "REPORT-%s.md" % day), HERE)
        _write_atomic(os.path.join(OUT_DIR, "latest.json"),
                      json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if attention:
        _queue_attention(day, summary, report_path)
    print("DAILY AUDIT %s — %s; silent=%d possible=%d coverage=%d failed=%d"
          % (day, status.upper(), counts["silent_drops"],
             counts["possible_missed"], counts["coverage_warnings"],
             len(failed)))
    print(report_path)
    return 1 if attention else 0


if __name__ == "__main__":
    audit_day = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    raise SystemExit(run(audit_day))
