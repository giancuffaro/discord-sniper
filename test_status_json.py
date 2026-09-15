"""STATUS.json — built from disk and the audit's own step outputs, small,
and every field ASK-MAP.md quotes is present."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import daily_brief                                          # noqa: E402
import reports                                              # noqa: E402
import status_json                                          # noqa: E402

DAY = "2026-09-14"
LEDGER = ("date,room,caller,symbol,account,manual,pl\n"
          "2026-09-14,Mugzone,MuggZone,TSLA,live,,-4\n"
          "2026-09-14,shabs,Skyy,QQQ,live,,25\n"
          "2026-09-14,?,,QQQ,live,,-50\n"
          "2026-09-14,?,Gian,SPY,live,True,-300\n"
          "2026-09-13,Mugzone,MuggZone,NVDA,live,,50\n")
GATE = ("PARSER GATE — parser + room + symbol rules  vs  HEAD\n"
        "11386 messages, 75 rooms, 6362 on the allowlist\n"
        "  entries fired BEFORE : 852\n  entries fired NOW    : 852   (+0)\n"
        "  all actions BEFORE/NOW: 3048 / 3048\n  JUNK TICKERS: 0 \n"
        "PASS — no invented tickers.\n")
TESTS = "...\nRan 248 tests in 18.7s\n\nFAILED (errors=1)\n"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class StatusFixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="status-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        saved = (status_json.HERE, status_json.PATH, reports.HERE,
                 daily_brief.HERE, status_json.bridge)
        status_json.HERE = self.root
        status_json.PATH = os.path.join(self.root, "STATUS.json")
        reports.HERE = self.root
        daily_brief.HERE = self.root
        status_json.bridge = lambda: {"up": False, "health": None}

        def restore():
            (status_json.HERE, status_json.PATH, reports.HERE,
             daily_brief.HERE, status_json.bridge) = saved
        self.addCleanup(restore)
        _write(os.path.join(self.root, "balance_daily.csv"),
               "date,nlv,day_pl,bp,read_at\n"
               "2026-09-13,1600,-10,1600,x\n2026-09-14,1279.86,-333.85,1279.86,x\n")
        _write(os.path.join(self.root, "master_ledger.csv"), LEDGER)
        _write(os.path.join(self.root, "master_broker.csv"),
               "date,status,pl\n2026-09-14,FILLED,\n")
        _write(os.path.join(self.root, "extension", "rooms.txt"),
               "1|https://discord.com/channels/1/2|A|g|on\n"
               "2|https://discord.com/channels/1/3|B|g|off\n"
               "3|https://whop.com/x/exp_1/app/|W|g|on\n")
        _write(os.path.join(self.root, "DS Logs",
                            "signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt"),
               "preamble\n\n===== Mon Sep 14 2026 =====\n\n"
               "=== RAW MESSAGES (3) ===\n"
               "2026-09-14 10:00:00  [Srv: room-a #1 message_id=11]  hi\n"
               "2026-09-14 10:00:01  [Srv: room-a #1 message_id=12]  hi2\n"
               "2026-09-14 10:00:02  [Srv: room-b #2]  yo\n\n"
               "=== WHAT THE BOT DID (1) ===\n"
               "2026-09-14 10:00:03  <skipped>  x\n")
        _write(os.path.join(self.root, "daily-audits", "review_queue.jsonl"),
               json.dumps({"date": "2026-09-11", "silent_drops": 2,
                           "possible_missed": 1, "failed_checks": []}) + "\n"
               + json.dumps({"date": DAY, "silent_drops": 11,
                             "possible_missed": 3, "failed_checks": []}) + "\n")
        _write(os.path.join(self.root, "HANDOFF.md"),
               "# H\n\n## Pending external setup and decisions\n"
               "1. First thing.\n2. DONE 9/1 — second thing.\n\n## Watch\n")
        self.summary = {"date": DAY, "status": "attention", "silent_drops": 11,
                        "possible_missed": 3, "coverage_warnings": 0,
                        "failed_checks": [],
                        "broker_sync": {"ok": True, "reconciled": True}}
        self.steps = [{"name": "JS test_a.js", "ok": True, "output": ""},
                      {"name": "JS test_b.js", "ok": False, "output": "boom"},
                      {"name": "Historical parser corpus gate", "ok": True,
                       "output": GATE},
                      {"name": "Python regression suite", "ok": False,
                       "output": TESTS}]


class TestStatus(StatusFixture):
    def test_fields_and_size(self):
        path = status_json.write(DAY, self.summary, self.steps)
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        self.assertLess(len(raw), 4000)
        d = json.loads(raw)
        self.assertEqual(d["date"], DAY)
        self.assertEqual(d["balance"], {"nlv": 1279.86, "day_pl": -333.85,
                                        "bp": 1279.86, "as_of": DAY})
        self.assertEqual(d["bot"], {"trades": 2, "pl": 21.0, "wins": 1, "losses": 1})
        self.assertEqual(d["rooms"]["discord"], {"on": 1, "spoke": 2, "reads": 3})
        self.assertEqual(d["rooms"]["whop"], {"on": 1, "spoke": None, "reads": None})
        self.assertEqual(d["audit"]["silent_drops"], 11)
        self.assertEqual(d["broke"][0]["date"], DAY)
        self.assertEqual(d["broke"][1]["date"], "2026-09-11")
        self.assertEqual(d["pending"], ["First thing."])
        v = d["verified"]
        self.assertEqual(v["tests"]["passed"], 247 + 1)
        self.assertEqual(v["tests"]["failed"], 1 + 1)
        self.assertEqual(v["parser_gate"]["counts"],
                         {"messages": 11386, "entries": 852, "actions": 3048,
                          "pass": True})
        self.assertIs(v["broker_reconciled"]["match"], True)
        self.assertTrue(v["bridge_code_live"]["at"])
        # Nothing is built in the fixture, so only the undated kinds appear
        # (MISSING lines are left out to keep the file small).
        self.assertTrue(all(" MISSING " not in ln for ln in d["reports"]))
        self.assertTrue(any(ln.startswith("scoreboard") for ln in d["reports"]))

    def test_hand_rebuild_keeps_the_recorded_checks(self):
        status_json.write(DAY, self.summary, self.steps)
        first = status_json.read()["verified"]
        # No fresh step output (a hand rebuild): the recorded tests and gate
        # stand, with their original timestamps — VERIFY ONCE.
        status_json.write(DAY, self.summary, [])
        again = status_json.read()["verified"]
        self.assertEqual(again["tests"], first["tests"])
        self.assertEqual(again["parser_gate"], first["parser_gate"])

    def test_balance_falls_back_to_the_last_read_before_the_day(self):
        d = status_json.build("2026-09-13", {}, [])
        self.assertEqual(d["balance"]["nlv"], 1600.0)
        self.assertEqual(d["bot"]["trades"], 1)
        d = status_json.build("2026-09-01", {}, [])
        self.assertIsNone(d["balance"]["nlv"])


if __name__ == "__main__":
    unittest.main()
