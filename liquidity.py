"""liquidity.py — will anyone buy this back from me?

G's rule, 9/8: "even if you can trade it or buy a contract you still don't want
to if there's no open interest.. you wouldn't be able to sell it to no one
later." Right instinct, and the data moved the answer one step further.

WHY VOLUME AND NOT OPEN INTEREST. Measured on the strikes his rooms actually
call (within 2% of spot, prior completed session):

    NVDA   OI  3,403   VOL 29,332
    TSLA   OI  1,076   VOL 21,480
    QQQ    OI    792   VOL  6,604
    SPY    OI  1,206   VOL  4,205
    MU     OI     94   VOL  1,867     <- looks dead on OI, trades fine
    SNDK   OI     27   VOL    336     <- the thinnest thing they touch

These are day-traded contracts: everyone flattens by the close, so OI stays
small while volume is enormous. An OI gate would have blocked MU and SNDK for
no reason at all — and SNDK is a real part of Brando's book. Volume is the
honest measure of "someone was on the other side of this today".

WHY THE **PRIOR** SESSION. Intraday volume starts at zero at 9:30. A gate that
reads TODAY's volume refuses every 0DTE trade at the open — precisely the
trades this bot exists to take. So the number used is the last COMPLETED
session's volume for that contract, which is known before the bell and cannot
move while we are deciding.

WHY A WARM CACHE. The fire path cannot afford a broker round trip; this is a
sniper. The whole map is pulled once in the morning and the entry check is a
dictionary lookup. A miss does one short lookup with a hard timeout and then
gets out of the way.

FAIL OPEN, ALWAYS. If Tradier is down, or the contract is not in the map, the
trade goes through with a note. Blocking real entries because a data provider
had a bad minute is a far more expensive failure than letting one thin contract
through — the spread gate in webull_options.py still stands behind this.

EXITS ARE NEVER GATED. Same rule as the spread gate: getting OUT is never
refused for liquidity reasons. Being stuck in a position you cannot exit is the
thing we are trying to avoid; refusing the exit would BE that thing.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "liquidity_cache.json")
BASE = "https://api.tradier.com/v1"

# G's call, 9/8. Set from the measurement above: SNDK's thinnest strike traded
# 336, so 250 passes everything his rooms touch today and only ever fires on
# something new and genuinely dead. Override in settings.json:
#   execution.min_contract_volume
DEFAULT_FLOOR = 250

_LOCK = threading.Lock()
_MAP = {}          # occ -> {"v": volume, "oi": open_interest}
_DAY = None        # the session the map describes
_MISS_AT = {}      # occ -> last on-demand lookup time, so we ask once


def _tok(cfg):
    try:
        return ((cfg.get("execution") or {}).get("tradier") or {}).get("access_token")
    except Exception:
        return None


def _get(tok, path, params, timeout):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _chain(tok, sym, expiry, timeout=20):
    """Every contract for one symbol+expiry, as {occ: {v, oi}}."""
    out = {}
    try:
        b = _get(tok, "/markets/options/chains",
                 {"symbol": sym, "expiration": expiry, "greeks": "false"}, timeout)
    except Exception:
        return out
    for o in (((b or {}).get("options") or {}).get("option")) or []:
        occ = str(o.get("symbol") or "").strip().upper()
        if not occ:
            continue
        out[occ] = {"v": int(o.get("volume") or 0),
                    "oi": int(o.get("open_interest") or 0)}
    return out


def _expiries(tok, sym, n=3, timeout=20):
    try:
        b = _get(tok, "/markets/options/expirations",
                 {"symbol": sym, "includeAllRoots": "true"}, timeout)
    except Exception:
        return []
    ex = (((b or {}).get("expirations") or {}).get("date")) or []
    return list(ex)[:n]


def _today(tok):
    """The session the numbers belong to. Tradier's clock, not our clock."""
    try:
        b = _get(tok, "/markets/clock", {}, 10)
        return str(((b or {}).get("clock") or {}).get("date") or "")
    except Exception:
        return time.strftime("%Y-%m-%d")


