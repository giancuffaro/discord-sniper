"""tape.py — ONE way to read everything we ever recorded about a contract.

    from tape import rows, at, contracts
    for r in rows(occ="SPY260908C00640000"):
        r.ts, r.occ, r.bid, r.ask, r.mid, r.delta, r.gamma, r.source

WHY (9/7/26)
------------
G asked for jobs the app does in several places that one thing could do.
Three files record the SAME contracts at the SAME moments, in three schemas
and two symbol formats:

    option_tape.csv    ts, occ,    bid, ask                  Webull, polled
    greeks_tape.csv    ts, symbol, price, iv, delta, ...      tastytrade
    quote_shadow.csv   ts, symbol, bid, ask, mid, sizes       tastytrade

`option_tape` keys on OCC (`SPY260908C00640000`); the other two key on
dxfeed (`.SPY260908C640`). So every tool that wants to look at one contract
has to know all three layouts, translate symbols, and join on nearest
timestamp. `quote_shadow.py` does exactly that by hand with `bisect` — and
`ratchet_lab`, `bars_capture` and `thetadata_probe` each read a different
subset with their own parsing.

This module is the single reader. It normalises symbols through `occ.py`,
yields one row type, and never asks the caller which file a number came from
— only, if they care, which `source` it came from.

WHY IT DOES NOT ALSO UNIFY THE WRITERS
--------------------------------------
Merging the three files on disk would mean rewriting live write paths and
migrating irreplaceable history. **Webull keeps no historical option prices**
— anything not recorded live is gone forever, so the tapes are the one thing
in this project that cannot be regenerated. Consolidating the READ side gets
the benefit (one mental model, one symbol format, no hand-written joins) at
zero risk to the recording. The writers can converge later, behind this.

HONEST LIMITS — repeat these in any analysis
  * These are separate feeds sampled at different instants. A row from
    Webull and a row from tastytrade at "the same time" are up to `tol`
    seconds apart. `at()` tells you the real gap; do not hide it.
  * The Webull tape carries no greeks; the greeks tape carries no bid/ask.
    A merged row can have holes. Holes are None, never zero.
  * option_tape is a POLL at ~1/sec while a position is open. It is not a
    record of every tick, and gaps mean "not watched", not "no trade".
"""
import bisect
import csv
import os

import occ as _occ

HERE = os.path.dirname(os.path.abspath(__file__))

SOURCES = {
    "webull": ("option_tape.csv", "occ"),
    "tasty_greeks": ("greeks_tape.csv", "dx"),
    "tasty_quote": ("quote_shadow.csv", "dx"),
}


class Row(object):
    """One observation of one contract at one instant, from one feed."""
    __slots__ = ("ts", "occ", "bid", "ask", "price", "iv", "delta", "gamma",
                 "theta", "vega", "rho", "source")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def mid(self):
        if self.bid is not None and self.ask is not None \
                and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.price          # greeks rows carry a theoretical price

    def __repr__(self):
        return "<%s %s %s mid=%s>" % (self.source, self.occ, self.ts,
                                      self.mid)


def _f(v):
    try:
        if v in ("", None):
            return None
        f = float(v)
        return None if f != f else f          # NaN -> None, never 0
    except (TypeError, ValueError):
        return None


def _normalise(sym, kind):
    """Whatever the file wrote -> OCC. One place, via occ.py."""
    if kind == "occ":
        return sym if _occ.is_occ(sym) else None
    return _occ.from_dx(sym)


def rows(occ=None, since=None, until=None, sources=None, root=None):
    """Every recorded observation, oldest first, as Row objects.

    occ      one contract (OCC form) — or None for all
    root     e.g. "SPY" to get every contract on that underlying
    since/until  unix timestamps
    sources  subset of SOURCES keys
    """
    want = list(sources or SOURCES)
    out = []
    for name in want:
        fname, keykind = SOURCES[name]
        path = os.path.join(HERE, fname)
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for r in csv.DictReader(fh):
                ts = _f(r.get("ts"))
                if ts is None:
                    continue
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue
                raw = r.get("occ") or r.get("symbol")
                o = _normalise(raw, keykind)
                if not o:
                    continue
                if occ and o != occ:
                    continue
                if root:
                    p = _occ.parse(o)
                    if not p or p[0] != root.upper():
                        continue
                out.append(Row(ts=ts, occ=o, source=name,
                               bid=_f(r.get("bid")), ask=_f(r.get("ask")),
                               price=_f(r.get("price")), iv=_f(r.get("iv")),
                               delta=_f(r.get("delta")),
                               gamma=_f(r.get("gamma")),
                               theta=_f(r.get("theta")),
                               vega=_f(r.get("vega")), rho=_f(r.get("rho"))))
    out.sort(key=lambda x: x.ts)
    return out


def contracts(since=None):
    """Every contract that appears anywhere in the tapes, as OCC."""
    seen = {}
    for r in rows(since=since):
        seen.setdefault(r.occ, 0)
        seen[r.occ] += 1
    return sorted(seen)


def at(occ, ts, tol=1.0, sources=None):
    """The nearest observation from EACH source to `ts`, within `tol`.

    Returns {source: (Row, gap_seconds)}. Sources with nothing close enough
    are simply absent — never filled in with the last known value, because a
    stale number presented as a contemporaneous one is how a comparison
    turns into a lie. `quote_shadow.py` hand-rolled this join with bisect;
    it lives here now.
    """
    got = {}
    for name in (sources or SOURCES):
        rs = rows(occ=occ, sources=[name])
        if not rs:
            continue
        times = [r.ts for r in rs]
        i = bisect.bisect_left(times, ts)
        best, gap = None, None
        for j in (i - 1, i):
            if 0 <= j < len(rs):
                d = abs(rs[j].ts - ts)
                if gap is None or d < gap:
                    best, gap = rs[j], d
        if best is not None and gap <= tol:
            got[name] = (best, gap)
    return got


def summary():
    """What have we actually got? For health checks and sanity."""
    out = {}
    for name, (fname, _k) in SOURCES.items():
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            out[name] = {"file": fname, "exists": False}
            continue
        rs = rows(sources=[name])
        out[name] = {
            "file": fname, "exists": True, "rows": len(rs),
            "contracts": len({r.occ for r in rs}),
            "first": rs[0].ts if rs else None,
            "last": rs[-1].ts if rs else None,
        }
    return out


if __name__ == "__main__":
    import time
    print("%-14s %8s %10s  %s" % ("SOURCE", "ROWS", "CONTRACTS", "SPAN"))
    for name, s in sorted(summary().items()):
        if not s["exists"]:
            print("%-14s %8s %10s  (%s not created yet)"
                  % (name, "-", "-", s["file"]))
            continue
        span = ""
        if s["first"] and s["last"]:
            span = "%s -> %s" % (
                time.strftime("%m-%d %H:%M", time.localtime(s["first"])),
                time.strftime("%m-%d %H:%M", time.localtime(s["last"])))
        print("%-14s %8d %10d  %s" % (name, s["rows"], s["contracts"], span))
