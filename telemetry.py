"""telemetry.py — the instruments, not the engine.

WHY THIS EXISTS (9/6/26)
------------------------
G asked what the rest of the field has that we don't. The honest answer,
after reading the one serious open-source competitor and every commercial
product with a public spec, is that **nobody measures the time between a
caller posting and our order filling.** Not the competitor, not the paid
products. Every one of them logs what happened; none of them logs how well.

That number decides things we currently argue about:

  * Which of 26 rooms is worth its subscription. A caller whose alerts we
    fill 400ms after he posts is a different asset from one we fill in 9s.
  * Whether chasing or waiting is right — PER CALLER, not as doctrine.
  * How much of a caller's posted edge survives contact with our execution.

NOTHING HERE CAN BREAK A TRADE. Every entry point is wrapped, every failure
is swallowed, and the module holds no locks the trading path waits on. If
telemetry dies the bot does not notice. That is deliberate: an instrument
that can crash the engine is worse than no instrument.

WHAT IT WRITES
--------------
telemetry.csv    one row per FILL — the latency chain and the conditions
alert_decay.csv  the contract's mid at +1s/+5s/+30s/+60s after the alert

alert_decay.csv is the one that has never been published by anyone. It is
the answer to "would we have done better waiting?" measured on OUR rooms
instead of on somebody's blog.

READING THE LATENCY CHAIN
-------------------------
    posted_at  -> seen_at    the reader's lag: DOM sweep + parse
    seen_at    -> sent_at    our decision + the bridge hop
    sent_at    -> filled_at  the market's answer (and our limit's patience)

Splitting it three ways matters. A slow total that is all reader lag is an
extension problem. A slow total that is all fill time means our limit is
priced too politely. They have opposite fixes, and one number can't tell
them apart.

HONEST LIMITS — say these out loud in any analysis built on this
  * posted_at comes from Discord's own <time datetime> attribute, which is
    the SERVER's receive time, not when the caller started typing.
  * A caller posting into a room we read in a background tab may be
    throttled by Chrome. That lag is real and ours, so it belongs in the
    number — but it is not the caller's fault.
  * Voice and vision alerts have no posted_at. They record as blank, not
    as zero. Never average a blank as if it were instant.
"""
import csv
import os
import queue
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FILLS = os.path.join(HERE, "telemetry.csv")
DECAY = os.path.join(HERE, "alert_decay.csv")

_LOCK = threading.Lock()

# ONE writer thread, started on first use, fed by a bounded queue.
#
# The first version spawned a thread PER FILL. It never raised and it wrote
# correct rows — and it made test_positions.py fail 2 runs in 3, on
# assertions about stop placement and P&L that have nothing to do with
# telemetry. Baseline without it: 5 of 5 clean. Thread churn on the fill
# path was enough to change how the book's own threads interleaved.
#
# That is the whole lesson of this module in one paragraph: an instrument
# that perturbs the thing it measures is not an instrument. Enqueue is a
# non-blocking put on a bounded queue — no allocation of threads, no file
# I/O, no lock the caller can wait on. If the queue is full the row is
# DROPPED, on purpose: losing a measurement is free, delaying a stop is not.
_Q = queue.Queue(maxsize=2000)
_WRITER = None
_DROPPED = 0

FILL_COLS = [
    "ts", "iso", "coid", "room", "trader", "symbol", "side", "strike",
    "expiry", "dte", "live", "qty",
    # the chain
    "posted_at", "seen_at", "sent_at", "filled_at",
    "read_ms", "decide_ms", "fill_ms", "total_ms",
    # what we paid vs what he said
    "their_price", "our_fill", "slip_abs", "slip_pct",
    # conditions at entry — why the fill was good or bad
    "bid", "ask", "spread", "spread_pct", "underlying",
    "delta", "gamma", "theta", "iv",
    # THE ENTRY MATH — computed once, at the fill, from the greeks above
    "stop_room_pts",      # underlying points to a -10% premium stop
    "stop_room_pct",      # same, as % of the stock price
    "theta_per_min",      # honest 0DTE burn, off extrinsic not quoted theta
    "theta_break_min",    # minutes the trade must work to outrun its own decay
    "gamma_read",         # sleepy / normal / hot / VIOLENT
    # how sure are we this fill is real
    "integrity",
]

DECAY_COLS = ["ts", "iso", "coid", "room", "trader", "symbol", "side",
              "strike", "expiry", "their_price", "t_plus_s", "mid",
              "pct_vs_their_price"]


def _iso(t):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(t)))
    except Exception:                                       # noqa: BLE001
        return ""