def warm(cfg, symbols, expiries_each=2, note=None):
    """Pull the volume map for `symbols` once. Call it in the morning.

    Deliberately bounded: a couple of expiries per symbol, because a room calls
    this week's contracts, not next quarter's. Roughly two Tradier calls per
    symbol — well inside the rate budget for a once-a-day job.
    """
    global _MAP, _DAY
    tok = _tok(cfg)
    if not tok:
        if note:
            note("LIQUIDITY: no Tradier token — volume gate is OFF (fails open)")
        return 0
    day = _today(tok)
    got = {}
    for sym in sorted(set(s for s in symbols if s)):
        for e in _expiries(tok, sym, expiries_each):
            got.update(_chain(tok, sym, e))
    with _LOCK:
        _MAP = got
        _DAY = day
    try:
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"day": day, "map": got}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CACHE)
    except Exception:
        pass
    if note:
        note("LIQUIDITY: warmed %d contracts across %d symbols for %s"
             % (len(got), len(set(symbols)), day))
    return len(got)


def load_cache(note=None):
    """Bring yesterday's map back after a restart, so a crash mid-day doesn't
    turn the gate off until tomorrow morning."""
    global _MAP, _DAY
    try:
        d = json.load(open(CACHE, encoding="utf-8"))
        with _LOCK:
            _MAP = d.get("map") or {}
            _DAY = d.get("day")
        if note:
            note("LIQUIDITY: loaded %d cached contracts (%s)" % (len(_MAP), _DAY))
        return len(_MAP)
    except Exception:
        return 0


def volume_of(occ, cfg=None, allow_lookup=True):
    """(volume, source) for one OCC symbol. None means we do not know."""
    if not occ:
        return (None, "no contract")
    occ = str(occ).strip().upper()
    with _LOCK:
        hit = _MAP.get(occ)
    if hit:
        return (hit.get("v"), "warm cache")
    if not allow_lookup or not cfg:
        return (None, "not in the cache")
    # One short on-demand try, once per contract. A hard 3s ceiling: if the
    # broker is slow we would rather trade than stall the fire path.
    now = time.time()
    if _MISS_AT.get(occ, 0) > now - 300:
        return (None, "looked once already")
    _MISS_AT[occ] = now
    tok = _tok(cfg)
    if not tok:
        return (None, "no token")
    try:
        sym, expiry = _split_occ(occ)
        if not sym:
            return (None, "unreadable contract")
        got = _chain(tok, sym, expiry, timeout=3)
        with _LOCK:
            _MAP.update(got)
        h = got.get(occ)
        return ((h.get("v") if h else None), "on-demand")
    except Exception:
        return (None, "lookup failed")


def _split_occ(occ):
    """SPY260908C00770000 -> ("SPY", "2026-09-08")."""
    import re
    m = re.match(r"^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})[CP]\d{8}$", occ)
    if not m:
        return (None, None)
    return (m.group(1), "20%s-%s-%s" % (m.group(2), m.group(3), m.group(4)))


def check(occ, cfg, note=None):
    """(ok, why). ok=False ONLY when we positively know it is too thin.

    Unknown is not a refusal — see the fail-open note at the top of this file.
    """
    ex = (cfg.get("execution") or {}) if isinstance(cfg, dict) else {}
    if ex.get("min_contract_volume") in (0, "0", False):
        return (True, "volume gate off")
    floor = int(ex.get("min_contract_volume") or DEFAULT_FLOOR)
    vol, src = volume_of(occ, cfg)
    if vol is None:
        return (True, "no volume data (%s) — allowed, the spread gate still applies" % src)
    if vol >= floor:
        return (True, "%d traded last session" % vol)
    return (False, "only %d contracts traded last session, floor is %d — you "
                   "could get in and find nobody to sell it back to" % (vol, floor))
