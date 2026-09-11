import unittest

from daily_audit import summarize_replay


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


if __name__ == "__main__":
    unittest.main()
