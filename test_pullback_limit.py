#!/usr/bin/env python3
"""The pullback entry's limit: cross the ask, NEVER above the caller's price.

G, 9/17: "even if it reaches the pullback and the price is more than the
caller we don't buy — we need to be at the same average or better than them."
9/16 is the case: Brett's AAPL 335C at 3.17, ask 3.45 at the touch, paid 3.40.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webull_options as wo                                # noqa: E402


class Quiet(wo.WebullOptions):
    def __init__(self):                 # no keys, no network — pricing only
        self.buffer_pct = 2.0


class TestPullbackLimit(unittest.TestCase):
    def setUp(self):
        self.wb = Quiet()

    def test_the_ask_ran_past_the_caller_so_we_rest_at_his_price(self):
        # AAPL is a Penny Program name: $0.05 ticks at $3 and over -> 3.15
        self.assertEqual(self.wb.pullback_limit(3.45, 3.17, "AAPL"), 3.15)

    def test_the_ask_is_under_the_caller_so_we_cross_it(self):
        self.assertEqual(self.wb.pullback_limit(2.69, 3.00, "TSLA"), 2.75)

    def test_no_caller_price_crosses_as_before(self):
        self.assertEqual(self.wb.pullback_limit(1.11, None, "QQQ"), 1.14)
        self.assertEqual(self.wb.pullback_limit(1.11, "", "QQQ"), 1.14)

    def test_rounding_never_lifts_us_over_the_caller(self):
        self.assertEqual(self.wb.pullback_limit(0.21, 0.18, "IWM"), 0.18)
        for ask, theirs, sym in ((3.45, 3.17, "AAPL"), (5.30, 5.22, "MSFT"),
                                 (1.27, 1.00, "QQQ"), (2.91, 2.66, "SPY")):
            self.assertLessEqual(self.wb.pullback_limit(ask, theirs, sym),
                                 theirs)

    def test_a_junk_caller_price_is_no_price(self):
        self.assertEqual(self.wb.pullback_limit(1.11, "n/a", "QQQ"), 1.14)


if __name__ == "__main__":
    unittest.main(verbosity=1)
