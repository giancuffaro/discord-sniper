"""Offline checks: unsafe futures entries never reach a broker, and the
entry gate opens only on evidence that still applies — PER MICRO. MES and MNQ
are proven on separate real trades, so MES proven is not MNQ proven."""
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
               ('MESZ6', 'LONG', 1, 7000, 6975.12, 's1'),
               ('MNQZ6', 'LONG', 1, 25000, 24990.1, 's1')]
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
        self.assertFalse(futures.protective_entries_ready('MES'))

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


class TheTwoMicros(unittest.TestCase):
    """FUT_SPECS is the one place the futures path reads a tick and a point
    value. It must agree with the table the bridge prices the day with."""

    def test_point_values_agree_with_the_bridges_money_table(self):
        import bridge
        for sym, spec in futures.FUT_SPECS.items():
            self.assertEqual(spec['point_value'], bridge.FUT_MULT[sym],
                             '%s point value disagrees with bridge.FUT_MULT' % sym)

    def test_a_full_size_root_is_judged_on_the_micro_it_would_buy(self):
        self.assertEqual(futures.proof_symbol('ES'), 'MES')
        self.assertEqual(futures.proof_symbol('NQ'), 'MNQ')
        self.assertEqual(futures.proof_symbol('mnq'), 'MNQ')
        self.assertIsNone(futures.proof_symbol('MGC'))
        self.assertIsNone(futures.proof_symbol(''))


