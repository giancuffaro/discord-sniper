"""Auditable trader identity links and unresolved candidates for research only."""
import json
import sqlite3
from collections import defaultdict, Counter
from caller_ledger import OUT


def reconcile(out=OUT):
    db=sqlite3.connect(out/'callers.sqlite3')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS trade_identity_links(record_id TEXT PRIMARY KEY,
        trader_id TEXT, status TEXT NOT NULL, candidates_json TEXT, reason TEXT NOT NULL);
      DROP VIEW IF EXISTS attributed_research;
      CREATE VIEW attributed_research AS SELECT r.*, i.trader_id AS verified_trader_id,
        i.status AS identity_status,i.candidates_json,i.reason AS identity_reason
        FROM ledger_records r LEFT JOIN trade_identity_links i USING(record_id)
        WHERE r.current=1;
    ''')
    names=defaultdict(set)
    sightings=defaultdict(set)
    for uid,cid,name in db.execute('SELECT discord_user_id,channel_id,display_name FROM account_sightings'):
        names[name.strip().casefold()].add(uid)
        sightings[uid].add(cid)
    for uid,name,evidence in db.execute('SELECT * FROM confirmed_accounts'):
        info=json.loads(evidence)
        for alias in [name]+info.get('claimed_aliases',[]):
            if alias:
                names[alias.strip().casefold()].add(uid)
    labels=defaultdict(set)
    for cid,label in db.execute('SELECT channel_id,label FROM channels'):
        if label:
            labels[label.strip().casefold()].add(cid)
    known={row[0] for row in db.execute('SELECT discord_user_id FROM confirmed_accounts')}
    totals=Counter()
    by_kind=defaultdict(Counter)
    for rid,kind,caller,room,cid,payload in db.execute('SELECT record_id,kind,caller,room,channel_id,payload FROM ledger_records WHERE current=1').fetchall():
        data=json.loads(payload)
        trader=None
        candidates=[]
        if str(data.get('manual','')).casefold() in ('true','1','yes'):
            status,reason='manual','Manual position; not assigned to a signal caller'
        elif data.get('trader_id') in known:
            trader=data['trader_id']
            status,reason='source_trader_id','Explicit trader_id in source; source attribution retained'
        elif not caller or caller.strip() in ('?','unknown','Unknown'):
            status,reason='unresolved','Source has no named caller; needs originating alert or order link'
        else:
            candidates=sorted(names.get(caller.strip().casefold(),set()))
            rooms={cid} if cid else labels.get((room or '').strip().casefold(),set())
            scoped=[uid for uid in candidates if sightings[uid] & rooms]
            if scoped:
                candidates=scoped
            if len(candidates)==1:
                status='candidate'
                reason='Exact caller alias'+(' and observed channel' if scoped else '')+'; historical attribution requires source confirmation'
            elif candidates:
                status,reason='ambiguous','Multiple account IDs share this name; needs original message/account evidence'
            else:
                status,reason='unresolved','Caller account ID or alias not yet verified'
        db.execute('INSERT OR REPLACE INTO trade_identity_links VALUES(?,?,?,?,?)',
                   (rid,trader,status,json.dumps(candidates),reason))
        totals[status]+=1
        by_kind[kind][status]+=1
    db.commit()
    report={'statuses':dict(totals),'by_kind':{k:dict(v) for k,v in by_kind.items()},
            'note':'Candidates are not verified trader links. Original ledgers unchanged. Broker rows, alerts, and positions are different record types.'}
    (out/'TRADE-IDENTITY-COVERAGE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    rows=db.execute('SELECT kind,caller,room,identity_status,COUNT(*) FROM attributed_research WHERE identity_status!=? GROUP BY kind,caller,room,identity_status ORDER BY kind,COUNT(*) DESC',('source_trader_id',)).fetchall()
    lines=['# Trade identity gaps','',report['note'],'',
           'To confirm a link, supply an original message link/account ID tied to the trade, or a broker order ID tied to that alert. For relay posts, identify the named trader separately from the posting account.','',
           '| Record type | Caller | Room | Status | Records |','|---|---|---|---|---:|']
    lines += ['| '+' | '.join(str(x or '').replace('|','/') for x in row)+' |' for row in rows]
    (out/'TRADE-IDENTITY-GAPS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    db.close()
    return report


if __name__=='__main__':
    print(json.dumps(reconcile(),indent=2))
