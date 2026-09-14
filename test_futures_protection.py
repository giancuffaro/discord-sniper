"""Offline checks: unsafe futures entries never reach a broker."""
import unittest
from unittest.mock import Mock

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


if __name__ == '__main__':
    unittest.main()
