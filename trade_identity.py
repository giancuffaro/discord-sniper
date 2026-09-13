"""Auditable trader identity links and unresolved candidates for research only."""
import json
import sqlite3
from collections import defaultdict, Counter
from caller_ledger import OUT


def reconcile(out=OUT):
    db=sqlite3.connect(out/'callers.sqlite3')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS entry_attribution(record_id TEXT PRIMARY KEY,
        entry_caller TEXT,entry_basis TEXT,exit_method TEXT,evidence_json TEXT);
      CREATE TABLE IF NOT EXISTS trade_source_recovery(record_id TEXT PRIMARY KEY,
        classification TEXT, recovered_caller TEXT, evidence_json TEXT, limitation TEXT);
      CREATE TABLE IF NOT EXISTS trade_identity_links(record_id TEXT PRIMARY KEY,
        trader_id TEXT, status TEXT NOT NULL, candidates_json TEXT, reason TEXT NOT NULL);
      DROP VIEW IF EXISTS attributed_research;
      CREATE VIEW attributed_research AS SELECT r.*, i.trader_id AS resolved_trader_id,
        CASE WHEN i.status='source_trader_id' THEN i.trader_id END AS verified_trader_id,
        i.status AS identity_status,i.candidates_json,i.reason AS identity_reason
        FROM ledger_records r LEFT JOIN trade_identity_links i USING(record_id)
        WHERE r.current=1;
      DROP VIEW IF EXISTS trade_attribution;
      CREATE VIEW trade_attribution AS SELECT a.*,
        CASE WHEN TRIM(COALESCE(a.caller,'')) NOT IN ('','?','unknown','Unknown')
          THEN a.caller END AS recorded_caller,
        s.recovered_caller AS recovered_posting_name,
        e.entry_caller AS recovered_entry_caller,e.entry_basis,e.exit_method,
        e.evidence_json AS entry_evidence,
        CASE WHEN e.entry_basis='contract_time_quantity_match' THEN e.entry_caller
          WHEN TRIM(COALESCE(a.caller,'')) NOT IN ('','?','unknown','Unknown')
          THEN a.caller ELSE s.recovered_caller END AS attribution_name,
        CASE WHEN e.entry_basis='contract_time_quantity_match' THEN 'entry_log_match'
          WHEN TRIM(COALESCE(a.caller,'')) NOT IN ('','?','unknown','Unknown')
          THEN 'recorded_caller' WHEN s.recovered_caller IS NOT NULL
          THEN 'log_candidate' ELSE 'missing' END AS name_basis,
        s.classification AS origin_classification,s.evidence_json AS origin_evidence,
        s.limitation AS origin_limitation,
        CASE WHEN a.identity_status='candidate' AND json_array_length(a.candidates_json)=1
          THEN json_extract(a.candidates_json,'$[0]') END AS candidate_trader_id
        FROM attributed_research a LEFT JOIN trade_source_recovery s USING(record_id)
        LEFT JOIN entry_attribution e USING(record_id);
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
    reviewed_path=out/'reviewed-trade-identities.json'
    reviewed_items=json.loads(reviewed_path.read_text(encoding='utf-8')) if reviewed_path.exists() else []
    current=db.execute('SELECT record_id,kind,caller,room,channel_id,payload FROM ledger_records WHERE current=1').fetchall()
    reviewed={item['record_id']:item for item in reviewed_items
              if item.get('record_id') and not item.get('match')}
    # Rebuilt CSV row numbers and reconciled fields change record_id. A reviewed
    # source link may follow a unique, fully specified source trade only while
    # its original message evidence remains in this research database.
    for item in reviewed_items:
        match=item.get('match')
        if not match:
            continue
        hits=[rid for rid,kind,caller,room,cid,payload in current
              if kind==match.get('kind') and
              all(json.loads(payload).get(k)==v for k,v in match.items() if k!='kind')]
        evidence=item.get('evidence_message_ids') or []
        if len(hits)==1 and evidence and all(
                db.execute('SELECT 1 FROM messages WHERE record_id=?',(mid,)).fetchone()
                for mid in evidence):
            reviewed[hits[0]]=item
    totals=Counter()
    by_kind=defaultdict(Counter)
    for rid,kind,caller,room,cid,payload in current:
        data=json.loads(payload)
        trader=None
        candidates=[]
        if str(data.get('manual','')).casefold() in ('true','1','yes'):
            status,reason='manual','Manual position; not assigned to a signal caller'
        elif rid in reviewed and reviewed[rid]['trader_id'] in known:
            item=reviewed[rid]
            trader=item['trader_id']
            status,reason='source_supported',item['reason']
            candidates=[trader]
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
