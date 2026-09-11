import datetime
import unittest
from unittest import mock

import announcer
import positions
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

    def test_claim_reduces_qty_when_stop_partially_filled(self):
        class Broker:
            def cancel(self, _oid):
                return True

            def order_status(self, _oid):
                return "dead", 1, 0.80

        broker = Broker()
        book = positions.Book(broker, lambda _line: None)
        key = positions.key_of("room", "SPY", 700, "C", "2026-09-18")
        book._pos[key] = {
            "key": key, "state": positions.FILLED, "closing": False,
            "symbol": "SPY", "side": "C", "strike": 700,
            "expiry": "2026-09-18", "qty": 3, "fill": 1.00,
            "cost": 300.0, "stop": 0.80, "stop_order_id": "stop-1",
            "live": True,
        }

        self.assertTrue(book.claim(key))
        self.assertEqual(book.qty_of(key), 2)
        self.assertEqual(book.info(key)["exits"][0]["qty"], 1)

    def test_take_profit_does_not_close_on_unfilled_acceptance(self):
        class Broker:
            def __init__(self):
                self.sent = 0

            def sell(self, *_args, **_kwargs):
                self.sent += 1
                return {"order_id": "sell-%d" % self.sent, "limit": 1.20}

            def order_status(self, _oid):
                return "dead", 0, None

            def cancel(self, _oid):
                return True

            def ask_bid(self, _occ):
                return 1.21, 1.20, {}

        broker = Broker()
        book = positions.Book(broker, lambda _line: None)
        book.take_profit_on = True
        book.take_profit_pct = 15
        key = positions.key_of("room", "QQQ", 600, "C", "2026-09-18")
        book._pos[key] = {
            "key": key, "state": positions.FILLED, "closing": False,
            "symbol": "QQQ", "side": "C", "strike": 600,
            "expiry": "2026-09-18", "qty": 1, "fill": 1.00,
            "cost": 100.0, "live": True, "stop_order_id": None,
        }

        self.assertFalse(book.auto_take_profit(key, 1.20))
        self.assertEqual(book.state_of(key), positions.FILLED)
        self.assertEqual(book.qty_of(key), 1)
        self.assertFalse(book.info(key).get("closing"))

    def test_failed_overnight_rearm_remains_pending(self):
        book = positions.Book(None, lambda _line: None)
        key = positions.key_of("room", "IWM", 300, "P", "2026-09-18")
        book._pos[key] = {
            "key": key, "state": positions.FILLED, "closing": False,
            "symbol": "IWM", "side": "P", "strike": 300,
            "expiry": "2026-09-18", "qty": 1, "fill": 1.00,
            "cost": 100.0, "swing": True, "stop_day": "",
        }
        book._arm_stop = lambda *_args, **_kwargs: None

        self.assertEqual(book.rearm_overnight_stops(), 0)
        self.assertTrue(book.overnight_stops_pending())
        book._pos[key]["no_auto_stop"] = True
        self.assertFalse(book.overnight_stops_pending())


if __name__ == "__main__":
    unittest.main()
