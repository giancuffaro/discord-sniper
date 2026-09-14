"""The screenshot reader goes where the text observer goes.

9/14, all day: every 📸 read failed
    IMG READ couldn't read the image (HTTP 400: Your credit balance is too low
    to access the Anthropic API...)
because the image lane still called Anthropic FIRST while the text observer had
already moved to OpenAI/Gemini. The picture lane now uses the same keys, the
same order and the same cooldowns, with Anthropic last and skipped outright
while it is billing-blocked.

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


class Availability(unittest.TestCase):
    def setUp(self):
        ai_reader._ANTHROPIC_BLOCK_UNTIL[0] = 0.0

    def test_a_provider_key_alone_makes_images_readable(self):
        self.assertTrue(ai_reader.image_available(cfg(anthropic=False)))

    def test_no_key_anywhere_is_off(self):
        self.assertFalse(ai_reader.image_available(
            cfg(anthropic=False, openai=False, gemini=False)))

    def test_a_billing_refusal_parks_anthropic(self):
        blank = cfg(anthropic=True, blocked=False, openai=False, gemini=False)
        self.assertFalse(ai_reader.anthropic_blocked(blank))
        self.assertTrue(ai_reader.note_anthropic_error(
            "Your credit balance is too low to access the Anthropic API."))
        self.assertTrue(ai_reader.anthropic_blocked(blank))
        self.assertFalse(ai_reader.image_available(blank))

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
