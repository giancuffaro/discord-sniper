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

ONE LOOKUP PER CONTRACT. The fire path cannot afford a broker round trip; this
is a sniper. The first call on a contract does one short Tradier lookup with a
hard timeout, the answer is kept in memory for the process, and every later
check on that contract is a dictionary lookup.

FAIL OPEN, ALWAYS. If Tradier is down, or the contract is not in the map, the
trade goes through with a note. Blocking real entries because a data provider
had a bad minute is a far more expensive failure than letting one thin contract
through — the spread gate in webull_options.py still stands behind this.

EXITS ARE NEVER GATED. Same rule as the spread gate: getting OUT is never
refused for liquidity reasons. Being stuck in a position you cannot exit is the
thing we are trying to avoid; refusing the exit would BE that thing.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.tradier.com/v1"

# G's call, 9/8. Set from the measurement above: SNDK's thinnest strike traded
# 336, so 250 passes everything his rooms touch today and only ever fires on
# something new and genuinely dead. Override in settings.json:
#   execution.min_contract_volume
DEFAULT_FLOOR = 250

_LOCK = threading.Lock()
_MAP = {}          # occ -> {"v": volume, "oi": open_interest}
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


def volume_of(occ, cfg=None, allow_lookup=True):
    """(volume, source) for one OCC symbol. None means we do not know."""
    if not occ:
        return (None, "no contract")
    occ = str(occ).strip().upper()
    with _LOCK:
        hit = _MAP.get(occ)
    if hit:
        return (hit.get("v"), "already looked up")
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
