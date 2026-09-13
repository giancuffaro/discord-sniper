"""Build the research caller catalog from retained exports; never changes live trading.

Run: python caller_ledger.py
IDs are strings. Legacy author names are channel-scoped observations, not identities.
The database is additive and keeps source rows for audit/replay.
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'local-reader-measure' / 'caller-identity'


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def channel_accounts(out=OUT):
    """Read verified sightings for presentation only; never infer trade attribution."""
    path = out / 'callers.sqlite3'
    if not path.exists():
        return {'available': False, 'accounts': []}
    try:
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2) as db:
            rows = db.execute('''SELECT channel_id,discord_user_id,display_name,server_id
                FROM account_sightings ORDER BY channel_id,discord_user_id,display_name''').fetchall()
        accounts = {}
        for cid,uid,name,gid in rows:
            item = accounts.setdefault((cid,uid), {'channel_id':cid,'user_id':uid,
                'name':name,'server_id':gid,'observed_names':[],'win_pct':None})
            if name not in item['observed_names']:
                item['observed_names'].append(name)
        return {'available':True,'accounts':list(accounts.values())}
    except sqlite3.Error:
        return {'available':False,'accounts':[]}


def build(root=ROOT, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out / 'callers.sqlite3')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS channels(channel_id TEXT PRIMARY KEY, server_id TEXT,
      label TEXT, configured_state TEXT);
    CREATE TABLE IF NOT EXISTS author_observations(observation_id TEXT PRIMARY KEY,
      channel_id TEXT REFERENCES channels, display_name TEXT,
      identity_status TEXT NOT NULL DEFAULT 'unverified');
    CREATE TABLE IF NOT EXISTS messages(record_id TEXT PRIMARY KEY,
      observation_id TEXT REFERENCES author_observations, message_id TEXT,
      posted_at TEXT, raw_text TEXT, dedup_basis TEXT);
    CREATE TABLE IF NOT EXISTS source_rows(source_path TEXT, line_number INTEGER,
      content_hash TEXT, record_id TEXT REFERENCES messages,
      PRIMARY KEY(source_path,line_number,content_hash));
    CREATE TABLE IF NOT EXISTS confirmed_accounts(discord_user_id TEXT PRIMARY KEY,
      caller_name TEXT, evidence_json TEXT);
    CREATE TABLE IF NOT EXISTS feed_evidence(evidence_id TEXT PRIMARY KEY, evidence_json TEXT);
    CREATE TABLE IF NOT EXISTS account_sightings(discord_user_id TEXT,
      channel_id TEXT, server_id TEXT, display_name TEXT, source_url TEXT,
      verification TEXT, PRIMARY KEY(discord_user_id,channel_id,display_name));
    CREATE INDEX IF NOT EXISTS message_author ON messages(observation_id);
    CREATE VIEW IF NOT EXISTS caller_coverage AS
      SELECT a.observation_id,a.display_name,c.channel_id,c.server_id,c.label,
      c.configured_state,a.identity_status,COUNT(m.record_id) retained_records,
      MIN(m.posted_at) first_seen,MAX(m.posted_at) last_seen
      FROM author_observations a JOIN channels c USING(channel_id)
      LEFT JOIN messages m USING(observation_id) GROUP BY a.observation_id;
    ''')
    for line in (root / 'extension/rooms.txt').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        p = line.split('|')
        if len(p) < 5:
            continue
        guild = re.search(r'discord.com/channels/(\d+)/', p[1])
        db.execute('INSERT INTO channels VALUES(?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET server_id=excluded.server_id,label=excluded.label,configured_state=excluded.configured_state',
                   (p[0], guild[1] if guild else None, p[2], p[4]))
    row_re = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d)?)\s+(?:\[(.*?) #([^\]]+)\]\s+)?(?:\[message_id=([^\]]+)\]\s+)?([^:]+):\s*(.*)$')
    files = sorted(set((root / 'DS Logs').glob('signal-room-chat*.txt')) | set((root / 'DS Logs').glob('grab *.txt')))
    for path in files:
        channel = label = None
        for n, line in enumerate(path.read_text(encoding='utf-8-sig', errors='replace').splitlines(), 1):
            if line.startswith('channel_id: '):
                channel = line[12:].strip()
            if line.startswith('room: '):
                label = line[6:].strip()
            match = row_re.match(line)
            if not match:
                continue
            at, room, cid, mid, author, body = match.groups()
            cid = cid or channel
            if not cid:
                continue
            db.execute('INSERT OR IGNORE INTO channels VALUES(?,?,?,?)', (cid, None, room or label, None))
            author = author.strip()
            obs = digest(cid, author)
            db.execute('INSERT OR IGNORE INTO author_observations(observation_id,channel_id,display_name) VALUES(?,?,?)', (obs,cid,author))
            mid = mid if mid and mid.isdigit() else None
            # Preserve edited variants; never collapse separate channel feeds.
            rid = digest(cid, mid, body) if mid else digest(cid, at, author, body)
            db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?)',
                       (rid,obs,mid,at,body,'message_id_and_content' if mid else 'legacy_exact_timestamp_author_text'))
            db.execute('INSERT OR IGNORE INTO source_rows VALUES(?,?,?,?)',
                       (str(path.relative_to(root)),n,digest(line),rid))
    for evidence_path in sorted(out.glob('browser-collection*.json')):
        for room in json.loads(evidence_path.read_text(encoding='utf-8-sig')):
            match = re.fullmatch(r'https://discord.com/channels/(\d+)/(\d+)',room.get('url',''))
            if not match:
                continue
            gid,cid=match.groups()
            for account in room.get('accounts',[]):
                uid=account.get('id')
                if not isinstance(uid,str) or not re.fullmatch(r'\d{17,20}',uid):
                    continue
                db.execute('INSERT OR IGNORE INTO confirmed_accounts VALUES(?,?,?)',
                  (uid,account['name'],json.dumps({'source':evidence_path.name,'account_type':'unverified','status':'browser_copy_user_id_verified'})))
                db.execute('INSERT OR REPLACE INTO account_sightings VALUES(?,?,?,?,?,?)',
                  (uid,cid,gid,account['name'],room['url'],evidence_path.name))
    registry_path = out / 'registry.json'
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding='utf-8-sig'))
        for account in registry.get('accounts', []):
            db.execute('INSERT OR REPLACE INTO confirmed_accounts VALUES(?,?,?)',
                       (account['discord_user_id'],account.get('caller_name'),json.dumps(account,ensure_ascii=False)))
            if account.get('status')=='browser_copy_user_id_verified':
                for cid in account.get('channel_ids',[]):
                    db.execute('INSERT OR IGNORE INTO account_sightings VALUES(?,?,?,?,?,?)',
                      (account['discord_user_id'],cid,account.get('server_id'),account['caller_name'],account.get('source_url'),account.get('source')))
        for item in registry.get('verified_feed_matches', []):
            db.execute('INSERT OR REPLACE INTO feed_evidence VALUES(?,?)', (digest(item),json.dumps(item)))
    db.commit()
    counts = {t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
              ('channels','author_observations','messages','source_rows','confirmed_accounts')}
    rows = db.execute('SELECT display_name,label,channel_id,retained_records,first_seen,last_seen FROM caller_coverage ORDER BY label,display_name').fetchall()
    report = ['# Caller research ledger', '',
              'All retained author observations, including chat participants and bots. These are not all confirmed traders.',
              'Names stay separate by channel until identity evidence confirms a link. Confirmed accounts are stored separately; name matching never assigns an account ID.',
              'Record counts are not alert counts or trade counts. Legacy exact duplicates are grouped, original file/line references remain. Timestamps retain export formatting and are not assumed to be UTC.',
              'No win-rate ranking is available from this catalog alone: paired caller exits, quote coverage, and broker evidence must be joined before ranking. Missing evidence must remain unavailable.',
              '', 'Counts: '+json.dumps(counts), '',
              '| Observed author | Room | Channel ID | Records | First | Last |',
              '|---|---|---|---:|---|---|']
    for row in rows:
        report.append('| '+' | '.join(str(x or '').replace('|','/').replace('\n',' ') for x in row)+' |')
    (out / 'CALLER-LEDGER.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    db.close()
    return counts


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
