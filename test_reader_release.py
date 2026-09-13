import unittest
import ai_reader
from reader_measure import comparison_category


class ReaderReleaseTests(unittest.TestCase):
    def test_no_direction_defaults(self):
        for instrument in ('option','future'):
            for side in (None,'UNKNOWN'):
                r={'action':'OPEN','instrument':instrument,'ticker':'SPY','strike':500,'side':side}
                self.assertFalse(ai_reader.validate(r,'SPY 500',[])[0])
                self.assertEqual(ai_reader.canonical(r),'')
        self.assertEqual(ai_reader.canonical({'action':'OPEN','instrument':'future','ticker':'NQ','side':'SELL'}),'SHORT NQ')
        self.assertIn('500P',ai_reader.canonical({'action':'OPEN','instrument':'option','ticker':'SPY','strike':500,'side':'PUT'}))

    def test_report_categories(self):
        g={'ok':True}
        self.assertEqual(comparison_category({'action':'PREPARE'},{'action':'OPEN'},{},g),'action_schema_review')
        self.assertEqual(comparison_category({'action':'CLOSE','strike':500},{'action':'CLOSE'},{},g),'conversion_field_loss')
        p={'action':'OPEN','symbol':'NQ','direction':'SHORT','limit':20000}
        self.assertEqual(comparison_category(p,dict(p,direction='LONG'),{},g),'potential_wrong_direction')
        self.assertEqual(comparison_category(p,dict(p,limit=21000),{},g),'price_field_review')
        self.assertEqual(comparison_category(dict(p,expiry='9/01'),dict(p,expiry='9/1'),{},g),'agreement')


if __name__ == '__main__':
    unittest.main()
