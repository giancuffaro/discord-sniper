"""Read-only-source integration of the existing research ledgers.

python research_ledger.py refresh
python research_ledger.py search CPS
python research_ledger.py gaps
"""
import argparse
import csv
import io
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from caller_ledger import ROOT, OUT, build, digest


def integrate(root=ROOT, out=OUT):
    db = sqlite3.connect(out / 'callers.sqlite3')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS ledger_records(
      record_id TEXT PRIMARY KEY, kind TEXT, source_path TEXT, source_row INTEGER,
      current INTEGER, date TEXT, channel_id TEXT, caller_id TEXT, caller TEXT,
      room TEXT, symbol TEXT, contract TEXT, event_key TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS research_links(
      from_id TEXT, to_id TEXT, basis TEXT, PRIMARY KEY(from_id,to_id,basis));
    CREATE TABLE IF NOT EXISTS research_imports(
      source_path TEXT PRIMARY KEY, content_hash TEXT, imported_at TEXT, row_count INTEGER);
    CREATE INDEX IF NOT EXISTS research_symbol ON ledger_records(symbol,date);
    CREATE VIEW IF NOT EXISTS research_gaps AS
      SELECT record_id,kind,source_path,source_row,channel_id,caller_id,
      CASE WHEN channel_id IS NULL THEN 'channel identity missing' END channel_gap,
      CASE WHEN caller_id IS NULL THEN 'account identity missing' END caller_gap
      FROM ledger_records WHERE current=1 AND (channel_id IS NULL OR caller_id IS NULL);
    ''')
    sources = [(root / 'master_alerts.csv','alert_decision'),
               (root / 'master_ledger.csv','reconciled_trade'),
               (root / 'master_broker.csv','broker_record'),
               (root / 'master_postmortems.csv','postmortem')]
    sources += [(p,'caller_counterfactual') for p in sorted((root / 'daily-reports').glob('CALLER-OUTCOMES-*.csv'))]
    # Read each file once. Rebuilt ledgers replace the current view, retaining old rows.
    for path, kind in sources:
        if not path.exists():
            continue
        raw = path.read_bytes()
        rel = str(path.relative_to(root))
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames or any(h is None for h in reader.fieldnames):
            raise ValueError('Invalid header: '+rel)
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError('Incomplete CSV snapshot: '+rel)
        db.execute('UPDATE ledger_records SET current=0 WHERE source_path=?',(rel,))
        for n, original in enumerate(rows,2):
            row = {k:(v if v.strip() else None) for k,v in original.items()}
            # Never infer IDs from labels, caller names, timestamps, or contract similarity.
            cid = row.get('channel_id')
            uid = row.get('discord_user_id') or row.get('author_id')
            rid = digest(rel,n,row)
            db.execute('INSERT INTO ledger_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET current=1',
                       (rid,kind,rel,n,1,row.get('date'),cid,uid,row.get('caller') or row.get('who'),
                        row.get('room'),row.get('symbol'),row.get('occ') or row.get('contract'),
                        row.get('ledger_key') if kind=='alert_decision' else row.get('key'),
                        json.dumps(row,ensure_ascii=False)))
        db.execute('INSERT OR REPLACE INTO research_imports VALUES(?,?,?,?)',
                   (rel,digest(raw.hex()),datetime.now(timezone.utc).isoformat(),len(rows)))
    # Only link an explicit ledger key to one current trade on the same date.
    # These are ledger-provided links, not proof of broker fills or caller identity.
    db.execute('DELETE FROM research_links WHERE basis=?',('explicit_ledger_key_same_date',))
    db.execute('''INSERT OR IGNORE INTO research_links
      SELECT a.record_id,MIN(t.record_id),'explicit_ledger_key_same_date'
      FROM ledger_records a JOIN ledger_records t ON a.event_key=t.event_key AND a.date=t.date
      WHERE a.current=1 AND t.current=1 AND a.kind='alert_decision'
      AND t.kind='reconciled_trade' AND a.event_key IS NOT NULL
      GROUP BY a.record_id HAVING COUNT(*)=1''')
    db.commit()
    result = dict(db.execute('SELECT kind,COUNT(*) FROM ledger_records WHERE current=1 GROUP BY kind'))
    result['explicit_links'] = db.execute('SELECT COUNT(*) FROM research_links').fetchone()[0]
    result['records_with_identity_gaps'] = db.execute('SELECT COUNT(*) FROM research_gaps').fetchone()[0]
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    (out / 'INTEGRATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    db.close()
    return result


def query(text=None, gaps=False):
    db = sqlite3.connect((OUT / 'callers.sqlite3').as_uri()+'?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    if gaps:
        rows = db.execute('SELECT * FROM research_gaps LIMIT 100')
    else:
        pattern = '%'+text.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        rows = db.execute('''SELECT record_id,kind,source_path,source_row,date,channel_id,
          caller_id,caller,room,symbol,payload FROM ledger_records
          WHERE current=1 AND payload LIKE ? ESCAPE '\\'
          UNION ALL SELECT m.record_id,'raw_message',s.source_path,s.line_number,
          m.posted_at,a.channel_id,NULL,a.display_name,c.label,NULL,m.raw_text
          FROM messages m JOIN author_observations a USING(observation_id)
          JOIN channels c USING(channel_id)
          JOIN source_rows s ON s.rowid=(SELECT MIN(s2.rowid) FROM source_rows s2
            WHERE s2.record_id=m.record_id)
          WHERE m.raw_text LIKE ? ESCAPE '\\' OR a.display_name LIKE ? ESCAPE '\\'
          LIMIT 100''',(pattern,pattern,pattern))
    result = [dict(row) for row in rows]
    db.close()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['refresh','search','gaps'])
    parser.add_argument('text',nargs='?')
    args=parser.parse_args()
    if args.action=='refresh':
        build()
        result=integrate()
        from trade_identity import reconcile
        result['trader_identity']=reconcile()
    elif args.action=='search':
        if not args.text:
            parser.error('search requires text')
        result=query(args.text)
    else:
        result=query(gaps=True)
    print(json.dumps(result,indent=2,ensure_ascii=False))
