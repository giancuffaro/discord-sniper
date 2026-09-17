#!/usr/bin/env python3
"""No round-number pullback entry arms before 10:00 Eastern (G, 9/17)."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge                                               # noqa: E402


def at(h, m):
    return dt.datetime(2026, 9, 17, h, m)


class TestTooEarly(unittest.TestCase):
    def setUp(self):
        self.saved = bridge.CFG.get("pullback")
        self.addCleanup(lambda: bridge.CFG.__setitem__("pullback", self.saved))

    def cfg(self, **kw):
        bridge.CFG["pullback"] = kw

    def test_nine_forty_is_skipped_and_says_why(self):
        self.cfg(no_entries_before="10:00")
        msg = bridge._pullback_too_early(at(9, 40))
        self.assertIn("before 10:00 ET", msg)
        self.assertIn("09:40", msg)

    def test_ten_sharp_and_later_arm(self):
        self.cfg(no_entries_before="10:00")
        self.assertEqual(bridge._pullback_too_early(at(10, 0)), "")
        self.assertEqual(bridge._pullback_too_early(at(14, 9)), "")

    def test_the_default_is_ten(self):
        self.cfg()
        self.assertTrue(bridge._pullback_too_early(at(9, 59)))

    def test_off_and_garbage_turn_it_off_never_guess(self):
        for value in ("off", "", "banana"):
            self.cfg(no_entries_before=value)
            self.assertEqual(bridge._pullback_too_early(at(9, 31)), "")

    def test_the_setting_moves_it(self):
        self.cfg(no_entries_before="09:45")
        self.assertTrue(bridge._pullback_too_early(at(9, 44)))
        self.assertEqual(bridge._pullback_too_early(at(9, 45)), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
