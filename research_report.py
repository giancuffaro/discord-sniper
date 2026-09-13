"""Generate a self-contained, searchable reading copy of the research SQL."""
import html
import json
import sqlite3
from datetime import datetime, timezone
from caller_ledger import OUT


def render(out=OUT):
    db=sqlite3.connect((out/'callers.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    def table(columns,rows):
        parts=['<table><thead><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in columns)+'</tr></thead><tbody>']
        for row in rows:
            parts.append('<tr>'+''.join('<td>'+html.escape('' if v is None else str(v))+'</td>' for v in row)+'</tr>')
        return ''.join(parts)+'</tbody></table>'
    trades=[]
    for r in db.execute("SELECT * FROM trade_attribution WHERE kind='reconciled_trade' ORDER BY date DESC,record_id"):
        p=json.loads(r['payload'])
        trades.append([r['date'],r['attribution_name'],r['display_room'],r['display_server_id'],r['symbol'],p.get('strike'),p.get('expiry'),
            p.get('fill'),p.get('exit_avg'),p.get('pl'),r['identity_status'],r['display_trader_id'],
            'N/A' if r['identity_status']=='manual' else r['candidate_trader_id'],r['name_basis'],r['origin_classification'],r['source_path'],r['source_row']])
    accounts=[list(r) for r in db.execute('SELECT display_name,discord_user_id,channel_id,server_id FROM account_sightings ORDER BY server_id,channel_id,display_name')]
    coverage=[list(r) for r in db.execute('SELECT label,channel_id,display_name,retained_records,first_seen,last_seen FROM caller_coverage ORDER BY label,display_name')]
    imports=[list(r) for r in db.execute('SELECT source_path,row_count,imported_at FROM research_imports ORDER BY source_path')]
    db.close()
    sections=[('Trades', ['Date','Recorded / recovered name','Room','Server ID','Symbol','Strike','Expiry','Entry','Exit','Ledger P/L','ID status','Resolved ID','Candidate ID','Name basis','Origin','Source','Row'],trades),
              ('Accounts',['Observed name','Account ID','Channel ID','Server ID'],accounts),
              ('Message coverage',['Room','Channel ID','Observed author','Records','First','Last'],coverage),
              ('Import dates',['Source','Records','Last imported (UTC)'],imports)]
    timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    body=''.join('<section data-section="'+str(i)+'"'+(' hidden' if i else '')+'><h2>'+name+'</h2>'+table(cols,rows)+'</section>' for i,(name,cols,rows) in enumerate(sections))
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Discord Sniper — Research SQL</title><style>
body{font:15px system-ui;background:#f5f7fa;color:#182535;margin:28px}h1{margin-bottom:5px}p{max-width:1050px;line-height:1.5}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0}button,input{font:inherit;padding:10px;border:1px solid #bac7d5;border-radius:6px;background:white}
button[aria-pressed=true]{background:#163b5c;color:white}input{width:min(600px,90%)}section{overflow:auto}table{border-collapse:collapse;background:white;width:100%;font-size:13px}
td,th{padding:10px;border-bottom:1px solid #dce3eb;text-align:left;vertical-align:top}th{background:#e8eef5;white-space:nowrap}td{min-width:85px;max-width:310px;overflow-wrap:anywhere}
[hidden]{display:none!important}.muted{color:#536579}#count{padding:10px 0}</style>
<h1>Your research SQL</h1><p class="muted">Reading copy generated '''+timestamp+''' · Opens locally; no upload.</p>
<p>Search trades by name, ticker, room or account ID. Blank cells mean missing information. Candidate IDs are unverified; manual trades stay separate. Ledger P/L is the existing recorded value, not a verified caller backtest. Different tabs show different record types and must not be added together as trade counts.</p>
<p>The master database is <b>callers.sqlite3</b> in this folder. This page is a snapshot: new logs appear after a research refresh, not automatically. Message coverage includes chat participants and posting bots, not only traders.</p>
<nav>'''+''.join('<button data-tab="'+str(i)+'" aria-pressed="'+str(i==0).lower()+'">'+name+'</button>' for i,(name,_,__) in enumerate(sections))+'''</nav>
<label for="search">Search the selected table</label><br><input id="search" type="search" placeholder="Brett, SPY, Honeydrip, account ID…"><div id="count" aria-live="polite"></div>
'''+body+'''<script>
let active='0';const input=document.getElementById('search');
function filter(){let shown=0,total=0;document.querySelectorAll('section').forEach(s=>{s.hidden=s.dataset.section!==active;if(s.hidden)return;s.querySelectorAll('tbody tr').forEach(r=>{total++;r.hidden=!r.textContent.toLowerCase().includes(input.value.toLowerCase());if(!r.hidden)shown++})});document.getElementById('count').textContent=shown+' of '+total+' records'}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{active=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));filter()});input.oninput=filter;filter();
</script></html>'''
    target=out/'MASTER-RESEARCH.html'
    target.write_text(page,encoding='utf-8')
    return {'report':str(target),'trades':len(trades),'account_observations':len(accounts),'author_channel_observations':len(coverage)}


if __name__=='__main__':
    print(json.dumps(render(),indent=2))
