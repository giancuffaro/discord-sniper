import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research_ledger import integrate


class IntegrationTests(unittest.TestCase):
    def test_explicit_links_blanks_revisions_and_repeated_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(name,headers,rows):
                with (root/name).open('w',newline='',encoding='utf-8') as f:
                    writer=csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)
            write('master_alerts.csv',['date','caller','ledger_key','symbol'],
                  [['2026-09-11','Demon','abc','CPS']])
            write('master_ledger.csv',['date','key','symbol'],[['2026-09-11','abc','CPS']])
            first=integrate(root,root)
            self.assertEqual(first,integrate(root,root))
            self.assertEqual(first['explicit_links'],1)
            db=sqlite3.connect(root/'callers.sqlite3')
            self.assertEqual(db.execute('SELECT channel_id,caller_id FROM ledger_records LIMIT 1').fetchone(),(None,None))
            # Ambiguous keys must not create a link; old snapshot stays queryable.
            write('master_ledger.csv',['date','key','symbol'],
                  [['2026-09-11','abc','CPS'],['2026-09-11','abc','IBM']])
            self.assertEqual(integrate(root,root)['explicit_links'],0)
            write('master_alerts.csv',['date','caller','ledger_key','symbol'],
                  [['2026-09-11','Demon','new','CPS']])
            integrate(root,root)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger_records WHERE kind='alert_decision' AND current=0").fetchone()[0],1)
            db.close()


if __name__=='__main__':
    unittest.main()
