#!/usr/bin/env python3
"""trend.py on hand-drawn paths — G's own staircase first."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trend                                                # noqa: E402


def walk(points, step=0.05):
    """Straight lines between the points, one 1-minute bar per step."""
    bars, ts, px = [], 0, points[0]
    for target in points[1:]:
        n = max(1, int(round(abs(target - px) / step)))
        for i in range(1, n + 1):
            nxt = px + (target - px) * i / n
            prev = bars[-1][4] if bars else px
            bars.append((ts, prev, max(prev, nxt) + 0.02, min(prev, nxt) - 0.02, nxt))
            ts += 60
        px = target
    return bars


class TestTrend(unittest.TestCase):
    def test_his_spy_staircase_is_up(self):
        got = trend.read(walk([711, 712, 711.5, 712.5, 712, 713]))
        self.assertEqual(got["label"], "UP")
        self.assertGreater(got["highs"][-1], got["highs"][-2])
        self.assertGreater(got["lows"][-1], got["lows"][-2])

    def test_the_mirror_is_down(self):
        self.assertEqual(trend.read(walk([713, 712, 712.5, 711.5, 712, 711]))["label"], "DOWN")

    def test_a_range_is_chop(self):
        self.assertEqual(trend.read(walk([711, 712, 711, 712, 711, 712]))["label"], "CHOP")

    def test_one_push_is_not_yet_a_trend(self):
        self.assertEqual(trend.read(walk([711, 713]))["label"], "CHOP")

    def test_wiggles_smaller_than_the_reversal_are_not_swings(self):
        got = trend.read(walk([711, 711.1, 711.05, 711.15, 711.1, 711.2]))
        self.assertLessEqual(len(got["pivots"]), 2)

    def test_a_failed_high_ends_the_uptrend(self):
        got = trend.read(walk([711, 712, 711.5, 712.5, 712, 712.3, 711.4]))
        self.assertNotEqual(got["label"], "UP")

    def test_with_and_counter(self):
        self.assertEqual(trend.with_or_counter("UP", "CALLS"), "WITH")
        self.assertEqual(trend.with_or_counter("UP", "PUTS"), "COUNTER")
        self.assertEqual(trend.with_or_counter("DOWN", "P"), "WITH")
        self.assertEqual(trend.with_or_counter("CHOP", "CALLS"), "CHOP")

    def test_minute_bars_from_ticks(self):
        bars = trend.minute_bars([(0, 1.0), (30, 2.0), (59, 1.5), (60, 3.0)], 120)
        self.assertEqual(bars[0], (0, 1.0, 2.0, 1.0, 1.5))
        self.assertEqual(bars[1][1:], (3.0, 3.0, 3.0, 3.0))


if __name__ == "__main__":
    unittest.main(verbosity=1)
