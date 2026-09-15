import os
import tempfile
import unittest

from daily_audit import summarize_replay
from daily_report import _reportable_channel, _reason, _caller_room, _source_message_url
import replay_check
from replay_check import find_missed_entries


class DailyAuditTests(unittest.TestCase):
    def test_personal_whop_pages_are_not_operating_rooms(self):
        self.assertFalse(_reportable_channel("whop:/messages"))
        self.assertFalse(_reportable_channel("whop:/@edlazar"))
        self.assertTrue(_reportable_channel(
            "whop:/firststeptrading/example/app"))

    def test_room_activity_requires_an_active_configured_channel(self):
        active = {"123", "whop:/firststeptrading/example/app"}
        self.assertTrue(_reportable_channel("123", active))
        self.assertFalse(_reportable_channel("1548907233490772083", active))

    def test_futures_safety_refusal_has_a_specific_report_reason(self):
        self.assertEqual(_reason({"kind": "failed", "text":
                         "Webull futures entry held: broker-confirmed protective stop is not operational"}),
                         "futures protective exit not operational; no order sent")

    def test_decision_attribution_splits_caller_and_room(self):
        caller, room = _caller_room({"text":
            "OPEN MNQ @ 29000 — Ninjago Futures Radar · NGD: ngd-trades — bridge refused"})
        self.assertEqual((caller, room), ("Ninjago Futures Radar", "NGD: ngd-trades"))

    def test_stale_decision_uses_preserved_original_author(self):
        caller, room = _caller_room({"text":
            "OPEN QQQ 710C — that call is 78 seconds old — too stale | EliteOptions | Brando: QQQ call"})
        self.assertEqual((caller, room), ("EliteOptions | Brando", "unavailable"))

    def test_discord_source_url_requires_a_real_message_id(self):
        self.assertEqual(
            _source_message_url("1537061197931618344", "123456789012345678"),
            "https://discord.com/channels/1065277732684058624/1537061197931618344/123456789012345678")
        self.assertEqual(_source_message_url("1537061197931618344", "legacy-unknown"), "")

    def test_load_keeps_raw_messages_when_live_parser_is_partial(self):
        content = """=== RAW MESSAGES ===
2026-09-11 09:31:00  [Morning #1 message_id=123456789012345678]  OPEN AAPL 100C @ 1.00
2026-09-11 09:32:00  [Second #2]  OPEN MSFT 200C @ 2.00
=== LIVE PARSER INPUTS ===
2026-09-11 09:31:00  [Morning #1]  OPEN AAPL 100C @ 1.00
=== WHAT THE BOT DID ===
2026-09-11 09:31:01  <sent>  ORDER IN AAPL 100C
"""
        old_day = replay_check.DAY
        path = None
        try:
            replay_check.DAY = "2026-09-11"
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False, suffix=".txt"
            ) as handle:
                handle.write(content)
                path = handle.name
            messages, decisions = replay_check.load(path)
            self.assertEqual({m[1] for m in messages}, {"Morning", "Second"})
            self.assertEqual(len(messages), 2)
            first = next(m for m in messages if m[1] == "Morning")
            self.assertEqual(first.message_id, "123456789012345678")
            self.assertEqual(next(m for m in messages if m[1] == "Second").message_id, "")
            self.assertEqual(len(decisions), 1)
        finally:
            replay_check.DAY = old_day
            if path and os.path.exists(path):
                os.unlink(path)

    def test_summary_counts_failures_and_coverage(self):
        text = """COVERAGE WARNING: discord empty
TOTAL silent drops: 2  (actionable)
POSSIBLE MISSED ENTRIES: 3
"""
        self.assertEqual(summarize_replay(text), {
            "silent_drops": 2,
            "possible_missed": 3,
            "coverage_warnings": 1,
        })

    def test_clean_replay_is_zero(self):
        self.assertEqual(summarize_replay(
            "TOTAL silent drops: 0\nPOSSIBLE MISSED ENTRIES: 0\n"), {
                "silent_drops": 0,
                "possible_missed": 0,
                "coverage_warnings": 0,
            })

    def test_unresolved_loaded_fill_is_reported(self):
        keep = [
            ("10:00:00", "Midas", "1", "Midas: Loaded AAPL 335c 0days"),
            ("10:01:00", "Midas", "1", "Midas: 1.46 on starters @here"),
        ]
        parsed = [
            {"action": "PREPARE", "symbol": "AAPL", "strike": 335,
             "side": "CALLS"},
            {"action": "OPEN", "needs_loaded": True, "limit": 1.46},
        ]
        flags = find_missed_entries(keep, parsed,
                                    [("10:01:00", "skipped",
                                      "POSSIBLE MISSED ENTRY 1.46 on starters")], [])
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0][3:6], ("AAPL", 335, "CALLS"))

    def test_production_loaded_fill_shape_is_reported(self):
        keep = [
            ("10:00:00", "Midas", "1", "Midas: Loaded AAPL 335c 0days"),
            ("10:01:00", "Midas", "1", "Midas: 1.46 on starters @here"),
        ]
        parsed = [
            {"action": "PREPARE", "symbol": "AAPL", "strike": 335,
             "side": "CALLS"},
            {"action": "OPEN", "symbol": None, "limit": 1.46,
             "matched": "fill confirmation on a loaded contract"},
        ]
        flags = find_missed_entries(keep, parsed, [], [])
        self.assertEqual(len(flags), 1)


if __name__ == "__main__":
    unittest.main()


