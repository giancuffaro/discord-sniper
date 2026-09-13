import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from trade_identity import reconcile


class IdentityTests(unittest.TestCase):
    def test_reviewed_trade_survives_ledger_row_renumbering_only_when_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            db=sqlite3.connect(out/'callers.sqlite3')
            db.executescript('''CREATE TABLE ledger_records(record_id TEXT,kind TEXT,caller TEXT,room TEXT,channel_id TEXT,payload TEXT,current INTEGER);
            CREATE TABLE account_sightings(discord_user_id TEXT,channel_id TEXT,display_name TEXT);
            CREATE TABLE confirmed_accounts(discord_user_id TEXT,caller_name TEXT,evidence_json TEXT);
            CREATE TABLE channels(channel_id TEXT,label TEXT);
            CREATE TABLE messages(record_id TEXT);''')
            db.execute("INSERT INTO confirmed_accounts VALUES('123','Trader','{}')")
            db.execute("INSERT INTO messages VALUES('source-message')")
            data={'date':'2026-08-26','occ':'SPY260827P00766000','source':'days-json'}
            db.execute('INSERT INTO ledger_records VALUES(?,?,?,?,?,?,1)',
                       ('new-row','reconciled_trade','Trader','Honey',None,json.dumps(data)))
            (out/'reviewed-trade-identities.json').write_text(json.dumps([{
                'record_id':'old-row','trader_id':'123',
                'match':{'kind':'reconciled_trade',**data},
                'evidence_message_ids':['source-message'],'reason':'original post',
            }]),encoding='utf-8')
            db.commit()
            reconcile(out)
            self.assertEqual(db.execute("SELECT trader_id,status FROM trade_identity_links WHERE record_id='new-row'").fetchone(),
                             ('123','source_supported'))
            db.execute('INSERT INTO ledger_records VALUES(?,?,?,?,?,?,1)',
                       ('second-row','reconciled_trade','Trader','Honey',None,json.dumps(data)))
            db.commit()
            reconcile(out)
            self.assertNotEqual(db.execute("SELECT status FROM trade_identity_links WHERE record_id='new-row'").fetchone()[0],
                                'source_supported')
            db.close()

    def test_name_matches_never_become_verified_and_manual_exit_is_not_entry_origin(self):
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
            self.assertEqual(db.execute("SELECT status FROM trade_identity_links WHERE record_id='manual'").fetchone()[0],
                             'candidate')
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
