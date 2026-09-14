"""BOTH live ai_reader lanes go where the text observer goes.

(Named for the lane it started in this morning; it now covers the one-message
text reader too. One file for one concern — this sandbox cannot delete, so the
name stays put rather than leaving two half-files behind.)

9/14, all day, both lanes died on the same hard-coded call:
    IMG READ couldn't read the image (HTTP 400: Your credit balance is too low
    to access the Anthropic API...)
    AI READ  no call — ai: HTTP 400                      (242 of these)
while the text observer had already moved to OpenAI/Gemini on 9/13. Both now
use the same keys, the same order and the same cooldowns, with Anthropic last
and skipped outright while it is billing-blocked.

No network, no API spend: every provider call is mocked.
"""
import unittest
from unittest import mock

import ai_reader
import observer_providers

IMAGES = ["https://cdn.discordapp.com/attachments/1/2/shot.png"]
GOOD = {"seen_text": "TSLA 357.5P 1.42", "action": "OPEN", "ticker": "TSLA",
        "side": "PUT", "strike": 357.5, "expiry": "0DTE", "price": 1.42,
        "confidence": 0.9}


def cfg(anthropic=True, blocked=True, openai=True, gemini=True):
    keys = {}
    if openai:
        keys["openai"] = "sk-test"
    if gemini:
        keys["gemini"] = "g-test"
    return {"ai_provider_keys": keys,
            "context_observer": {"enabled": True,
                                 "provider_order": ["gemini", "openai"]},
            "execution": {"ai_reader": {
                "api_key": "anthropic-test" if anthropic else "",
                "billing_blocked": blocked}}}


class ImageProviderOrder(unittest.TestCase):
    def setUp(self):
        observer_providers._cooldown.clear()
        ai_reader._ANTHROPIC_BLOCK_UNTIL[0] = 0.0
        patch = mock.patch.object(ai_reader, "_fetch_image_b64",
                                  return_value=("image/png", "QUJD"))
        patch.start()
        self.addCleanup(patch.stop)
        # Anthropic must never be reached in these tests.
        nope = mock.patch.object(ai_reader.urllib.request, "urlopen",
                                 side_effect=AssertionError("called Anthropic"))
        nope.start()
        self.addCleanup(nope.stop)

    def test_openai_reads_it_while_anthropic_is_billing_blocked(self):
        with mock.patch.object(observer_providers, "request",
                               return_value=dict(GOOD, _provider="openai",
                                                 _model="gpt-5.4")) as call:
            out = ai_reader.read_image(IMAGES, "", ["TSLA"], cfg())
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0], "openai")
        self.assertEqual(out["_provider"], "openai")
        self.assertEqual(out["_seen_text"], "TSLA 357.5P 1.42")

    def test_the_image_actually_rides_along(self):
        with mock.patch.object(observer_providers, "request",
                               return_value=dict(GOOD)) as call:
            ai_reader.read_image(IMAGES, "caption", ["TSLA"], cfg())
        self.assertEqual(call.call_args.kwargs["images"], [("image/png", "QUJD")])

    def test_gemini_is_the_fallback(self):
        with mock.patch.object(observer_providers, "request",
                               side_effect=[{"_error": "HTTP_429"},
                                            dict(GOOD, _provider="gemini")]) as call:
            out = ai_reader.read_image(IMAGES, "", ["TSLA"], cfg())
        self.assertEqual([c.args[0] for c in call.call_args_list],
                         ["openai", "gemini"])
        self.assertEqual(out["_provider"], "gemini")

    def test_both_down_and_anthropic_blocked_says_so_and_spends_nothing(self):
        with mock.patch.object(observer_providers, "request",
                               return_value={"_error": "timeout"}):
            out = ai_reader.read_image(IMAGES, "", ["TSLA"], cfg())
        self.assertIn("openai timeout", out["_error"])
        self.assertIn("gemini timeout", out["_error"])
        self.assertIn("anthropic billing-blocked", out["_error"])

    def test_text_observer_order_is_untouched(self):
        """The image lane has its own order; changing it must not move the
        observer, which G left on Gemini-first."""
        with mock.patch.object(observer_providers, "request",
                               return_value={"action": "NONE"}) as call:
            observer_providers.read("sys", "prompt", cfg())
        self.assertEqual(call.call_args.args[0], "gemini")


