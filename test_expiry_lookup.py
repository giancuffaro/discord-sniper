#!/usr/bin/env python3
"""test_expiry_lookup.py — a call with NO date must land on a REAL listing.

    python3 test_expiry_lookup.py        (exit 0 = every case passes)

WHY (9/14/26)
-------------
10:21, "Platinum nitro" / "PT | ei trades": `Entry Contract: TSLA $357.5c
Price: $1.42` — no expiry, because that room never posts one. The bridge
assumed "a single stock has FRIDAY WEEKLIES ONLY", bought TSLA 357.5C
2026-09-18 at $7.40, and never noticed it had paid five times the price the
caller posted. Two minutes later the same bot bought NVDA 210P expiring
WEDNESDAY 9/16 — proof single mega-caps list Mon/Wed/Fri and the assumption
was stale.

So the listing is asked, not assumed, and the caller's own premium is the
check on the answer. Every case below is that day, mocked: no network, no
broker, no orders.
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bridge                                            # noqa: E402
import webull_options as wo                              # noqa: E402

FAILED = []
LOG = []


def check(name, got, want):
    if got == want:
        print("  OK    %s" % name)
    else:
        print("  FAIL  %s\n          got  %r\n          want %r" % (name, got, want))
        FAILED.append(name)


def check_in(name, needle, hay):
    if needle in hay:
        print("  OK    %s" % name)
    else:
        print("  FAIL  %s\n          %r not in %r" % (name, needle, hay))
        FAILED.append(name)


TODAY = dt.date.today().isoformat()
FRIDAY = wo.weekly_expiry()
CANDS = wo.dateless_candidates()


class FakeWB(object):
    """Stands in for the live Webull client. Answers only what is listed."""

    def __init__(self, listed=None, blow_up=False):
        self.listed = listed or {}
        self.blow_up = blow_up
        self.calls = 0

    def listed_expiries(self, symbol, strike, option_type, candidates):
        self.calls += 1
        if self.blow_up:
            raise RuntimeError("429 Webull quote throttle; sweep deferred")
        return {d: a for d, a in self.listed.items() if d in candidates}


def with_wb(wb, fn):
    old = bridge.WB
    bridge.WB = wb
    try:
        return fn()
    finally:
        bridge.WB = old


def order(sym="TSLA", strike=357.5, side="CALLS", limit=1.42):
    return {"action": "OPEN", "symbol": sym, "strike": strike, "side": side,
            "limit": limit, "raw": "Entry Contract: %s $%gc Price: $%s"
            % (sym, strike, limit)}


# --------------------------------------------------------------------------
print("\ndateless_candidates — the QUESTION we ask the broker")
check("today leads the candidate list",
      CANDS[0] == TODAY or dt.date.today().weekday() >= 5, True)
check("this week's Friday is in it", FRIDAY in CANDS, True)
check("candidates are unique", len(CANDS) == len(set(CANDS)), True)
check("candidates are in date order", CANDS == sorted(CANDS), True)

# --------------------------------------------------------------------------
print("\n1. dateless TSLA, today IS listed -> today")
wb = FakeWB({TODAY: 1.45, FRIDAY: 7.40})
exp, why, asks = with_wb(wb, lambda: bridge._dateless_expiry("TSLA", order()))
check("picks today", exp, TODAY)
check_in("says why", "today (%s) IS a listed expiration" % TODAY, why)
check("one lookup call", wb.calls, 1)

print("\n2. dateless NVDA, today NOT listed -> the nearest that is")
_wed = [d for d in CANDS if d != TODAY][0]
wb = FakeWB({_wed: 2.40, FRIDAY: 5.10})
exp, why, asks = with_wb(
    wb, lambda: bridge._dateless_expiry("NVDA", order("NVDA", 210, "PUTS", 2.40)))
check("picks the nearest listed", exp, _wed)
check_in("says why", "nearest listed is %s" % _wed, why)

print("\n3. the lookup itself fails -> the old static table, and it SAYS so")
wb = FakeWB(blow_up=True)
exp, why, asks = with_wb(wb, lambda: bridge._dateless_expiry("TSLA", order()))
check("single stock falls back to Friday", exp, FRIDAY)
check_in("says it fell back", "fell back to Friday", why)
check("no asks come back from a failed lookup", asks, {})

exp, why, asks = with_wb(
    wb, lambda: bridge._dateless_expiry("SPY", order("SPY", 761, "CALLS", 0.44)))
check("SPY falls back to TODAY, not Friday", exp, TODAY)
check_in("says it fell back", "fell back to the daily-expiry table", why)

print("\n4. SPY with a working lookup still resolves to today")
wb = FakeWB({TODAY: 0.44, FRIDAY: 1.90})
exp, why, asks = with_wb(
    wb, lambda: bridge._dateless_expiry("SPY", order("SPY", 761, "CALLS", 0.44)))
check("SPY -> today", exp, TODAY)

# --------------------------------------------------------------------------
print("\n5. the caller-price gate")
_noted, bridge_note = [], bridge.note
bridge.note = lambda line: _noted.append(str(line))
try:
    # 5a. the real 9/14 shape: resolved to Friday, asking 7.40, caller said 1.42
    o = order()
    o["expiry"] = FRIDAY
    msg = bridge._price_sanity("TSLA", o, {TODAY: 1.45, FRIDAY: 7.40})
    check("switches to the expiry that matches their price", o["expiry"], TODAY)
    check("and does not refuse", msg, "")
    check_in("says it switched", "which is the trade they posted",
             " ".join(_noted))

    # 5b. nothing listed matches -> REFUSE, in plain words
    del _noted[:]
    o = order()
    o["expiry"] = FRIDAY
    msg = bridge._price_sanity("TSLA", o, {FRIDAY: 7.40})
    check_in("refuses", "REFUSED OPEN TSLA", msg)
    check_in("names the ask", "asks 7.40", msg)
    check_in("names their price", "the caller said 1.42", msg)
    check_in("says what it will not do",
             "not buying the wrong contract", msg)
    check("the expiry is left alone on a refusal", o["expiry"], FRIDAY)

    # 5c. NO caller price -> the gate is inert, whatever the ask says
    o = order(limit=None)
    o["expiry"] = FRIDAY
    msg = bridge._price_sanity("TSLA", o, {FRIDAY: 7.40})
    check("no caller price, no opinion", msg, "")
    check("and the expiry is untouched", o["expiry"], FRIDAY)

    # 5d. a price inside the band passes untouched
    o = order(limit=7.00)
    o["expiry"] = FRIDAY
    msg = bridge._price_sanity("TSLA", o, {TODAY: 1.45, FRIDAY: 7.40})
    check("in-band ask is fine", msg, "")
    check("and nothing is switched", o["expiry"], FRIDAY)

    # 5e. no ask for the resolved contract -> nothing to compare, stay quiet
    o = order()
    o["expiry"] = FRIDAY
    check("no ask, no opinion", bridge._price_sanity("TSLA", o, {}), "")

    # 5f. the band edges, off the settings multipliers
    o = order(limit=2.00)
    o["expiry"] = FRIDAY
    check("2.5x exactly is still in band",
          bridge._price_sanity("TSLA", o, {FRIDAY: 5.00}), "")
    o = order(limit=2.00)
    o["expiry"] = FRIDAY
    check_in("past 2.5x refuses", "REFUSED OPEN",
             bridge._price_sanity("TSLA", o, {FRIDAY: 5.01}))
    o = order(limit=2.00)
    o["expiry"] = FRIDAY
    check("0.4x exactly is still in band",
          bridge._price_sanity("TSLA", o, {FRIDAY: 0.80}), "")
    o = order(limit=2.00)
    o["expiry"] = FRIDAY
    check_in("under 0.4x refuses", "REFUSED OPEN",
             bridge._price_sanity("TSLA", o, {FRIDAY: 0.79}))
finally:
    bridge.note = bridge_note

# --------------------------------------------------------------------------
print("\n6. listed_expiries — one batched call, cached per contract per day")


class FakeQuotes(wo.WebullOptions):
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def ask_bid_many(self, occs):
        self.calls += 1
        out = {}
        for o in occs:
            if o in self.rows:
                out[o] = (self.rows[o], self.rows[o] - 0.05, {})
        return out


_occ_t = wo.occ_symbol("TSLA", TODAY, "CALL", 357.5)
_occ_f = wo.occ_symbol("TSLA", FRIDAY, "CALL", 357.5)
q = FakeQuotes({_occ_t: 1.45, _occ_f: 7.40})
got = q.listed_expiries("TSLA", 357.5, "CALLS", CANDS)
check("only the listed dates come back", sorted(got), sorted({TODAY: 0, FRIDAY: 0}))
check("with their asks", got[FRIDAY], 7.40)
check("one call for the whole candidate set", q.calls, 1)
q.listed_expiries("TSLA", 357.5, "CALLS", CANDS)
check("the second read is cached, not a second call", q.calls, 1)

q2 = FakeQuotes({})
check("an empty answer is empty", q2.listed_expiries("ZZZZ", 5, "CALL", CANDS), {})
q2.listed_expiries("ZZZZ", 5, "CALL", CANDS)
check("and is NOT cached (a throttle must not blind the day)", q2.calls, 2)

# --------------------------------------------------------------------------
print("")
if FAILED:
    print("FAILED (%d): %s" % (len(FAILED), ", ".join(FAILED)))
    sys.exit(1)
print("test_expiry_lookup: all good.")
