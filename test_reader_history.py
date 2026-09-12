"""Regressions for importing history without fabricating alert coverage."""
import tempfile
import unittest
from pathlib import Path

import reader_history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'extension').mkdir()
        (self.root/'DS Logs').mkdir()
        (self.root/'extension/rooms.txt').write_text(
            '123|https://discord.com/channels/1/123|Example|Group|off\n'
            '456|https://discord.com/channels/1/456|Empty|Group|on\n'
            'whop:day-trades|https://whop.com/team/exp_abc/app/|Whop|Group|on\n',
            encoding='utf-8')

    def test_history_whop_and_duplicate_export_views(self):
        text = ('=== RAW MESSAGES THE READER SAW ===\n'
                '2026-07-01 10:00:00  [Example #123]  <history> Alice: SPY 500C\n'
                '2026-07-01 10:00:02  [Whop #whop:/team/exp_abc/app]  Bob: in @ 1.00\n'
                '=== LIVE PARSER INPUTS ===\n'
                '2026-07-01 10:00:00  [Example #123]  Alice: SPY 500C\n')
        for name in ('signal-room-chat A.txt', 'signal-room-chat B.txt'):
            (self.root/'DS Logs'/name).write_text(text, encoding='utf-8')
        rows, coverage = reader_history.load(self.root, '2026-06-12', '2026-09-12')
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]['history_only'])
        self.assertEqual(len(rows[0]['sources']), 2)
        self.assertEqual(rows[1]['channelId'], 'whop:day-trades')
        missing = next(c for c in coverage['channels'] if c['channelId']=='456')
        self.assertEqual(missing['messages'], 0)
        self.assertEqual(missing['coverage'], 'unverified')

    def test_grab_utc_timestamp_multiline_and_date_cutoff(self):
        (self.root/'DS Logs/grab 123 Example.txt').write_text(
            'channel_id: 123\nroom: Example\n'
            '2026-07-01 14:02  Alice: SPY 500C\nfilled @ 1.25\n'
            '2026-01-01 14:02  Alice: old post\n', encoding='utf-8')
        rows, _ = reader_history.load(self.root, '2026-06-12', '2026-09-12')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['at'], '2026-07-01 10:02:00')
        self.assertEqual(rows[0]['text'], 'SPY 500C filled @ 1.25')
        self.assertEqual(rows[0]['timestamp_precision'], 'minute')

    def test_same_text_different_callers_is_not_deduplicated(self):
        (self.root/'DS Logs/signal-room-chat A.txt').write_text(
            '2026-07-01 10:00:00  [Example #123]  Alice: in\n'
            '2026-07-01 10:00:00  [Example #123]  Bob: in\n', encoding='utf-8')
        rows, _ = reader_history.load(self.root)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])

    def test_grab_overlap_uses_precise_time_without_duplicate_alert(self):
        (self.root/'DS Logs/signal-room-chat A.txt').write_text(
            '2026-07-01 10:02:33  [Example #123]  Alice: SPY 500C\n', encoding='utf-8')
        (self.root/'DS Logs/grab 123 Example.txt').write_text(
            'channel_id: 123\nroom: Example\n2026-07-01 14:02  Alice: SPY 500C\n', encoding='utf-8')
        rows, coverage = reader_history.load(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['at'], '2026-07-01 10:02:33')
        self.assertEqual(len(rows[0]['sources']), 2)
        self.assertEqual(coverage['import_counts']['matched_minute_export'], 1)


if __name__ == '__main__':
    unittest.main()
