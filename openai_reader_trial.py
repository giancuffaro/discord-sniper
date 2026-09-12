"""User-authorized $5 offline trial. Never imported by the live order path.

Run with pythonw openai_reader_trial.py for masked, memory-only key entry.
Pricing checked 2026-09-12: https://developers.openai.com/api/docs/models/gpt-4.1
Budget is conservative API-token cost, not an account-wide billing limit/tax cap.
Do not delete the trial database to reset its allowance.
"""
import json
import queue
import random
import sqlite3
import threading
import time
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path

import ai_reader
import context_reader
import reader_measure

HERE = Path(__file__).resolve().parent
OUT = HERE / 'local-reader-measure' / 'openai-trial-2026-09-12'
SOURCE = HERE / 'local-reader-measure' / 'all-channels-2026-06-12' / 'corpus.jsonl'
MODEL = 'gpt-4.1-2025-04-14'
LIMIT_MICRO = 5_000_000
MAX_REQUESTS = 100
MAX_OUTPUT = 600


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS attempts '
               '(id TEXT PRIMARY KEY, reserved INTEGER NOT NULL, result TEXT)')
    db.commit()
    return db


def reserve(db, key, micro):
    """Durably reserve before network; failed/uncertain calls are never refunded."""
    if not isinstance(micro, int) or micro <= 0:
        raise ValueError('Invalid reservation')
    with db:
        db.execute('BEGIN IMMEDIATE')
        count, spent = db.execute('SELECT COUNT(*), COALESCE(SUM(reserved),0) FROM attempts').fetchone()
        if count >= MAX_REQUESTS or spent + micro > LIMIT_MICRO:
            return False
        if db.execute('SELECT 1 FROM attempts WHERE id=?', (key,)).fetchone():
            return False
        db.execute('INSERT INTO attempts VALUES (?, ?, NULL)', (key, micro))
    return True


def request_body(row, allowed):
    prompt = context_reader.prompt_for(row, row['prior'], allowed)
    body = {'model': MODEL, 'instructions': context_reader.SYSTEM,
            'input': prompt, 'max_output_tokens': MAX_OUTPUT, 'store': False,
            'text': {'format': {'type': 'json_object'}}}
    # UTF-8 byte count exceeds text token count; 4096 extra tokens cover framing.
    # Full output allowance reserved. No discounts/refunds assumed. Rates $2/$8 per M.
    maximum_input = len((context_reader.SYSTEM + prompt).encode('utf-8')) + 4096
    return body, maximum_input * 2 + MAX_OUTPUT * 8


