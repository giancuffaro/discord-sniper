"""test_entry_slack.py — the crossing rule, at its boundaries, and the switch
that refuses to arm.

entry_slack decides whether real money crosses a spread, so it is tested the
way index_mirror is: no broker, no network, no bridge — a price in, a decision
out. The boundary cases are the whole point (an ask EXACTLY on the line, an
ask one tick over it), because a rule that is ambiguous at its edge is a rule
nobody can audit afterwards.
"""

import json
import os
import unittest

import entry_slack
from entry_slack import decide

HERE = os.path.dirname(os.path.abspath(__file__))


class ZeroSlackIsTodaysRule(unittest.TestCase):
    """slack=0 must reproduce the bot exactly: a resting limit at the caller's
    price, which fills at the ask when the ask has come down to it."""

    def test_ask_above_the_caller_price_never_crosses(self):
        d = decide(3.50, 3.55, 3.65, 0.0, "CRWD")       # the real 9/15 CRWD 250C
        self.assertFalse(d.cross)
        self.assertIsNone(d.price)
        self.assertEqual(d.rest, 3.50)

    def test_ask_at_or_under_the_caller_price_is_the_price_improvement(self):
        d = decide(1.94, 1.86, 1.88, 0.0, "META")       # the real 9/15 META 690C
        self.assertTrue(d.cross)
        self.assertEqual(d.price, 1.88)

    def test_zero_slack_is_the_default_when_no_slack_is_passed(self):
        self.assertEqual(decide(3.50, 3.55, 3.65, symbol="CRWD"),
                         decide(3.50, 3.55, 3.65, 0.0, "CRWD"))


class TheBoundary(unittest.TestCase):
    """caller 2.00 at 5% slack: the line is exactly 2.10."""

    def test_ask_exactly_on_the_line_crosses(self):
        d = decide(2.00, 2.05, 2.10, 5.0, "SPY")
        self.assertTrue(d.cross)
        self.assertEqual(d.price, 2.10)

    def test_ask_one_penny_over_the_line_rests(self):
        d = decide(2.00, 2.06, 2.11, 5.0, "SPY")
        self.assertFalse(d.cross)
        self.assertEqual(d.rest, 2.00)

    def test_floating_point_noise_does_not_move_the_line(self):
        # 0.07 * 3 is 0.21000000000000002 in binary floating point; a rule
        # that flips on that is not a rule.
        d = decide(0.07, 0.20, 0.21, 200.0, "SPY")
        self.assertTrue(d.cross)

    def test_the_line_widens_with_the_slack(self):
        crossed = [s for s in entry_slack.SLACK_LEVELS
                   if decide(3.50, 3.55, 3.65, s, "CRWD").cross]
        self.assertEqual(crossed, [5.0, 7.5, 10.0])     # 3.65/3.50 = +4.29%


class MissingQuotesNeverCross(unittest.TestCase):
    def test_no_ask_at_all(self):
        for ask in (None, "", 0, 0.0, -1.0, "nonsense"):
            d = decide(3.50, 3.55, ask, 10.0, "CRWD")
            self.assertFalse(d.cross, ask)
            self.assertIsNone(d.price)

    def test_no_caller_price_is_not_a_trade(self):
        for price in (None, 0, -2.0, ""):
            self.assertFalse(decide(price, 3.55, 3.65, 10.0, "CRWD").cross)

    def test_a_crossed_quote_is_refused(self):
        d = decide(3.50, 3.70, 3.60, 10.0, "CRWD")      # bid over ask
        self.assertFalse(d.cross)
        self.assertIn("crossed quote", d.why)

    def test_a_missing_bid_is_not_fatal_because_the_rule_reads_the_ask(self):
        self.assertTrue(decide(3.50, None, 3.60, 10.0, "CRWD").cross)

    def test_a_negative_slack_is_treated_as_zero(self):
        self.assertEqual(decide(3.50, 3.45, 3.60, -25.0, "CRWD").cross,
                         decide(3.50, 3.45, 3.60, 0.0, "CRWD").cross)


class LegalTicksOnly(unittest.TestCase):
    """A crossing price that is not on the exchange's grid is not a price.
    webull_options.tick_step: SPY/QQQ/IWM a penny always; Penny Program names
    a penny under $3 and a nickel at or above; everything else a nickel under
    $3 and a dime at or above."""

    def test_a_nickel_name_rounds_the_cross_up_not_down(self):
        # CRWD is a Penny Program name, so at $3 and above its tick is a
        # nickel. An ask printed at 3.62 must not be paid at 3.60 — that is a
        # resting bid wearing a cross's clothes.
        d = decide(3.50, 3.55, 3.62, 10.0, "CRWD")
        self.assertTrue(d.cross)
        self.assertGreaterEqual(d.price, 3.62)
        self.assertEqual(d.price, round(round(d.price / 0.05) * 0.05, 2))

    def test_spy_keeps_its_penny_grid(self):
        d = decide(3.50, 3.55, 3.62, 10.0, "SPY")
        self.assertEqual(d.price, 3.62)

    def test_the_resting_price_floors_to_the_legal_tick(self):
        # The live floor rule (webull_options, 9/2): IWM's 0.18 must not go
        # out at 0.20 — 11% over the caller on a penny name.
        self.assertEqual(decide(0.18, 0.17, 0.30, 0.0, "IWM").rest, 0.18)


class TheSwitchRefusesToArm(unittest.TestCase):
    def test_activation_is_blocked(self):
        self.assertFalse(entry_slack.live_ready())

    def test_default_is_zero_and_silent(self):
        for cfg in ({}, None, {"execution": {}},
                    {"execution": {"entry_slack_pct": 0}}):
            self.assertEqual(entry_slack.slack_pct(cfg), 0.0)
            self.assertEqual(entry_slack.armed(cfg), (False, ""))

    def test_a_non_zero_value_refuses_to_arm_and_says_why(self):
        armed, why = entry_slack.armed({"execution": {"entry_slack_pct": 5}})
        self.assertFalse(armed)
        self.assertTrue(why.startswith("SLACK"))
        self.assertIn("refused to arm", why)
        self.assertIn("entry_slack_replay", why)

    def test_junk_and_negatives_read_as_off(self):
        for bad in ("banana", None, -5, [], {"x": 1}):
            self.assertEqual(entry_slack.slack_pct(
                {"execution": {"entry_slack_pct": bad}}), 0.0)

    def test_settings_json_ships_the_switch_at_zero(self):
        p = os.path.join(HERE, "settings.json")
        if not os.path.exists(p):
            self.skipTest("settings.json is not on this machine")
        with open(p, encoding="utf-8") as fh:
            execution = json.load(fh).get("execution") or {}
        self.assertIn("entry_slack_pct", execution)
        self.assertEqual(float(execution["entry_slack_pct"]), 0.0)

    def test_the_bridge_reads_the_switch_through_this_one_module(self):
        with open(os.path.join(HERE, "bridge.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("import entry_slack", src)
        self.assertIn("entry_slack.armed(CFG)", src)
        # No second reader: nothing else may pull the number out of settings.
        self.assertNotIn('"entry_slack_pct"', src.replace(
            'body["entry_slack_pct"]', ""))


if __name__ == "__main__":
    unittest.main()
