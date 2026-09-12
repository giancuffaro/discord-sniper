import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import openai_reader_trial as trial


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'budget.sqlite3'
        self.db = trial.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_budget_persists_across_connections(self):
        self.assertTrue(trial.reserve(self.db, 'one', 4_999_999))
        other = trial.connect(self.path)
        try:
            self.assertFalse(trial.reserve(other, 'two', 2))
            self.assertTrue(trial.reserve(other, 'three', 1))
            self.assertFalse(trial.reserve(other, 'four', 1))
        finally:
            other.close()

    def test_request_cap_and_duplicate(self):
        self.assertTrue(trial.reserve(self.db, '0', 1))
        self.assertFalse(trial.reserve(self.db, '0', 1))
        for i in range(1,100):
            self.assertTrue(trial.reserve(self.db, str(i), 1))
        self.assertFalse(trial.reserve(self.db, '101', 1))

    def test_only_successful_retry_resolves_previous_error(self):
        failed = (json.dumps({'id':'a','ai_raw':{'_error':'HTTP_429'}}),)
        success = (json.dumps({'id':'a','ai_raw':{'action':'NONE'}}),)
        self.assertTrue(trial.unresolved_failure([failed]))
        self.assertFalse(trial.unresolved_failure([failed,success]))
        self.assertTrue(trial.unresolved_failure([success,failed]))
        self.assertTrue(trial.unresolved_failure([(None,),success]))

    def test_full_budget_uses_known_cost_but_retains_uncertain_reservations(self):
        trial.reserve(self.db, 'a', 10000)
        trial.reserve(self.db, 'b', 20000)
        with self.db:
            self.db.execute('UPDATE attempts SET result=? WHERE id=?',
                (json.dumps({'ai_raw':{'_usage':{'input_tokens':100,'output_tokens':10}}}), 'a'))
        with patch.object(trial, 'FULL_SCAN', True):
            self.assertEqual(trial.budget_used(self.db),20280)

    def test_full_replay_rate_limit_backoff_and_skip_success(self):
        trial.reserve(self.db,'a',100)
        with self.db:
            self.db.execute('UPDATE attempts SET result=? WHERE id=?',
                (json.dumps({'id':'a','ai_raw':{'action':'NONE'}}),'a'))
        stop = Mock()
        stop.wait.return_value = False
        responses = [{'ai_raw':{'_error':'HTTP_429','_error_code':'rate_limit_exceeded'}},
                     {'ai_raw':{'action':'NONE'}}]
        with patch.object(trial,'read_one',side_effect=responses) as reader:
            status = trial.full_replay([{'id':'a'},{'id':'b'}], [], 'secret', self.db,stop,Mock())
        self.assertIn('complete',status)
        self.assertEqual(reader.call_count,2)
        self.assertEqual([c.args[0] for c in stop.wait.call_args_list],[4,60])

    def test_full_replay_quota_does_not_retry(self):
        stop = Mock()
        stop.wait.return_value = False
        with patch.object(trial,'read_one',return_value={'ai_raw':{'_error':'HTTP_429','_error_code':'insufficient_quota'}}) as reader:
            status = trial.full_replay([{'id':'b'}], [], 'secret', self.db,stop,Mock())
        self.assertIn('insufficient_quota',status)
        self.assertEqual(reader.call_count,1)

    def test_explicit_retry_preserves_budget_and_cannot_repeat_success(self):
        trial.reserve(self.db, 'a', 100)
        with self.db:
            self.db.execute('UPDATE attempts SET result=? WHERE id=?',
                (json.dumps({'id':'a','ai_raw':{'_error':'HTTP_429'}}), 'a'))
        def fake_read(row, allowed, key, db):
            self.assertTrue(trial.reserve(db, row['id'], 200))
            return {'id':row['id'], 'ai_raw':{'action':'NONE'}}
        with patch.object(trial, 'read_one', side_effect=fake_read) as reader:
            result = trial.retry_one([{'id':'a'}], [], 'secret', self.db)
            self.assertEqual(result['id'], 'a')
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(self.db.execute('SELECT SUM(reserved) FROM attempts').fetchone()[0],300)
            with self.assertRaises(ValueError):
                trial.retry_one([{'id':'a'}], [], 'secret', self.db)
            self.assertEqual(reader.call_count, 1)

    def test_failed_request_not_refunded_or_retried(self):
        row = {'id':'a','text':'hello','prior':[], 'author':'x', 'postedAt':1}
        opener = Mock(side_effect=TimeoutError())
        result = trial.read_one(row, [], 'test-key', self.db, opener)
        self.assertIn('_error', result['ai_raw'])
        self.assertIsNone(trial.read_one(row, [], 'test-key', self.db, opener))
        self.assertEqual(opener.call_count, 1)
        self.assertGreater(self.db.execute('SELECT reserved FROM attempts').fetchone()[0],0)

    def test_completed_response_and_no_secret_in_result(self):
        row = {'id':'a','text':'hello','prior':[], 'author':'x', 'postedAt':1}
        response = {'status':'completed','output':[{'content':[{'type':'output_text', 'text':'{"action":"NONE"}'}]}],
                    'usage':{'input_tokens':100,'output_tokens':10}}
        opener = Mock(return_value=io.BytesIO(json.dumps(response).encode()))
        result = trial.read_one(row, [], 'test-secret', self.db, opener)
        self.assertEqual(result['ai_raw']['action'],'NONE')
        self.assertNotIn('test-secret', json.dumps(result))
        payload = json.loads(opener.call_args.args[0].data)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'],600)


if __name__ == '__main__':
    unittest.main()
