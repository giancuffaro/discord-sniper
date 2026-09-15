"""market_hours.py — the holiday table warns before it lapses and shouts once
it has. Dates are monkeypatched; nothing here reads the clock or the network."""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_brief                                          # noqa: E402
import market_hours                                         # noqa: E402
import status_json                                          # noqa: E402

END = market_hours.HOLIDAYS_THROUGH


def _at(year, month, day):
    return dt.datetime(year, month, day, 10, 0)


class HolidayTableFlag(unittest.TestCase):
    def test_covered_year_is_clean(self):
        self.assertIsNone(market_hours.holiday_table_flag(_at(END - 1, 9, 15)))
        self.assertIsNone(market_hours.holiday_table_line(_at(END - 1, 9, 15)))
        self.assertIsNone(market_hours.holiday_table_flag(_at(END, 10, 1)))

    def test_last_sixty_days_say_expiring(self):
        self.assertEqual(market_hours.holiday_table_flag(_at(END, 11, 2)),
                         "holiday_table_expiring")
        self.assertEqual(market_hours.holiday_table_flag(_at(END, 12, 31)),
                         "holiday_table_expiring")
        self.assertIn("runs out on %d-12-31" % END,
                      market_hours.holiday_table_line(_at(END, 12, 1)))

    def test_past_the_table_says_stale(self):
        self.assertEqual(market_hours.holiday_table_flag(_at(END + 1, 1, 2)),
                         "holiday_table_stale")
        self.assertIn("through %d" % END,
                      market_hours.holiday_table_line(_at(END + 1, 1, 2)))

    def test_status_carries_the_flag(self):
        with mock.patch.object(market_hours, "_now",
                               return_value=_at(END + 1, 3, 1)):
            self.assertEqual(market_hours.status()["holiday_table_flag"],
                             "holiday_table_stale")
        with mock.patch.object(market_hours, "_now",
                               return_value=_at(END - 1, 3, 1)):
            self.assertIsNone(market_hours.status()["holiday_table_flag"])

    def test_the_table_has_no_invented_years(self):
        self.assertEqual(max(market_hours.FULL_CLOSE), END)
        self.assertEqual(max(market_hours.HALF_DAY), END)


class Surfaced(unittest.TestCase):
    def test_status_json_broke_list_leads_with_it(self):
        with mock.patch.object(market_hours, "_now",
                               return_value=_at(END + 1, 1, 5)):
            items = status_json.broke("%d-01-05" % (END + 1), {})
        self.assertTrue(items)
        self.assertEqual(items[0]["holiday_table"], "holiday_table_stale")
        self.assertIn("HOLIDAY TABLE", items[0]["note"])

    def test_status_json_is_quiet_while_covered(self):
        with mock.patch.object(market_hours, "_now",
                               return_value=_at(END - 1, 9, 15)):
            items = status_json.broke("%d-09-15" % (END - 1), {})
        self.assertFalse([i for i in items if "holiday_table" in i])

    def test_daily_brief_what_broke_shows_it(self):
        with mock.patch.object(market_hours, "_now",
                               return_value=_at(END, 12, 15)):
            line = daily_brief._holiday_table_fault()
        self.assertTrue(line.startswith("- HOLIDAY TABLE"))
        with mock.patch.object(market_hours, "_now",
                               return_value=_at(END - 1, 9, 15)):
            self.assertIsNone(daily_brief._holiday_table_fault())


if __name__ == "__main__":
    unittest.main()
