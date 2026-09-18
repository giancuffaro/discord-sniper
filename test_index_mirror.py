"""test_index_mirror.py — the index mirror is provably inert while it is off,
and provably a one-contract micro-futures order while it is on.

No broker, no network, no bridge: index_mirror only ever reads a settings dict
and rewrites an order dict. That is the whole point of it living in its own
file — the thing that decides whether real money buys an option or a future is
small enough to read in one sitting and to test exactly.
"""

import copy
import csv
import datetime as dt
import os
import tempfile
import unittest

import index_mirror

ET = index_mirror.ET
NOON = dt.datetime(2026, 9, 11, 12, 0, tzinfo=ET)       # inside 09:30-15:45

OFF = {"execution": {"index_mirror": {"enabled": False,
                                      "map": {"SPY": "MES", "QQQ": "MNQ"},
                                      "qty": 1}}}
QUOTES = tempfile.mkdtemp(prefix="nt_quotes_")
ON = {"execution": {"index_mirror": {"enabled": True,
                                     "map": {"SPY": "MES", "QQQ": "MNQ"},
                                     "qty": 1}},
      "futures_brokers": {"webull": False,
                          "ninjatrader": {"enabled": True, "quote_dir": QUOTES,
                                          "atm_templates": {"MES": "SNIPER-MES-LEVEL",
                                                            "MNQ": "SNIPER-MNQ-LEVEL"}}}}


def write_quote(root, last, when=NOON):
    """What SniperQuoteTape writes: the last price and when."""
    import json
    with open(os.path.join(QUOTES, "nt_quote_%s.json" % root), "w", encoding="utf-8") as fh:
        json.dump({"root": root, "last": last, "ts": when.timestamp()}, fh)


write_quote("ES", 7712.75)      # long: level 7700, limit 7702 (2 before)
write_quote("NQ", 24975.50)     # short: level 25000, limit at 25000


def spy_call(action="OPEN"):
    return {"action": action, "symbol": "SPY", "side": "CALLS", "strike": 655,
            "expiry": "2026-09-12", "limit": 3.10, "qty": 1, "kind": "option",
            "trader": "Brando", "room": "ELITE OPTIONS", "live": True,
            "coid": "abc123"}


def qqq_put():
    o = spy_call()
    o.update(symbol="QQQ", side="PUTS", strike=590)
    return o


class MirrorOffIsInert(unittest.TestCase):
    def test_live_activation_stays_blocked_without_a_broker_side_exit(self):
        self.assertFalse(index_mirror.live_exit_ready())
        self.assertFalse(index_mirror.live_exit_ready(OFF))
        webull = copy.deepcopy(ON)
        webull["futures_brokers"]["webull"] = True
        self.assertFalse(index_mirror.live_exit_ready(webull))
        bare = copy.deepcopy(ON)
        bare["futures_brokers"]["ninjatrader"]["atm_templates"] = {}
        self.assertFalse(index_mirror.live_exit_ready(bare))
        self.assertTrue(index_mirror.live_exit_ready(ON))
        self.assertTrue(index_mirror.live_exit_ready(ON, "MES"))
        self.assertFalse(index_mirror.live_exit_ready(ON, "M2K"))

    def test_new_york_clock_tracks_winter_offset(self):
        winter = dt.datetime(2026, 12, 1, 12, 0, tzinfo=ET)
        self.assertEqual(winter.utcoffset(), dt.timedelta(hours=-5))
    def test_spy_call_is_byte_for_byte_unchanged_when_off(self):
        order = spy_call()
        before = copy.deepcopy(order)
        self.assertFalse(index_mirror.convert(order, OFF, now=NOON))
        self.assertEqual(order, before)

    def test_missing_setting_entirely_is_also_off(self):
        order = spy_call()
        before = copy.deepcopy(order)
        self.assertFalse(index_mirror.convert(order, {}, now=NOON))
        self.assertEqual(order, before)

    def test_no_note_line_is_written_when_off(self):
        said = []
        index_mirror.convert(spy_call(), OFF, note=said.append, now=NOON)
        self.assertEqual(said, [])


