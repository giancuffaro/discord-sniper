"""Correlate historical entries independently of exit ownership (research only)."""
import json
import re
import sqlite3
from datetime import datetime
from collections import Counter
from caller_ledger import ROOT, OUT

ORDER=re.compile(r'^(\S+)\tORDER IN (?:\[\w+\] )?BUY\s+(\d+)\s+(\S+)\s+([\d.]+)([CP])\s+(\d{4}-\d\d-\d\d)\s+@\s+([\d.]+)')


def read_orders(path):
    lines=path.read_text(encoding='utf-8',errors='replace').splitlines()
    orders=[]
    for index,line in enumerate(lines):
        m=ORDER.match(line)
        if not m:
            continue
        stamp,qty,sym,strike,side,expiry,price=m.groups()
        ts=datetime.fromisoformat(stamp).timestamp()
        callers={}
        for offset,following in enumerate(lines[index+1:index+7],index+2):
            if '\t' not in following:
                continue
            at,body=following.split('\t',1)
            try:
                delta=datetime.fromisoformat(at).timestamp()-ts
            except ValueError:
                continue
            if not 0<=delta<=2:
                continue
            w=re.match(r'WORKING\s+'+re.escape(sym)+r'\s+.+?\s+(.+?)\x27s call,',body)
            if w and w[1]!='?':
                callers[w[1]]=offset
        if len(callers)==1:
            caller=next(iter(callers))
            orders.append(dict(date=stamp[:10],timestamp=ts,symbol=sym,strike=float(strike),side=side,
                expiry=expiry,qty=int(qty),caller=caller,order_line=index+1,caller_line=callers[caller]))
    return orders


def match_orders(row,orders):
    try:
        strike=float(row.get('strike'))
    except (TypeError,ValueError):
        return [],[]
    side=str(row.get('side') or '')[:1].upper()
    candidates=[o for o in orders if o['date']==row.get('date') and o['symbol']==row.get('symbol')
        and o['strike']==strike and o['side']==side and o['expiry']==row.get('expiry')]
    try:
        opened=float(row.get('opened_ts') or 0)
        qty=float(row.get('qty') or 0)
    except ValueError:
        opened=qty=0
    timed=[o for o in candidates if opened and 0<=opened-o['timestamp']<=120 and qty==o['qty']]
    return candidates,timed


def recover_entries(root=ROOT,out=OUT):
    orders=read_orders(root/'trades.log')
    db=sqlite3.connect(out/'callers.sqlite3')
    db.execute('''CREATE TABLE IF NOT EXISTS entry_attribution(record_id TEXT PRIMARY KEY,
        entry_caller TEXT,entry_basis TEXT,exit_method TEXT,evidence_json TEXT)''')
    results=Counter()
    for rid,payload in db.execute("SELECT record_id,payload FROM ledger_records WHERE current=1 AND kind='reconciled_trade'").fetchall():
        row=json.loads(payload)
        candidates,timed=match_orders(row,orders)
        names={o['caller'] for o in timed}
        recorded=row.get('caller')
        recorded=recorded if recorded not in (None,'','?','Gian') else None
        adopted=db.execute('SELECT classification FROM trade_source_recovery WHERE record_id=?',(rid,)).fetchone()
        if adopted and adopted[0]=='broker_adoption':
            timed=[];names=set()
        if len(timed)==1 and len(names)==1:
            found=next(iter(names))
            if recorded and recorded.casefold()!=found.casefold():
                name,basis=recorded,'conflict_review'
            else:
                name,basis=found,'contract_time_quantity_match'
        elif recorded:
            name,basis=recorded,'recorded_caller'
        elif candidates:
            name,basis=None,'same_contract_candidates'
        else:
            name,basis=None,'unknown'
        why=str(row.get('why') or '')
        exit_method='external_broker_exit' if "bot didn't send this sell" in why else row.get('exit_by')
        db.execute('INSERT OR REPLACE INTO entry_attribution VALUES(?,?,?,?,?)',
            (rid,name,basis,exit_method,json.dumps(candidates)))
        results[basis]+=1
    db.commit();db.close()
    result=dict(results)
    (out/'ENTRY-RECOVERY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    print(json.dumps(recover_entries(),indent=2))
