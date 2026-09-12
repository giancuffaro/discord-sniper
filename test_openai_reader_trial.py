import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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
