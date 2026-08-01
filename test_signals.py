"""Run with: python test_signals.py — no test framework needed.
Every line here is taken from, or modelled directly on, the real room."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals as sigmod
from guards import Guards

CFG = {"allowed_symbols": ["SPY", "AAPL", "AMD", "NVDA", "NFLX", "QQQ",
                           "AMZN", "MSFT"]}
NOSTOP = "/tmp/__no_stop_here__"
fails = []


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

# -----------------------------------------------------------------------------
if fails:
    print("FAILED %d check(s):" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
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
    raise SystemExit(1)
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
    raise SystemExit(1)
print("Planning talk is not an order: no adds, trim targets and "
      "from-percents all stay ignored.")
