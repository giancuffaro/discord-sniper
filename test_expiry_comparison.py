import unittest
from reader_measure import expiry_key


class ExpiryComparisonTests(unittest.TestCase):
    def test_equivalent_without_year(self):
        for value in ['9/01','09/1','09/01','Sep 1','September 1st','1 Sept','SEP. 01']:
            self.assertEqual(expiry_key(value),expiry_key('9/1'),value)

    def test_equivalent_with_year(self):
        for value in ['09/01/2026','9/1/26','Sep 1st, 2026','2026-09-01']:
            self.assertEqual(expiry_key(value),expiry_key('9/1/2026'),value)

    def test_no_invented_date(self):
        for a,b in [('9/1','1/9'),('9/1','9/2'),('9/1','9/1/2026'),
                    ('9/1/2026','9/1/2027'),('','9/1'),('next week','9/1'),
                    ('0DTE','9/1'),('2/30','3/2')]:
            self.assertNotEqual(expiry_key(a),expiry_key(b),(a,b))


if __name__ == '__main__':
    unittest.main()
