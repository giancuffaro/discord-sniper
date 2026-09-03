"""Run with: python test_signals.py — no test framework needed.
Every line here is taken from, or modelled directly on, the real room."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals as sigmod
from guards import Guards

CFG = {"allowed_symbols": ["SPY", "AAPL", "AMD", "NVDA", "NFLX", "QQQ",
                           "AMZN", "MSFT", "META"]}
NOSTOP = "/tmp/__no_stop_here__"
fails = []
TOTAL_FAILS = 0


def ok(cond, label):
    if not cond:
        fails.append(label)


def check(text, action=None, fire=None, **want):
    s = sigmod.parse(text, cfg=CFG)
    if fire is not None:
        ok(s.fire == fire, "%r: fire was %s, expected %s (%s)"
           % (text[:52], s.fire, fire, s.why))
    if action is not None:
        ok(s.action == action, "%r: action was %s, expected %s (%s)"
           % (text[:52], s.action, action, s.why))
    for k, v in want.items():
        ok(getattr(s, k) == v, "%r: %s was %r, expected %r"
           % (text[:52], k, getattr(s, k), v))
    return s


# --- LOADING must never buy. The room says so in its own rules message. ------
check("@Unraveller (Admin)🔮 loading AMD 7/31 480P @here",
      action="PREPARE", fire=False, symbol="AMD", strike=480.0, side="PUTS",
      expiry="7/31")
check("@Mike (Admin) loading NVDA 7/31 202.5P @here",
      action="PREPARE", fire=False, strike=202.5)
check("HoneyDrip (Scribe) — 9:15 AM LOADING= Get contracts ready, DO NOT BUY IN "
      "Specfied contracts = Admins are in, look for what their avg is and try to "
      "get in as close as possible to that. @everyone", fire=False)

# --- the entry --------------------------------------------------------------
check("@Unraveller (Admin)🔮 in AMD 7/31 480P @everyone",
      action="OPEN", fire=True, symbol="AMD", side="PUTS", strike=480.0,
      expiry="7/31", limit=None)
check("@Brett (Admin) in AAPL 7/31 345C @ 3.4 @everyone",
      action="OPEN", fire=True, symbol="AAPL", side="CALLS", limit=3.4)
check("@Mike (Admin) in NFLX 7/31 70C @ 1.32 @everyone",
      action="OPEN", fire=True, symbol="NFLX", limit=1.32)

s = check("@Brett (Admin) in AAPL 7/31 345C @ 3.4 @everyone")
ok(s.caller == "Brett", "caller should be Brett, got %r" % s.caller)

# --- exits ------------------------------------------------------------------
check("@Brett (Admin) all out of AAPL @everyone", action="CLOSE", fire=True,
      symbol="AAPL")
check("@Brett (Admin) all out AAPL @ 30% @everyone", action="CLOSE", fire=True,
      symbol="AAPL", pct=30.0)
check("@Unraveller (Admin)🔮 exited SPY, and back in @ 2.84 @everyone",
      action="CLOSE", fire=True, symbol="SPY", limit=2.84)
r = sigmod.parse("@Unraveller (Admin)🔮 exited SPY, and back in @ 2.84", cfg=CFG)
ok(r.warn, "the exit-and-back-in line should carry a warning")
ok(r.reenter, "'exited and back in' has to buy the same contract straight back")
ok(r.reenter_limit == 2.84,
   "2.84 is the price they got back in at, got %r" % r.reenter_limit)
# A plain exit is NOT a re-entry — getting this wrong buys you back into
# something the room just told you to be out of.
ok(not sigmod.parse("all out of AAPL", cfg=CFG).reenter,
   "'all out' must not re-enter")

# --- trims ------------------------------------------------------------------
# The trim_action setting is DELETED — "no filters wanted. id like to follow
# everything to the tee as they do." A trim always parses as TRIM and never
# fires from the parser: the follow-them logic downstream sells its share.
# The percentage still has to be read as a percentage, never a limit price.
t = check("@Unraveller (Admin)🔮 trimming SPY @everyone @ 45%",
          action="TRIM", fire=False, symbol="SPY", pct=45.0)
ok(t.limit is None, "'@ 45%%' must not be read as a limit price, got %r" % t.limit)
check("@Brett (Admin) trimming AAPL @ 9% @everyone", action="TRIM", fire=False,
      pct=9.0)
check("@Unraveller (Admin)🔮 trimming AMD @everyone", action="TRIM", fire=False,
      symbol="AMD", pct=None)
# A trim with no ticker asks the position book instead of guessing.
nt = sigmod.parse("@Brett (Admin) trimming @here", cfg=CFG)
ok(nt.action == "TRIM" and nt.needs_position and not nt.fire,
   "a bare trim hands off to the position book, got %s" % nt.why)

# --- the other room's grammar, verbatim from 7/23 ---------------------------
# These two admins post straight into the channel instead of going through the
# scribe, and they write trades completely differently: no "trimming SPY @ 38%",
# just the bare number. A percentage with no full contract in the line can only
# be a trim — nobody opens a position by posting "34%".
b = check("Brett (Admin) — 11:02 AM In NVDA $210C to July 29th. Stop below $206. "
          "Not a swing- but lotto sized.",
          action="OPEN", fire=True, symbol="NVDA", side="CALLS", strike=210.0,
          expiry="7/29")
ok(b.caller == "Brett", "the header names the caller, got %r" % b.caller)
ok(b.warn, "no price was posted, so it should warn there is nothing to compare against")

# The fill price arrives as its own message a minute later. Nothing to do.
check("Brett (Admin) — 11:04 AM My avg is $3.05", fire=False, action=None)

# Bare trims. No ticker anywhere, so the parser hands off to the guards.
for line in ["Brett (Admin) — 11:19 AM Trimming @here",
             "Brett (Admin) — 11:23 AM 20%",
             "Brett (Admin) — 11:31 AM 28% @here half out",
             "Brett (Admin) — 11:44 AM Out of 80% of my position. Stops moved to $208.30",
             "Brett (Admin) — 11:52 AM Tapped 40% there into $210. Stop moved to $208.70",
             "Brett (Admin) — 12:06 PM 50% @here"]:
    n = check(line, action="TRIM", fire=False)
    ok(n.needs_position, "%r should ask the guards which position it means" % line[-24:])

# Lowercase tickers still resolve from the vocabulary list — it helps the
# parser READ more; nothing is ever refused off it. Trims never fire from the
# parser: the follow-them logic downstream sells its share.
check("Unraveller (Admin) — 10:04 AM 30% on SPY @here",
      action="TRIM", fire=False, symbol="SPY", pct=30.0)
check("Unraveller (Admin) — 10:18 AM 40% in spy now. Down to runners",
      action="TRIM", fire=False, symbol="SPY", pct=40.0)
check("Unraveller (Admin) — 10:09 AM Trimmed more on spy 35% @here",
      action="TRIM", fire=False, symbol="SPY", pct=35.0)

# Talk about the trade is not the trade.
for line in ["Unraveller (Admin) — 9:58 AM Spy holding beautiful",
             "Unraveller (Admin) — 10:12 AM Moving trail stop on spy to 736.5 now",
             "Unraveller (Admin) — 10:58 AM Spy holding our 738 trail stop level. "
             "Still holding runners",
             "Brett (Admin) — 12:14 PM 210 broke Please self manage.",
             "Brett (Admin) — 12:29 PM Still holding my 20% of cons as runners"]:
    check(line, fire=False)

# --- 7/22: three admins, three tickers, and some new shapes -----------------
# An entry with no date on it. The room's own rules say weekly unless they
# spell out 0DTE or a date, so the parser leaves it blank and the bridge fills
# in that week's Friday — one calendar, in one place.
n = check("@Brett (Admin) in SPY 747C @ 3.00 @everyone",
          action="OPEN", fire=True, symbol="SPY", side="CALLS", strike=747.0,
          limit=3.0)
ok(n.expiry is None, "no date in the call means no date invented, got %r" % n.expiry)

import webull_options as wo
import datetime as _dt
for day, want in ((_dt.date(2026, 7, 22), "2026-07-24"),    # a Wednesday
                  (_dt.date(2026, 7, 24), "2026-07-24"),    # Friday itself
                  (_dt.date(2026, 7, 25), "2026-07-31"),    # Saturday rolls on
                  (_dt.date(2026, 6, 29), "2026-07-02")):   # 7/3 is a holiday
    got = wo.weekly_expiry(day)
    ok(got == want, "weekly expiry from %s should be %s, got %s" % (day, want, got))

# "added to SPY, new avg is 2.8" — they doubled up. The parser marks it and
# stops: whether you follow them in depends on three things it can't see, so it
# hands the decision to guards.resolve_add and fires nothing on its own.
a = check("@Brett (Admin) added to SPY @everyone new avg is 2.8",
          fire=False, action="ADD", symbol="SPY", limit=2.8)
ok(a.needs_add, "an add must be flagged for the guards, got %s" % a.why)

# The one that would ruin a day if it were treated as an add. The room posts
# "my avg is 3.05" straight after every single entry. There's no add verb in
# it, so it stays a non-order — otherwise every position doubles itself the
# moment it's opened.
avg = check("@Brett (Admin) my avg is 3.05 @everyone", fire=False)
ok(avg.action != "ADD" and not avg.needs_add,
   "a bare average with no add verb must not read as an add, got %s" % avg.action)

# A trim priced in dollars instead of percent is still a trim.
check("@Mike (Admin) trimming AMZN @everyone +20 dollar per con",
      action="TRIM", fire=False, symbol="AMZN", pct=None)
check("@Unraveller (Admin)🔮 all out of NVDA @ 125% @everyone",
      action="CLOSE", fire=True, symbol="NVDA", pct=125.0)

# The victory lap. Percentages, prices and a ticker, and not one order in it.
for line in [
    "Unraveller (Admin) — 11:18 AM I took the same setup yesterday at 204 and "
    "206 and took same setup at 206 today. Made 35% and 25% yesterday and today "
    "several hundred percent. Never switched bias or altered my conviction.",
    "Unraveller (Admin) — 11:06 AM Wish I told u guys NVDA would squeeze. Who "
    "caught this with me? Gave u several entries and conviction? @everyone",
    "Have a nice day! See you all tomorrow",
    "Mike (Admin) — 10:37 AM This could still work but it's too slow and I don't "
    "like slow action. Can become trappy fast. I just sold at break even @here",
]:
    check(line, fire=False)

# --- working out which position a bare trim meant ---------------------------
RES = {"guards": {"regular_hours_only": False, "max_message_age_seconds": 0,
                  "cooldown_seconds": 0, "max_trades_per_day": 9}}
rg = Guards(RES, here=NOSTOP)
nv = sigmod.parse("Brett (Admin) — 11:02 AM In NVDA 7/29 210C", cfg=CFG)
rg.record(nv, "Brett")

bare = sigmod.parse("Brett (Admin) — 11:19 AM Trimming @here", cfg=CFG)
rg.resolve_symbol(bare, "Brett")
ok(bare.fire and bare.symbol == "NVDA",
   "Brett's bare trim should close Brett's NVDA, got %r (%s)" % (bare.symbol, bare.why))

# The dangerous case: somebody ELSE trims and you're only in Brett's trade.
# Taking it would close a position that admin never put you in.
other = sigmod.parse("Unraveller (Admin) — 11:20 AM 25% @here", cfg=CFG)
rg.resolve_symbol(other, "Unraveller")
ok(not other.fire and not other.symbol,
   "a trim from an admin whose trade you're not in must not close somebody "
   "else's position, got %r" % other.symbol)

empty = Guards(RES, here=NOSTOP)
lone = sigmod.parse("Brett (Admin) — 11:19 AM Trimming @here", cfg=CFG)
empty.resolve_symbol(lone, "Brett")
ok(not lone.fire and "not in anything" in lone.why,
   "a bare trim with nothing open should say so, got %s" % lone.why)

# --- 7/21: the entry that arrives as two messages ---------------------------
# "Loading 205 calls Friday expiration on NVDA" names the contract and buys
# nothing. Six lines later "Filled 3.95 starters" is the actual order and names
# nothing. Neither half is a trade on its own; together they are one.
check("Loading 205 calls Friday expiration on NVDA", fire=False, action="PREPARE",
      symbol="NVDA", side="CALLS", strike=205.0, expiry="WEEKLY")
half = sigmod.parse("Filled 3.95 starters @here", cfg=CFG)
ok(half.action == "OPEN" and not half.fire and half.needs_loaded
   and half.limit == 3.95 and not half.symbol,
   "a bare fill price should be held back, not fired or dropped: %s" % half.why)

lg = Guards(dict(RES, allowed_symbols=CFG["allowed_symbols"]), here=NOSTOP)
lg.remember_loading(sigmod.parse("Loading 205 calls Friday expiration on NVDA",
                                 cfg=CFG), "Unraveller")
got = lg.resolve_loaded(sigmod.parse("Filled 3.95 starters @here", cfg=CFG),
                        "Unraveller")
ok(got.fire and got.symbol == "NVDA" and got.strike == 205.0
   and got.side == "CALLS" and got.expiry == "WEEKLY" and got.limit == 3.95,
   "the fill should take the contract from the loading call, got %r (%s)"
   % (got.human(), got.why))

# Used up. The next bare price from the same admin is them averaging in, and
# you only ever hold the one contract.
again = lg.resolve_loaded(sigmod.parse("Filled 4.20 more", cfg=CFG), "Unraveller")
ok(not again.fire, "a second bare fill must not re-open the same trade: %s" % again.why)

# --- 9/3: RWGates' shape — "$TICKER I took entry $PRICE fill" ---------------
# Same two-message entry as 7/21 above, but the ticker leads the confirmation
# line and "fill" trails the price instead of a fill verb leading it, so the
# original RE_BARE_FILL (message must START with filled/bought/bto/entered)
# never matched it. Silently dropped an NVDA 230C entry on 9/3 (real money:
# nothing was sent, the caller ran it to +100%).
half2 = sigmod.parse("@here $NVDA I took entry 1.37 fill", cfg=CFG)
ok(half2.action == "OPEN" and not half2.fire and half2.needs_loaded
   and half2.limit == 1.37 and not half2.symbol
   and half2.named_symbol == "NVDA",
   "a took-entry fill should be held back with the ticker pinned, not "
   "dropped: %s" % half2.why)

lg2 = Guards(dict(RES, allowed_symbols=CFG["allowed_symbols"]), here=NOSTOP)
lg2.remember_loading(sigmod.parse("Loaded $NVDA .NVDA260904C230", cfg=CFG),
                     "TradeLikeGates")
got2 = lg2.resolve_loaded(
    sigmod.parse("@here $NVDA I took entry 1.37 fill", cfg=CFG),
    "TradeLikeGates")
ok(got2.fire and got2.symbol == "NVDA" and got2.strike == 230.0
   and got2.side == "CALLS" and got2.limit == 1.37,
   "the took-entry fill should take the contract from the loading call, "
   "got %r (%s)" % (got2.human(), got2.why))

# A different ticker's loaded contract must never get paired with a
# took-entry fill that named its own ticker.
lg2.remember_loading(sigmod.parse("Loaded $META .META260904C630", cfg=CFG),
                     "TradeLikeGates")
wrong = lg2.resolve_loaded(
    sigmod.parse("@here $NVDA I took entry 1.37 fill", cfg=CFG),
    "TradeLikeGates")
ok(not wrong.fire, "a took-entry fill naming NVDA must not buy the trader's "
   "last-loaded META instead: %s" % wrong.why)

# --- 9/3: Unraveller's shape — "$TICKER avg $PRICE" with only a LOADING
# behind it, no full-contract message ever fired --------------------------
# "Loading meta 610 puts weeklies" then, 12 minutes later, "Meta avg 5.7
# @here" — the avg line IS the fill. Silently dropped on 9/3 (real money:
# nothing was sent).
avg_half = sigmod.parse("Meta avg 5.7 @here", cfg=CFG)
ok(avg_half.action == "OPEN" and not avg_half.fire and avg_half.needs_loaded
   and avg_half.limit == 5.7 and avg_half.named_symbol == "META",
   "a named-ticker avg should be held back with the ticker pinned, not "
   "dropped: %s" % avg_half.why)

lg3 = Guards(dict(RES, allowed_symbols=CFG["allowed_symbols"]), here=NOSTOP)
lg3.remember_loading(sigmod.parse("Loading meta 610 puts weeklies", cfg=CFG),
                     "Unraveller")
got3 = lg3.resolve_loaded(sigmod.parse("Meta avg 5.7 @here", cfg=CFG),
                          "Unraveller")
ok(got3.fire and got3.symbol == "META" and got3.strike == 610.0
   and got3.side == "PUTS" and got3.limit == 5.7,
   "the avg fill should take the contract from the loading call, got %r (%s)"
   % (got3.human(), got3.why))

# A bare "my avg is $3.05" with NO ticker must stay exactly as before —
# purely informational, never tried against the loading shelf (too
# ambiguous which position it means).
bare_avg = sigmod.parse("My avg is $3.05", cfg=CFG)
ok(bare_avg.action is None and not bare_avg.needs_loaded,
   "a bare avg with no ticker must stay informational, got action=%r why=%s"
   % (bare_avg.action, bare_avg.why))

# And an avg that follows a trade ALREADY filled (no PREPARE on the shelf)
# must still refuse rather than invent a position — same as before this fix.
lg3b = Guards(dict(RES, allowed_symbols=CFG["allowed_symbols"]), here=NOSTOP)
already = lg3b.resolve_loaded(sigmod.parse("SPY avg 2.10 @here", cfg=CFG),
                              "Random Trader")
ok(not already.fire, "an avg with a ticker but nothing loaded for that "
   "trader must refuse, not fire: %s" % already.why)

# --- 9/3: Unraveller's shape again — "Filled $PRICE ... on $TICKER" with a
# NAMED ticker. RE_BARE_FILL used to disable itself the moment a ticker
# appeared in the message, so this fell through to "no contract" and the
# stateless AI-vision fallback guessed a nonsense "AAPL EQUITY @ 2.26" read
# instead of resolving the AAPL 330P Unraveller had just loaded 3 min prior.
named_fill = sigmod.parse("Filled 2.26 starter size on AAPL @here", cfg=CFG)
ok(named_fill.action == "OPEN" and not named_fill.fire
   and named_fill.needs_loaded and named_fill.limit == 2.26
   and named_fill.named_symbol == "AAPL",
   "a named-ticker bare fill should be held back with the ticker pinned, "
   "not dropped: %s" % named_fill.why)

lg4 = Guards(dict(RES, allowed_symbols=CFG["allowed_symbols"]), here=NOSTOP)
lg4.remember_loading(sigmod.parse("Load aapl 330 puts friday exp", cfg=CFG),
                     "Unraveller")
got4 = lg4.resolve_loaded(
    sigmod.parse("Filled 2.26 starter size on AAPL @here", cfg=CFG),
    "Unraveller")
ok(got4.fire and got4.symbol == "AAPL" and got4.strike == 330.0
   and got4.side == "PUTS" and got4.limit == 2.26,
   "the named-ticker fill should take the contract from the loading call, "
   "got %r (%s)" % (got4.human(), got4.why))

# The original no-ticker shape ("Filled 3.95 starters") must still work
# exactly as before — this fix only ADDS the named-ticker path.
still_bare = sigmod.parse("Filled 3.95 starters @here", cfg=CFG)
ok(still_bare.action == "OPEN" and still_bare.needs_loaded
   and still_bare.limit == 3.95 and not still_bare.named_symbol,
   "the original bare (no-ticker) fill shape must be unaffected: %s"
   % still_bare.why)

# --- averaging in -----------------------------------------------------------
# The average_in switch and the add ceiling are DELETED — adds always follow.
# The one rule left isn't a preference: you can only add to a trade you hold.
AVON = {"allowed_symbols": CFG["allowed_symbols"],
        "guards": dict(RES["guards"])}
on = Guards(AVON, here=NOSTOP)
first = sigmod.parse("in SPY 7/31 745C @ 2.40", cfg=CFG)
on.record(first, "Brett")
add1 = on.resolve_add(sigmod.parse("Brett (Admin) added to SPY, new avg is 2.8",
                                   cfg=CFG), "Brett")
ok(add1.fire and add1.action == "ADD", "averaging in should fire: %s" % add1.why)
# The contract comes from what you hold, never from their message — "added to
# SPY" doesn't name a strike, and a different strike isn't averaging.
ok(add1.strike == 745.0 and add1.side == "CALLS" and add1.expiry == "7/31",
   "an add must buy the contract you're holding, got %r %r %r"
   % (add1.strike, add1.side, add1.expiry))
# 2.8 is their blended average across both contracts, not the price of the one
# they just bought — it is not a price you can buy at, so it must not survive as
# the limit on this order.
ok(add1.limit is None,
   "their blended average must not become the limit, got %r" % add1.limit)
on.record(add1, "Brett")
# Positions are keyed by trader now — Brett's SPY, not just SPY.
ok(on.open_pos["brett|SPY"]["qty"] == 2 and on.open_pos["brett|SPY"]["adds"] == 1,
   "after one add you hold two contracts, got %r" % on.open_pos["brett|SPY"])

# No ceiling any more — every add they post follows. Three in a row all fire.
add2 = on.resolve_add(sigmod.parse("Brett (Admin) adding to SPY @ 2.5", cfg=CFG), "Brett")
ok(add2.fire, "the second add follows: %s" % add2.why)
on.record(add2, "Brett")
add3 = on.resolve_add(sigmod.parse("Brett (Admin) adding to SPY @ 2.2", cfg=CFG), "Brett")
ok(add3.fire, "the third add follows too — no ceiling, his rule: %s" % add3.why)

# And the exit sells all three, not one. Selling one would leave you holding
# two contracts while the log says you're flat.
out = sigmod.parse("Brett (Admin) all out of SPY", cfg=CFG)
on.fill_from_position(out)
ok(out.qty == 3, "an exit must sell everything you averaged into, got %r" % out.qty)
ok(on.clamp_qty(out.qty, "CLOSE") == 3,
   "max_qty caps what you buy, never what you sell, got %r"
   % on.clamp_qty(out.qty, "CLOSE"))

# Adding to something you're not in has nothing to average into.
notin = Guards(AVON, here=NOSTOP)
nope = notin.resolve_add(sigmod.parse("Brett (Admin) added to QQQ, new avg 1.9",
                                      cfg=CFG), "Brett")
ok(not nope.fire and "you're not in it" in nope.why,
   "an add on a trade you don't hold must send nothing: %s" % nope.why)

# An unnamed add when that admin has TWO of their own open picks the NEWEST —
# Aristotle runs a swing and a scalp at once, and his bare "Added a lil" is
# always about the trade he just opened, not the swing from Tuesday.
amb = Guards(AVON, here=NOSTOP)
amb.record(sigmod.parse("in SPY 7/31 745C @ 2.40", cfg=CFG), "Brett")
amb.record(sigmod.parse("in NVDA 7/31 210C @ 3.10", cfg=CFG), "Brett")
vague = amb.resolve_add(sigmod.parse("Brett (Admin) adding more, new avg 2.6",
                                     cfg=CFG), "Brett")
ok(vague.fire and vague.symbol == "NVDA",
   "an unnamed add lands on their newest position: %s" % vague.why)

# And an unnamed add from an admin whose trade you're not in must never land on
# somebody else's position — same rule as a bare trim.
theirs = Guards(AVON, here=NOSTOP)
theirs.record(sigmod.parse("in SPY 7/31 745C @ 2.40", cfg=CFG), "Brett")
wrong = theirs.resolve_add(sigmod.parse("Mike (Admin) adding more, new avg 2.6",
                                        cfg=CFG), "Mike")
ok(not wrong.fire, "one admin's add must not average into another's position: "
   "%s" % wrong.why)

# No daily limit means no daily limit. 0 is the setting he runs.
NOCAP = Guards({"guards": dict(RES["guards"], max_trades_per_day=0)}, here=NOSTOP)
NOCAP._count = 500
ok(NOCAP.check(sigmod.parse("in AMD 7/31 480P", cfg=CFG), 1, 2, "bob",
               msg_epoch=time.time())[0],
   "max_trades_per_day 0 must not cap anything")

# Nobody loaded anything. This is the case that would otherwise buy blind.
nolo = Guards(RES, here=NOSTOP)
orphan = nolo.resolve_loaded(sigmod.parse("Filled 3.95 starters", cfg=CFG), "Brett")
ok(not orphan.fire and "can't find the LOADING call" in orphan.why,
   "a fill price with no loading call must not fire: %s" % orphan.why)

# A patient fill still counts. Day one live: Midas loaded before 10:20 and
# posted "Filled at 1.46" at 11:56 — 97 minutes of resting at his price —
# and the old 30-minute window threw the trade away. The window is four
# hours now: the Loaded call names the whole contract, so the late fill is
# unambiguous.
old = Guards(dict(RES, allowed_symbols=CFG["allowed_symbols"]), here=NOSTOP)
old.remember_loading(sigmod.parse("Loading 205 calls Friday expiration on NVDA",
                                  cfg=CFG), "Unraveller")
old.loaded["unraveller"]["ts"] -= 7200
late_fill = old.resolve_loaded(sigmod.parse("Filled 3.95 starters", cfg=CFG),
                               "Unraveller")
ok(late_fill.fire,
   "a fill two hours after the loading call is Midas being patient — it must "
   "fire: %s" % late_fill.why)

# But not FOREVER: past four hours it is yesterday's plan, not this fill.
old.loaded["unraveller"]["ts"] -= 12800
dead_fill = old.resolve_loaded(sigmod.parse("Filled 3.95 starters", cfg=CFG),
                               "Unraveller")
ok(not dead_fill.fire and "too long ago" in dead_fill.why,
   "a fill five-plus hours after the loading call must not fire: %s"
   % dead_fill.why)

# "Loading does not mean enter" is a loading line with no contract in it, so
# there is nothing to pin a later price to.
blank = Guards(RES, here=NOSTOP)
blank.remember_loading(sigmod.parse("Loading does not mean enter", cfg=CFG), "Unraveller")
ok(not blank.loaded, "a loading line with no contract should not be remembered")

# The lines from that day that must stay quiet.
for line in [
    "5-6% risk.",                 # position sizing, not a gain
    "205.7 risk @here",
    "206.5 need to clear now",    # must not become a strike of 5
    "Loading does not mean enter",
    "Staying patient",
    "Finally volume coming in",   # has "in" in it and nothing else
    "Will signal a reentry",
    "207 then 208. Just use emas for runners",
    "Squeezing into close @here choppy day but we nailed the read and entries "
    "today on spy and nvda",
]:
    check(line, fire=False)

# "Full sold" is a complete exit, not a trim — the word FULL is the tell.
check("Full sold nvda close to 25% on weeklies. We are at 208 sqz level now @here",
      fire=True, action="CLOSE", symbol="NVDA")

# --- chatter, verbatim from the room ----------------------------------------
for line in [
    "Mike (Admin) — 9:46 AM This went crazy. Sorry guys missed entry",
    "Mike (Admin) — 10:15 AM Pissed I missed NVDA breakdown but glad we caught "
    "some NFLX cash @here",
    "Brett (Admin) — 10:20 AM 50% on SPY, 30% on AAPL. One 14% loss on AAPL as "
    "well but made it up 2x. Monday sets the tone. @here",
    "Brett (Admin) — 10:23 AM AAPL strongest ticker of session. Look at that read!",
    "With a weak SPY",
    "Use $336.50 as risk if you are still holding! There is a lot of gamma at $340",
    "Mike (Admin) — 10:24 AM NVDA read was spot on. NFLX 20% and sold runners in "
    "the green. Overall great session from the team @here",
]:
    check(line, fire=False)

# --- guards -----------------------------------------------------------------
G = {"guards": {"cooldown_seconds": 0,
                "dedupe_seconds": 60, "regular_hours_only": False,
                "max_message_age_seconds": 0}}
g = Guards(G, here=NOSTOP)
now = time.time

entry = sigmod.parse("in AMD 7/31 480P", cfg=CFG)
a, why = g.check(entry, 1, 2, "bob", msg_epoch=now())
ok(a, "first entry should be allowed: %s" % why)
g.record(entry)

a, why = g.check(entry, 1, 2, "bob", msg_epoch=now())
ok(not a and "already in AMD" in why, "second admin calling AMD should be blocked: %s" % why)

ghost = sigmod.parse("all out of SPY", cfg=CFG)
a, why = g.check(ghost, 1, 2, "bob", msg_epoch=now())
ok(not a and "nothing to close" in why,
   "closing something you don't hold must be refused (it would open a short): %s" % why)

# "exited SPY, and back in @ 2.84" — sold and bought the SAME contract right
# back. The line never names the contract, so the guards have to supply it from
# what's being held, and you have to still be holding it afterwards.
spy_in = sigmod.parse("in SPY 7/28 745P @ 2.76", cfg=CFG)
ok(g.check(spy_in, 1, 2, "bob", msg_epoch=now())[0], "SPY entry should pass")
g.record(spy_in)

spy_out = sigmod.parse("exited SPY, and back in @ 2.84", cfg=CFG)
ok(g.check(spy_out, 1, 2, "bob", msg_epoch=now())[0], "the exit should pass")
ok(spy_out.strike is None and spy_out.expiry is None,
   "the room's line names no contract, so the parser must not invent one")
g.fill_from_position(spy_out)
ok(spy_out.strike == 745 and spy_out.side == "PUTS" and spy_out.expiry == "7/28",
   "the contract should be filled in from the open position, got %r %r %r"
   % (spy_out.strike, spy_out.side, spy_out.expiry))
g.record(spy_out)
# Recorded with no author, so the key's owner is "?" — an unknown-owner
# position still blocks re-entry and still answers exits in that name.
ok("?|SPY" in g.open_pos,
   "after out-and-straight-back-in you are still holding SPY, not flat")
ok(g.open_pos["?|SPY"]["strike"] == 745 and g.open_pos["?|SPY"]["expiry"] == "7/28",
   "the re-entry is the same contract, so the tracker keeps 7/28 745P")
a, why = g.check(spy_in, 1, 2, "bob", msg_epoch=now())
ok(not a and "already in SPY" in why,
   "you're back in already — a further 'in SPY' would double you up: %s" % why)

# A plain exit with no re-entry does leave you flat, and the dedupe must not
# then swallow a genuine fresh entry on the same ticker.
flat = sigmod.parse("all out of SPY", cfg=CFG)
ok(g.check(flat, 1, 2, "bob", msg_epoch=now())[0], "the plain exit should pass")
g.record(flat)
ok("?|SPY" not in g.open_pos, "a plain 'all out' leaves you flat")
a, why = g.check(spy_in, 1, 2, "bob", msg_epoch=now())
ok(a, "a fresh entry after a plain exit must NOT read as a duplicate: %s" % why)

ok(g.clamp_qty(50) == 1, "qty should clamp to max_qty")

stale = Guards({"guards": {"regular_hours_only": False,
                           "max_message_age_seconds": 20}}, here=NOSTOP)
a, why = stale.check(entry, 1, 2, "bob", msg_epoch=now() - 300)
ok(not a and "stale" in why, "an old message should be refused: %s" % why)

chan = Guards({"channel_ids": ["829754942817828884"],
               "guards": {"regular_hours_only": False}}, here=NOSTOP)
a, why = chan.check(entry, 111, 2, "bob", msg_epoch=now())
ok(not a and "channel" in why, "wrong channel should be refused: %s" % why)
a, _ = chan.check(entry, "829754942817828884", 2, "bob", msg_epoch=now())
ok(a, "the right channel should pass")

who = Guards({"author_names": ["honeydrip"], "guards": {"regular_hours_only": False}},
             here=NOSTOP)
ok(not who.check(entry, 1, 2, "randomguy", msg_epoch=now())[0],
   "an untrusted poster should be refused")
ok(who.check(entry, 1, 2, "HoneyDrip", msg_epoch=now())[0],
   "the scribe should be allowed")

# --- Aug 4 fixes: took-an-L, wrong-ticker, exit-with-stray-in ----------------
# "Took an L" and friends are a loss-close (was read as nothing → position sat).
check("we took an L", action="CLOSE")
check("taking the L on this", action="CLOSE")
check("big L today", action="CLOSE")
ok(sigmod.parse("LOL that was close", cfg=CFG).action != "CLOSE",
   "'LOL' must not read as a loss")
ok(sigmod.parse("cool, nice trade", cfg=CFG).action != "CLOSE",
   "'cool' must not read as a loss")

# A loose 'in' that names a ticker must never buy a different ticker's load.
_CFG2 = {"allowed_symbols": ["SPY", "QQQ", "TSLA", "META", "AAPL", "NVDA"]}
_g = Guards(_CFG2, NOSTOP)
_lo = sigmod.parse("Loading tsla 320 puts Friday expiration", cfg=_CFG2)
_lo.caller = "Unraveller"; _g.remember_loading(_lo, "Unraveller")
_en = sigmod.parse("In meta 6.10 avg", cfg=_CFG2); _en.caller = "Unraveller"
ok(_en.named_symbol == "META", "a named 'in' should record the ticker")
_r = _g.resolve_loaded(_en, "Unraveller")
ok(not _r.fire and _r.symbol != "TSLA",
   "'In meta' must refuse when the load is TSLA, never buy TSLA")
# ...but a matching load fires.
_g2 = Guards(_CFG2, NOSTOP)
_lo2 = sigmod.parse("Loading meta 570 puts friday exp", cfg=_CFG2)
_lo2.caller = "Unraveller"; _g2.remember_loading(_lo2, "Unraveller")
_en2 = sigmod.parse("In meta 6.10 avg", cfg=_CFG2); _en2.caller = "Unraveller"
ok(_g2.resolve_loaded(_en2, "Unraveller").fire,
   "'In meta' should fire when the load IS meta")

# Vero: "QQQ OUT 2.10 In one runner on MNQ futures" is a QQQ exit, not an entry.
check("QQQ OUT 2.10 In one runner on MNQ futures.", action="CLOSE", symbol="QQQ")
check("QQQ 717C 8/4 1.50 4 CONTRACTS", action="OPEN", symbol="QQQ")

# Whop (MOD) badge: "Full sold NQ" is an NQ exit, NOT a close on ticker 'MOD'.
_CFGF = {"allowed_symbols": ["SPY", "QQQ", "NQ", "MNQ", "ES", "SLV"]}
_m = sigmod.parse("Full sold NQ $3000 a contract", cfg=_CFGF)
ok(_m.action == "CLOSE" and _m.symbol == "NQ",
   "'(MOD) ... Full sold NQ' must close NQ, never ticker MOD")
print("Aug 4 fixes read: took-an-L closes, wrong-ticker refuses, "
      "an exit with a stray 'in' still closes.")

# -----------------------------------------------------------------------------
if fails:
    print("FAILED %d check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("All checks passed.")

# --- the echo guard ----------------------------------------------------------
# Mike replied to his own morning entry; the scribe line reposted word for
# word and the bot re-bought AMD at top tick. Same trader + same contract +
# same posted price runs ONCE a day. A real re-entry has a new price.
eg = Guards({"guards": {"regular_hours_only": False, "cooldown_seconds": 0,
                        "max_message_age_seconds": 0}}, here=NOSTOP)
first_amd = sigmod.parse("@Mike (Admin) in AMD 7/31 470P @ 3.55 @everyone", cfg=CFG)
ok(eg.check(first_amd, 1, 2, "Mike", msg_epoch=now())[0],
   "the first AMD entry passes")
eg.record(first_amd, "Mike")
# trade closes...
closed_amd = sigmod.parse("@Mike (Admin) all out of AMD @ 56% @everyone", cfg=CFG)
eg.record(closed_amd, "Mike")
echo = sigmod.parse("@Mike (Admin) in AMD 7/31 470P @ 3.55 @everyone", cfg=CFG)
a, why = eg.check(echo, 1, 2, "Mike", msg_epoch=now())
ok(not a and "already ran today" in why,
   "the word-for-word repost must be refused: %s" % why)
fresh = sigmod.parse("@Mike (Admin) in AMD 7/31 470P @ 2.90 @everyone", cfg=CFG)
ok(eg.check(fresh, 1, 2, "Mike", msg_epoch=now())[0],
   "a genuine re-entry at a NEW price still passes")

if fails:
    print("FAILED %d echo-guard check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("A repost is not a trade: the same call at the same price runs once.")


# --- Midas planning out loud, day one live. None of these are orders. -------
# "Not adding" contains "adding", and the ADD pattern would have bought five
# more if we'd been holding his trade. The other two are maps of where he
# MIGHT sell — read as trims they'd have sold.
check("Midas (Admin): Not adding to this position", action=None)
check("Midas (Admin): Some trim targets are 737.70 and lower", action=None)
check("Midas (Admin): Or from 15% profit", action=None)
# But the real actions those words appear near must still fire.
check("Taking more cons @here at 748.50", action="OPEN")
check("Midas (Admin): Trimmed at 17% @here", action="TRIM")

if fails:
    print("FAILED %d Midas-chatter check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Planning talk is not an order: no adds, trim targets and "
      "from-percents all stay ignored.")


# --- day two live: the reader bought a verb. Never again. --------------------
# "I'm going to take 742c starters" fired OPEN TAKE 742C, and "I'm about 80%
# sure" fired a TRIM. Both are Midas narrating a plan, not doing a thing.
check("Midas (Admin): 741.60 is new line in the sand. I'm going to take 742c "
      "starters and add full size at 741.60, stop loss is a 5 min close "
      "below 741.60 @everyone", action=None)
check("Midas (Admin): Multiple tries to break above 742.70 has failed. I'm "
      "about 80% sure market falls without breaking above that level",
      action=None)
# KingBeeAri's challenge-room entry stays a real entry.
s = check("In some light MSFT 462.5 call @everyone", action="OPEN",
          symbol="MSFT", strike=462.5, side="CALLS")

if fails:
    print("FAILED %d plan-talk check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("A plan is not an order: announced intent and confidence percentages "
      "stay ignored, and the challenge room's real entries still fire.")
# --- Felony's Whop shorthand, from the channel survey ------------------------
# Same trades as his Discord screenshots, fewer characters: no @ before the
# price, SL for Stop, "a con" for "a contract".
s = check("Short nq 28240.50 SL 28302", action="OPEN", symbol="NQ")
ok(s.kind == "future" and s.direction == "SHORT",
   "bare 'Short nq 28240.50' is a futures short, got %s/%s" % (s.kind, s.direction))
ok(s.their_stop == 28302.0, "SL 28302 is his stop, got %s" % s.their_stop)
s = check("40 points $800 a con on NQ long - Trimmed", action="TRIM")
ok(s.usd == 800.0, "'$800 a con' carries the honest exit, got %s" % s.usd)
s = check("Trimmed $800 a contract SL at be", action="TRIM")
ok(s.usd == 800.0 and s.their_stop is None,
   "'SL at be' has no number so no stop is invented, got %s/%s"
   % (s.usd, s.their_stop))

if fails:
    print("FAILED %d Whop-shorthand check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Felony's shorthand reads: bare shorts, SL stops, dollars a con.")


# --- the Day Trades room, from his paste of the whole channel ----------------
# Progress updates never trade; verbs do. Resting orders never trade; fills do.
check("Stopped on nq", action="CLOSE", symbol="NQ")
check("Stopped at be", action="CLOSE")
check("Full sold nq 500 points $10,000 a contract", action="CLOSE",
      symbol="NQ", usd=10000.0)
check("Trailed out nq", action="CLOSE", symbol="NQ")
check("First trim order at 28550", action=None)
check("Sell order at 29630", action=None)
check("Buy order sitting at 28934", action=None)
check("Load nvda 205p", action="PREPARE", fire=False, symbol="NVDA")
s = check("Entered nvda July 20th 205c\nAvg 2.25\nSl 203", action="OPEN",
          symbol="NVDA", strike=205.0, expiry="7/20")
ok(s.limit == 2.25, "their Avg is the price they paid, got %s" % s.limit)
check("Made small add into nvda", action="ADD", symbol="NVDA")
check("$1000 a contract", action=None)
check("Up 210 points $4200 a contract", action=None)
check("First trim 37% on SPY", action="TRIM", symbol="SPY")

if fails:
    print("FAILED %d Day-Trades check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Day Trades reads clean: verbs trade, updates and resting orders don't.")


# --- the Futures channel, from his paste --------------------------------------
s = check("Long NQ - AVG 24015\nStop 23990\nTarget 24050", action="OPEN",
          symbol="NQ")
ok(s.limit == 24015.0 and s.their_stop == 23990.0,
   "AVG-style futures entry carries his price and stop, got %s/%s"
   % (s.limit, s.their_stop))
check("Entered NQ short 23477 average\nStop 23515", action="OPEN", symbol="NQ")
check("Stopped\nCouldn't update was busy earlier", action="CLOSE")
check("Stop got hit, was putting little one to bed.", action="CLOSE")
check("Trailing stop hit on RTY, beautiful trade!", action="CLOSE", symbol="RTY")
check("Stopped on gold. Reclaim here is nasty", action="CLOSE", symbol="GC")
check("Don't like this hold - Taking papercut.", action="CLOSE")
check("Again those paper cuts we took yesterday and today gone", action=None)
check("Stops BE won't let this go red!", action=None)
check("Short NQ @ 29792\n\nStop 29840\nTarget 29550\n\nIf we get stopped will "
      "look for re-entry.", action="OPEN", symbol="NQ")

if fails:
    print("FAILED %d Futures-channel check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("The Futures channel reads: AVG entries, seven ways of saying stopped, "
      "papercuts sell, war stories don't.")


# --- High Risk + the 2K challenge, from his pastes ---------------------------
# The near-disaster: a trim update carries a direction, a symbol, a stop with
# digits and the word "in" — everything an AVG-entry needs except the truth.
check("$1,000 a contract on NQ short - Trimmed\n\nStop now BE holding "
      "runners for full target. We are now 9/10 this week. Every winning "
      "trade has been at least 50 points. Be sure to post in gains",
      action="TRIM")
check("Re-Entered NQ short @ 29555\n\nStop 29620\nTarget 29300",
      action="OPEN", symbol="NQ")
check("Re-entered long here @ 23480 on NQ. Stop is candles low - 23440",
      action="OPEN", symbol="NQ")
s = check("Short NQ @ 28165\nSt0p 28225\nTarget 28000", action="OPEN")
ok(s.their_stop == 28225.0, "St0p with a zero still reads, got %s" % s.their_stop)
s = check("Long ES @ 7580\nStop 7565\nTarget 1: 7600\nTarget 2: 7650",
          action="OPEN")
ok(s.their_target == 7600.0,
   "Target 1: 7600 keeps the level, not the label, got %s" % s.their_target)
check("Taking BE on NQ\n\nHave to rock out.", action="CLOSE", symbol="NQ")
s = check("Entered (4) SLV 55C 8/21 @ 1.61\nStop is todays low.\nTarget 60",
          action="OPEN", symbol="SLV", strike=55.0, expiry="8/21")
ok(s.qty == 4, "his (4) is his size, got %s" % s.qty)
check("Stopped on VXX -15%", action="CLOSE", symbol="VXX")

if fails:
    print("FAILED %d High-Risk/2K check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("High Risk and the 2K challenge read clean — and a trim update can "
      "never turn into an entry.")


# --- Market Guru™ Alerts: labeled futures entry + point-count management ------
# Ticker:/Entry:/Stoploss: is one message (newlines collapse to spaces). The
# micro symbol trades, the extra words are noise, entry/stop are index points.
# Then management is bare point counts: a verb acts, a lone number is a brag.
s = check("Ticker:\n`MNQ SHORT SMALL RISKY TRADE`\nEntry:\n28590\nStoploss:\n28620",
          action="OPEN", fire=True, symbol="MNQ", direction="SHORT",
          kind="future", limit=28590.0)
ok(s.their_stop == 28620.0, "their stop rides along, got %s" % s.their_stop)
check("Ticker:\n`MNQ LONG`\nEntry:\n28465\nStoploss:\n28430",
      action="OPEN", fire=True, symbol="MNQ", direction="LONG", limit=28465.0)
# management — trims and the exit resolve against what you hold; brags don't act
s = check("14 points trim", action="TRIM")
ok(s.needs_position, "a bare points trim has to find the position it belongs to")
check("45 points trim 2", action="TRIM")
check("102 points exit      target hit", action="CLOSE")
check("16 points", fire=False, action=None)
check("309 points omg", fire=False, action=None)
# and it must NOT eat Felony's dollar-carrying trim
s = check("40 points $800 a con on NQ long - Trimmed", action="TRIM")
ok(s.usd == 800.0, "Felony's $800-a-con exit still survives, got %s" % s.usd)

if fails:
    print("FAILED %d Market-Guru check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Market Guru reads: labeled futures entry with the stop, point-count "
      "trims and exits resolve to the held position, brags stay quiet, and "
      "Felony's dollar exit is left untouched.")


# --- "Open / Update / Closed" alert-bot format (JPM Options) ------------------
# Open buys; the running "Update ... (+N%)" posts are P&L tracking and must NOT
# read as trims; Closed exits. A keyword with no contract does nothing.
check("Open\nSPY 08/03 753C @.92", action="OPEN", fire=True,
      symbol="SPY", strike=753.0, side="CALLS", expiry="08/03", limit=0.92)
check("Update\nSPY 08/03 753C @1.29 (+40%)", fire=False, action=None)
check("Update\nSPY 08/03 753C @1.83 (+100%)", fire=False, action=None)
check("Closed\nSPY 08/03 753C @3.68", action="CLOSE", symbol="SPY", strike=753.0)
check("Open the discussion for today", fire=False, action=None)

if fails:
    print("FAILED %d JPM check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("JPM Options reads: Open buys, the +% Updates are ignored as P&L "
      "tracking, Closed exits, and a bare keyword with no contract is nothing.")


# --- Bullwinkle (ZTRADEZ) format ---------------------------------------------
# "TICKER | $STRIKE C/P PREMIUM" options and "/MES | LONG HERE" futures. The
# premium is the plain decimal after the side, never a "$266.50 break" level.
# CC (covered call) and CSP (cash-secured put) are SELLING strategies and must
# NEVER be read as a buy.
check("AMD | $550 C 12.72", action="OPEN", fire=True, symbol="AMD",
      strike=550.0, side="CALLS", limit=12.72)
check("QQQ $707 P 8.75 NEXT WEEK", action="OPEN", fire=True, symbol="QQQ",
      strike=707.0, side="PUTS", limit=8.75)
check("NVDA | $205 C 2.45 NEXT W ON THE BREAK OF $197.85", action="OPEN",
      fire=True, symbol="NVDA", strike=205.0, side="CALLS", limit=2.45)
check("SPY | $742 C 4.49 7/31", action="OPEN", fire=True, symbol="SPY",
      strike=742.0, side="CALLS", limit=4.49, expiry="7/31")
s = check("/MES | LONG HERE", action="OPEN", fire=True, symbol="MES")
ok(s.kind == "future" and s.direction == "LONG", "the /MES call is a long future")
check("MES | SHORT HERE", action="OPEN", fire=True, symbol="MES", direction="SHORT")
# The money-critical ones: selling strategies must NOT buy.
check("AEO | $13 CSP .45 AUG", fire=False, action=None)
check("IBIT | $39 CC 1.92 JULY", fire=False, action=None)
check("MARA | $6 CSP .35 DEC", fire=False, action=None)
check("NVDA | 1.80 TOP FLOW L", fire=False, action=None)

if fails:
    print("FAILED %d Bullwinkle check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Bullwinkle reads: TICKER | $strike C/P premium buys (premium not the "
      "break level), /MES LONG HERE is a long future, and CC/CSP selling "
      "strategies are never bought.")


# --- four more z-trades bots: Market Bishop, Vero, MR.TOPHAT, EvaPanda --------
check("I'm Entering Option: NOW 97 C 7/24 Entry: 0.82", action="OPEN", fire=True,
      symbol="NOW", strike=97.0, side="CALLS", expiry="7/24", limit=0.82)
check("QQQ 708C 7/21 1.03 2 CONTRACTS", action="OPEN", fire=True, symbol="QQQ",
      strike=708.0, side="CALLS", expiry="7/21", limit=1.03)
check("SPY 757P 8/3 1.13 4 CONS - Looking for 7600 on ES", action="OPEN",
      fire=True, symbol="SPY", strike=757.0, side="PUTS", limit=1.13)
# SPX isn't tradeable on Webull. Normally retargeted to SPY at 1/10 the
# strike (INDEX_ETF in signals.py), but SPX_ENTRIES_ENABLED was switched
# off 8/15 ("for now") - a fresh SPX entry is refused outright instead,
# symbol/strike/limit left exactly as the room posted them.
check("lotto yolo SPX 7460C 0dte @0.25 QUICK SCALP LOTTO!!", action="OPEN",
      fire=False, symbol="SPX", strike=7460.0, side="CALLS", limit=0.25)
check("Close STC NVDA 07/31/2026 200c @ 1.36 all out", action="CLOSE",
      symbol="NVDA", strike=200.0)
# guards: EvaPanda "Update:" analysis is ignored; a lotto recap with % is not a buy
check("Update: IWM 300C 8/7 ~ 0.47 - waiting to see 296 break", fire=False, action=None)
check("lotto SPX 7460C @3.00 +200% huge win", fire=False, action=None)

if fails:
    print("FAILED %d z-bot check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Market Bishop / Vero / MR.TOPHAT / EvaPanda read: labeled 'Entering "
      "Option' buys, 'N CONTRACTS' buys, a lotto lead buys, STC closes, and "
      "analysis Updates and lotto recaps do nothing.")


# --- Boka: JonnyOptions (adding_is_entry) + Sir Goldman ENTRY/COMMENT ---------
# JonnyOptions writes both "adding" and "added" for a fresh entry, sometimes
# with the fill price, sometimes only a share-support level that must NOT become
# the premium.
BOKA = {"allowed_symbols": ["SPY", "SPX", "LMND", "ONDS", "MRVL", "HOOD",
                            "CIFR", "USAR", "NVTS", "INOD", "ORCL", "ZETA",
                            "ASTS", "SOFI", "RIVN"],
        "adding_is_entry": True}


def bcheck(text, action=None, fire=None, **want):
    s = sigmod.parse(text, cfg=BOKA)
    if fire is not None:
        ok(s.fire == fire, "%r: fire was %s, expected %s (%s)"
           % (text[:52], s.fire, fire, s.why))
    if action is not None:
        ok(s.action == action, "%r: action was %s, expected %s (%s)"
           % (text[:52], s.action, action, s.why))
    for k, v in want.items():
        ok(getattr(s, k) == v, "%r: %s was %r, expected %r"
           % (text[:52], k, getattr(s, k), v))
    return s


# past-tense "added <contract>" was a silent miss — now a fresh entry
bcheck("added $ONDS 10c 7/17 @Premium", action="OPEN", fire=True,
       symbol="ONDS", strike=10.0, side="CALLS", expiry="7/17")
# a share-support "@ $52" must never be read as the option premium
bcheck("adding $LMND 65c 6/18 @Premium,buying this off strong support @ $52 + "
       "we are sweeping the swing low filling the mid because the spread is "
       "like .50", action="OPEN", fire=True, symbol="LMND", strike=65.0,
       side="CALLS", expiry="6/18", limit=None)
# "filled 10.00" IS the premium
bcheck("adding $MRVL 250c 7/17 filled 10.00 @Premium", action="OPEN", fire=True,
       symbol="MRVL", strike=250.0, expiry="7/17", limit=10.0)
# "avg 8.70" still read as premium
bcheck("adding $HOOD 115c 8/7 @Premium avg 8.70", action="OPEN", fire=True,
       symbol="HOOD", strike=115.0, expiry="8/7", limit=8.7)
# trims / exits unchanged
bcheck("stopped out $USAR @Premium", action="CLOSE", fire=True, symbol="USAR")
bcheck("all out of $NVTS here at 600% @Premium", action="CLOSE", fire=True,
       symbol="NVTS")
bcheck("30% $CIFR taking my first trim here @Premium", action="TRIM",
       symbol="CIFR")
# Sir Goldman: ENTRY fires, COMMENT never does
# SPX isn't tradeable on Webull. Normally retargeted to SPY at 1/10 the
# strike (INDEX_ETF in signals.py), but SPX_ENTRIES_ENABLED was switched
# off 8/15 ("for now") - a fresh SPX entry is refused outright instead.
bcheck("@Premium ENTRY $SPX 7575c @ 1.2 LOTTO no Sl, holding this for "
       "afternoon rally", action="OPEN", fire=False, symbol="SPX",
       strike=7575.0, side="CALLS", limit=1.2)
bcheck("@Premium COMMENT Calls off the 5m", fire=False, action=None)
# advice / P&L musings must not read as trims
bcheck("Make sure u take trims and hold runners for breakeven", fire=False,
       action=None)
bcheck("Probably only got 10% out of that", fire=False, action=None)

if fails:
    print("FAILED %d Boka check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Boka reads: JonnyOptions 'added/adding' entries (share level never the "
      "premium, 'filled'/'avg' is), trims/exits, Sir Goldman ENTRY vs COMMENT, "
      "and advice/recap lines fire nothing.")


# --- ZT opt rooms: are alerts, stockguy007, Nitro Trades --------------------
ZT = {"allowed_symbols": ["SPY", "QQQ", "NVDA", "AAPL", "HPE", "SLV", "GLD",
                          "USO", "XLY", "ROKU", "TSLA", "AMZN", "PLTR"]}


def zcheck(text, action=None, fire=None, **want):
    s = sigmod.parse(text, cfg=ZT)
    if fire is not None:
        ok(s.fire == fire, "%r: fire was %s, expected %s (%s)"
           % (text[:52], s.fire, fire, s.why))
    if action is not None:
        ok(s.action == action, "%r: action was %s, expected %s (%s)"
           % (text[:52], s.action, action, s.why))
    for k, v in want.items():
        ok(getattr(s, k) == v, "%r: %s was %r, expected %r"
           % (text[:52], k, getattr(s, k), v))
    return s


# are alerts: OPEN with a short lead-in, and the "SPOT on" non-ticker
zcheck("For my small fries : OPEN $HPE $30 call 5/15 @ 0.50 (swing)",
       action="OPEN", fire=True, symbol="HPE", strike=30.0, side="CALLS",
       expiry="5/15", limit=0.50)
zcheck("OPEN $NVDA $205 call 7/20 @ 4.28 (swing)", action="OPEN", fire=True,
       symbol="NVDA", strike=205.0, expiry="7/20", limit=4.28)
zcheck("Past few positions we have been SPOT on with direction, just early and "
       "getting stopped out", fire=False, action=None)
# stockguy007: spelled-out entries, the " APP " badge is not a ticker
zcheck("USO Calls Jul 18th exp 74 Might swing overnight", action="OPEN",
       fire=True, symbol="USO", strike=74.0, side="CALLS", expiry="7/18")
zcheck("SPY Puts Aug 6th exp 630s", action="OPEN", fire=True, symbol="SPY",
       strike=630.0, side="PUTS", expiry="8/6")
zcheck("AAPL Calls Aug 22dn exp 235s", action="OPEN", fire=True, symbol="AAPL",
       strike=235.0, expiry="8/22")
zcheck("ROKU Calls May 15th 120s", action="OPEN", fire=True, symbol="ROKU",
       strike=120.0, expiry="5/15")
zcheck("stockguy007 APP — 9/26/25, 10:28 AM Friday, September 26, 2025 at "
       "10:28 AM Stopping out here guys", symbol=None)  # not CLOSE APP
# Nitro Trades: labeled entry with price, and "on watch" fires nothing
zcheck("Entry Contract: TSLA $390p Price: $1.75 Comments:none", action="OPEN",
       fire=True, symbol="TSLA", strike=390.0, side="PUTS", limit=1.75)
zcheck("Entry Contract: TSLA $412.5c Price: $2.22 Comments:none", action="OPEN",
       fire=True, symbol="TSLA", strike=412.5, side="CALLS", limit=2.22)
# Platinum Blue Collar (9/2): labelled template with a risk % and a
# leading-dot premium — was bailing as "that's their risk" before the
# contract was read. Both parsers must see BTO SPY 764C @ 0.50.
zcheck("Challenge Account LONG SETUP Ticker: SPY Contract: 764 C Entry Zone: .50 "
       "Risk: 20% Stop TP1: 20% TP2: 763.93 @Options Scalps", action="OPEN",
       fire=True, symbol="SPY", strike=764.0, side="CALLS", limit=0.5)
zcheck("SHORT SETUP Ticker: QQQ Contract: 705 P Entry Zone: 1.10 Risk: 25%", action="OPEN",
       fire=True, symbol="QQQ", strike=705.0, side="PUTS", limit=1.1)
# Discord "Server Tag" junk around a call (9/2, Vero's SPY 763C parsed as nothing)
zcheck("Vero [PAID], Server Tag: PAID PAID SPY 763C 9/2 1.22 2 CONTRACTS @vero-alerts",
       action="OPEN", fire=True, symbol="SPY", strike=763.0, side="CALLS", limit=1.22)
zcheck("risking 20% on this one", action=None)
# COLLECTIVE CORPUS (9/2 evening): formats found by replaying 13 days of every room.
zcheck("@everyone 0DTE GOOGL 345C .84 IG: ClutchInvestments | None of this is financial advice",
       action="OPEN", fire=True, symbol="GOOGL", strike=345.0, side="CALLS", limit=0.84)
zcheck("@everyone Swing: 9/04 SMR 10C .54 Grabeed HALF POSITION. Will add on pullback if we get one.",
       action="OPEN", fire=True, symbol="SMR", strike=10.0, side="CALLS", limit=0.54)
zcheck("Contract: QQQ $711 p Price: $1.68 @Options Scalps", action="OPEN", fire=True,
       symbol="QQQ", strike=711.0, side="PUTS", limit=1.68)
zcheck("Aapl Aug 26 315 call at 1.75 Tartet 2.10", action="OPEN", fire=True,
       symbol="AAPL", strike=315.0, side="CALLS", limit=1.75)
zcheck("I'm in 80 C 9/18s for uber", action="OPEN", fire=True, symbol="UBER", strike=80.0, side="CALLS")
zcheck("Short NQ @ 29530 Stop 29570 Target 29450 Very high risk here as we are hovering right over "
       "intraday lows + PWL. Entering early as if we break this should see a nice move",
       action="OPEN", fire=True, symbol="NQ", limit=29530.0)
zcheck("MGC SHORT (1m) @ 4496.35 | TP:4484.35 SL:4504.35 | Prob:88.4% | R:R:1.5 NEW POTENTIAL SIGNAL - "
       "MGC SHORT A setup has been detected on the futures radar. probability",
       action="OPEN", fire=True, symbol="MGC", limit=4496.35)
zcheck("@everyone MES quick short here 7697", action="OPEN", fire=True, symbol="MES", limit=7697.0)
zcheck("mnq long 29100 Do not take this as financial advice! || 09:56:24 EST", action="OPEN",
       fire=True, symbol="MNQ", limit=29100.0)
zcheck("@everyone Update SPY 08/19 771P @.89 (+25%) Jpm Options", action=None)
zcheck("Idea Watching AMZN 260 call 8/28 @Namrood", action=None)
# Partial sells are trims, gains-reported closes are closes (9/2 corpus)
zcheck("sold 1/2 UPS here", action="TRIM", fire=False, symbol="UPS", pct=50.0)
zcheck("sell 2/3 UPS 105 calls sept 18th from 1.75 to 2.60 for 45-50% WIN!!", action="TRIM", symbol="UPS")
zcheck("sold the rest of UPS", action="CLOSE", fire=True, symbol="UPS")
zcheck("closed AAPL for +20%", action="CLOSE", fire=True, symbol="AAPL")
zcheck("QQQ OUT @ 150% PROFIT", action="CLOSE", fire=True, symbol="QQQ")
zcheck("sold some AAPL 315C into strength, holding the rest", action="TRIM", symbol="AAPL")
# Discord row junk around a forwarded call
zcheck("ZTRADEZ BOT APP — 9:44 AM Wednesday, September 2, 2026 at 9:44 AM Forwarded @everyone Open SPY 09/02 763C @1.04 Jpm Options | For Informational Purposes Only",
       action="OPEN", fire=True, symbol="SPY", strike=763.0, side="CALLS", limit=1.04)
zcheck(":green_alert: AAPL | $335 C SEPT 18 3.65-3.70 @everyone Spoiler", action="OPEN", fire=True,
       symbol="AAPL", strike=335.0, side="CALLS", limit=3.65)
zcheck("Comment TSLA $400c on watch", fire=False, action=None)
zcheck("Comment NVDA $187.5c on watch, will be quarter sized again", fire=False,
       action=None)

if fails:
    print("FAILED %d ZT-opt check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("ZT opt reads: are-alerts OPEN with a lead-in (SPOT-on ignored), "
      "stockguy007 spelled-out entries (APP badge never a ticker), Nitro "
      "'Entry Contract' buys with price, and 'on watch' fires nothing.")


# --- ZT batch 2: King Maker, KuMo, Adex, Namrood, Stormzy + safety -----------
ZB = {"allowed_symbols": ["SPY", "QQQ", "NVDA", "TSLA", "AMD", "MU", "GOOGL",
                          "MSFT", "MA", "COST", "LOW", "TJX", "CAVA", "TWLO",
                          "RILY", "AIRS", "MNQ"]}


def bch(text, action=None, fire=None, **want):
    s = sigmod.parse(text, cfg=ZB)
    if fire is not None:
        ok(s.fire == fire, "%r: fire was %s, expected %s (%s)"
           % (text[:52], s.fire, fire, s.why))
    if action is not None:
        ok(s.action == action, "%r: action was %s, expected %s (%s)"
           % (text[:52], s.action, action, s.why))
    for k, v in want.items():
        ok(getattr(s, k) == v, "%r: %s was %r, expected %r"
           % (text[:52], k, getattr(s, k), v))
    return s


# King Maker: entry fires; a % update is a trim, not an entry
bch("@everyone RILY 07/17 $8 Call @$0.60 SL: RILY < $7.10", action="OPEN",
    fire=True, symbol="RILY", strike=8.0, side="CALLS", expiry="7/17", limit=0.60)
bch("@everyone SYY 06/18 $80 Calls @$1.40, up +22%! trimming some for profits!",
    fire=False)  # update, not an entry
# KuMo: single-leg entry fires; a debit spread does NOT
bch("@everyone Weekly CAVA 07/17/26 $100 Call @$1.50-$1.60 PT1: $2.10",
    action="OPEN", fire=True, symbol="CAVA", strike=100.0, expiry="7/17", limit=1.50)
bch("@everyone Update KSS 08/21/26 $18.5/$20 Call Debit Spread close to PT2",
    fire=False)  # spread, skipped
# Adex: Entering fires as an OPEN (was mis-reading as ADD)
bch("Entering $MA 535C 6/18 @4.5", action="OPEN", fire=True, symbol="MA",
    strike=535.0, side="CALLS", expiry="6/18", limit=4.5)
bch("Entering: $LOW 230C 8/21 @3.30", action="OPEN", fire=True, symbol="LOW",
    strike=230.0, limit=3.30)
# Namrood: Buy To Open fires
bch("@everyone Buy To Open MSFT 400C 1DTE $2.6", action="OPEN", fire=True,
    symbol="MSFT", strike=400.0, side="CALLS", limit=2.6)
bch("@everyone Lotto Trade — RISKY TSLA 402.5C 7/17/2026 $3.35", action="OPEN",
    fire=True, symbol="TSLA", strike=402.5, limit=3.35)
# Stormzy futures: entry fires with direction
sz = bch("@everyone Trade Alert TRADE ENTRY - MNQ Shorts - 1/4 Size Position "
         "Entry: 28163.75 Sl: 28194.50", action="OPEN", fire=True, symbol="MNQ")
ok(sz.kind == "future" and sz.direction == "SHORT" and sz.limit == 28163.75,
   "Stormzy MNQ short entry price")
# Safety: garbage words by OUT never become a ticker that fires
bch("OUT ALL BUT 1 SL ENTRY LETTING IT RIDE", symbol=None)
bch("WILL STOP OUT @ .97", symbol=None)
bch("OUT HALF", symbol=None)

if fails:
    print("FAILED %d ZT-batch-2 check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("ZT batch 2 reads: King Maker/KuMo/Adex/Namrood option entries and "
      "Stormzy futures fire; % updates and debit spreads don't; and 'OUT ALL "
      "BUT 1' / 'WILL STOP OUT' never invent a ticker.")


# --- Aug 12 regression: AI-reader canonical text must keep its stated month --
# 8/12 13:47: the AI reader read 'META | $585 C AUG 21 10.10 @everyone' fine
# (expiry "AUG 21", 0.95 confidence) and handed back the canonical string
# "BTO META $585C AUG 21 @ 10.1" for the regex parser to re-read - but the
# expiry never made it into the order, so bridge.py's "no date in that call"
# fallback silently substituted that week's Friday (8/14 instead of 8/21) and
# bought the wrong contract. Same miss hit AMZN (twice) and SPCX and NVDA
# that same morning. These four are the real canonical strings the AI reader
# produced for those exact messages, straight from bridge.log.2 - if the
# regex parser ever again lets the month drop out of one of these, this fails.
check("BTO META $585C AUG 21 @ 10.1", action="OPEN", fire=True,
      symbol="META", side="CALLS", strike=585.0, expiry="8/21", limit=10.1)
check("BTO AMZN $277.5C AUG 21 @ 2.4", action="OPEN", fire=True,
      symbol="AMZN", side="CALLS", strike=277.5, expiry="8/21", limit=2.4)
check("BTO SPCX $155C AUG 21 @ 2.84", action="OPEN", fire=True,
      symbol="SPCX", side="CALLS", strike=155.0, expiry="8/21", limit=2.84)
check("BTO NVDA $217.5P AUG 21 @ 2.42", action="OPEN", fire=True,
      symbol="NVDA", side="PUTS", strike=217.5, expiry="8/21", limit=2.42)

if fails:
    print("FAILED %d Aug-12 expiry-regression check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    TOTAL_FAILS += len(fails)
    fails = []
print("Aug 12 expiry regression: AI-reader canonical strings for META/AMZN/"
      "SPCX/NVDA all keep their stated AUG 21 expiry through the regex parser "
      "- none silently fall back to that week's Friday.")

# --- final tally across every section ---------------------------------------
TOTAL_FAILS += len(fails)
if TOTAL_FAILS:
    print("\nTOTAL: %d failing check(s) across the whole suite." % TOTAL_FAILS)
    raise SystemExit(1)
print("\nTOTAL: all checks passed across the whole suite.")
