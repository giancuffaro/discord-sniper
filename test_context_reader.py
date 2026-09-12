"""Context must never borrow contract details from another room participant."""
import unittest

import context_reader


class ContextReaderTests(unittest.TestCase):
    def setUp(self):
        self.current = {"id": "now", "author": "Alice", "postedAt": 300000,
                        "text": "Filled at 1.25"}
        self.raw = {"action": "OPEN", "instrument": "option", "ticker": "SPY",
                    "strike": 500, "side": "CALL", "price": 1.25,
                    "confidence": 0.9}

    def test_same_author_recent_contract_can_be_measured(self):
        prior = [{"id": "one", "author": "Alice", "postedAt": 240000,
                  "text": "Loading SPY 500C"}]
        result = context_reader.assess(self.current, prior, self.raw, [])
        self.assertTrue(result["ok"])
        self.assertEqual(result["eligible_prior_ids"], ["one"])

    def test_other_author_cannot_supply_contract(self):
        prior = [{"id": "one", "author": "Bob", "postedAt": 240000,
                  "text": "Loading SPY 500C"}]
        result = context_reader.assess(self.current, prior, self.raw, [])
        self.assertFalse(result["ok"])
        self.assertEqual(result["eligible_prior_ids"], [])

    def test_old_contract_cannot_supply_fields(self):
        prior = [{"id": "one", "author": "Alice", "postedAt": -1000,
                  "text": "Loading SPY 500C"}]
        result = context_reader.assess(self.current, prior, self.raw, [])
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
