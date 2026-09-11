import os
import tempfile
import unittest

from daily_audit import summarize_replay
import replay_check
from replay_check import find_missed_entries


class DailyAuditTests(unittest.TestCase):
    def test_load_keeps_raw_messages_when_live_parser_is_partial(self):
        content = """=== RAW MESSAGES ===
2026-09-11 09:31:00  [Morning #1]  OPEN AAPL 100C @ 1.00
2026-09-11 09:32:00  [Second #2]  OPEN MSFT 200C @ 2.00
=== LIVE PARSER ===
2026-09-11 09:31:00  [Morning #1]  OPEN AAPL 100C @ 1.00
=== DECISIONS ===
2026-09-11 09:31:01  [Morning #1]  SENT AAPL 100C
"""
        old_day = replay_check.DAY
        path = None
        try:
            replay_check.DAY = "2026-09-11"
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False, suffix=".txt"
            ) as handle:
                handle.write(content)
                path = handle.name
            messages, decisions = replay_check.load(path)
            self.assertEqual({m[1] for m in messages}, {"Morning", "Second"})
            self.assertEqual(len(messages), 2)
            self.assertEqual(len(decisions), 1)
        finally:
            replay_check.DAY = old_day
            if path and os.path.exists(path):
                os.unlink(path)

    def test_summary_counts_failures_and_coverage(self):
        text = """COVERAGE WARNING: discord empty
TOTAL silent drops: 2  (actionable)
POSSIBLE MISSED ENTRIES: 3
"""
        self.assertEqual(summarize_replay(text), {
            "silent_drops": 2,
            "possible_missed": 3,
            "coverage_warnings": 1,
        })

    def test_clean_replay_is_zero(self):
        self.assertEqual(summarize_replay(
            "TOTAL silent drops: 0\nPOSSIBLE MISSED ENTRIES: 0\n"), {
                "silent_drops": 0,
                "possible_missed": 0,
                "coverage_warnings": 0,
            })

    def test_unresolved_loaded_fill_is_reported(self):
        keep = [
            ("10:00:00", "Midas", "1", "Midas: Loaded AAPL 335c 0days"),
            ("10:01:00", "Midas", "1", "Midas: 1.46 on starters @here"),
        ]
        parsed = [
            {"action": "PREPARE", "symbol": "AAPL", "strike": 335,
             "side": "CALLS"},
            {"action": "OPEN", "needs_loaded": True, "limit": 1.46},
        ]
        flags = find_missed_entries(keep, parsed,
                                    [("10:01:00", "skipped",
                                      "POSSIBLE MISSED ENTRY 1.46 on starters")], [])
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0][3:6], ("AAPL", 335, "CALLS"))

    def test_production_loaded_fill_shape_is_reported(self):
        keep = [
            ("10:00:00", "Midas", "1", "Midas: Loaded AAPL 335c 0days"),
            ("10:01:00", "Midas", "1", "Midas: 1.46 on starters @here"),
        ]
        parsed = [
            {"action": "PREPARE", "symbol": "AAPL", "strike": 335,
             "side": "CALLS"},
            {"action": "OPEN", "symbol": None, "limit": 1.46,
             "matched": "fill confirmation on a loaded contract"},
        ]
        flags = find_missed_entries(keep, parsed, [], [])
        self.assertEqual(len(flags), 1)


if __name__ == "__main__":
    unittest.main()
