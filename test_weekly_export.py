"""ONE FILE PER WEEK PER LANE — the exports' naming, delta and day blocks.

G, 9/15: "signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt", week
starts Monday, each day appended under its own header, a new week starts a new
file. The export is CUMULATIVE — every pass re-writes the whole retained
backlog — so a day's block holds only what the earlier days of that file do
not already hold, and a re-export of the same day REPLACES its block instead
of stacking a second header.
"""
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import ds_logs
import reader_history

HERE = Path(__file__).resolve().parent


def export(day, raw=(), did=(), state="v1"):
    """One export file body, the shape extension/background.js writes."""
    return ("Discord Sniper — self-learning export (%s, refreshed %s 23:45:00 ET)\n\n"
            "=== CURRENT STATE (as of %s 23:45:00 ET) ===\n  version:        %s\n\n"
            "=== RAW MESSAGES THE READER SAW (%d) ===\n%s\n\n"
            "=== LIVE PARSER INPUTS (0) ===\n\n\n"
            "=== WHAT THE BOT DID (%d) ===\n%s\n"
            % (day, day, day, state, len(raw), "\n".join(raw), len(did), "\n".join(did)))


def msg(at, cid, text, mid="legacy-unknown"):
    return "%s  [Example #%s message_id=%s]  Alice: %s" % (at, cid, mid, text)


