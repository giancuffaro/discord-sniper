"""Offline audit reproductions. Every broker is a fake; no live bridge import."""
import ast
import datetime
import json
import pathlib
import threading
import time
import types
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parent
RESULTS = []


def extract(file, name, globals_=None):
    tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = dict(globals_ or {})
    exec(compile(ast.Module(body=[fn], type_ignores=[]), file, "exec"), ns)
    return ns[name]


def record(name, condition, detail):
    RESULTS.append(dict(name=name, reproduced=bool(condition), detail=detail))
    assert condition, (name, detail)


class InertThread:
    made = []
    def __init__(self, *args, **kwargs):
        self.made.append(kwargs)
    def start(self):
        pass


import positions
import webull_options
import quote_bus
import build_alerts
import build_ledger
import alert_tape

# 1: two independently bought contracts share one mutable position row.
b = positions.Book.__new__(positions.Book)
b._lock = threading.RLock()
b._pos = {}
b._archive = []
b._reserve = b._event = lambda *a, **k: None
b._wait_label = lambda: "test"
with patch.object(positions.threading, "Thread", InertThread):
    for strike in (225, 230):
        b.entry_sent(dict(symbol="NVDA", trader="Caller", side="CALLS", strike=strike,
                          expiry="2026-10-16", live=True),
                     dict(order_id=str(strike), occ=str(strike), limit=2, qty=1))
record("multi_contract_overwrite", len(b._pos) == 1 and b._pos['caller|NVDA']['strike'] == 230,
       {k: {'strike': v['strike'], 'order_id': v['order_id']} for k, v in b._pos.items()})

# 2: successful entry returns normally but the hard-stop worker never starts.
InertThread.made.clear()
place = extract("bridge.py", "place", dict(_alert_tape_register=lambda o: None,
                _place_impl=lambda o: (True, "accepted"), _RECENT_COIDS={},
                QUOTES=None, time=time, threading=types.SimpleNamespace(Thread=InertThread),
                _underlying_stop_watch=lambda o: None))
result = place(dict(action="OPEN", symbol="INTC", their_stop=97))
record("undefined_symbol_silences_hard_stop", result[0] and not InertThread.made,
       {"entry_result": result, "workers_started": len(InertThread.made)})

# 3: a timeout after submitting a bracket causes a second, plain BUY.
w = webull_options.WebullOptions.__new__(webull_options.WebullOptions)
w._cfg = {'execution': {'min_contract_volume': 0}}
w.ask_bid = lambda occ: (2.01, 2.0, {})
w.max_spread_dollars = .2
w.entry_limit = lambda bid, ask: 2.0
w.afford_check = lambda *a: None
w.blind_entry_max = 0
submits = []
w._order = lambda *a, **kw: [{'client_order_id': str(len(submits))}]
def ambiguous(*a):
    submits.append('bracket BUY submitted, response lost')
    raise TimeoutError('response lost after acceptance')
w._send_combo = ambiguous
w._send = lambda *a: submits.append('plain BUY submitted') or {}
# FIXED (F03/F01, 9/11 same-night patch): an ambiguous failure (timeout
# after acceptance, indistinguishable from a real rejection) no longer
# falls straight through to a second plain BUY. buy() now tries to
# reconcile against the account first (open_orders); when it can't check
# at all -- as here, where this fake object has no working account plumbing
# -- it fails CLOSED with webull_options.Refused rather than guessing.
# Bug behavior was: len(submits)==2 and r['ok'] is True (silent double-buy).
# Fixed behavior: exactly ONE submit, and a raised Refused instead of a
# false "ok".
try:
    r = w.buy('SPY', 'CALLS', 600, '2026-10-16', 1, bracket_stop_pct=5)
    reproduced = len(submits) == 2 and r.get('ok')
    detail = {'submits': submits, 'returned_ok': r.get('ok')}
except webull_options.Refused as _e:
    reproduced = False
    detail = {'submits': submits, 'raised': 'Refused', 'message': str(_e)[:160]}
record('ambiguous_bracket_duplicate_buy', reproduced, detail)

