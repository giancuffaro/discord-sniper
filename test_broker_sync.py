#!/usr/bin/env python3
"""broker_sync.py against a FAKE Webull client — no network, no credentials.

The point of these: the pull that did not exist until 9/15 must page to the
end, must stamp Eastern, must overwrite one file instead of piling up dated
ones, and must keep exactly one balance row per trading day.
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import broker_sync                                         # noqa: E402


def order(occ_symbol="QQQ", strike="704.00", kind="PUT", expiry="2026-09-14",
          side="BUY", status="FILLED", placed="2026-09-14T14:36:56.809Z",
          filled="2026-09-14T14:36:57.081Z", limit="1.13", stop=None,
          avg="1.13", coid="c0"):
    body = {"symbol": occ_symbol, "side": side, "status": status,
            "instrument_type": "OPTION", "client_order_id": coid,
            "filled_quantity": "1", "total_quantity": "1",
            "filled_price": avg, "time_in_force": "DAY",
            "place_time_at": placed, "filled_time_at": filled,
            "legs": [{"symbol": occ_symbol, "option_type": kind,
                      "option_expire_date": expiry, "strike_price": strike}]}
    if limit is not None:
        body["limit_price"] = limit
    if stop is not None:
        body["stop_price"] = stop
    return body


class FakeClient:
    """Answers order_history/account_snapshot; raises on anything that trades."""

    def __init__(self, pages=None, snapshot=None):
        self.pages = pages or [[order()]]
        self.snapshot = snapshot
        self.calls = []

    def order_history(self, start, end, page_size=100):
        self.calls.append(("order_history", start, end))
        return [o for page in self.pages for o in page]

    def account_snapshot(self):
        self.calls.append(("account_snapshot",))
        return self.snapshot

    def __getattr__(self, name):
        raise AssertionError("broker_sync must not call %s()" % name)


class SyncFixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sync-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        saved = (broker_sync.HERE, broker_sync.EXPORT, broker_sync.BALANCES)
        broker_sync.HERE = self.root
        broker_sync.EXPORT = os.path.join(self.root, "Webull_Orders_auto.csv")
        broker_sync.BALANCES = os.path.join(self.root, "balance_daily.csv")

        def restore():
            (broker_sync.HERE, broker_sync.EXPORT,
             broker_sync.BALANCES) = saved
        self.addCleanup(restore)

    def read_export(self):
        with open(broker_sync.EXPORT, encoding="utf-8", newline="") as fh:
            return list(csv.reader(fh))


class TestExportShape(SyncFixture):
    def test_occ_is_built_from_the_leg(self):
        rows = broker_sync.export_rows([order()])
        self.assertEqual(rows[0][0], "QQQ260914P00704000")

    def test_a_call_and_a_fractional_strike(self):
        rows = broker_sync.export_rows(
            [order(occ_symbol="TSLA", strike="357.5", kind="CALL",
                   expiry="2026-09-18")])
        self.assertEqual(rows[0][0], "TSLA260918C00357500")

    def test_utc_is_stamped_eastern(self):
        rows = broker_sync.export_rows([order()])
        self.assertEqual(rows[0][9], "2026-09-14 10:36:56")
        self.assertEqual(rows[0][10], "2026-09-14 10:36:57")

    def test_a_stop_leg_uses_its_stop_as_the_price(self):
        rows = broker_sync.export_rows([order(limit=None, stop="0.95")])
        self.assertEqual(rows[0][6], "0.95")

    def test_rows_with_no_contract_are_dropped_not_guessed(self):
        bad = order()
        bad["legs"] = [{"symbol": "QQQ"}]
        self.assertEqual(broker_sync.export_rows([bad]), [])

    def test_non_option_rows_are_skipped(self):
        stock = order()
        stock["instrument_type"] = "EQUITY"
        self.assertEqual(broker_sync.export_rows([stock]), [])

    def test_rows_come_out_in_placed_order(self):
        late = order(placed="2026-09-14T19:00:00.000Z", coid="c2")
        early = order(placed="2026-09-14T13:30:00.000Z", coid="c1")
        rows = broker_sync.export_rows([late, early])
        self.assertEqual([r[9] for r in rows],
                         ["2026-09-14 09:30:00", "2026-09-14 15:00:00"])

    def test_the_header_is_what_build_ledger_absorbs(self):
        broker_sync.write_export(broker_sync.export_rows([order()]))
        self.assertEqual(self.read_export()[0], broker_sync.EXPORT_HEAD)

    def test_the_export_is_overwritten_never_stacked(self):
        broker_sync.write_export(broker_sync.export_rows(
            [order(coid="a"), order(coid="b")]))
        self.assertEqual(len(self.read_export()), 3)
        broker_sync.write_export(broker_sync.export_rows([order(coid="c")]))
        self.assertEqual(len(self.read_export()), 2)
        self.assertEqual(len(os.listdir(self.root)), 1)


class TestBalanceRecord(SyncFixture):
    def test_one_row_per_day_and_a_rerun_replaces_it(self):
        broker_sync.record_balance("2026-09-14",
                                   {"nlv": 1279.86, "day_pl": -333.85,
                                    "bp": 1279.86})
        broker_sync.record_balance("2026-09-14",
                                   {"nlv": 1300.0, "day_pl": -300.0,
                                    "bp": 1300.0})
        with open(broker_sync.BALANCES, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["nlv"], "1300.00")

    def test_days_accumulate_and_stay_sorted(self):
        broker_sync.record_balance("2026-09-15", {"nlv": 1.0, "day_pl": 0.0,
                                                  "bp": 1.0})
        broker_sync.record_balance("2026-09-14", {"nlv": 2.0, "day_pl": 0.0,
                                                  "bp": 2.0})
        with open(broker_sync.BALANCES, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["date"] for r in rows],
                         ["2026-09-14", "2026-09-15"])

    def test_a_refused_balance_records_nothing(self):
        self.assertIsNone(broker_sync.record_balance("2026-09-14", None))
        self.assertFalse(os.path.exists(broker_sync.BALANCES))

    def test_a_partial_read_keeps_the_fields_it_got(self):
        broker_sync.record_balance("2026-09-14", {"nlv": None,
                                                  "day_pl": -10.0,
                                                  "bp": 500.0})
        got = broker_sync.latest_balance("2026-09-14")
        self.assertIsNone(got["nlv"])
        self.assertEqual(got["day_pl"], -10.0)
        self.assertEqual(got["bp"], 500.0)

    def test_latest_balance_with_no_file_is_none_not_a_crash(self):
        self.assertIsNone(broker_sync.latest_balance())
        self.assertIsNone(broker_sync.latest_balance("2026-09-14"))

    def test_latest_balance_for_a_day_we_have_no_row_for(self):
        broker_sync.record_balance("2026-09-11", {"nlv": 5.0, "day_pl": 1.0,
                                                  "bp": 5.0})
        self.assertIsNone(broker_sync.latest_balance("2026-09-14"))
        self.assertEqual(broker_sync.latest_balance()["date"], "2026-09-11")


class TestMainFlow(SyncFixture):
    def _patch(self, client, ledger_rows=7):
        broker_sync._settings = lambda: {"execution": {"webull": {}}}
        broker_sync._client = lambda _settings: client

        class FakeLedger:
            @staticmethod
            def build():
                return ([{}] * ledger_rows, [])

            @staticmethod
            def write(rows):
                FakeLedger.written = len(rows)
        sys.modules["build_ledger"] = FakeLedger
        self.addCleanup(sys.modules.pop, "build_ledger", None)
        return FakeLedger

    def test_the_whole_flow_writes_both_files_and_rebuilds(self):
        client = FakeClient(pages=[[order(coid="a"), order(coid="b")]],
                            snapshot={"nlv": 1279.86, "day_pl": -333.85,
                                      "bp": 1279.86})
        ledger = self._patch(client)
        self.assertEqual(broker_sync.main("2026-09-14"), 0)
        self.assertEqual(len(self.read_export()), 3)
        self.assertEqual(ledger.written, 7)
        self.assertEqual(broker_sync.latest_balance("2026-09-14")["nlv"],
                         1279.86)

    def test_it_asks_a_day_either_side(self):
        client = FakeClient()
        self._patch(client)
        broker_sync.main("2026-09-14")
        self.assertIn(("order_history", "2026-09-13", "2026-09-15"),
                      client.calls)

    def test_it_never_calls_anything_that_trades(self):
        client = FakeClient()
        self._patch(client)
        broker_sync.main("2026-09-14")
        self.assertEqual({c[0] for c in client.calls},
                         {"order_history", "account_snapshot"})

    def test_a_refused_balance_still_writes_the_export(self):
        client = FakeClient(snapshot=None)
        self._patch(client)
        self.assertEqual(broker_sync.main("2026-09-14"), 0)
        self.assertEqual(len(self.read_export()), 2)
        self.assertFalse(os.path.exists(broker_sync.BALANCES))

    def test_a_day_with_no_orders_writes_a_header_only_file(self):
        client = FakeClient(pages=[[]])
        self._patch(client)
        broker_sync.main("2026-09-14")
        self.assertEqual(self.read_export(), [broker_sync.EXPORT_HEAD])


if __name__ == "__main__":
    unittest.main(verbosity=2)
