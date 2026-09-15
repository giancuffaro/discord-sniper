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
               "broker_sync": {"ok": broker_step["ok"],
                               "note": (steps_note[-1] if steps_note
                                        else "")[:200]},
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
    policy_step = _run("ratchet policy comparison",
                       [sys.executable,
                        os.path.join(HERE, "daily_policy_compare.py"), day],
                       120)
    if not policy_step["ok"]:
        attention = True
        summary["status"] = "attention"
        summary["failed_checks"].append(policy_step["name"])
    else:
        summary["ratchet_comparison"] = os.path.relpath(
            os.path.join(HERE, "daily-reports",
                         "RATCHET-COMPARE-%s.md" % day), HERE)
    caller_step = _run("caller outcome ledger",
                       [sys.executable,
                        os.path.join(HERE, "caller_outcomes.py"), day],
                       120)
    if not caller_step["ok"]:
        attention = True
        summary["status"] = "attention"
        summary["failed_checks"].append(caller_step["name"])
    else:
        summary["caller_outcomes"] = os.path.relpath(
            os.path.join(HERE, "daily-reports",
                         "CALLER-OUTCOMES-%s.md" % day), HERE)
    paired_step = _run("caller versus ratchet comparison",
                       [sys.executable,
                        os.path.join(HERE, "caller_ratchet_compare.py"), day],
                       120)
    if not paired_step["ok"]:
        attention = True
        summary["status"] = "attention"
        summary["failed_checks"].append(paired_step["name"])
    else:
        summary["caller_ratchet_comparison"] = os.path.relpath(
            os.path.join(HERE, "daily-reports",
                         "CALLER-VS-RATCHET-%s.md" % day), HERE)
    summary["status"] = "attention" if attention else "pass"
    _write_atomic(os.path.join(OUT_DIR, "latest.json"),
                  json.dumps(summary, indent=2, sort_keys=True) + "\n")
    # INDEX MIRROR (9/13) — score the SPY/QQQ -> MES/MNQ idea on today's real
    # ES/NQ bars and update the running total. It runs AFTER the audit and can
    # never fail it: the mirror is a measurement of a switch that is off, and
    # the audit is the day's books.
    try:
        import futures_mirror_daily
        futures_mirror_daily.main(day)
        summary["index_mirror"] = os.path.relpath(
            os.path.join(HERE, "daily-reports",
                         "FUTURES-MIRROR-%s.md" % day), HERE)
    except Exception as _mirror_error:                  # noqa: BLE001
        summary["index_mirror"] = {"status": "failed",
                                   "why": str(_mirror_error)[:200]}
        print("INDEX MIRROR replay failed: %s" % str(_mirror_error)[:200])

    try:
        import departments
        summary["daily_analyst"] = departments.daily(day)
    except Exception:
        summary["daily_analyst"] = {"status": "failed"}
    # THE BRIEF (9/15) — the one screen G reads on his phone, built from every
    # report above and posted to Sniper HQ through the Fill Announcer webhook.
    # It runs LAST so the reports it summarises already exist, and it is
    # wrapped: a brief that cannot be built must never cost him the audit.
    try:
        import daily_brief
        daily_brief.main(day, do_post=True)
        summary["brief"] = os.path.relpath(
            os.path.join(HERE, "daily-reports", "BRIEF-%s.md" % day), HERE)
    except Exception as _brief_error:                   # noqa: BLE001
        summary["brief"] = {"status": "failed",
                            "why": str(_brief_error)[:200]}
        print("DAILY BRIEF failed: %s" % str(_brief_error)[:200])
    _write_atomic(os.path.join(OUT_DIR, "latest.json"), json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if attention:
        _queue_attention(day, summary, report_path)
    print("DAILY AUDIT %s — %s; silent=%d possible=%d coverage=%d failed=%d"
          % (day, summary["status"].upper(), counts["silent_drops"],
             counts["possible_missed"], counts["coverage_warnings"],
             len(summary["failed_checks"])))
    print(report_path)
    return 1 if attention else 0


if __name__ == "__main__":
    import eastern
    raise SystemExit(run(eastern.day_arg()))
