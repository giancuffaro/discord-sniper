"""reports.py — weekly report files and the REUSE-DON'T-REBUILD cache.

Nothing here touches the real repo: every test points reports.HERE (and the
index) at a temp folder and registers its own throwaway kind whose builder
is a two-line script.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ds_logs                                              # noqa: E402
import reports                                              # noqa: E402

DAY = "2026-09-14"
D = dt.date(2026, 9, 14)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class DayBlocks(unittest.TestCase):
    def test_put_day_replaces_and_orders_newest_first(self):
        text = ds_logs.put_day("", D, "monday v1\n", ["# pre"], newest_first=True)
        text = ds_logs.put_day(text, dt.date(2026, 9, 15), "tuesday\n", ["# pre"],
                               newest_first=True)
        text = ds_logs.put_day(text, D, "monday v2\n", ["# pre"], newest_first=True)
        self.assertEqual(text.count("===== Mon Sep 14 2026 ====="), 1)
        self.assertLess(text.index("Tue Sep 15"), text.index("Mon Sep 14"))
        self.assertNotIn("monday v1", text)
        self.assertEqual(ds_logs.get_day(text, D), "monday v2\n")
        self.assertIsNone(ds_logs.get_day(text, dt.date(2026, 9, 16)))
        self.assertTrue(text.startswith("# pre\n"))
        self.assertEqual(text.count("# pre"), 1)

    def test_weekly_file_name_matches_ds_logs_style(self):
        self.assertEqual(ds_logs.weekly_file("REPORT", D, "md"),
                         "REPORT week-of-Sep-14-to-Sep-20-2026.md")
        self.assertEqual(ds_logs.weekly_file("AUDIT", dt.date(2026, 9, 11), "txt"),
                         "AUDIT week-of-Sep-7-to-Sep-13-2026.txt")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="reports-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        saved = (reports.HERE, reports.INDEX, dict(reports.KINDS))
        reports.HERE = self.root
        reports.INDEX = os.path.join(self.root, "reports", "INDEX.json")
        # A throwaway kind: reads in.txt, writes its day block.
        _write(os.path.join(self.root, "mk.py"),
               "import os, sys\n"
               "sys.path.insert(0, %r)\n"
               "import reports\n"
               "reports.HERE = %r\n"
               "reports.KINDS['t'] = reports.Kind('t', 'T', 'daily-reports', 'md')\n"
               "day = sys.argv[1]\n"
               "body = open(os.path.join(reports.HERE, 'in.txt')).read()\n"
               "reports.write_day('t', day, '# T %%s\\n%%s' %% (day, body))\n"
               % (os.path.dirname(os.path.abspath(reports.__file__)), self.root))
        reports.KINDS["t"] = reports.Kind(
            "t", "T", "daily-reports", "md", "mk.py",
            ("f:in.txt", "dated:trades.log", "block:u"), csv_name="T.csv")
        reports.KINDS["u"] = reports.Kind("u", "U", "daily-reports", "md")
        _write(os.path.join(self.root, "in.txt"), "one\n")
        _write(os.path.join(self.root, "trades.log"),
               "2026-09-14T10:00:00-04:00\tFILLED x\n"
               "2026-09-15T10:00:00-04:00\tFILLED y\n")

        def restore():
            reports.HERE, reports.INDEX = saved[0], saved[1]
            reports.KINDS.clear()
            reports.KINDS.update(saved[2])
        self.addCleanup(restore)


class WeeklyIO(Fixture):
    def test_write_day_lands_in_the_week_file_and_day_text_reads_it_back(self):
        p = reports.write_day("t", DAY, "hello\n")
        self.assertEqual(os.path.basename(p), "T week-of-Sep-14-to-Sep-20-2026.md")
        self.assertEqual(reports.day_text("t", DAY), "hello\n")
        reports.write_day("t", "2026-09-16", "wed\n")
        reports.write_day("t", DAY, "hello again\n")
        self.assertEqual(reports.days_in("t", DAY), ["2026-09-16", DAY])
        self.assertEqual(reports.day_text("t", DAY), "hello again\n")
        self.assertIsNone(reports.day_text("t", "2026-09-17"))
        # Another week is another file.
        reports.write_day("t", "2026-09-21", "next\n")
        self.assertTrue(os.path.exists(os.path.join(
            self.root, "daily-reports", "T week-of-Sep-21-to-Sep-27-2026.md")))

    def test_csv_rows_replace_by_date(self):
        fields = ["a", "b"]
        reports.write_csv_rows("t", DAY, fields, [{"a": "1", "b": "x"}])
        reports.write_csv_rows("t", "2026-09-15", fields, [{"a": "2", "b": "y"}])
        reports.write_csv_rows("t", DAY, fields, [{"a": "3", "b": "z"},
                                                  {"a": "4", "b": "w"}])
        with open(os.path.join(self.root, "daily-reports", "T.csv"),
                  encoding="utf-8") as fh:
            head = fh.readline().strip()
        self.assertEqual(head, "date,a,b")
        self.assertEqual([r["a"] for r in reports.csv_rows("t", DAY)], ["3", "4"])
        self.assertEqual([r["a"] for r in reports.csv_rows("t", "2026-09-15")], ["2"])
        self.assertEqual(reports.csv_rows("t", "2026-09-16"), [])
        self.assertIsNone(reports.csv_rows("u", DAY))     # kind has no csv


class Cache(Fixture):
    def test_build_then_current_then_stale_on_input_change(self):
        state, why, _ = reports.check("t", DAY)
        self.assertEqual(state, "missing")
        res = reports.build("t", DAY, quiet=True)
        self.assertEqual(res["status"], "built", res["output"])
        self.assertIn("one", reports.day_text("t", DAY))
        self.assertEqual(reports.check("t", DAY)[0], "current")
        res = reports.build("t", DAY, quiet=True)
        self.assertEqual(res["status"], "current")
        # The input moves: stale, names the input, rebuilds.
        time.sleep(1.1)
        _write(os.path.join(self.root, "in.txt"), "two\n")
        state, why, _ = reports.check("t", DAY)
        self.assertEqual(state, "stale")
        self.assertIn("in.txt", why)
        self.assertNotIn("trades.log", why)
        res = reports.build("t", DAY, quiet=True)
        self.assertEqual(res["status"], "built")
        self.assertIn("two", reports.day_text("t", DAY))
        self.assertEqual(reports.check("t", DAY)[0], "current")

    def test_another_days_lines_do_not_stale_this_day(self):
        reports.build("t", DAY, quiet=True)
        with open(os.path.join(self.root, "trades.log"), "a") as fh:
            fh.write("2026-09-16T10:00:00-04:00\tFILLED z\n")
        self.assertEqual(reports.check("t", DAY)[0], "current")
        with open(os.path.join(self.root, "trades.log"), "a") as fh:
            fh.write("2026-09-14T15:00:00-04:00\tFILLED late\n")
        state, why, _ = reports.check("t", DAY)
        self.assertEqual(state, "stale")
        self.assertIn("trades.log (day lines)", why)

    def test_another_reports_day_block_is_an_input(self):
        reports.build("t", DAY, quiet=True)
        reports.write_day("u", "2026-09-15", "other day\n")
        self.assertEqual(reports.check("t", DAY)[0], "current")
        reports.write_day("u", DAY, "same day\n")
        state, why, _ = reports.check("t", DAY)
        self.assertEqual(state, "stale")
        self.assertIn("U week-of", why)

    def test_manual_kind_is_reported_not_built(self):
        self.assertEqual(reports.check("u", DAY)[0], "missing")
        reports.write_day("u", DAY, "by hand\n")
        self.assertEqual(reports.check("u", DAY)[0], "manual")
        self.assertEqual(reports.build("u", DAY, quiet=True)["status"], "manual")

    def test_force_rebuilds_and_status_lines_say_why(self):
        reports.build("t", DAY, quiet=True)
        self.assertEqual(reports.build("t", DAY, force=True, quiet=True)["status"],
                         "built")
        lines = [ln for ln in reports.status_lines(DAY) if ln.startswith("t ")]
        self.assertEqual(len(lines), 1)
        self.assertIn("CURRENT", lines[0])
        self.assertIn("T week-of-Sep-14-to-Sep-20-2026.md", lines[0])

    def test_a_failed_build_records_nothing(self):
        _write(os.path.join(self.root, "mk.py"), "import sys\nsys.exit(3)\n")
        res = reports.build("t", DAY, quiet=True)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(reports.load_index(), {})


class Registry(unittest.TestCase):
    def test_every_audit_kind_has_a_script_and_a_weekly_home(self):
        for name in reports.BUILD_ORDER + ("audit",):
            k = reports.KINDS[name]
            self.assertTrue(k.script, name)
            self.assertTrue(os.path.exists(os.path.join(
                os.path.dirname(os.path.abspath(reports.__file__)), k.script)), name)
            self.assertIn("week-of-Sep-14-to-Sep-20-2026", k.rel_path(DAY))
        self.assertEqual(reports.KINDS["caller-outcomes"].csv_name,
                         "CALLER-OUTCOMES.csv")
        self.assertEqual(reports.KINDS["scoreboard"].rel_path(DAY), "SCOREBOARD.html")


if __name__ == "__main__":
    unittest.main()