# 4: 429 is swallowed by request-shape discovery.
requests = []
w = types.SimpleNamespace(quote_client=None, _warned_no_batch=True,
    _pace_batch=lambda: None, ask_bid=lambda o: (None, None, None))
w._quote_fns = lambda: [('mock', lambda *a, **kw:
    requests.append(429) or types.SimpleNamespace(status_code=429))]
r = webull_options.WebullOptions.ask_bid_many(w, ['SPY261016C00600000'])
record('429_eight_requests_no_backoff_signal', len(requests) == 8, {'requests': len(requests), 'returned': r})

# 5: timed-out rate budget is ignored.
budget_calls = []
w = types.SimpleNamespace(budget=types.SimpleNamespace(take=lambda *a, **kw: budget_calls.append(False) or False))
r = webull_options.WebullOptions._pace_batch(w)
record('budget_denial_ignored', budget_calls == [False] and r is None, {'denied': True, 'returned_without_error': True})

# 6: watchdog exits during a working ADD without clearing its liveness flag.
b = positions.Book.__new__(positions.Book)
b._lock = threading.RLock(); b.poll_seconds = 0
b._pos = {'caller|SPY': {'state': positions.WORKING, 'watching': True}}
b._watchdog('caller|SPY')
record('watchdog_dead_flag_remains_true', b._pos['caller|SPY']['watching'], b._pos)

# 7: stop re-arm claims success even if _arm_stop installed no broker stop.
b = positions.Book.__new__(positions.Book)
b._lock = threading.RLock()
b._pos = {'caller|SPY': dict(state=positions.FILLED, qty=1, swing=True, fill=2,
                            side='CALLS', strike=600, expiry='2026-10-16')}
b._stop_still_resting = lambda p: False
b._arm_stop = lambda *a: None  # real _arm_stop swallows broker refusal
r = b.rearm_overnight_stops()
record('failed_stop_rearm_marked_done', r == 1 and b._pos['caller|SPY']['stop_day'] == datetime.date.today().isoformat(),
       {'reported_rearmed': r, 'stop_order_id': b._pos['caller|SPY'].get('stop_order_id')})

# 8: orphan cleaner cancels a different expiry/side and has no ownership check.
b = positions.Book.__new__(positions.Book)
b._event = lambda *a: None; b._await_cancel = lambda *a: None
cancelled = []
w = types.SimpleNamespace(open_orders=lambda sym: [dict(order_id='human-put-later-expiry',
    action='SELL', strike=600, side='PUTS', expiry='2027-01-15')], cancel=cancelled.append)
b._clear_orphans(w, 'caller|SPY', 'SPY', 600)
record('orphan_cleaner_cancels_unowned_contract', cancelled == ['human-put-later-expiry'], cancelled)

# 9: seller ignores cancellation discovering that the FIRST sell filled.
clock = [0]
def now():
    clock[0] += 10
    return clock[0]
seller = extract('positions.py', '_sell_confirmed', {'time': types.SimpleNamespace(time=now, sleep=lambda s: None)})
sells = []
b = types.SimpleNamespace(_sell_retry=lambda *a, **kw: sells.append('sell') or {'order_id': str(len(sells)), 'limit': 2},
                          _await_cancel=lambda *a: ('filled', 2.0))
w = types.SimpleNamespace(order_status=lambda oid: ('working', 0, None), cancel=lambda oid: True,
                          ask_bid=lambda occ: (2.01, 2, {}))
r = seller(b, w, 'caller|SPY', 'OCC', 'SPY', 'CALLS', 600, '2026-10-16', 1, 2)
record('sell_retry_ignores_late_fill', len(sells) == 2 and r == (False, None), {'sell_submissions': len(sells), 'result': r})

# 10: a different contract can be mistaken for a fill after cancellation.
watch = extract('positions.py', '_watch_fill', {'time': types.SimpleNamespace(time=lambda: 100, sleep=lambda s: None),
                                             'WORKING': positions.WORKING, 'FILLED': positions.FILLED, 'FAILED': positions.FAILED})
