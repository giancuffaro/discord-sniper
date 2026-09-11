import unittest

import caller_outcomes
import caller_ratchet_compare


class CallerOutcomeEvidenceTests(unittest.TestCase):
    def test_dot_decimal_exit_is_exact_price(self):
        price, pct, per_contract, partial = caller_outcomes._claim_values(
            "STC QQQ 9/11 716c @ .24 taking first trim here PARTIAL", "TRIM")
        self.assertEqual(price, 0.24)
        self.assertIsNone(pct)
        self.assertIsNone(per_contract)
        self.assertTrue(partial)

    def test_partial_claim_never_becomes_full_result(self):
        price, pct, per_contract, partial = caller_outcomes._claim_values(
            "still in DELL calls, currently up 185%", "TRIM")
        self.assertIsNone(price)
        self.assertEqual(pct, 185.0)
        self.assertIsNone(per_contract)
        self.assertTrue(partial)

    def test_exact_full_exit_price_is_calculable(self):
        price, pct, per_contract, partial = caller_outcomes._claim_values(
            "out on all MU calls 2.40", "CLOSE")
        self.assertEqual(price, 2.40)
        self.assertFalse(partial)

    def test_broker_actual_overrides_ratchet_replay(self):
        event = {"actual": 5.0, "actual_exit": 0.70}
        replay = {"exit": 0.65, "pct": 0.0, "pl": 0.0}
        exit_px, pct, pl, basis = caller_ratchet_compare._our_result(
            event, 0.65, replay)
        self.assertEqual(exit_px, 0.70)
        self.assertAlmostEqual(pct, 7.6923077)
        self.assertEqual(pl, 5.0)
        self.assertEqual(basis, "broker-confirmed actual")


if __name__ == "__main__":
    unittest.main()
