import os
import tempfile
import threading
import unittest

from request_journal import RequestJournal


class RequestJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "requests.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_result_survives_restart(self):
        first = RequestJournal(self.path)
        self.assertEqual(first.begin("abc"), (True, None))
        first.finish("abc", (True, "placed"))
        self.assertEqual(RequestJournal(self.path).begin("abc"),
                         (False, (True, "placed")))

    def test_unresolved_claim_fails_closed(self):
        self.assertEqual(RequestJournal(self.path).begin("abc"), (True, None))
        owned, result = RequestJournal(self.path).begin("abc")
        self.assertFalse(owned)
        self.assertFalse(result[0])
        self.assertIn("unresolved earlier submission", result[1])

    def test_concurrent_claim_has_one_owner(self):
        gate = threading.Barrier(6)
        answers = []

        def claim():
            gate.wait()
            answers.append(RequestJournal(self.path).begin("same")[0])

        threads = [threading.Thread(target=claim) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(answers.count(True), 1)


if __name__ == "__main__":
    unittest.main()
