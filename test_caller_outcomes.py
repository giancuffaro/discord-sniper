import unittest

import caller_outcomes
import caller_ratchet_compare


class CallerOutcomeEvidenceTests(unittest.TestCase):
    def test_futures_entry_keeps_its_own_price(self):
        row = caller_outcomes._entry_contract("MNQ @ 29411.75", "2026-09-11")
        self.assertEqual(row["symbol"], "MNQ")
        self.assertEqual(row["entry"], 29411.75)

    def test_dot_decimal_exit_is_exact_price(self):
        price, pct, per_contract, partial, trim = caller_outcomes._claim_values(
            "STC QQQ 9/11 716c @ .24 taking first trim here PARTIAL", "TRIM")
        self.assertEqual(price, 0.24)
        self.assertIsNone(pct)
        self.assertIsNone(per_contract)
        self.assertTrue(partial)
        self.assertIsNone(trim)

    def test_partial_claim_never_becomes_full_result(self):
        price, pct, per_contract, partial, _trim = caller_outcomes._claim_values(
            "still in DELL calls, currently up 185%", "TRIM")
        self.assertIsNone(price)
        self.assertEqual(pct, 185.0)
        self.assertIsNone(per_contract)
        self.assertTrue(partial)

    def test_exact_full_exit_price_is_calculable(self):
        price, pct, per_contract, partial, _trim = caller_outcomes._claim_values(
            "out on all MU calls 2.40", "CLOSE")
        self.assertEqual(price, 2.40)
        self.assertFalse(partial)

    # Brando's exits (9/14): the price sits straight after the contract, with
    # no STC, no "at" and no "@". Both were filed "price unavailable".
    def test_brando_sold_half_reads_price_and_trim(self):
        price, pct, per_contract, partial, trim = caller_outcomes._claim_values(
            "@Elite SOLD | QQQ SEPT 16 710C $4.80 1/2 POSITION", "TRIM")
        self.assertEqual(price, 4.80)
        self.assertIsNone(pct)
        self.assertIsNone(per_contract)
        self.assertTrue(partial)
        self.assertEqual(trim, 0.5)

    def test_brando_sold_quarter_reads_price_and_trim(self):
        price, pct, per_contract, partial, trim = caller_outcomes._claim_values(
            "@Elite SOLD | QQQ SEPT 16 710C $5.50 1/4 POS", "TRIM")
        self.assertEqual(price, 5.50)
        self.assertTrue(partial)
        self.assertEqual(trim, 0.25)

    def test_brando_prices_against_a_345_entry(self):
        # 3.45 -> 4.80 is +39%, 3.45 -> 5.50 is +59%. Those are the numbers the
        # 9/14 report must show instead of "price unavailable".
        self.assertAlmostEqual((4.80 - 3.45) / 3.45 * 100.0, 39.13, places=2)
        self.assertAlmostEqual((5.50 - 3.45) / 3.45 * 100.0, 59.42, places=2)

    def test_at_and_bare_forms_after_the_contract(self):
        self.assertEqual(caller_outcomes._claim_values(
            "SOLD | META 7/2 630C @7.60 (ALL OUT)", "CLOSE")[0], 7.60)
        self.assertEqual(caller_outcomes._claim_values(
            "SOLD | DELL 7/2 450C 1.25 all out", "CLOSE")[0], 1.25)

    def test_a_price_far_from_any_exit_word_is_ignored(self):
        # Bot footers and promo lines ride inside the same accessible card as
        # a real post. Only a price within 80 characters of an exit word counts.
        self.assertIsNone(caller_outcomes._price_after_contract(
            "sold nothing here. " + "x" * 120 + " QQQ 710C $4.80"))
        self.assertIsNone(caller_outcomes._price_after_contract(
            "Informational purposes only. Bot Version 6.7 -- 09/14/26 3.10"))

    def test_expiry_and_strike_are_never_read_as_the_exit_price(self):
        price, _pct, _pc, _partial, trim = caller_outcomes._claim_values(
            "trimming QQQ SEPT 16 710C 1/2 here", "TRIM")
        self.assertIsNone(price)
        self.assertEqual(trim, 0.5)

    def test_a_date_is_not_a_trim_fraction(self):
        self.assertIsNone(caller_outcomes._trim_size(
            "STC QQQ 9/11 716c @ .24"))
        self.assertIsNone(caller_outcomes._trim_size(
            "SOLD | META 7/2 630C at 7.60"))

    def test_half_counts_as_a_trim_size(self):
        self.assertEqual(caller_outcomes._trim_size("sold half here"), 0.5)

    def test_broker_actual_overrides_ratchet_replay(self):
        event = {"actual": 5.0, "actual_exit": 0.70}
        replay = {"exit": 0.65, "pct": 0.0, "pl": 0.0}
        exit_px, pct, pl, basis = caller_ratchet_compare._our_result(
            event, 0.65, replay)
        self.assertEqual(exit_px, 0.70)
        self.assertAlmostEqual(pct, 7.6923077)
        self.assertEqual(pl, 5.0)
        self.assertEqual(basis, "broker-confirmed actual")


class PostedStockPriceTests(unittest.TestCase):
    """Midas, 9/14: 'SPY 760P 9/14 @ 760.40'. 760.40 is SPY, not the premium.

    The live OPEN path has refused this since v3.8.24. These tests pin the
    report-side rule: within 2% of the recorded underlying AND several times
    the contract's own ask.
    """

    def setUp(self):
        caller_outcomes._UND_CACHE[("2026-09-14", "SPY")] = [
            (1789054080.0, 759.64), (1789054200.0, 759.47)]
        caller_outcomes._UND_CACHE[("2026-09-14", "DRAM")] = [
            (1789054080.0, 58.10)]
        self.addCleanup(caller_outcomes._UND_CACHE.clear)

    def test_stock_price_posted_as_premium_is_caught(self):
        self.assertTrue(caller_outcomes.is_posted_stock_price(
            "2026-09-14", "SPY", 760.40, 1789054080.0, ask=1.17))

    def test_a_real_premium_is_not_caught(self):
        self.assertFalse(caller_outcomes.is_posted_stock_price(
            "2026-09-14", "SPY", 1.25, 1789054080.0, ask=1.17))

    def test_deep_itm_premium_near_its_underlying_is_not_caught(self):
        # A $57.90 premium on a $58.10 stock is within 2%, but it is also
        # roughly the contract's own ask, so it is a premium, not a quote.
        self.assertFalse(caller_outcomes.is_posted_stock_price(
            "2026-09-14", "DRAM", 57.90, 1789054080.0, ask=57.95))

    def test_no_recorded_underlying_means_no_verdict(self):
        self.assertFalse(caller_outcomes.is_posted_stock_price(
            "2026-09-14", "AAPL", 250.0, 1789054080.0, ask=1.0))


if __name__ == "__main__":
    unittest.main()
