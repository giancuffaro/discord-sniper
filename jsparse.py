"""jsparse — call the PRODUCTION parser (extension/parser.js) from Python.

parse_many(texts) -> list of dicts {action, symbol, strike, side, expiry, limit,
why, matched, fire, kind, direction}. One node process per call, so batch.

THE FALLBACK IS LOUD NOW (9/7)
------------------------------
This used to drop to `signals.py` — the hand-maintained PYTHON MIRROR of
parser.js — whenever `node` was missing, and say so only in a `why` suffix
buried in each row. That is the quietest possible way to get a different
answer than production: `scoreboard.py`, `replay_check.py` and
`audit_history.py` all read through here, and a room could be judged on a
parser the bot does not use. It has happened before — see the note in
`parse_batch.js` about the mirror lagging and calling a room silent that the
bot was reading fine.

So the fallback now PRINTS a warning every time it fires, and sets
`USED_MIRROR` so a caller can refuse to publish numbers derived from it.

`node` is not currently installed or verified by START HERE — it is an
undeclared dependency of the audit tooling. `health.py` reports whether it
is present. Once it is confirmed on the trading PC, `signals.py` and its
~2,400 lines of sync tax can be deleted outright and this fallback with it.
"""
import json
import os
import subprocess
import sys

USED_MIRROR = False     # set True the moment the stale mirror is consulted


def node_available():
    """Is the production parser reachable? Cheap, and health.py reports it."""
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                           timeout=10)
        return r.returncode == 0
    except Exception:                                       # noqa: BLE001
        return False

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = os.path.join(HERE, "extension", "parse_batch.js")


def parse_many(texts):
    texts = [str(t or "") for t in texts]
    if not texts:
        return []
    try:
        r = subprocess.run(["node", BATCH, "--json"], input=json.dumps(texts).encode("utf-8"),
                           capture_output=True, timeout=120)
        if r.returncode == 0 and r.stdout:
            out = json.loads(r.stdout.decode("utf-8", "replace"))
            if isinstance(out, list) and len(out) == len(texts):
                return out
    except Exception:                                   # noqa: BLE001
        pass
    # FALLBACK — and it says so, every time, to stderr.
    global USED_MIRROR
    USED_MIRROR = True
    sys.stderr.write(
        "\n*** jsparse: `node` did not answer, so these %d message(s) were\n"
        "*** parsed by signals.py — the PYTHON MIRROR, not the parser the\n"
        "*** bot actually uses. The mirror is maintained by hand and HAS\n"
        "*** drifted before. Do not trust these results for a decision.\n"
        "*** Install Node.js and re-run.\n\n" % len(texts))
    sys.path.insert(0, HERE)
    import signals
    out = []
    for t in texts:
        try:
            s = signals.parse(t)
            out.append({"action": s.action, "symbol": s.symbol, "strike": s.strike, "side": s.side,
                        "expiry": s.expiry, "limit": s.limit, "why": (s.why or "") + " [py-mirror]",
                        "matched": getattr(s, "matched", ""), "fire": bool(s.fire),
                        "kind": getattr(s, "kind", ""), "direction": getattr(s, "direction", None)})
        except Exception as e:                          # noqa: BLE001
            out.append({"action": None, "why": "ERR %s" % e})
    return out
