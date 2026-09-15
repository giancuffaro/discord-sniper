import unittest

from daily_policy_compare import _path_after


class DailyPolicyCompareTests(unittest.TestCase):
    def test_missing_timestamp_is_unavailable_not_day_wide(self):
        quotes = {"AAPL 100C": [(100.0, 1.0, 1.1), (200.0, 1.2, 1.3)]}
        self.assertEqual(_path_after(quotes, {"occ": "AAPL 100C", "ts": None}), [])

    def test_path_starts_at_source_event(self):
        quotes = {"AAPL 100C": [(100.0, 1.0, 1.1), (200.0, 1.2, 1.3)]}
        self.assertEqual(_path_after(quotes, {"occ": "AAPL 100C", "ts": 150.0}),
                         [(200.0, 1.2, 1.3)])


if __name__ == "__main__":
    unittest.main()
