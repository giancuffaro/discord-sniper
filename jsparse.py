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


def parse_many(texts, configs=None):
    texts = [str(t or "") for t in texts]
    if not texts:
        return []
    try:
        payload = texts if configs is None else [
            {"text": t, "cfg": (configs[i] if i < len(configs) else {}) or {}}
            for i, t in enumerate(texts)]
        r = subprocess.run(["node", BATCH, "--json"], input=json.dumps(payload).encode("utf-8"),
                           capture_output=True, timeout=120)
        if r.returncode == 0 and r.stdout:
            out = json.loads(r.stdout.decode("utf-8", "replace"))
            if isinstance(out, list) and len(out) == len(texts):
                return out
    except Exception:                                   # noqa: BLE001
        pass
    # NO MIRROR TO FALL BACK TO — and that is deliberate (9/7).
    #
    # `signals.py` was 2,350 lines of hand-maintained Python that duplicated
    # extension/parser.js. It never priced a trade: bridge.py never imported
    # it, and only this fallback, its own test and a debug dumper did. What
    # it DID do was drift — on 9/2 it disagreed with the real parser and
    # called a room silent that the bot was reading fine.
    #
    # Two parsers means the audit tools can quietly answer a different
    # question than the bot asks. One parser and a hard failure is safer
    # than two parsers and a silent disagreement.
    global USED_MIRROR
    USED_MIRROR = True
    raise RuntimeError(
        "jsparse: Node.js did not answer, so %d message(s) could not be "
        "parsed.\n"
        "The audit tools (scoreboard, replay_check, audit_history) run the "
        "REAL extension parser through node — there is no Python mirror any "
        "more, on purpose: it drifted and gave different answers than the "
        "bot.\n"
        "Install Node.js from https://nodejs.org and re-run. Nothing is "
        "wrong with the bot; only these read-only reports need node."
        % len(texts))
    # (Nothing follows the raise. What used to live here was the fallback
    # into signals.parse() — dead since the Python mirror was deleted 9/9,
    # unreachable behind that raise, and `signals` is not even imported, so
    # it was a NameError waiting for the day node went missing. Removed 9/10
    # rather than left as a comforting-looking safety net that never was
    # one. REPLACE, DON'T STACK: the mirror went, so its call site goes.)