class TextProviderOrder(unittest.TestCase):
    """The ONE-MESSAGE reader — the lane that proposes live entries. Whoever
    reads it, the answer is still only data: validate() and the parser decide."""

    def setUp(self):
        observer_providers._cooldown.clear()
        ai_reader._ANTHROPIC_BLOCK_UNTIL[0] = 0.0
        nope = mock.patch.object(ai_reader.urllib.request, "urlopen",
                                 side_effect=AssertionError("called Anthropic"))
        nope.start()
        self.addCleanup(nope.stop)

    def test_openai_reads_it_while_anthropic_is_billing_blocked(self):
        with mock.patch.object(observer_providers, "request",
                               return_value=dict(GOOD, _provider="openai",
                                                 _model="gpt-5.4")) as call:
            out = ai_reader.read_signal("TSLA 357.5p 1.42", ["TSLA"], cfg())
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0], "openai")
        self.assertEqual(out["_provider"], "openai")

    def test_gemini_is_the_fallback(self):
        with mock.patch.object(observer_providers, "request",
                               side_effect=[{"_error": "HTTP_500"},
                                            dict(GOOD, _provider="gemini")]) as call:
            out = ai_reader.read_signal("TSLA 357.5p 1.42", ["TSLA"], cfg())
        self.assertEqual([c.args[0] for c in call.call_args_list],
                         ["openai", "gemini"])
        self.assertEqual(out["_provider"], "gemini")

    def test_a_parse_failure_is_no_call_never_an_order(self):
        with mock.patch.object(observer_providers, "request",
                               return_value={"_error": "incomplete_or_invalid_json"}):
            out = ai_reader.read_signal("TSLA 357.5p 1.42", ["TSLA"], cfg())
        ok, why, cleaned = ai_reader.validate(out, "TSLA 357.5p 1.42", ["TSLA"])
        self.assertFalse(ok)
        self.assertIsNone(cleaned)
        self.assertIn("incomplete_or_invalid_json", why)

    def test_a_hallucinated_ticker_is_still_refused(self):
        """Changing WHO reads changes nothing about what a read may do."""
        with mock.patch.object(observer_providers, "request",
                               return_value=dict(GOOD, ticker="AAPL")):
            out = ai_reader.read_signal("TSLA 357.5p 1.42", ["TSLA"], cfg())
        ok, why, cleaned = ai_reader.validate(out, "TSLA 357.5p 1.42", ["TSLA"])
        self.assertFalse(ok)
        self.assertIsNone(cleaned)
        self.assertIn("AAPL", why)

    def test_a_clean_read_still_has_to_clear_validate(self):
        with mock.patch.object(observer_providers, "request",
                               return_value=dict(GOOD, _provider="openai")):
            out = ai_reader.read_signal("TSLA 357.5P 1.42", ["TSLA"], cfg())
        ok, why, cleaned = ai_reader.validate(out, "TSLA 357.5P 1.42", ["TSLA"])
        self.assertTrue(ok, why)
        self.assertEqual(cleaned["ticker"], "TSLA")

    def test_both_down_and_anthropic_blocked_spends_nothing(self):
        with mock.patch.object(observer_providers, "request",
                               return_value={"_error": "timeout"}):
            out = ai_reader.read_signal("TSLA 357.5p", ["TSLA"], cfg())
        self.assertIn("anthropic billing-blocked", out["_error"])
        self.assertFalse(ai_reader.validate(out, "TSLA 357.5p", ["TSLA"])[0])


