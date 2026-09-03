"""jsparse — call the PRODUCTION parser (extension/parser.js) from Python.

parse_many(texts) -> list of dicts {action, symbol, strike, side, expiry, limit,
why, matched, fire, kind, direction}. One node process per call, so batch.
Falls back to signals.py (the Python mirror) only if node is missing.
"""
import json
import os
import subprocess

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
    # fallback: the Python mirror (may lag parser.js — say so)
    import sys
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
