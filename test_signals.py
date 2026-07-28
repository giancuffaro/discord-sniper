"""Run with: python test_signals.py — no test framework needed.
Every line here is taken from, or modelled directly on, the real room."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals as sigmod
from guards import Guards

CFG = {"allowed_symbols": ["SPY", "AAPL", "AMD", "NVDA", "NFLX", "QQQ"]}
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

# --- trims: a percentage is never mistaken for a price ----------------------
t = check("@Unraveller (Admin)🔮 trimming SPY @everyone @ 45%",
          action="TRIM", fire=False, symbol="SPY", pct=45.0)
ok(t.limit is None, "'@ 45%%' must not be read as a limit price, got %r" % t.limit)
check("@Brett (Admin) trimming AAPL @ 9% @everyone", action="TRIM", fire=False,
      pct=9.0)
check("@Unraveller (Admin)🔮 trimming AMD @everyone", action="TRIM", fire=False,
      symbol="AMD", pct=None)

CLOSER = dict(CFG, trim_action="close")
ok(sigmod.parse("@Brett (Admin) trimming SPY @ 12% @everyone", cfg=CLOSER).fire,
   "trim_action=close should fire on the first trim")

ATPCT = dict(CFG, trim_action="at_pct", close_at_trim_pct=50)
ok(not sigmod.parse("trimming SPY @everyone @ 45%", cfg=ATPCT).fire,
   "45% is under a 50% target — should hold")
ok(sigmod.parse("trimming SPY @everyone @ 50%", cfg=ATPCT).fire,
   "50% meets a 50% target — should close")
ok(not sigmod.parse("trimming AMD @everyone", cfg=ATPCT).fire,
   "a trim with no percentage should hold, not guess")

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
G = {"guards": {"max_qty": 1, "max_trades_per_day": 4, "cooldown_seconds": 0,
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
ok("SPY" in g.open_pos,
   "after out-and-straight-back-in you are still holding SPY, not flat")
ok(g.open_pos["SPY"]["strike"] == 745 and g.open_pos["SPY"]["expiry"] == "7/28",
   "the re-entry is the same contract, so the tracker keeps 7/28 745P")
a, why = g.check(spy_in, 1, 2, "bob", msg_epoch=now())
ok(not a and "already in SPY" in why,
   "you're back in already — a further 'in SPY' would double you up: %s" % why)

# A plain exit with no re-entry does leave you flat, and the dedupe must not
# then swallow a genuine fresh entry on the same ticker.
flat = sigmod.parse("all out of SPY", cfg=CFG)
ok(g.check(flat, 1, 2, "bob", msg_epoch=now())[0], "the plain exit should pass")
g.record(flat)
ok("SPY" not in g.open_pos, "a plain 'all out' leaves you flat")
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