fills = []
w = types.SimpleNamespace(cancel=lambda oid: True, positions=lambda: [dict(symbol='SPY',strike=600,side='PUTS',expiry='2027-01-15',qty=1,fill=5)])
b = types.SimpleNamespace(_lock=threading.RLock(), fill_seconds=0,
    _pos={'caller|SPY':dict(state=positions.WORKING, symbol='SPY', side='CALLS', strike=600,
                          expiry='2026-10-16',order_id='bid',occ='OCC',limit=2,want_qty=1,live=True)},
    _wbfor=lambda p:w, _probe=lambda *a,**kw:('dead',0,None),
    _became_filled=lambda *a:fills.append(a), _became_nofill=lambda *a:None)
watch(b,'caller|SPY')
record('different_put_mistaken_for_call_fill', bool(fills), fills)

# 11: pullback fill bypasses STOP after the delayed entry has been armed.
# FIXED (F09, same-night patch): _pullback_enter now checks the kill switch
# itself, the same way do_POST always did, instead of only reaching
# _place_impl (which also checks it now, but this test isolates
# _pullback_enter on its own so it needs its own real _stop_file_set()).
import os as _os
_HERE = str(ROOT)
def _real_stop_file_set():
    return (_os.path.exists(_os.path.join(_HERE, "STOP"))
            or _os.path.exists(_os.path.join(_HERE, "STOP.txt")))
enter = extract('bridge.py', '_pullback_enter',
                {'_place_impl': lambda o: (True, 'sent'),
                 '_stop_file_set': _real_stop_file_set,
                 'note': lambda s: None})
(ROOT/'STOP').write_text('stop')
r = enter(dict(action='OPEN', symbol='SPY', entry_mode='pullback'))
(ROOT/'STOP').unlink()
record('armed_pullback_bypasses_stop_file', r[0], {'STOP_present': True, 'result': r})

# 12: alert metadata joins different expiries and callers.
meta = ROOT/'audit-meta.csv'
meta.write_text('date,symbol,strike,side,expiry,caller,room,stage,bid,ask\n2026-09-11,SPY,600,CALLS,2026-09-11,A,room-A,quote,1,1.1\n')
with patch.object(build_alerts,'META',str(meta)):
    rows=[dict(date='2026-09-11',symbol='SPY',strike='600',side='CALLS',expiry='2026-10-16')]
    build_alerts._apply_meta(rows)
record('alert_metadata_cross_contract_join', rows[0].get('caller')=='A',rows)

# 13: trade dedupe ignores expiry.
a=dict(who='A',symbol='SPY',strike=600,side='CALLS',fill=2,expiry='2026-09-11')
c=dict(a,expiry='2026-10-16')
record('ledger_dedupe_key_omits_expiry',build_ledger._dedupe_key(a,'2026-09-11')==build_ledger._dedupe_key(c,'2026-09-11'),
       {'different_expiries_same_key':True})

# 14: alert greeks slots never released when expiry is pruned.
rec=alert_tape.AlertRecorder(lambda o:{},quote_bus.Budget())
old='SPY200101C00600000';rec._occs=[old];rec._seen={old};rec._greeked={old}
with rec._lock:rec._prune_locked()
record('expired_greek_slots_leak',not rec._occs and old in rec._greeked,{'remaining_greek_slots':len(rec._greeked)})

# 15: same coid is not reserved before dispatch, so concurrent ADDs both run.
barrier = threading.Barrier(2)
dispatches = []
def dispatch(o):
    dispatches.append(o['coid'])
    barrier.wait(timeout=3)
    return True, 'accepted'
place = extract('bridge.py','place',dict(_alert_tape_register=lambda o:None,
    _place_impl=dispatch,_RECENT_COIDS={},QUOTES=None,time=time,note=lambda s:None))
ts=[threading.Thread(target=place,args=(dict(action='ADD',coid='same-id'),)) for _ in range(2)]
for t in ts:t.start()
for t in ts:t.join(5)
record('concurrent_coid_dispatches_twice',len(dispatches)==2,dispatches)