class NeverRaises(unittest.TestCase):
    """OpenAI writes "" where Anthropic wrote null, and sometimes a RANGE.
    validate() floats those and raises — 249 of the 12,162 retained reads from
    the 9/12 scan do it. A bad field is a refusal, never a crash and never an
    order; an unhandled raise in the bridge's read lane would answer the
    extension with a 500 that reads to it like a dead bridge."""

    BAD = ({"action": "TRIM", "ticker": "SHEL", "side": "CALL", "strike": 93,
            "expiry": "9/4", "price": "2.18-2.20", "confidence": 1.0},
           {"action": "ADD", "ticker": "AAPL", "side": "", "strike": "",
            "expiry": "", "price": 2.85, "qty": "", "confidence": 0.8},
           {"action": "OPEN", "ticker": "SPY", "side": "CALL",
            "strike": "570-580", "expiry": "0DTE", "price": "Premium"})

    def test_validate_really_does_raise_on_these(self):
        hit = 0
        for bad in self.BAD:
            try:
                ai_reader.validate(dict(bad), "SHEL AAPL SPY 93 2.85 0DTE", [])
            except (TypeError, ValueError, OverflowError):
                hit += 1
        self.assertTrue(hit, "fixtures no longer reproduce the raise")

    def test_judge_turns_every_one_into_no_call(self):
        for bad in self.BAD:
            ok, why, cleaned = ai_reader.judge(
                dict(bad), "SHEL AAPL SPY 93 2.85 0DTE", [])
            self.assertFalse(ok)
            self.assertIsNone(cleaned)
            self.assertTrue(why)

    def test_a_good_read_is_unaffected(self):
        ok, why, cleaned = ai_reader.judge(dict(GOOD), "TSLA 357.5P 1.42",
                                           ["TSLA"])
        self.assertTrue(ok, why)
        self.assertEqual(cleaned["ticker"], "TSLA")


class Availability(unittest.TestCase):
    def setUp(self):
        ai_reader._ANTHROPIC_BLOCK_UNTIL[0] = 0.0

    def test_a_provider_key_alone_makes_both_lanes_readable(self):
        self.assertTrue(ai_reader.image_available(cfg(anthropic=False)))
        self.assertTrue(ai_reader.signal_available(cfg(anthropic=False)))

    def test_no_key_anywhere_is_off(self):
        blank = cfg(anthropic=False, openai=False, gemini=False)
        self.assertFalse(ai_reader.image_available(blank))
        self.assertFalse(ai_reader.signal_available(blank))

    def test_a_billing_refusal_parks_anthropic(self):
        blank = cfg(anthropic=True, blocked=False, openai=False, gemini=False)
        self.assertFalse(ai_reader.anthropic_blocked(blank))
        self.assertTrue(ai_reader.note_anthropic_error(
            "Your credit balance is too low to access the Anthropic API."))
        self.assertTrue(ai_reader.anthropic_blocked(blank))
        self.assertFalse(ai_reader.image_available(blank))
        self.assertFalse(ai_reader.signal_available(blank))

    def test_an_ordinary_error_does_not_park_it(self):
        self.assertFalse(ai_reader.note_anthropic_error("overloaded_error"))


class LastResort(unittest.TestCase):
    def setUp(self):
        observer_providers._cooldown.clear()
        ai_reader._ANTHROPIC_BLOCK_UNTIL[0] = 0.0
        patch = mock.patch.object(ai_reader, "_fetch_image_b64",
                                  return_value=("image/png", "QUJD"))
        patch.start()
        self.addCleanup(patch.stop)

    def test_anthropic_still_reads_when_it_is_the_only_one_and_is_healthy(self):
        c = cfg(anthropic=True, blocked=False, openai=False, gemini=False)
        body = mock.Mock()
        body.read.return_value = (
            b'{"content":[{"type":"text","text":"{\\"seen_text\\":\\"SPY 660C\\",'
            b'\\"action\\":\\"OPEN\\",\\"ticker\\":\\"SPY\\"}"}]}')
        body.__enter__ = lambda s: body
        body.__exit__ = lambda s, *a: False
        with mock.patch.object(ai_reader.urllib.request, "urlopen",
                               return_value=body):
            out = ai_reader.read_image(IMAGES, "", ["SPY"], c)
        self.assertEqual(out["_provider"], "anthropic")
        self.assertEqual(out["_seen_text"], "SPY 660C")


if __name__ == "__main__":
    unittest.main()
