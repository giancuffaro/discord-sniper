import datetime
import unittest
from unittest import mock

import announcer
from build_ledger import _dedupe_key


class _Response:
    status_code = 200

    @staticmethod
    def json():
        return {"orders": []}


class _Broker:
    account_id = "acct-1"

    def _pace(self):
        return None


class AuditRegressionTests(unittest.TestCase):
    def tearDown(self):
        announcer._RO_WIN.clear()

    def test_cached_recent_orders_refreshes_date_window(self):
        calls = []

        def recent(account, start_date=None, end_date=None):
            calls.append((account, start_date, end_date))
            return _Response()

        announcer._RO_WIN["acct-1"] = (
            recent,
            ("acct-1",),
            {"start_date": "2026-01-01", "end_date": "2026-01-03"},
        )

        class Tomorrow(datetime.date):
            @classmethod
            def today(cls):
                return cls(2026, 9, 12)

        with mock.patch("datetime.date", Tomorrow):
            self.assertEqual(announcer._recent_orders(_Broker()), [])

        self.assertEqual(calls, [("acct-1", "2026-09-11", "2026-09-13")])

    def test_ledger_key_separates_accounts(self):
        common = {
            "who": "trader", "symbol": "SPY", "strike": 700,
            "side": "C", "expiry": "2026-09-18", "fill": 1.25,
        }
        live = dict(common, account_id="live-account")
        paper = dict(common, account_id="paper-account")
        self.assertNotEqual(_dedupe_key(live, "2026-09-11"),
                            _dedupe_key(paper, "2026-09-11"))


if __name__ == "__main__":
    unittest.main()
