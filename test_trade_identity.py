import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from trade_identity import reconcile


class IdentityTests(unittest.TestCase):
    def test_name_matches_never_become_verified_and_manual_stays_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            db=sqlite3.connect(out/'callers.sqlite3')
            db.executescript('''CREATE TABLE ledger_records(record_id TEXT,kind TEXT,caller TEXT,room TEXT,channel_id TEXT,payload TEXT,current INTEGER);
            CREATE TABLE account_sightings(discord_user_id TEXT,channel_id TEXT,display_name TEXT);
            CREATE TABLE confirmed_accounts(discord_user_id TEXT,caller_name TEXT,evidence_json TEXT);
            CREATE TABLE channels(channel_id TEXT,label TEXT);''')
            db.execute("INSERT INTO confirmed_accounts VALUES('123','Brett','{}')")
            db.execute("INSERT INTO account_sightings VALUES('123','honey','Brett')")
            db.execute("INSERT INTO channels VALUES('honey','Honey')")
            for rid,payload in [('candidate',{'author_id':'123'}),('manual',{'manual':True}),('explicit',{'trader_id':'123'})]:
                db.execute('INSERT INTO ledger_records VALUES(?,?,?,?,?,?,1)',(rid,'reconciled_trade','Brett','Honey',None,json.dumps(payload)))
            db.commit()
            first=reconcile(out)
            self.assertEqual(first,reconcile(out))
            actual=dict(db.execute('SELECT record_id,trader_id FROM trade_identity_links'))
            self.assertEqual(actual,{'candidate':None,'manual':None,'explicit':'123'})
            merged=db.execute("SELECT recorded_caller,attribution_name,candidate_trader_id,verified_trader_id FROM trade_attribution WHERE record_id='candidate'").fetchone()
            self.assertEqual(merged,('Brett','Brett','123',None))
            db.execute("UPDATE ledger_records SET caller='?' WHERE record_id='candidate'")
            db.execute("INSERT INTO trade_source_recovery VALUES('candidate','source_name_candidate','Poster','[]','Posting name only')")
            db.commit()
            reconcile(out)
            merged=db.execute("SELECT recorded_caller,attribution_name,name_basis,verified_trader_id FROM trade_attribution WHERE record_id='candidate'").fetchone()
            self.assertEqual(merged,(None,'Poster','log_candidate',None))
            db.close()


if __name__=='__main__':
    unittest.main()