# 16: concurrent atomic writers share .tmp; second moves away published primary.
import os
path=str(ROOT/'atomic-race.json')
pathlib.Path(path).write_text('{}')
sync=threading.Barrier(2); first_done=threading.Event(); failures=[]
real_replace=os.replace
def synced_fsync(fd):
    sync.wait(timeout=3)
def ordered_replace(a,b):
    if threading.current_thread().name=='writer-two':first_done.wait(3)
    return real_replace(a,b)
write=extract('bridge.py','write_json_atomic',dict(json=json,os=types.SimpleNamespace(
    path=os.path,fsync=synced_fsync,replace=ordered_replace)))
def writer():
    try:write(path,{'writer':threading.current_thread().name})
    except OSError as e:failures.append(type(e).__name__)
    finally:
        if threading.current_thread().name=='writer-one':first_done.set()
ts=[threading.Thread(target=writer,name=name) for name in ['writer-one','writer-two']]
for t in ts:t.start()
for t in ts:t.join(5)
record('atomic_writer_race_removes_primary',not pathlib.Path(path).exists() and bool(failures),
       {'primary_exists':pathlib.Path(path).exists(),'backup_exists':pathlib.Path(path+'.bak').exists(),'errors':failures})

# 17: adapter's accepted sell returns a string, but shared seller expects dict.
import tradier
adapter=tradier.TradierOptions('dummy','ACCT')
adapter._req=lambda *a,**kw:{'order':{'id':'accepted-sell'}}
returned=adapter.sell('SPY','CALLS',600,'2026-10-16',1)
try:
    returned.get('order_id')
    error=None
except AttributeError as e:error=type(e).__name__
record('alternate_adapter_sell_contract_mismatch',error=='AttributeError',{'returned_type':type(returned).__name__,'consumer_error':error})

# 18: backtest credits stop price despite first observed bid gapping below it.
simulate=extract('ratchet_backtest.py','simulate',dict(BORN_STOP_PCT=5,
    rt=types.SimpleNamespace(ratchet_locked_pct=lambda *a:None)))
r=simulate([(1,1.0,1.1)],2.0)
record('backtest_credits_unavailable_stop_price',r[0]>-6,{'entry':2,'observed_bid':1,'reported_percent':r[0]})

# 19: positions() swallows an outage into [], bridge labels that successful.
w=webull_options.WebullOptions.__new__(webull_options.WebullOptions)
w._pace=lambda:None;w.account_id='dummy';w._try_calls=lambda *a,**kw:(None,'HTTP 429')
assert w.positions()==[]
cache={'t':0,'v':[],'busy':False}
read=extract('bridge.py','broker_positions',dict(WB=w,WB_LIVE=w,WB_PAPER=None,
    time=time,_POS=cache,paper_on=lambda:False,_FUT_POS_BACKOFF={'until':float('inf'),'fails':0},
    CFG={},threading=threading,note=lambda *a:None))
r=read()
record('throttle_misreported_as_verified_flat',r==[] and cache.get('ok_live') is True,
       {'adapter_failure':'HTTP 429','positions':r,'trusted_live':cache.get('ok_live')})

# 20: a persisted running-worker flag prevents a worker after process restart.
b=positions.Book(None,lambda *a:None)
saved={'pos':{'caller|SPY':dict(state=positions.FILLED,symbol='SPY',qty=1,fill=2,
    watching=True,stop_order_id='resting',stop=1.9,side='CALLS',strike=600,expiry='2026-10-16',live=True)}}
b.restore_state(saved,False)
b._stop_still_resting=lambda p:True
InertThread.made.clear()
with patch.object(positions.threading,'Thread',InertThread):
    b.reconcile_gone([dict(symbol='SPY',side='CALLS',strike=600,expiry='2026-10-16',qty=1,live=True)])
record('restored_watchdog_never_started',not InertThread.made and b._pos['caller|SPY']['watching'],
       {'watching_flag':True,'threads_created':len(InertThread.made)})

(ROOT/'reproductions.json').write_text(json.dumps(RESULTS,indent=2),encoding='utf-8')
for r in RESULTS: print('REPRODUCED',r['name'])
