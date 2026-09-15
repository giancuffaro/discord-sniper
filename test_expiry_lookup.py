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

# THE TEST MUST NOT WRITE TO THE REAL TRADE LOG (9/15). bridge.note() appends
# to trades.log, which is the money record the journal is built from. Every run
# of this file was dropping fake EXPIRY/LISTING lines about TSLA 357.5C and
# INTC 97C into it, mixed in with real fills — 15 of them on 9/15 alone. The
# lines go to LOG instead; assert on LOG if a test ever needs to read them.
bridge.note = lambda *a, **k: LOG.append(" ".join(str(x) for x in a))


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
print("\n7. _verify_listed — a date the CALLER typed still has to be real")
# 9/14's recap posted "INTC 9/14 97C" — a MONDAY expiry on a stock that has no
# Monday expirations. Mon/Wed exist on the nine Qualifying Securities only.
# The next Monday that is not today — a real future date the broker will
# not list for a stock outside the nine Qualifying Securities.
_t = dt.date.today()
MON = (_t + dt.timedelta(days=((7 - _t.weekday()) % 7) or 7)).isoformat()


def vorder(sym, strike, expiry, side="CALLS", limit=0.90, guessed=False):
    o = order(sym=sym, strike=strike, side=side, limit=limit)
    o["expiry"] = expiry
    if guessed:
        o["_expiry_guessed"] = True
    return o


# The contract is listed -> silence, and exactly one call.
wb = FakeWB({FRIDAY: 0.95})
o = vorder("INTC", 97, FRIDAY)
check("a listed date passes", with_wb(wb, lambda: bridge._verify_listed("INTC", o)), "")
check("one call to check it", wb.calls, 1)
check("and it is marked verified", o.get("_expiry_verified"), True)

# Verified once, never asked again.
wb2 = FakeWB({FRIDAY: 0.95})
check("an already-verified order is not re-asked",
      with_wb(wb2, lambda: bridge._verify_listed("INTC", o)), "")
check("so no call was spent", wb2.calls, 0)

# The contract is NOT listed, but siblings are -> REFUSE, and say who said it.
wb3 = FakeWB({FRIDAY: 0.95})
o3 = vorder("INTC", 97, MON)
msg = with_wb(wb3, lambda: bridge._verify_listed("INTC", o3))
check_in("an unlisted date is refused", "BAD-CONTRACT INTC 97C %s" % MON, msg)
check_in("names what IS listed", FRIDAY, msg)
check_in("names the room and the raw alert", "the room said:", msg)
check("two calls: the date, then the rest of the week", wb3.calls, 2)
check("and it is NOT marked verified", o3.get("_expiry_verified"), None)

# NOTHING answers -> that is the feed, not the contract. Fail OPEN.
wb4 = FakeWB({})
o4 = vorder("INTC", 97, MON)
check("a dead feed never becomes a trading halt",
      with_wb(wb4, lambda: bridge._verify_listed("INTC", o4)), "")

# An exception is a guard failing, not a trade failing.
wb5 = FakeWB({FRIDAY: 0.95}, blow_up=True)
check("a throttle lets the order through",
      with_wb(wb5, lambda: bridge._verify_listed("INTC", 
              vorder("INTC", 97, MON))), "")

# No connection at all.
check("no broker, no opinion",
      with_wb(None, lambda: bridge._verify_listed("INTC", vorder("INTC", 97, MON))), "")

# Only entries. A close uses the contract you hold, never a guess.
wb6 = FakeWB({FRIDAY: 0.95})
oc = vorder("INTC", 97, MON)
oc["action"] = "CLOSE"
check("a CLOSE is never second-guessed",
      with_wb(wb6, lambda: bridge._verify_listed("INTC", oc)), "")
check("and costs nothing", wb6.calls, 0)

# Futures have no OCC symbol.
wb7 = FakeWB({})
of = vorder("MNQ", 24000, MON)
of["kind"] = "future"
check("futures are skipped",
      with_wb(wb7, lambda: bridge._verify_listed("MNQ", of)), "")

# The switch.
_old = bridge.EXEC
try:
    bridge.EXEC = dict(_old or {})
    bridge.EXEC["verify_listed"] = False
    wb8 = FakeWB({FRIDAY: 0.95})
    check("execution.verify_listed=false turns it off",
          with_wb(wb8, lambda: bridge._verify_listed("INTC", vorder("INTC", 97, MON))), "")
    check("and spends nothing", wb8.calls, 0)
finally:
    bridge.EXEC = _old

# A GUESSED date gets the siblings in the SAME call, so the price gate can
# switch to the one that matches what the caller actually posted.
wb9 = FakeWB({TODAY: 1.45, FRIDAY: 7.40})
og = vorder("TSLA", 357.5, FRIDAY, limit=1.42, guessed=True)
msg9 = with_wb(wb9, lambda: bridge._verify_listed("TSLA", og))
check("a guessed date is price-checked too", msg9, "")
check("and switched to the one the caller priced", og["expiry"], TODAY)
check("in one call, not two", wb9.calls, 1)

# A date the caller TYPED is never second-guessed on price — only on existence.
wb10 = FakeWB({FRIDAY: 7.40})
ot = vorder("TSLA", 357.5, FRIDAY, limit=1.42)
check("a stated date is not price-switched",
      with_wb(wb10, lambda: bridge._verify_listed("TSLA", ot)), "")
check("and keeps the date the caller typed", ot["expiry"], FRIDAY)

# --------------------------------------------------------------------------
print("")
if FAILED:
    print("FAILED (%d): %s" % (len(FAILED), ", ".join(FAILED)))
    sys.exit(1)
print("test_expiry_lookup: all good.")
