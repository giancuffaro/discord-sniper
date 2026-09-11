import datetime
import csv
import os
import tempfile
import unittest
from unittest import mock

import announcer
import build_alerts
import option_tape_pull
import positions
import pullback
import ratchet_backtest
import ratchet_sweep
import ratchet_sweep_fine
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

    def test_alert_metadata_does_not_cross_expiries(self):
        with tempfile.TemporaryDirectory() as td:
            meta = os.path.join(td, "alert_meta.csv")
            with open(meta, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=[
                    "date", "symbol", "strike", "side", "expiry", "caller",
                    "room", "stage"])
                w.writeheader()
                w.writerow({"date": "2026-09-11", "symbol": "SPY",
                            "strike": "700", "side": "C",
                            "expiry": "2026-09-11", "caller": "alpha",
                            "room": "zero dte", "stage": "alert"})
                w.writerow({"date": "2026-09-11", "symbol": "SPY",
                            "strike": "700", "side": "C",
                            "expiry": "2026-09-18", "caller": "beta",
                            "room": "weekly", "stage": "alert"})
            rows = [{"date": "2026-09-11", "symbol": "SPY",
                     "strike": "700", "side": "C",
                     "expiry": "2026-09-18", "caller": "beta", "room": ""},
                    {"date": "2026-09-11", "symbol": "SPY",
                     "strike": "700", "side": "C",
                     "expiry": "2026-09-25", "caller": "", "room": ""}]
            with mock.patch.object(build_alerts, "META", meta):
                build_alerts._apply_meta(rows)
            self.assertEqual(rows[0]["room"], "weekly")
            self.assertEqual(rows[1]["room"], "")

    def test_incomplete_broker_is_rejected_for_execution(self):
        import broker

        class DataOnly:
            pass

        with mock.patch.dict(broker._REGISTRY, {"data": lambda _cfg: DataOnly()}):
            with self.assertRaises(Exception):
                broker.get_broker({"execution": {}}, "data",
                                  require_execution=True)

    def test_pullback_waits_for_fill_and_records_option_price(self):
        managed = []
        pb = pullback.Pullback(
            lambda _sym: 100.0,
            lambda _order: (True, "bid accepted"),
            lambda _order, _why: (True, "closed"),
            lambda _line: None,
            timeout_seconds=0.1, entry_poll_seconds=0.001,
            position_fn=lambda _order: {
                "state": "filled", "qty": 1, "fill": 1.25,
                "order_id": "entry-1", "sent_at": 10, "occ": "OCC"},
            fill_wait_seconds=0.1)
        pb._manage_exit = lambda *args: managed.append(args)
        order = {"symbol": "SPY", "side": "CALLS", "strike": 700,
                 "expiry": "2026-09-18", "trader": "room"}
        with mock.patch.object(pullback, "log_ledger") as ledger:
            pb._wait_entry(order, "SPY", "CALLS", 100.0, "arm-1")

        self.assertEqual(ledger.call_args_list[0].args[0], "submitted")
        self.assertEqual(ledger.call_args_list[1].args[0], "filled")
        self.assertEqual(ledger.call_args_list[1].args[3], 1.25)
        self.assertEqual(len(managed), 1)

    def test_tape_completion_uses_exact_window_marker(self):
        with tempfile.TemporaryDirectory() as td:
            coverage = os.path.join(td, "coverage.json")
            done = {("SPY260918C00700000", "2026-09-11", 10, 20)}
            with mock.patch.object(option_tape_pull, "COVERAGE_JSON", coverage):
                option_tape_pull.save_completed(done)
                self.assertEqual(option_tape_pull.completed_windows(), done)

    def test_ratchet_replays_gap_at_observed_bid(self):
        quotes = [(1, 0.50, 0.55)]
        self.assertEqual(ratchet_backtest.simulate(quotes, 1.00)[0], -50.0)
        trade = {"entry": 1.00, "quotes": quotes}
        self.assertEqual(ratchet_sweep.simulate_one(trade, 5, 3)[0], -50.0)
        self.assertEqual(ratchet_sweep_fine.sim(trade, 5, 3, 5)[0], -50.0)

    def test_old_watchdog_cannot_clear_new_generation(self):
        book = positions.Book(None, lambda _line: None)
        key = positions.key_of("room", "SPY", 700, "C", "2026-09-18")
        p = {"key": key, "state": positions.FILLED, "watching": False}
        book._pos[key] = p

        class Thread:
            def __init__(self, **kwargs):
                self.args = kwargs["args"]

            def start(self):
                return None

        with mock.patch.object(positions.threading, "Thread", Thread):
            self.assertTrue(book._start_watchdog_locked(key, p))
            self.assertEqual(p["watch_generation"], 1)
            p["watching"] = False
            self.assertTrue(book._start_watchdog_locked(key, p))
            self.assertEqual(p["watch_generation"], 2)

        book._retire_watchdog(key, 1)
        self.assertTrue(p["watching"])
        book._retire_watchdog(key, 2)
        self.assertFalse(p["watching"])

    def test_orphan_cleanup_only_cancels_bot_owned_order(self):
        class Broker:
            def __init__(self):
                self.cancelled = []

            def open_orders(self, _sym):
                return [
                    {"order_id": "owned", "action": "SELL",
                     "strike": 700, "side": "C", "expiry": "2026-09-18"},
                    {"order_id": "human", "action": "SELL",
                     "strike": 700, "side": "C", "expiry": "2026-09-18"},
                ]

            def cancel(self, oid):
                self.cancelled.append(oid)

            def order_status(self, _oid):
                return "dead", 0, None

        broker = Broker()
        book = positions.Book(broker, lambda _line: None)
        key = positions.key_of("room", "SPY", 700, "C", "2026-09-18")
        book._pos[key] = {"stop_order_id": "owned"}

        pulled = book._clear_orphans(
            broker, key, "SPY", 700, "C", "2026-09-18")
        self.assertEqual(pulled, 1)
        self.assertEqual(broker.cancelled, ["owned"])


if __name__ == "__main__":
    unittest.main()
