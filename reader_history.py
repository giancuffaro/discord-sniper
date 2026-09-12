"""Offline history importer. Reads only known room-export formats; never trades."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from eastern import ET

ROW = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(.+?)#([^\]]+)\]\s+(.*)$")
GRAB_ROW = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s{2}(.*)$")
DOM_PREFIX = re.compile(r"^(?:.*?)?(?:\[\s*)?\d{1,2}:\d{2}\s*[AP]M(?:\s*\])?\s+[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M\s+", re.I)


def room_list(root):
    rooms, aliases = {}, {}
    for line in (Path(root) / 'extension/rooms.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        p = line.split('|')
        if len(p) < 5:
            continue
        rooms[p[0]] = {'channelId': p[0], 'room': p[2], 'url': p[1], 'state': p[4]}
        if p[0].startswith('whop:'):
            aliases['whop:' + urlparse(p[1]).path.rstrip('/')] = p[0]
    return rooms, aliases


def split_author(text):
    pos = text.find(': ')
    return (text[:pos].strip(), text[pos+2:]) if 0 <= pos < 100 else ('?', text)


def load(root, since=None, until=None):
    root = Path(root)
    rooms, aliases = room_list(root)
    rows, seen, counts = [], {}, Counter()

    def add(stamp, cid, room, body, source, line, history, tz, precision='second'):
        dt = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S' if precision == 'second' else '%Y-%m-%d %H:%M').replace(tzinfo=tz)
        et = dt.astimezone(ET)
        if (since and et.date().isoformat() < since) or (until and et.date().isoformat() > until):
            counts['outside_date_range'] += 1
            return
        cid = aliases.get(cid.strip().rstrip('/'), cid.strip())
        author, text = split_author(body)
        text = re.sub(r'\s+', ' ', DOM_PREFIX.sub('', text)).strip()
        if not text:
            return
        posted = int(dt.timestamp()*1000)
        key = json.dumps([cid, posted, author, text], ensure_ascii=False)
        provenance = {'file': source.name, 'line': line, 'history': history}
        if key in seen:
            existing = seen[key]
            existing['sources'].append(provenance)
            existing['history_only'] &= history
            counts['duplicate_exports'] += 1
            return
        row = {'id': hashlib.sha256(key.encode()).hexdigest()[:24], 'seq': len(rows),
               'at': et.strftime('%Y-%m-%d %H:%M:%S'), 'postedAt': posted,
               'channelId': cid, 'room': rooms.get(cid, {}).get('room', room.strip()),
               'author': author, 'text': text, 'history_only': history,
               'timestamp_precision': precision, 'sources': [provenance]}
        seen[key] = row
        rows.append(row)

    for file in sorted((root/'DS Logs').glob('signal-room-chat*.txt')):
        section = None
        for n, line in enumerate(file.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if line.startswith('==='):
                section = 'raw' if line.startswith('=== RAW MESSAGES') else 'other'
                continue
            if section == 'other':
                continue  # LIVE PARSER INPUTS is another view of the same post.
            m = ROW.match(line)
            if not m:
                continue
            body = m[4]
            history = body.startswith('<history> ')
            if history:
                body = body[len('<history> '):]
            add(m[1], m[3], m[2], body, file, n, history, ET)

    # The existing grabber exports UTC minute timestamps and multiline bodies.
    for file in sorted((root/'DS Logs').glob('grab *.txt')):
        data = file.read_text(encoding='utf-8', errors='replace')
        cid = re.search(r'^channel_id: (.+)$', data, re.M)
        room = re.search(r'^room: (.*)$', data, re.M)
        if not cid:
            counts['grab_missing_channel'] += 1
            continue
        pending = None
        for n, line in enumerate(data.splitlines(), 1):
            m = GRAB_ROW.match(line)
            if m:
                if pending:
                    add(pending[0], cid[1], room[1] if room else cid[1], pending[1], file, pending[2], True, timezone.utc, 'minute')
                pending = [m[1], m[2], n]
            elif pending:
                pending[1] += '\n' + line
        if pending:
            add(pending[0], cid[1], room[1] if room else cid[1], pending[1], file, pending[2], True, timezone.utc, 'minute')

    rows.sort(key=lambda r: (r['postedAt'], r['channelId'], r['seq']))
    coverage = {cid: dict(room, messages=0, history_messages=0, first=None, last=None,
                          retrieval_status='not_retrieved', coverage='unverified')
                for cid, room in rooms.items()}
    for row in rows:
        c = coverage.setdefault(row['channelId'], {'channelId': row['channelId'],
            'room': row['room'], 'state': 'historical_only', 'messages': 0,
            'history_messages': 0, 'first': None, 'last': None,
            'retrieval_status': 'not_retrieved', 'coverage': 'unverified'})
        c['messages'] += 1
        c['history_messages'] += int(row['history_only'])
        c['first'] = c['first'] or row['at']
        c['last'] = row['at']
        c['retrieval_status'] = 'local_exports_only'
    return rows, {'since': since, 'until': until, 'messages': len(rows),
                  'configured_channels': len(rooms), 'import_counts': dict(counts),
                  'channels': list(coverage.values()),
                  'note': 'Earliest/latest retained timestamps do not establish continuous channel coverage. No remote history retrieval has been confirmed.'}
