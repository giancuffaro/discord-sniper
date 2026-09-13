"""Recover provenance from retained logs without manufacturing caller identities."""
import json
import re
import sqlite3
from datetime import datetime
from collections import Counter
from caller_ledger import ROOT, OUT, digest


def recover(root=ROOT,out=OUT):
    db=sqlite3.connect(out/'callers.sqlite3')
    db.execute('''CREATE TABLE IF NOT EXISTS trade_source_recovery(record_id TEXT PRIMARY KEY,
        classification TEXT, recovered_caller TEXT, evidence_json TEXT, limitation TEXT)''')
    events=[]
    path=root/'trades.log'
    for line_no,line in enumerate(path.read_text(encoding='utf-8',errors='replace').splitlines(),1):
        if '\t' not in line:
            continue
        stamp,body=line.split('\t',1)
        if not re.match(r'(ADOPTED\s|ADOPT\s|AI READ\s|WORKING\s|ORDER IN\s)',body):
            continue
        try:
            ts=datetime.fromisoformat(stamp).timestamp()
        except ValueError:
            continue
        events.append((ts,{'file':'trades.log','line':line_no,'timestamp':stamp,'text':body,'hash':digest(line)}))
    counts=Counter()
    for rid,payload in db.execute("SELECT record_id,payload FROM ledger_records WHERE current=1 AND kind='reconciled_trade'").fetchall():
        row=json.loads(payload)
        if row.get('caller') not in ('?','Gian',None,'') or str(row.get('manual')).lower() in ('true','1'):
            continue
        try:
            opened=float(row.get('opened_ts') or 0)
        except ValueError:
            opened=0
        symbol=row.get('symbol') or ''
        nearby=[e for t,e in events if opened and abs(t-opened)<=3]
        related=[e for e in nearby if symbol and re.search(r'\b'+re.escape(symbol)+r'\b',e['text'])]
        adopted=[e for e in related if re.match(r'ADOPTED\s+'+re.escape(symbol)+r'\s+x',e['text'])]
        evidence=[];caller=None
        if adopted:
            classification='broker_adoption'
            evidence=adopted+[e for e in related if e['text'].startswith('ADOPT ')]
            limitation='Stored opening time matches broker adoption, not original entry. Original caller remains unknown; adoption alone does not prove a manual trade.'
        else:
            ai=[e for e in nearby if e['text'].startswith('AI READ') and re.search(r'->\s+BTO\s+'+re.escape(symbol)+r'\s',e['text'])]
            posted=set()
            for e in ai:
                match=re.search(r"AI READ\s+'(.+?) posted ",e['text'])
                if match:
                    posted.add(match[1])
            if len(posted)==1 and any(e['text'].startswith('ORDER IN') for e in related):
                caller=next(iter(posted));classification='source_name_candidate';evidence=ai+related
                limitation='Nearby AI READ and order events identify a candidate posting name, not verified human trader/account ownership.'
            else:
                classification='no_recovery';evidence=related
                limitation='No unambiguous caller-origin evidence in the timestamp-matched event logs.'
        db.execute('INSERT OR REPLACE INTO trade_source_recovery VALUES(?,?,?,?,?)',
                   (rid,classification,caller,json.dumps(evidence,ensure_ascii=False),limitation))
        counts[classification]+=1
    db.commit()
    summary={'counts':dict(counts),'scope':'Missing/Gian caller records; adoption is provenance only, never a trader-ID assignment'}
    (out/'LOG-RECOVERY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    rows=db.execute('''SELECT r.date,r.symbol,r.caller,s.classification,s.recovered_caller,s.evidence_json
      FROM ledger_records r JOIN trade_source_recovery s USING(record_id) WHERE r.current=1
      ORDER BY r.date,r.symbol''').fetchall()
    lines=['# Log recovery','',summary['scope'],'',
           '| Date | Symbol | Existing caller | Recovery | Candidate name | Log lines |',
           '|---|---|---|---|---|---|']
    for date,symbol,old,kind,name,evidence in rows:
        nums=', '.join(str(e['line']) for e in json.loads(evidence))
        lines.append('| '+' | '.join(str(x or '').replace('|','/') for x in (date,symbol,old,kind,name,nums))+' |')
    (out/'LOG-RECOVERY.md').write_text('\n'.join(lines),encoding='utf-8')
    db.close()
    return summary


if __name__=='__main__':
    print(json.dumps(recover(),indent=2))
