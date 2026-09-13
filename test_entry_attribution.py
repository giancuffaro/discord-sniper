import unittest
from entry_attribution import match_orders


class EntryMatchTests(unittest.TestCase):
    def test_full_contract_and_entry_time_required_regardless_of_manual_flag(self):
        o=dict(date='2026-09-11',symbol='SPY',strike=700.0,side='C',expiry='2026-09-11',qty=1,timestamp=1000,caller='Mike')
        r=dict(date='2026-09-11',symbol='SPY',strike='700',side='CALLS',expiry='2026-09-11',qty='1',opened_ts='1003',manual='True')
        self.assertEqual(match_orders(r,[o])[1],[o])
        for key,value in [('expiry','2026-09-18'),('side','PUTS'),('strike','701'),('date','2026-09-12'),('qty','2'),('opened_ts','2000')]:
            self.assertEqual(match_orders(dict(r,**{key:value}),[o])[1],[])


if __name__=='__main__':
    unittest.main()
