"""Offline checks: unsafe futures entries never reach a broker, and the
entry gate opens only on evidence that still applies."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import webull_futures as futures


class ProtectiveStops(unittest.TestCase):
    def test_long_stop_is_a_single_gtc_sell_on_the_exact_contract(self):
        row = futures.protective_stop_order('MESZ6', 'LONG', 1, 7000.0,
                                            6975.0, 'sniperstop123')
        self.assertEqual((row['side'], row['order_type'], row['stop_price']),
                         ('SELL', 'STOP_LOSS', '6975'))
        self.assertEqual((row['symbol'], row['quantity'], row['time_in_force']),
                         ('MESZ6', '1', 'GTC'))
        self.assertNotIn('limit_price', row)
        self.assertNotIn('target_price', row)

    def test_short_stop_buys_back_without_a_target_order(self):
        row = futures.protective_stop_order('MNQZ6', 'SHORT', 1, 25000,
                                            25025.25, 'sniperstop456')
        self.assertEqual((row['side'], row['stop_price']), ('BUY', '25025.25'))

    def test_ambiguous_or_invalid_protection_refuses(self):
        bad = [('MES', 'LONG', 1, 7000, 6975, 's1'),
               ('MESZ6', 'LONG', 2, 7000, 6975, 's1'),
               ('MESZ6', 'LONG', 1, None, 6975, 's1'),
               ('MESZ6', 'LONG', 1, 7000, 7001, 's1'),
               ('MNQZ6', 'SHORT', 1, 25000, 24975, 's1'),
               ('MESZ6', 'LONG', 1, 7000, 6975.12, 's1')]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(futures.FuturesRefused):
                futures.protective_stop_order(*args)

    def test_live_entry_refuses_before_any_broker_lookup_or_submission(self):
        wb = Mock()
        result = futures.execute(wb, None,
                                 {'action': 'OPEN', 'symbol': 'MES',
                                  'direction': 'LONG', 'limit': None},
                                 'room|MES', lambda _: None)
        self.assertFalse(result[0])
        self.assertIn('no order was sent', result[1])
        wb.assert_not_called()
        self.assertFalse(futures.protective_entries_ready())

    def test_the_refusal_message_carries_the_reason_the_gate_is_shut(self):
        wb = Mock()
        with patch.object(futures, 'protection_proof_state',
                          return_value=(False, 'the dog ate the proof')):
            ok, msg = futures.execute(wb, None,
                                      {'action': 'OPEN', 'symbol': 'MES',
                                       'direction': 'LONG', 'limit': None},
                                      'room|MES', lambda _: None)
        self.assertFalse(ok)
        self.assertIn('the dog ate the proof', msg)
        self.assertIn('no order was sent', msg)
        wb.assert_not_called()

    def test_broker_stop_requires_exact_working_detail(self):
        payload = futures.protective_stop_order('MESZ6', 'LONG', 1, 7000,
                                                6975, 'sniperstop123')
        wb = Mock(futures_account_id='fake-futures-account')
        api = wb.trade.order_v3
        api.place_order.return_value = Mock(status_code=200)
        api.get_order_detail.return_value = Mock(status_code=200)
        api.get_order_detail.return_value.json.return_value = {
            'orders': [dict(payload, status='SUBMITTED')]}
        self.assertEqual(futures.submit_protective_stop(wb, payload),
                         'sniperstop123')
        api.place_order.assert_called_once_with('fake-futures-account', [payload])
        api.get_order_detail.assert_called_once_with('fake-futures-account',
                                                      'sniperstop123')

    def test_wrong_contract_or_unknown_response_never_counts_as_protection(self):
        payload = futures.protective_stop_order('MNQZ6', 'SHORT', 1, 25000,
                                                25025, 'sniperstop456')
        wb = Mock(futures_account_id='fake-futures-account')
        api = wb.trade.order_v3
        api.place_order.return_value = Mock(status_code=200)
        api.get_order_detail.return_value = Mock(status_code=200)
        api.get_order_detail.return_value.json.return_value = {
            'orders': [dict(payload, symbol='MESZ6', status='SUBMITTED')]}
        with self.assertRaisesRegex(futures.FuturesRefused, 'unverified'):
            futures.submit_protective_stop(wb, payload)
        api.place_order.assert_called_once()

    def test_cancel_confirmation_prevents_a_second_exit_after_stop_fill(self):
        payload = futures.protective_stop_order('MESZ6', 'LONG', 1, 7000,
                                                6975, 'sniperstop789')
        wb = Mock(futures_account_id='fake-futures-account')
        api = wb.trade.order_v3
        api.get_order_detail.return_value = Mock(status_code=200)
        api.get_order_detail.return_value.json.return_value = {
            'orders': [dict(payload, status='FILLED')]}
        self.assertEqual(futures.cancel_protective_stop(wb, payload), 'filled')
        api.get_order_detail.return_value.json.return_value = {
            'orders': [dict(payload, status='PENDING')]}
        with self.assertRaisesRegex(futures.FuturesRefused, 'no separate close'):
            futures.cancel_protective_stop(wb, payload)

    def test_caller_exit_replaces_the_same_stop_never_places_second_sell(self):
        payload = futures.protective_stop_order('MESZ6', 'LONG', 1, 7000,
                                                6975, 'sniperstop999')
        wb = Mock(futures_account_id='fake-futures-account')
        api = wb.trade.order_v3
        api.get_order_detail.return_value = Mock(status_code=200)
        api.get_order_detail.return_value.json.return_value = {
            'orders': [dict(payload, status='SUBMITTED')]}
        self.assertEqual(futures.request_exit_through_stop(wb, payload),
                         'replace_requested')
        api.replace_order.assert_called_once_with('fake-futures-account', [
            {'client_order_id': 'sniperstop999', 'order_type': 'MARKET',
             'quantity': '1'}])
        api.place_order.assert_not_called()
        api.get_order_detail.return_value.json.return_value = {
            'orders': [dict(payload, status='FILLED', order_type='MARKET')]}
        self.assertEqual(futures.request_exit_through_stop(wb, payload), 'filled')
        api.replace_order.assert_called_once()


class TheEntryGate(unittest.TestCase):
    """protective_entries_ready() is evidence, not a boolean. These build
    their own proof files in a temp dir; the real one is never touched."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='futproof')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.proof = os.path.join(self.dir, futures.PROOF_FILE)
        self.module = os.path.join(self.dir, 'webull_futures.py')
        with open(self.module, 'w', encoding='utf-8') as fh:
            fh.write('# a stand-in for the futures module\n')

    def _write(self, **over):
        doc = {'proof_version': futures.PROOF_VERSION,
               'written_at': '2026-09-16T10:00:00-04:00', 'contract': 'MESZ6',
               'module_sha256': futures.module_sha256(self.module),
               'steps': [{'name': n, 'ok': True, 'at': 'x', 'detail': 'y'}
                         for n in futures.PROOF_STEPS]}
        doc.update(over)
        with open(self.proof, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh)
        return doc

    def _state(self):
        return futures.protection_proof_state(self.proof, self.module)

    def test_no_proof_file_means_shut_and_says_so(self):
        ok, why = self._state()
        self.assertFalse(ok)
        self.assertIn('never been run', why)

    def test_malformed_proof_is_not_a_proof(self):
        with open(self.proof, 'w', encoding='utf-8') as fh:
            fh.write('{not json at all')
        ok, why = self._state()
        self.assertFalse(ok)
        self.assertIn('cannot be read', why)

    def test_a_proof_from_another_version_is_not_accepted(self):
        self._write(proof_version=futures.PROOF_VERSION + 7)
        ok, why = self._state()
        self.assertFalse(ok)
        self.assertIn('different proof version', why)

    def test_a_failed_step_names_the_step_and_keeps_the_door_shut(self):
        doc = self._write()
        doc['steps'][4]['ok'] = False
        with open(self.proof, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh)
        ok, why = self._state()
        self.assertFalse(ok)
        self.assertIn(futures.PROOF_STEPS[4], why)

    def test_a_proof_that_stopped_early_proves_only_what_it_reached(self):
        doc = self._write()
        doc['steps'] = doc['steps'][:3]
        with open(self.proof, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh)
        ok, why = self._state()
        self.assertFalse(ok)
        self.assertIn('flat_confirmed', why)

    def test_editing_the_futures_module_kills_the_proof(self):
        self._write()
        self.assertTrue(self._state()[0])
        with open(self.module, 'a', encoding='utf-8') as fh:
            fh.write('# one more line, and the proof no longer applies\n')
        ok, why = self._state()
        self.assertFalse(ok)
        self.assertIn('has changed since the proof', why)

    def test_a_clean_proof_that_still_matches_opens_the_door(self):
        self._write()
        ok, why = self._state()
        self.assertTrue(ok)
        self.assertIn('MESZ6', why)

    def test_the_shipped_repo_has_no_proof_file_checked_in(self):
        """Nobody hand-writes this file. It is written by a live run only."""
        self.assertFalse(futures.protective_entries_ready())
        self.assertIn('PROVE FUTURES STOPS', futures.protective_entries_reason())


if __name__ == '__main__':
    unittest.main()
