"""Context must never borrow contract details from another room participant."""
import unittest
from unittest.mock import patch

import context_reader


class ContextReaderTests(unittest.TestCase):
    def test_pause_prevents_network_request(self):
        with patch('context_reader.os.path.exists',return_value=True), patch('context_reader.urllib.request.urlopen') as network:
            raw, ms=context_reader.read({},[],[],{})
        self.assertEqual(raw,{'_error':'paused'})
        self.assertEqual(ms,0)
        network.assert_not_called()

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

    def test_shared_scribe_does_not_mix_admins(self):
        current = dict(self.current, author="HoneyDrip (Scribe)",
                       text="@Brett (Admin) filled at 1.25")
        prior = [{"id": "other", "author": "HoneyDrip (Scribe)",
                  "postedAt": 240000,
                  "text": "@Unraveller (Admin) loading SPY 500C"}]
        result = context_reader.assess(current, prior, self.raw, [])
        self.assertFalse(result["ok"])
        self.assertEqual(result["eligible_prior_ids"], [])

    def test_flags_invented_year_and_option_side(self):
        current = dict(self.current, text="in SPY 500C 9/18 @ 1.25")
        raw = dict(self.raw, side="LONG", expiry="2025-09-18")
        self.assertEqual(context_reader.safety_flags(current, [], raw),
                         ["option_side_not_call_or_put", "expiry_not_literal"])


if __name__ == "__main__":
    unittest.main()
