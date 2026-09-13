import sqlite3
import tempfile
import unittest
from pathlib import Path
from caller_ledger import channel_accounts


class ChannelAccountTests(unittest.TestCase):
    def test_channel_identity_and_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            self.assertFalse(channel_accounts(out)['available'])
            with sqlite3.connect(out/'callers.sqlite3') as db:
                db.execute('CREATE TABLE account_sightings(channel_id TEXT,discord_user_id TEXT,display_name TEXT,server_id TEXT)')
                db.executemany('INSERT INTO account_sightings VALUES(?,?,?,?)',[
                    ('options','111','Nitro Trades','server'),
                    ('futures','222','Nitro Trades','server'),
                    ('honey','333','Brett','honey-server'),
                    ('honey','333','Brett (Admin)','honey-server')])
            result=channel_accounts(out)
            self.assertTrue(result['available'])
            self.assertEqual(len(result['accounts']),3)
            self.assertTrue(all(x['win_pct'] is None for x in result['accounts']))
            self.assertEqual({x['channel_id'] for x in result['accounts'] if x['user_id']=='333'},{'honey'})
            self.assertEqual({x['user_id'] for x in result['accounts'] if x['name']=='Nitro Trades'},{'111','222'})


if __name__=='__main__':
    unittest.main()