class MirrorOnConverts(unittest.TestCase):
    def test_spy_call_becomes_a_long_mes(self):
        order = spy_call()
        self.assertTrue(index_mirror.convert(order, ON, now=NOON))
        self.assertEqual(order["symbol"], "MES")
        self.assertEqual(order["direction"], "LONG")
        self.assertEqual(order["kind"], "future")
        self.assertEqual(order["qty"], 1)
        # The LEVEL shape, from futures_mirror_daily.LEVEL: ES at 7712.75, long,
        # the 25 below is 7700, the limit rests 2 before it.
        from futures_mirror_daily import LEVEL, LEVEL_WAIT
        L = LEVEL["ES"]
        self.assertEqual(order["limit"], 7700 + L["buf"])
        self.assertEqual(order["their_stop"], order["limit"] - L["stop"])
        self.assertEqual(order["their_target"], order["limit"] + L["target"])
        self.assertEqual(order["level_ttl_s"], LEVEL_WAIT * 60)
        self.assertEqual(order["atm_template"], "SNIPER-MES-LEVEL")
        self.assertIsNone(order["strike"])
        self.assertIsNone(order["expiry"])
        self.assertFalse(order["swing"])

    def test_qqq_put_becomes_a_short_mnq(self):
        order = qqq_put()
        self.assertTrue(index_mirror.convert(order, ON, now=NOON))
        self.assertEqual(order["symbol"], "MNQ")
        self.assertEqual(order["direction"], "SHORT")
        self.assertEqual(order["kind"], "future")
        from futures_mirror_daily import LEVEL
        L = LEVEL["NQ"]
        self.assertEqual(order["limit"], 25000 - L["buf"])        # short: the 50 above
        self.assertEqual(order["their_stop"], order["limit"] + L["stop"])
        self.assertIsNone(order["their_target"])                 # MNQ runs on the trail
        self.assertEqual(order["atm_template"], "SNIPER-MNQ-LEVEL")

    def test_spy_put_is_short_mes_and_qqq_call_is_long_mnq(self):
        o = spy_call()
        o["side"] = "PUTS"
        index_mirror.convert(o, ON, now=NOON)
        self.assertEqual((o["symbol"], o["direction"]), ("MES", "SHORT"))
        o2 = qqq_put()
        o2["side"] = "CALLS"
        index_mirror.convert(o2, ON, now=NOON)
        self.assertEqual((o2["symbol"], o2["direction"]), ("MNQ", "LONG"))

    def test_a_stale_quote_blocks_the_order_instead_of_guessing(self):
        write_quote("ES", 7712.75, when=NOON - dt.timedelta(minutes=5))
        try:
            order = spy_call()
            said = []
            self.assertFalse(index_mirror.convert(order, ON, note=said.append, now=NOON))
            self.assertIn("not mirrored", order["mirror_block"])
            self.assertEqual(order["symbol"], "SPY")          # untouched
            self.assertEqual(order["limit"], 3.10)
            self.assertTrue(any("no fresh ES price" in m for m in said))
        finally:
            write_quote("ES", 7712.75)

    def test_already_past_the_level_takes_the_price_it_has(self):
        write_quote("ES", 7701.00)                            # long, level 7700, limit 7702 > price
        try:
            order = spy_call()
            self.assertTrue(index_mirror.convert(order, ON, now=NOON))
            self.assertEqual(order["limit"], 7701.00)
        finally:
            write_quote("ES", 7712.75)

    def test_the_room_toggle_and_caller_ride_through_untouched(self):
        order = spy_call()
        index_mirror.convert(order, ON, now=NOON)
        self.assertTrue(order["live"])
        self.assertEqual(order["trader"], "Brando")
        self.assertEqual(order["coid"], "abc123")

    def test_one_mirror_line_is_logged(self):
        said = []
        index_mirror.convert(spy_call(), ON, note=said.append, now=NOON)
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0].startswith("MIRROR"))
        self.assertIn("NOT bought", said[0])