def _ms(a, b):
    """b - a in milliseconds, or "" when either end is missing. Returns a
    BLANK, never a zero — a missing timestamp is not an instant one, and a
    zero here would quietly drag every average toward fast."""
    try:
        if not a or not b:
            return ""
        d = (float(b) - float(a)) * 1000.0
        # A negative chain means clocks disagree (Discord's server time vs
        # this PC). Record it as blank rather than as a fast fill.
        return round(d, 1) if d >= 0 else ""
    except Exception:                                       # noqa: BLE001
        return ""


def _write_now(path, cols, row):
    with _LOCK:
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(row)


def _drain():
    while True:
        try:
            path, cols, row = _Q.get()
        except Exception:                                   # noqa: BLE001
            return
        try:
            _write_now(path, cols, row)
        except Exception:                                   # noqa: BLE001
            pass
        finally:
            try:
                _Q.task_done()
            except Exception:                               # noqa: BLE001
                pass


def _append(path, cols, row):
    """Hand the row to the writer and return immediately. Never blocks,
    never raises, never spawns per call."""
    global _WRITER, _DROPPED
    try:
        if _WRITER is None or not _WRITER.is_alive():
            _WRITER = threading.Thread(target=_drain, daemon=True,
                                       name="telemetry-writer")
            _WRITER.start()
        _Q.put_nowait((path, cols, row))
    except queue.Full:
        _DROPPED += 1           # measurements are cheap; the fill path isn't
    except Exception:                                       # noqa: BLE001
        pass


def flush(timeout=5.0):
    """Wait for queued rows to reach disk. For scripts and shutdown only —
    never call this from the trading path."""
    try:
        end = time.time() + float(timeout)
        while not _Q.empty() and time.time() < end:
            time.sleep(0.02)
    except Exception:                                       # noqa: BLE001
        pass
    return _DROPPED


def record_fill(p, quote=None, integrity="Reliable"):
    """One row per fill. `p` is the position dict; `quote` is an optional
    {bid, ask, underlying} snapshot taken at entry.

    `integrity` is borrowed from an OMS that got this right: when the broker
    won't confirm a fill and we proceed on assumption, the row says so. Every
    later analysis can then exclude trades whose fill we never actually saw,
    instead of quietly treating a guess as a measurement.
    """
    try:
        q = quote or {}
        posted = p.get("alert_at") or p.get("posted_at")
        seen = p.get("seen_at")
        sent = p.get("sent_at")
        filled = p.get("filled_at")
        theirs = p.get("their_price") or p.get("limit")
        ours = p.get("fill")

        slip_abs = slip_pct = ""
        try:
            if theirs and ours:
                slip_abs = round(float(ours) - float(theirs), 4)
                slip_pct = round(slip_abs / float(theirs) * 100.0, 2)
        except Exception:                                   # noqa: BLE001
            pass

        bid, ask = q.get("bid"), q.get("ask")
        spread = spread_pct = ""
        try:
            if bid and ask and float(ask) > 0:
                spread = round(float(ask) - float(bid), 4)
                mid = (float(ask) + float(bid)) / 2.0
                if mid > 0:
                    spread_pct = round(spread / mid * 100.0, 2)
        except Exception:                                   # noqa: BLE001
            pass

        g = p.get("greeks_in") or {}
        now = time.time()
        entry = _entry_math(p, g, ours)
        _append(FILLS, FILL_COLS, {
            "ts": round(now, 3), "iso": _iso(now),
            "coid": p.get("coid") or "", "room": p.get("room") or "",
            "trader": p.get("trader") or "", "symbol": p.get("symbol") or "",
            "side": p.get("side") or "", "strike": p.get("strike") or "",
            "expiry": p.get("expiry") or "", "dte": p.get("dte", ""),
            "live": 1 if p.get("live") else 0, "qty": p.get("qty") or 0,
            "posted_at": posted or "", "seen_at": seen or "",
            "sent_at": sent or "", "filled_at": filled or "",
            "read_ms": _ms(posted, seen),
            "decide_ms": _ms(seen, sent),
            "fill_ms": _ms(sent, filled),
            "total_ms": _ms(posted, filled),
            "their_price": theirs or "", "our_fill": ours or "",
            "slip_abs": slip_abs, "slip_pct": slip_pct,
            "bid": bid or "", "ask": ask or "", "spread": spread,
            "spread_pct": spread_pct, "underlying": q.get("underlying") or "",
            "delta": g.get("delta", ""), "gamma": g.get("gamma", ""),
            "theta": g.get("theta", ""), "iv": g.get("iv", ""),
            "integrity": integrity,
        })
    except Exception:                                       # noqa: BLE001
        pass            # an instrument may never take the engine down