class WeekNaming(unittest.TestCase):
    def test_week_runs_monday_to_sunday(self):
        # 2026-09-14 is a Monday; his example names that week.
        self.assertEqual(ds_logs.week_tag(date(2026, 9, 14)),
                         "week-of-Sep-14-to-Sep-20-2026")
        for d in range(14, 21):
            self.assertEqual(ds_logs.week_tag(date(2026, 9, d)),
                             "week-of-Sep-14-to-Sep-20-2026")
        # Sunday 9/13 belongs to the week BEFORE, not to Monday 9/14's.
        self.assertEqual(ds_logs.week_tag(date(2026, 9, 13)),
                         "week-of-Sep-7-to-Sep-13-2026")

    def test_single_digit_day_is_not_zero_padded(self):
        self.assertEqual(ds_logs.week_tag(date(2026, 9, 1)),
                         "week-of-Aug-31-to-Sep-6-2026")
        self.assertEqual(ds_logs.week_tag(date(2026, 6, 3)),
                         "week-of-Jun-1-to-Jun-7-2026")

    def test_year_boundary_carries_both_years(self):
        # A week that straddles New Year can never be read two ways.
        self.assertEqual(ds_logs.week_tag(date(2025, 12, 31)),
                         "week-of-Dec-29-2025-to-Jan-4-2026")
        self.assertEqual(ds_logs.week_tag(date(2026, 1, 4)),
                         "week-of-Dec-29-2025-to-Jan-4-2026")
        # The Monday of the next week starts a new file.
        self.assertEqual(ds_logs.week_tag(date(2026, 1, 5)),
                         "week-of-Jan-5-to-Jan-11-2026")

    def test_file_name_and_day_header(self):
        self.assertEqual(ds_logs.weekly_name(date(2026, 9, 14), "discord"),
                         "signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt")
        self.assertEqual(ds_logs.weekly_name(date(2026, 9, 17), "whop"),
                         "signal-room-chat week-of-Sep-14-to-Sep-20-2026 (whop).txt")
        self.assertEqual(ds_logs.day_header(date(2026, 9, 14)),
                         "===== Mon Sep 14 2026 =====")
        self.assertEqual(ds_logs.parse_day_header("===== Mon Sep 14 2026 ====="),
                         date(2026, 9, 14))
        self.assertIsNone(ds_logs.parse_day_header("=== RAW MESSAGES (3) ==="))

    def test_name_round_trips(self):
        for d in (date(2026, 9, 14), date(2025, 12, 31), date(2026, 1, 5)):
            name = ds_logs.weekly_name(d, "discord")
            start, end, lane = ds_logs.week_of_name(name)
            self.assertEqual((start, end), ds_logs.week_bounds(d))
            self.assertEqual(lane, "discord")
        self.assertIsNone(ds_logs.week_of_name("signal-room-chat Sep-9-2026.txt"))
        self.assertEqual(ds_logs.day_of_name("signal-room-chat Sep-9-2026.txt"),
                         "2026-09-09")

    def test_the_extension_names_the_week_the_same_way(self):
        """background.js and ds_logs must never drift on the week name."""
        js = (HERE / "extension" / "background.js").read_text(encoding="utf-8")
        block = js[js.index('  const MON3 = ["Jan"'):
                   js.index("  })();", js.index("const weekTag")) + len("  })();")]
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "wk.js"
            probe.write_text("let day = process.argv[2];\n" + block +
                             "\nconsole.log(weekTag);\n", encoding="utf-8")
            day = date(2025, 12, 20)
            while day <= date(2027, 1, 20):
                got = subprocess.run(["node", str(probe), day.isoformat()],
                                     capture_output=True, text=True).stdout.strip()
                self.assertEqual(got, ds_logs.week_tag(day), day.isoformat())
                day += timedelta(days=1)

    def test_the_extension_posts_the_day_and_names_the_week(self):
        js = (HERE / "extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn('const fname = "signal-room-chat " + weekTag + " (" + lane + ").txt";', js)
        self.assertIn("name: fname, text: text, day: day, lane: lane", js)
        self.assertNotIn("fileDay", js)


class DayBlocks(unittest.TestCase):
    def test_a_later_day_writes_only_what_is_new(self):
        mon, tue = date(2026, 9, 14), date(2026, 9, 15)
        a = msg("2026-09-14 09:30:00", "123", "SPY 500C", "111")
        b = msg("2026-09-14 09:31:00", "123", "QQQ 400C", "222")
        c = msg("2026-09-15 09:30:00", "123", "IWM 200C", "333")
        text, _ = ds_logs.merge_day("", mon, export(
            "2026-09-14", [a, b], ["2026-09-14 09:30:01  <sent>  OPEN SPY"]), "discord")
        # Tuesday's export still carries Monday's backlog. It must not repeat.
        text, stats = ds_logs.merge_day(
            text, tue, export("2026-09-15", [a, b, c],
                              ["2026-09-14 09:30:01  <sent>  OPEN SPY",
                               "2026-09-15 09:30:01  <sent>  OPEN IWM"]), "discord")
        self.assertEqual(stats["2026-09-15"]["raw"], 2)
        self.assertEqual(stats["2026-09-15"]["did"], 1)
        blocks = dict(ds_logs.split_day_blocks(text))
        self.assertEqual(len(blocks), 2)
        self.assertIn(a, "\n".join(blocks[mon]))
        self.assertNotIn(a, "\n".join(blocks[tue]))
        self.assertIn(c, "\n".join(blocks[tue]))
        # Nothing is lost: every line is still in the file exactly once.
        for line in (a, b, c):
            self.assertEqual(text.count(line), 1)
        # The header count is the count of what is in THAT block.
        self.assertIn("=== RAW MESSAGES THE READER SAW (1) ===", "\n".join(blocks[tue]))

    def test_an_edited_message_keeps_both_versions(self):
        mon = date(2026, 9, 14)
        first = msg("2026-09-14 09:30:00", "123", "SPY 500C", "111")
        edited = msg("2026-09-14 09:30:00", "123", "SPY 505C", "111")
        text, _ = ds_logs.merge_day("", mon, export("2026-09-14", [first]), "discord")
        text, _ = ds_logs.merge_day(text, date(2026, 9, 15),
                                    export("2026-09-15", [first, edited]), "discord")
        self.assertIn("SPY 500C", text)
        self.assertIn("SPY 505C", text)

    def test_re_exporting_the_same_day_replaces_its_block(self):
        mon = date(2026, 9, 14)
        a = msg("2026-09-14 09:30:00", "123", "SPY 500C", "111")
        b = msg("2026-09-14 10:00:00", "123", "QQQ 400C", "222")
        text, _ = ds_logs.merge_day("", mon, export("2026-09-14", [a], state="v1"), "discord")
        text, _ = ds_logs.merge_day(text, mon, export("2026-09-14", [a, b], state="v2"), "discord")
        self.assertEqual(text.count("===== Mon Sep 14 2026 ====="), 1)
        self.assertEqual(text.count(a), 1)
        self.assertEqual(text.count(b), 1)
        # The day's CURRENT STATE is the latest one, not the first.
        self.assertIn("version:        v2", text)
        self.assertNotIn("version:        v1", text)
        # And it is idempotent: exporting it a third time changes nothing.
        again, _ = ds_logs.merge_day(text, mon, export("2026-09-14", [a, b], state="v2"), "discord")
        self.assertEqual(again, text)

    def test_a_restarted_extension_resending_everything_costs_nothing(self):
        mon, tue = date(2026, 9, 14), date(2026, 9, 15)
        a = msg("2026-09-14 09:30:00", "123", "SPY 500C", "111")
        c = msg("2026-09-15 09:30:00", "123", "IWM 200C", "333")
        text, _ = ds_logs.merge_day("", mon, export("2026-09-14", [a]), "discord")
        text, _ = ds_logs.merge_day(text, tue, export("2026-09-15", [c]), "discord")
        full, stats = ds_logs.merge_day(text, tue, export("2026-09-15", [a, c]), "discord")
        self.assertEqual(stats["2026-09-15"]["raw"], 1)   # the resent 'a' is dropped
        self.assertEqual(full.count(a), 1)
        self.assertEqual(full.count(c), 1)

    def test_a_raw_line_never_suppresses_its_live_parser_twin(self):
        """LIVE PARSER INPUTS is a second view of a RAW message, not a copy."""
        line = msg("2026-09-14 09:30:00", "123", "SPY 500C", "111")
        body = ("=== RAW MESSAGES THE READER SAW (1) ===\n" + line +
                "\n\n=== LIVE PARSER INPUTS (1) ===\n" + line + "\n")
        text, stats = ds_logs.merge_day("", date(2026, 9, 14), body, "discord")
        self.assertEqual(stats["2026-09-14"].get("parser", 0), 0)
        self.assertEqual(text.count(line), 2)

    def test_a_new_week_is_a_new_file(self):
        sun, mon = date(2026, 9, 13), date(2026, 9, 14)
        self.assertNotEqual(ds_logs.weekly_name(sun, "discord"),
                            ds_logs.weekly_name(mon, "discord"))
        a = msg("2026-09-13 09:30:00", "123", "SPY 500C", "111")
        b = msg("2026-09-14 09:30:00", "123", "QQQ 400C", "222")
        # Sunday's backlog rides along into Monday's export, but Monday is a
        # different FILE, so it is written there in full rather than dropped.
        last, _ = ds_logs.merge_day("", sun, export("2026-09-13", [a]), "discord")
        new, stats = ds_logs.merge_day("", mon, export("2026-09-14", [a, b]), "discord")
        self.assertEqual(stats["2026-09-14"]["raw"], 2)
        self.assertIn(a, new)
        self.assertIn(a, last)


class ReadersFindTheDays(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "DS Logs").mkdir()
        (self.root / "extension").mkdir()
        (self.root / "extension" / "rooms.txt").write_text(
            "123|https://discord.com/channels/1/123|Example|Group|on\n",
            encoding="utf-8")
        self.mon, self.tue = date(2026, 9, 14), date(2026, 9, 15)
        self.a = msg("2026-09-14 09:30:00", "123", "SPY 500C", "111")
        self.b = msg("2026-09-15 09:30:00", "123", "IWM 200C", "222")

    def _write_weekly(self):
        text, _ = ds_logs.merge_day("", self.mon, export("2026-09-14", [self.a]), "discord")
        text, _ = ds_logs.merge_day(text, self.tue,
                                    export("2026-09-15", [self.a, self.b]), "discord")
        p = self.root / "DS Logs" / ds_logs.weekly_name(self.mon, "discord")
        p.write_text(text, encoding="utf-8")
        return p

    def _write_dailies(self):
        for d, raw in (("Sep-14-2026", [self.a]), ("Sep-15-2026", [self.a, self.b])):
            (self.root / "DS Logs" / ("signal-room-chat %s (discord).txt" % d)).write_text(
                export("2026-09-%s" % d.split("-")[1], raw), encoding="utf-8")

    def test_days_come_from_the_headers_not_the_file_name(self):
        p = self._write_weekly()
        self.assertEqual(ds_logs.days_covered(p), {"2026-09-14", "2026-09-15"})
        self.assertEqual(ds_logs.all_days(self.root), ["2026-09-14", "2026-09-15"])
        self.assertEqual(ds_logs.files_for_day(self.root, "2026-09-15"), [str(p)])
        self.assertEqual(ds_logs.files_for_day(self.root, "2026-09-16"), [])

    def test_a_legacy_daily_is_still_found_by_name(self):
        (self.root / "DS Logs" / "signal-room-chat Sep-9-2026.txt").write_text(
            export("2026-09-09", [msg("2026-09-09 09:30:00", "123", "OLD")]),
            encoding="utf-8")
        self._write_weekly()
        self.assertEqual(ds_logs.all_days(self.root),
                         ["2026-09-09", "2026-09-14", "2026-09-15"])
        self.assertTrue(ds_logs.files_for_day(self.root, "2026-09-09")[0]
                        .endswith("Sep-9-2026.txt"))

    def test_reader_history_reads_the_same_messages_it_read_from_the_dailies(self):
        self._write_dailies()
        was, _ = reader_history.load(self.root, "2026-09-01", "2026-09-30")
        for f in (self.root / "DS Logs").glob("signal-room-chat *(discord).txt"):
            f.unlink()
        self._write_weekly()
        now, _ = reader_history.load(self.root, "2026-09-01", "2026-09-30")

        def key(rows):
            return sorted((r["at"], r["channelId"], r["author"], r["text"])
                          for r in rows)

        self.assertEqual(key(now), key(was))
        self.assertEqual(len(now), 2)


if __name__ == "__main__":
    unittest.main()