class TheEntryGate(unittest.TestCase):
    """protective_entries_ready(symbol) is evidence, not a boolean, and the
    evidence is per micro. These build their own proof files in a temp dir; the
    real one is never touched and never created."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='futproof')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.proof = os.path.join(self.dir, futures.PROOF_FILE)
        self.module = os.path.join(self.dir, 'webull_futures.py')
        with open(self.module, 'w', encoding='utf-8') as fh:
            fh.write('# a stand-in for the futures module\n')

    def _block(self, root, **over):
        block = {'proof_version': futures.PROOF_VERSION,
                 'written_at': '2026-09-16T10:00:00-04:00', 'root': root,
                 'contract': root + 'Z6',
                 'module_sha256': futures.module_sha256(self.module),
                 'steps': [{'name': n, 'ok': True, 'at': 'x', 'detail': 'y'}
                           for n in futures.PROOF_STEPS]}
        block.update(over)
        return block

    def _write(self, *roots, **over):
        doc = {r: self._block(r, **over) for r in roots}
        with open(self.proof, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh)
        return doc

    def _save(self, doc):
        with open(self.proof, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh)

    def _state(self, sym):
        return futures.protection_proof_state(sym, self.proof, self.module)

    def test_no_proof_file_means_shut_and_says_so(self):
        for sym in ('MES', 'MNQ'):
            ok, why = self._state(sym)
            self.assertFalse(ok)
            self.assertIn('never been run', why)
            self.assertIn('--symbol %s --live' % sym, why)

    def test_malformed_proof_is_not_a_proof(self):
        with open(self.proof, 'w', encoding='utf-8') as fh:
            fh.write('{not json at all')
        ok, why = self._state('MES')
        self.assertFalse(ok)
        self.assertIn('cannot be read', why)

    def test_a_proof_from_another_version_is_not_accepted(self):
        self._write('MES', proof_version=futures.PROOF_VERSION + 7)
        ok, why = self._state('MES')
        self.assertFalse(ok)
        self.assertIn('different proof version', why)

    def test_a_failed_step_names_the_step_and_keeps_the_door_shut(self):
        doc = self._write('MES')
        doc['MES']['steps'][4]['ok'] = False
        self._save(doc)
        ok, why = self._state('MES')
        self.assertFalse(ok)
        self.assertIn(futures.PROOF_STEPS[4], why)

    def test_a_proof_that_stopped_early_proves_only_what_it_reached(self):
        doc = self._write('MNQ')
        doc['MNQ']['steps'] = doc['MNQ']['steps'][:3]
        self._save(doc)
        ok, why = self._state('MNQ')
        self.assertFalse(ok)
        self.assertIn('flat_confirmed', why)

    def test_a_malformed_block_for_one_micro_shuts_only_that_one(self):
        doc = self._write('MES', 'MNQ')
        doc['MNQ'] = 'proved, honest'
        self._save(doc)
        ok, why = self._state('MNQ')
        self.assertFalse(ok)
        self.assertIn('not a proof document', why)
        self.assertTrue(self._state('MES')[0])
        doc = self._write('MES', 'MNQ')
        doc['MNQ']['steps'] = [{'ok': True}]        # a step with no name
        self._save(doc)
        ok, why = self._state('MNQ')
        self.assertFalse(ok)
        self.assertIn('malformed step', why)
        self.assertTrue(self._state('MES')[0])

    def test_a_block_that_records_the_other_micros_run_is_refused(self):
        doc = self._write('MES')
        doc['MNQ'] = self._block('MES')             # an MES run filed as MNQ
        self._save(doc)
        ok, why = self._state('MNQ')
        self.assertFalse(ok)
        self.assertIn('records a MES run', why)

    def test_editing_the_futures_module_kills_both_proofs(self):
        self._write('MES', 'MNQ')
        self.assertTrue(self._state('MES')[0])
        self.assertTrue(self._state('MNQ')[0])
        with open(self.module, 'a', encoding='utf-8') as fh:
            fh.write('# one more line, and the proof no longer applies\n')
        for sym in ('MES', 'MNQ'):
            ok, why = self._state(sym)
            self.assertFalse(ok)
            self.assertIn('has changed since the %s proof' % sym, why)

    def test_a_clean_proof_that_still_matches_opens_that_micros_door(self):
        self._write('MNQ')
        ok, why = self._state('MNQ')
        self.assertTrue(ok)
        self.assertIn('MNQZ6', why)

    def test_proving_one_micro_does_not_open_the_other(self):
        self._write('MES')
        self.assertTrue(self._state('MES')[0])
        ok, why = self._state('MNQ')
        self.assertFalse(ok)
        self.assertIn('records no MNQ proof', why)
        self.assertIn('it has MES', why)
        self.assertIn('--symbol MNQ --live', why)

    def test_a_full_size_call_is_gated_on_its_micro_and_the_reason_says_so(self):
        self._write('MES')
        ok, why = self._state('ES')
        self.assertTrue(ok)
        self.assertIn('trades as MES here', why)
        ok, why = self._state('NQ')
        self.assertFalse(ok)
        self.assertIn('an NQ call trades as MNQ here', why)
        self.assertIn('records no MNQ proof', why)

    def test_a_symbol_the_loop_was_never_proven_on_is_refused(self):
        self._write('MES', 'MNQ')
        ok, why = self._state('MGC')
        self.assertFalse(ok)
        self.assertIn('not one of the two micros', why)

    def test_the_summary_line_is_true_only_when_both_micros_are_proven(self):
        self._write('MES')
        ready, why = futures.protection_proof_summary(self.proof, self.module)
        self.assertFalse(ready)
        self.assertIn('MNQ', why)
        self._write('MES', 'MNQ')
        ready, why = futures.protection_proof_summary(self.proof, self.module)
        self.assertTrue(ready)
        self.assertIn('MES', why)
        self.assertIn('MNQ', why)

    def test_an_open_is_refused_for_the_unproven_micro_by_name(self):
        """The whole path: execute() reading the real gate, with the repo's
        files redirected into this temp dir."""
        self._write('MES')
        real = futures._repo_file

        def fake(name):
            if name == futures.PROOF_FILE:
                return self.proof
            if name == 'webull_futures.py':
                return self.module
            return real(name)

        with patch.object(futures, '_repo_file', fake):
            wb = Mock()
            ok, msg = futures.execute(wb, None,
                                      {'action': 'OPEN', 'symbol': 'MNQ',
                                       'direction': 'LONG', 'limit': None},
                                      'room|MNQ', lambda _: None)
            self.assertFalse(ok)
            self.assertIn('MNQ', msg)
            self.assertIn('no order was sent', msg)
            wb.assert_not_called()
            # ...and the micro that WAS proven is not held by the other's gate.
            self.assertTrue(futures.protective_entries_ready('MES'))
            self.assertFalse(futures.protective_entries_ready('MNQ'))


class TheProofHarness(unittest.TestCase):
    """futures_protection_proof.py walked end to end against a fake broker, for
    each micro. The proof it writes lands in a temp dir — never in the repo."""

    def setUp(self):
        import futures_protection_proof as fpp
        self.fpp = fpp
        self.dir = tempfile.mkdtemp(prefix='futproofrun')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.here = patch.object(fpp, 'HERE', self.dir)
        self.here.start()
        self.addCleanup(self.here.stop)

    def _broker(self, contract='MESZ6', fill='6800.25', exit_px='6800.00',
                stop_symbol=None):
        placed, state = {}, {'stop': 'SUBMITTED'}
        wb = Mock(futures_account_id='F1')
        api = wb.trade.order_v3

        def place(account, orders):
            o = orders[0]
            placed[o['client_order_id']] = o
            return Mock(status_code=200, **{'json.return_value':
                        {'data': {'order_id': 'B%d' % len(placed)}}})

        def detail(account, cid):
            if cid.startswith('proofstop'):
                row = dict(placed.get(cid, {}), status=state['stop'])
                if stop_symbol:
                    row['symbol'] = stop_symbol
            else:
                row = {'client_order_id': cid, 'symbol': contract,
                       'side': 'BUY' if cid.startswith('proofentry') else 'SELL',
                       'status': 'FILLED', 'quantity': '1',
                       'filled_quantity': '1',
                       'avg_fill_price': fill if
                       cid.startswith('proofentry') else exit_px}
            return Mock(status_code=200, **{'json.return_value': {'orders': [row]}})

        def cancel(account, cid):
            state['stop'] = 'CANCELLED'
            return Mock(status_code=200)

        api.place_order.side_effect = place
        api.get_order_detail.side_effect = detail
        api.cancel_order.side_effect = cancel
        wb._try_calls.side_effect = lambda *a, **k: ({'positions': []}, 'fake')
        return wb, api, state

    def _walk(self, root, contract, **kw):
        wb, api, state = self._broker(contract=contract, **kw)
        proof = self.fpp.Proof(root, contract, 'F1')
        proof.step('preflight', True, 'fake')
        code = self.fpp.run_live(wb, 'F1', api, root, contract, proof)
        return code, proof, api

    def test_a_clean_mes_run_records_every_step_and_opens_the_mes_gate(self):
        code, proof, api = self._walk('MES', 'MESZ6')
        self.assertEqual(code, 0)
        self.assertTrue(proof.clean())
        names = [s['name'] for s in proof.doc['steps']]
        self.assertEqual(names, list(futures.PROOF_STEPS))
        path, warn = proof.write()
        self.assertEqual(os.path.dirname(path), self.dir)
        self.assertEqual(warn, '')
        self.assertTrue(futures.protection_proof_state('MES', path)[0])
        # ...and MNQ is untouched by it.
        ok, why = futures.protection_proof_state('MNQ', path)
        self.assertFalse(ok)
        self.assertIn('records no MNQ proof', why)
        # One entry, one stop, one flatten. Never a second exit.
        self.assertEqual(api.place_order.call_count, 3)
        self.assertEqual(api.cancel_order.call_count, 1)

    def test_a_clean_mnq_run_walks_the_same_loop_on_the_other_micro(self):
        code, proof, api = self._walk('MNQ', 'MNQZ6', fill='25000.25',
                                      exit_px='25000.00')
        self.assertEqual(code, 0)
        self.assertTrue(proof.clean())
        self.assertEqual(proof.doc['point_value'], 2.0)
        stop = proof.doc['orders']['stop']
        self.assertEqual(stop['stop_price'], '24990.25')   # 10 points under
        path, _warn = proof.write()
        self.assertTrue(futures.protection_proof_state('MNQ', path)[0])
        self.assertEqual(api.place_order.call_count, 3)
        self.assertEqual(api.cancel_order.call_count, 1)

    def test_proving_one_micro_merges_and_leaves_the_others_proof_intact(self):
        path = os.path.join(self.dir, futures.PROOF_FILE)
        mes = {'proof_version': futures.PROOF_VERSION, 'root': 'MES',
               'contract': 'MESZ6', 'written_at': '2026-09-16T10:00:00-04:00',
               'module_sha256': futures.module_sha256(),
               'orders': {'entry': {'client_order_id': 'proofentry1'}},
               'steps': [{'name': n, 'ok': True, 'at': 'x', 'detail': 'y'}
                         for n in futures.PROOF_STEPS]}
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'MES': mes}, fh)

        code, proof, _api = self._walk('MNQ', 'MNQZ6', fill='25000.25',
                                       exit_px='25000.00')
        self.assertEqual(code, 0)
        proof.write()
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
        self.assertEqual(sorted(doc), ['MES', 'MNQ'])
        self.assertEqual(doc['MES'], mes)          # byte for byte, untouched
        self.assertTrue(futures.protection_proof_state('MES', path)[0])
        self.assertTrue(futures.protection_proof_state('MNQ', path)[0])

    def test_an_unreadable_proof_file_is_replaced_and_said_out_loud(self):
        path = os.path.join(self.dir, futures.PROOF_FILE)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('{ this was never a proof')
        code, proof, _api = self._walk('MES', 'MESZ6')
        self.assertEqual(code, 0)
        _path, warn = proof.write()
        self.assertIn('could not be read', warn)
        self.assertTrue(futures.protection_proof_state('MES', path)[0])

    def test_a_stop_that_does_not_match_stops_the_run_and_writes_nothing(self):
        code, proof, api = self._walk('MES', 'MESZ6', stop_symbol='MNQZ6')
        self.assertEqual(code, 5)
        self.assertFalse(proof.clean())
        # entry + the one stop attempt, and nothing after it
        self.assertEqual(api.place_order.call_count, 2)
        api.cancel_order.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.dir,
                                                     futures.PROOF_FILE)))

    def test_the_batch_file_never_sends_anything_itself(self):
        bat = os.path.join(os.path.dirname(os.path.abspath(futures.__file__)),
                           'PROVE FUTURES STOPS.bat')
        for line in open(bat, encoding='utf-8'):
            if line.strip().startswith('python '):
                self.assertNotIn('--live', line)


if __name__ == '__main__':
    unittest.main()