def watch_decay(p, quote_fn, marks=(1, 5, 30, 60), note=None):
    """Sample the contract's mid at +1s/+5s/+30s/+60s after the ALERT and
    record each one against the caller's stated price.

    This is the measurement that answers "should we chase or wait?" with our
    own data. It runs on entries we TOOK and — more importantly — it can be
    run on alerts we refused, which is the only way to learn what a skipped
    trade would have done.

    quote_fn(p) -> (bid, ask) or a mid float. Anything it raises is ignored.
    """
    def _run():
        base = p.get("alert_at") or p.get("seen_at") or time.time()
        theirs = p.get("their_price") or p.get("limit")
        for m in marks:
            try:
                wait = float(base) + float(m) - time.time()
                if wait > 0:
                    time.sleep(min(wait, 120.0))
                q = quote_fn(p)
                if q is None:
                    continue
                if isinstance(q, (list, tuple)) and len(q) >= 2:
                    bid, ask = float(q[0]), float(q[1])
                    mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0
                else:
                    mid = float(q)
                if mid <= 0:
                    continue
                pct = ""
                try:
                    if theirs and float(theirs) > 0:
                        pct = round((mid - float(theirs))
                                    / float(theirs) * 100.0, 2)
                except Exception:                           # noqa: BLE001
                    pass
                _append(DECAY, DECAY_COLS, {
                    "ts": round(time.time(), 3), "iso": _iso(time.time()),
                    "coid": p.get("coid") or "", "room": p.get("room") or "",
                    "trader": p.get("trader") or "",
                    "symbol": p.get("symbol") or "",
                    "side": p.get("side") or "",
                    "strike": p.get("strike") or "",
                    "expiry": p.get("expiry") or "",
                    "their_price": theirs or "", "t_plus_s": m,
                    "mid": round(mid, 4), "pct_vs_their_price": pct})
            except Exception:                               # noqa: BLE001
                continue
        if note:
            try:
                note("DECAY    sampled %s at +%s s after the alert"
                     % (p.get("symbol"), "/".join(str(x) for x in marks)))
            except Exception:                               # noqa: BLE001
                pass

    try:
        t = threading.Thread(target=_run, daemon=True,
                             name="decay-%s" % (p.get("symbol") or "?"))
        t.start()
        return t
    except Exception:                                       # noqa: BLE001
        return None


def summary(path=FILLS, min_n=5):
    """Per-caller latency and slippage, for the scoreboard and the journal.

    Returns {trader: {...}}. `min_n` exists because a median of two fills is
    not a median. Callers under the floor are still returned, with
    `enough=False`, so the report can show them greyed out rather than
    pretending they have a number.
    """
    out = {}
    try:
        if not os.path.exists(path):
            return out
        rows = list(csv.DictReader(open(path, encoding="utf-8",
                                        errors="replace")))
    except Exception:                                       # noqa: BLE001
        return out

    def _med(v):
        v = sorted(x for x in v if x != "" and x is not None)
        if not v:
            return None
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0

    by = {}
    for r in rows:
        t = (r.get("trader") or "?").strip() or "?"
        b = by.setdefault(t, {"total": [], "read": [], "fill": [],
                              "slip": [], "spread": [], "n": 0,
                              "rooms": set(), "assumed": 0})
        b["n"] += 1
        if (r.get("integrity") or "") != "Reliable":
            b["assumed"] += 1
        if r.get("room"):
            b["rooms"].add(r["room"])
        for src, dst in (("total_ms", "total"), ("read_ms", "read"),
                         ("fill_ms", "fill"), ("slip_pct", "slip"),
                         ("spread_pct", "spread")):
            try:
                if r.get(src) not in ("", None):
                    b[dst].append(float(r[src]))
            except Exception:                               # noqa: BLE001
                pass

    for t, b in by.items():
        out[t] = {
            "n": b["n"],
            "enough": b["n"] >= int(min_n),
            "rooms": sorted(b["rooms"]),
            "median_total_ms": _med(b["total"]),
            "median_read_ms": _med(b["read"]),
            "median_fill_ms": _med(b["fill"]),
            "median_slip_pct": _med(b["slip"]),
            "median_spread_pct": _med(b["spread"]),
            "assumed_fills": b["assumed"],
        }
    return out


if __name__ == "__main__":
    s = summary()
    if not s:
        print("No telemetry yet. telemetry.csv fills up as trades fill.")
        raise SystemExit(0)
    print("%-22s %5s %10s %10s %10s %9s" %
          ("CALLER", "N", "total ms", "read ms", "fill ms", "slip %"))
    for t, v in sorted(s.items(),
                       key=lambda kv: (kv[1]["median_total_ms"] is None,
                                       kv[1]["median_total_ms"] or 0)):
        def _f(x, w=10):
            return ("%*.0f" % (w, x)) if x is not None else "%*s" % (w, "-")
        print("%-22s %5d %s %s %s %s%s" %
              (t[:22], v["n"], _f(v["median_total_ms"]),
               _f(v["median_read_ms"]), _f(v["median_fill_ms"]),
               ("%9.2f" % v["median_slip_pct"])
               if v["median_slip_pct"] is not None else "%9s" % "-",
               "" if v["enough"] else "   (too few to trust)"))
