import unittest

from daily_audit import summarize_replay
from replay_check import find_missed_entries


class DailyAuditTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