def read_one(row, allowed, key, db, opener=urllib.request.urlopen):
    body, maximum = request_body(row, allowed)
    if not reserve(db, row['id'], maximum):
        return None
    started = time.monotonic()
    try:
        req = urllib.request.Request('https://api.openai.com/v1/responses',
                data=json.dumps(body).encode('utf-8'), method='POST',
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        with opener(req, timeout=45) as response:
            data = json.loads(response.read().decode('utf-8'))
        if data.get('status') != 'completed':
            raise ValueError('incomplete')
        text = ''.join(part.get('text', '') for item in data.get('output', [])
                       for part in item.get('content', []) if part.get('type') == 'output_text')
        raw = ai_reader._extract_json(text)
        if not isinstance(raw, dict) or raw.get('action') not in ('OPEN','ADD','TRIM','CLOSE','NONE'):
            raise ValueError('invalid output')
        usage = data.get('usage') or {}
        input_tokens, output_tokens = usage.get('input_tokens'), usage.get('output_tokens')
        if (type(input_tokens) is not int or type(output_tokens) is not int
                or input_tokens < 0 or output_tokens < 0):
            raise ValueError('missing usage')
        cost = input_tokens * 2 + output_tokens * 8
        raw.update(_model=MODEL, _usage=usage, _cost_upper_usd=cost / 1_000_000)
        if cost > maximum:
            raw['_error'] = 'usage_exceeds_reservation'
    except urllib.error.HTTPError as exc:
        raw = {'_error': 'HTTP_%s' % exc.code}
        try:
            code = json.loads(exc.read(16384)).get('error', {}).get('code')
            if code in ('insufficient_quota', 'rate_limit_exceeded', 'invalid_api_key', 'model_not_found'):
                raw['_error_code'] = code
        except Exception:
            pass
    except Exception:
        # Never expose response bodies, request headers, or exception text.
        raw = {'_error': 'request_or_response_failed'}
    result = {'id': row['id'], 'ai_raw': raw,
              'ai': context_reader.assess(row, row['prior'], raw, allowed),
              'model_ms': round((time.monotonic()-started)*1000)}
    with db:
        db.execute('UPDATE attempts SET result=? WHERE id=?', (json.dumps(result), row['id']))
    return result


def sample(rows):
    rng = random.Random(20260912)
    groups = [[], [], []]
    for row in rows:
        text = row['text'].lower()
        group = 0 if (row.get('parser') or {}).get('action') else (
            1 if any(w in text for w in ('fill','entry','bought','calls','puts',' in '))
            and any(c.isdigit() for c in text) else 2)
        groups[group].append(row)
    selected = []
    for group, n in zip(groups, (34,33,33)):
        selected.extend(rng.sample(group, min(n, len(group))))
    return selected


def run(key, notify, stop, retry_once=False):
    import msvcrt
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / 'trial.lock', 'a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            notify('Another test window is already running.')
            return
        try:
            _run(key, notify, stop, retry_once)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def retry_one(rows, allowed, key, db):
    """Explicit single retry; retain every old reservation and result."""
    latest = db.execute('SELECT result FROM attempts ORDER BY rowid DESC LIMIT 1').fetchone()
    if not latest or latest[0] is None:
        raise ValueError('No completed failed request to retry')
    previous = json.loads(latest[0])
    if previous.get('ai_raw', {}).get('_error') != 'HTTP_429':
        raise ValueError('Latest request is not a reviewed 429')
    source = next(r for r in rows if r['id'] == previous['id'])
    attempt = dict(source, id=source['id'] + ':retry:' + uuid.uuid4().hex)
    result = read_one(attempt, allowed, key, db)
    if result is not None:
        result['id'] = source['id']
        with db:
            db.execute('UPDATE attempts SET result=? WHERE id=?', (json.dumps(result), attempt['id']))
    return result


def unresolved_failure(prior):
    """An explicit successful retry resolves its source's earlier failed attempt."""
    latest = {}
    for (serialized,) in prior:
        if serialized is None:
            return True
        result = json.loads(serialized)
        latest[result['id']] = result
    return any((r.get('ai_raw') or {}).get('_error') for r in latest.values())


def _run(key, notify, stop, retry_once=False):
    OUT.mkdir(parents=True, exist_ok=True)
    db = connect(OUT / 'budget.sqlite3')
    try:
        prepared = OUT / 'corpus.jsonl'
        if not prepared.exists():
            rows = sample(list(reader_measure.jsonl(str(SOURCE))))
            temp = prepared.with_suffix('.tmp')
            temp.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
            temp.replace(prepared)
        rows = list(reader_measure.jsonl(str(prepared)))
        cfg = json.loads((HERE / 'settings.json').read_text(encoding='utf-8'))
        allowed = cfg.get('allowed_symbols', []) or []
        # Uncertain and failed calls require inspection, not an automatic rerun.
        prior = db.execute('SELECT result FROM attempts ORDER BY rowid').fetchall()
        if not retry_once and unresolved_failure(prior):
            notify('Stopped: previous error or interrupted request needs review.')
            return
        final_status = 'Test stopped. Results saved; full historical scan remains paused.'
        if retry_once:
            result = retry_one(rows, allowed, key, db)
            raw = (result or {}).get('ai_raw', {})
            final_status = ('Single retry succeeded. Saved for review; bulk scan stays paused.'
                            if result and not raw.get('_error') else
                            'Retry stopped: %s. Bulk scan stays paused.' %
                            (raw.get('_error_code') or raw.get('_error') or 'budget limit'))
        for row in ([] if retry_once else rows):
            if stop.is_set():
                break
            result = read_one(row, allowed, key, db)
            if result is None:
                continue
            count, reserved = db.execute('SELECT COUNT(*), SUM(reserved) FROM attempts').fetchone()
            notify('Reviewed %s / 100; conservative budget used $%.2f / $5.' % (count, reserved/1_000_000))
            if (result.get('ai_raw') or {}).get('_error'):
                final_status = 'Stopped on %s. No automatic retry.' % result['ai_raw']['_error']
                notify(final_status)
                break
        results = [json.loads(r) for (r,) in db.execute('SELECT result FROM attempts WHERE result IS NOT NULL ORDER BY rowid')]
        (OUT / 'ai-context.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in results), encoding='utf-8')
        reader_measure.OUT = str(OUT)
        reader_measure.PREPARED = str(prepared)
        reader_measure.AI_OUT = str(OUT / 'ai-context.jsonl')
        reader_measure.QUEUE = str(OUT / 'disagreements.csv')
        reader_measure.SUMMARY = str(OUT / 'summary.json')
        reader_measure.report()
        notify(final_status)
    finally:
        db.close()


def main():
    import tkinter as tk
    from tkinter import ttk
    retry_once = '--retry-once' in sys.argv
    root = tk.Tk()
    root.title('Discord Sniper - OpenAI retry' if retry_once else 'Discord Sniper - OpenAI test')
    root.geometry('620x250')
    ttk.Label(root, text=('One OpenAI retry / existing $5 budget preserved' if retry_once else
                         'OpenAI offline test: up to 100 messages / $5 maximum'), font=('',12)).pack(pady=12)
    ttk.Label(root, text='GPT-4.1 | previous 10 messages | no live orders\nKey stays in memory and is cleared from this field when you start.').pack()
    entry = ttk.Entry(root, show='*', width=65)
    entry.pack(pady=10)
    messages = queue.Queue()
    stop = threading.Event()
    status = tk.StringVar(value='Paste your OpenAI key here, then start the test.')
    def start():
        key = entry.get().strip()
        if not key.startswith('sk-'):
            status.set('Enter an OpenAI API key in the masked field.')
            return
        entry.delete(0, 'end')
        button.config(state='disabled')
        def worker():
            try:
                run(key, messages.put, stop, retry_once)
            except Exception:
                messages.put('Test stopped due to a local error. No automatic retry.')
        threading.Thread(target=worker, daemon=True).start()
    button = ttk.Button(root, text='Retry once' if retry_once else 'Start capped test', command=start)
    button.pack()
    ttk.Button(root, text='Stop after current request', command=stop.set).pack(pady=5)
    ttk.Label(root, textvariable=status, wraplength=590).pack()
    def poll():
        while not messages.empty():
            status.set(messages.get_nowait())
        root.after(250, poll)
    poll()
    entry.focus_set()
    root.mainloop()


if __name__ == '__main__':
    main()