class MirrorNeverTouchesAnythingElse(unittest.TestCase):
    def test_tsla_is_untouched_either_way(self):
        for cfg in (OFF, ON):
            order = spy_call()
            order.update(symbol="TSLA", strike=440)
            before = copy.deepcopy(order)
            self.assertFalse(index_mirror.convert(order, cfg, now=NOON))
            self.assertEqual(order, before)

    def test_close_and_trim_are_never_mirrored(self):
        for action in ("CLOSE", "TRIM", "ADD", "STOPMOVE", "RETRACT"):
            order = spy_call(action=action)
            before = copy.deepcopy(order)
            self.assertFalse(index_mirror.convert(order, ON, now=NOON))
            self.assertEqual(order, before)

    def test_a_real_futures_call_is_not_re_mirrored(self):
        order = {"action": "OPEN", "symbol": "MNQ", "kind": "future",
                 "direction": "SHORT", "limit": 24950, "side": ""}
        before = copy.deepcopy(order)
        self.assertFalse(index_mirror.convert(order, ON, now=NOON))
        self.assertEqual(order, before)

    def test_outside_the_measured_window_the_option_stands(self):
        for when in (dt.datetime(2026, 9, 11, 9, 29, tzinfo=ET),
                     dt.datetime(2026, 9, 11, 15, 46, tzinfo=ET),
                     dt.datetime(2026, 9, 11, 19, 5, tzinfo=ET)):
            order = spy_call()
            before = copy.deepcopy(order)
            self.assertFalse(index_mirror.convert(order, ON, now=when))
            self.assertEqual(order, before)


class ShadowRecord(unittest.TestCase):
    def _rows(self, path):
        with open(path, encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_a_row_is_written_while_the_switch_is_off(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "shadow.csv")
            index_mirror.record(spy_call(), "REFUSED not enough cash",
                                path=p, now=NOON)
            rows = self._rows(p)
            self.assertEqual(rows[0], index_mirror.SHADOW_HEADER)
            self.assertEqual(rows[1][3:6], ["SPY", "L", "MES"])
            self.assertEqual(rows[1][8], "3.1")
            self.assertIn("REFUSED", rows[1][9])

    def test_a_mirrored_order_is_still_recorded_under_its_own_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "shadow.csv")
            order = qqq_put()
            index_mirror.convert(order, ON, now=NOON)
            index_mirror.record(order, "futures order in", path=p, now=NOON)
            rows = self._rows(p)
            self.assertEqual(rows[1][3:6], ["QQQ", "S", "MNQ"])
            self.assertEqual(rows[1][8], "3.1")

    def test_appends_do_not_repeat_the_header(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "shadow.csv")
            for _ in range(3):
                index_mirror.record(spy_call(), "ok", path=p, now=NOON)
            self.assertEqual(len(self._rows(p)), 4)

    def test_tsla_and_exits_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "shadow.csv")
            tsla = spy_call()
            tsla["symbol"] = "TSLA"
            self.assertFalse(index_mirror.record(tsla, "ok", path=p, now=NOON))
            self.assertFalse(index_mirror.record(spy_call("CLOSE"), "ok",
                                                 path=p, now=NOON))
            self.assertFalse(os.path.exists(p))

    def test_an_unwritable_path_never_raises(self):
        self.assertFalse(index_mirror.record(
            spy_call(), "ok", path=os.path.join(os.sep, "no", "such", "dir",
                                                "x.csv"), now=NOON))


class BridgeWiring(unittest.TestCase):
    """The shipped settings file must have the switch, and it must be OFF."""

    def test_settings_json_ships_the_switch_off(self):
        import json
        here = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(here, "settings.json")
        if not os.path.exists(p):
            self.skipTest("settings.json is not on this machine")
        with open(p, encoding="utf-8") as f:
            im = (json.load(f).get("execution", {}).get("index_mirror") or {})
        self.assertIs(im.get("enabled"), False)
        self.assertEqual(im.get("map"), {"SPY": "MES", "QQQ": "MNQ"})

    def test_bridge_calls_convert_before_it_builds_the_book_key(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "bridge.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("index_mirror.convert(order, CFG, note)", src)
        self.assertIn("index_mirror.record(order,", src)
        self.assertLess(src.index("index_mirror.convert(order, CFG, note)"),
                        src.index("key = find_key(order) if BOOK is not None"))

    def test_the_mirror_runs_before_the_round_number_pullback(self):
        """SPY and QQQ are both in pullback.MANAGED, so a SPY entry near a
        round number would otherwise arm a stock-level wait. A mirrored order
        is MES/MNQ by then, which is not managed, so it goes straight out at
        market — which is the entry the replay measured. Locking the order of
        those two blocks here because nothing else would notice if it moved."""
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "bridge.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertLess(src.index("index_mirror.convert(order, CFG, note)"),
                        src.index("okp, msgp = pullback_manager().start(order)"))
        import pullback
        self.assertNotIn("MES", pullback.MANAGED)
        self.assertNotIn("MNQ", pullback.MANAGED)


if __name__ == "__main__":
    unittest.main()
