"""Tiered ratchet — his ask, 9/2/26.

WHY TIERS EXIST
---------------
A percentage is not the same amount of noise at every premium. The bid on a
$0.40 contract moves in $0.01 ticks, so ONE tick is 2.5% — a "breakeven" stop
on a cheap lotto sits inside the spread and gets scratched by a quote flicker,
not by the market. That same 5% on a $4.00 contract is $0.20, several ticks
away, and perfectly safe to use.

So the rule stops being one number and becomes three, picked off what he
actually PAID for the contract:

    UNDER $1.00   arms +25%, first lock +10%, then +15% a rung   (loose)
    $1.00-$1.99   arms +15%, first lock  0% (BE), then +10%      (middle)
    $2.00 AND UP  arms +10%, first lock  +5%, then  +5%          (tight)

Cheap contracts lock LATER but lock MORE per rung. Expensive contracts lock
early and often, because their noise floor is small enough to allow it.

TWO SAFETY FLOORS
-----------------
1. TICK FLOOR (widens the rung) — a rung must be worth at least 4 ticks of the
   contract's own tick size ($0.01 under $3.00, $0.05 at or above). A 5% rung
   on a $3.00 contract is $0.15 = 3 ticks, too tight, so the step is widened
   until it clears 4 ticks.
2. SPREAD FLOOR (lowers the stop) — the new stop must sit at least one full
   bid/ask spread under the live bid. If the spread is $0.20 and the ratchet
   wants the stop $0.08 under the bid, that stop lives INSIDE the noise and
   gets hit by the quote, not by the trade.

Neither floor ever moves a stop DOWN from where it already sits. They only
refuse to raise it somewhere unsafe; the trade then keeps its old stop until
it earns the room for a better one.
"""

# premium ceiling -> (arm_pct, first_lock_pct, step_pct)
#
# 9/3 — G, in his own words, restoring the ladder he wrote the bot around:
#   "it was supposed to start all along from -10% and +10%. When it touched
#    +10% the new stop becomes automatically 0%, and the next target is 20%.
#    When 20% is touched the new stop is +10% and the new target is +30%.
#    When +30% is touched the new stop is +20%, and so on and so forth."
# So: ONE ladder for every premium — arm at +10%, first lock breakeven, then
# a rung every +10%. The 9/2 price tiers (cheap contracts arming later so a
# one-tick wiggle couldn't scratch them) are retired; his rule is the rule.
# The two safety FLOORS below still apply and will say so in the log when
# they move one of his numbers: a rung must clear 4 ticks, and the stop is
# never placed inside the spread.
#
# 9/8 — RESPACED, same shape, off real data. ratchet_sweep.py backtested
# (born_pct, arm_pct) pairs against 80 real fills (Gian's own trades
# excluded, refused/nofill calls excluded — see that file's docstring for
# why). The 10/10 pair above actually LOST money in that sample: -$434
# total, ranked 30th of 50 spacings tried. Best found: born 7.5%, arm 5%
# (this file's arm/lock/step — the born stop itself lives in settings.json
# strategy.stop_loss_pct, moved 10 -> 7.5 the same day) at +$251, and the
# shape around it wasn't a fluke of one lucky cell — 7.5% born beat every
# other born value at nearly every arm width, and arm 3-6% beat both
# tighter (1-2%, scratched by ordinary quote noise before the trade proves
# itself) and looser (10%+, gives back too much before locking) almost
# everywhere. HONEST LIMIT, same as the sweep's own: 80 trades over ~5
# weeks is a small sample and this doesn't model the tick/spread floors
# below — read it as a lean, not a verdict, and see HANDOFF.md 9/8.
# 9/9 — RUNG TIGHTENED 5% -> 2% (G's settle). ratchet_sweep_fine.py decoupled the
# rung from the arm (the earlier sweep forced them equal) and swept 294 combos on
# the same 80 fills: the live 7.5/5/5 ranked #13; the whole top of the board uses
# a +2-3% rung, and 7.5 / arm +5 / step +2 lifts the sample from $152 to $281
# (best cell 7.5/4/2 = $321, but arm 4-vs-5 is within noise, so the arm stays +5).
# Small rungs lock a run more smoothly; the stop still trails ~4-6% off price (the
# ARM sets that gap, not the step), and MIN_RUNG_TICKS=4 below floors the rung so
# 2% never goes sub-tick. ONE ladder kept — cheap (<$1) loses under EVERY spacing,
# so no cheap tier (G's call 9/9); the real cheap lever is sizing/filtering, which
# is tracked separately. Same HONEST LIMIT: 80 fills / ~5 weeks, a lean not a
# verdict — the rn/ratchet tooling keeps collecting so this can be re-checked.
TIERS = (
    (None, (5.0, 0.0, 2.0)),         # every premium: arm +5%, lock BE, +2% rungs
)

MIN_RUNG_TICKS = 4.0                 # floor 1
MIN_STOP_TICKS = 2.0                 # floor 2 hard minimum


def tick_size(price):
    """US option tick: a penny under $3.00, a nickel at $3.00 and above."""
    try:
        return 0.05 if float(price) >= 3.0 else 0.01
    except (TypeError, ValueError):
        return 0.01


def ratchet_plan(fill_price):
    """(arm_pct, first_lock_pct, step_pct) for what he paid, tick floor applied.

    fill_price is the REAL fill, not the caller's posted price — the same
    number every other stop in this program is measured from.
    """
    try:
        f = float(fill_price or 0)
    except (TypeError, ValueError):
        f = 0.0
    plan = TIERS[-1][1]
    for ceiling, p in TIERS:
        if ceiling is None or f < ceiling:
            plan = p
            break
    arm, first, step = plan
    if f > 0:
        # FLOOR 1: widen the rung until it is worth at least 4 ticks.
        min_step = (tick_size(f) * MIN_RUNG_TICKS) / f * 100.0
        if step < min_step:
            step = round(min_step, 2)
    return arm, first, step


def ratchet_locked_pct(gain_pct, fill_price):
    """How much profit the stop should be locking right now, as a percent above
    the fill — or None while the trade hasn't reached its first rung.

    Rung 0 is first_lock. Every further step_pct of gain adds another step_pct
    of locked profit. No ceiling: a runner keeps climbing forever.

    One blanket rule since 9/3 (see TIERS above), respaced 9/8:

        any fill : +5% -> lock BE | +10% -> +5 | +15% -> +10 | +20% -> +15 ...
                   (tick floor widens the 5% rung on cheap/nickel-tick names)

    (These used to read three different premium bands — $0.50 / $1.50 / $3
    each with its own arm/lock — from the 9/2 price-tiered version. Retired
    9/3; TIERS is one blanket tuple now, so one example line covers it.)
    """
    if gain_pct is None:
        return None
    arm, first, step = ratchet_plan(fill_price)
    if step <= 0:
        return None
    if float(gain_pct) < arm - 1e-9:
        return None
    k = int((float(gain_pct) - arm + 1e-9) // step)
    return first + step * k


def ratchet_stop_price(fill_price, locked_pct, bid=None, ask=None,
                       current_stop=None, direction=1):
    """The dollar price the resting stop should move to, spread floor applied.

    Returns None when the move isn't safe or isn't an improvement — the caller
    then leaves the existing stop alone and spends no API call on it.

    direction is +1 for a long (the normal case: every options BUY) and -1 for
    a short. A short's protective stop lives ABOVE the entry and walks DOWN as
    the trade profits — the exact mirror of a long — so "never loosen" flips
    to "never raise" and the spread floor pushes the stop UP off the ask
    instead of down off the bid.

    bid/ask are the live market. Pass whatever you have; with no quote the
    spread floor simply doesn't apply.
    """
    try:
        fill = float(fill_price or 0)
    except (TypeError, ValueError):
        return None
    if fill <= 0 or locked_pct is None:
        return None

    dirn = -1 if int(direction or 1) < 0 else 1
    want = fill * (1.0 + dirn * float(locked_pct) / 100.0)
    tick = tick_size(want)

    try:
        b = float(bid) if bid else None
        a = float(ask) if ask else None
    except (TypeError, ValueError):
        b = a = None

    # FLOOR 2 — never inside the spread.
    if dirn == 1:
        # LONG: you exit by SELLING into the bid, so the stop sits under it.
        if b and b > 0:
            spread = (a - b) if (a and a > b) else 0.0
            room = max(spread, tick * MIN_STOP_TICKS)
            ceiling = b - room
            if want > ceiling:
                want = ceiling
    else:
        # SHORT: you exit by BUYING at the ask, so the stop sits above it.
        ref = a if (a and a > 0) else b
        if ref and ref > 0:
            spread = (a - b) if (a and b and a > b) else 0.0
            room = max(spread, tick * MIN_STOP_TICKS)
            floor_px = ref + room
            if want < floor_px:
                want = floor_px

    want = round(max(0.01, want), 2)

    # Never loosen. For a long that means never lower; for a short, never
    # raise — both are "never give back ground the trade already earned".
    if current_stop is not None:
        try:
            cur = float(current_stop)
            if dirn == 1 and want <= cur + 1e-9:
                return None
            if dirn == -1 and want >= cur - 1e-9:
                return None
        except (TypeError, ValueError):
            pass
    return want


# =====================================================================
# FUTURES — points, not percent
# =====================================================================
# A percentage is meaningless on a future. MNQ trades near 24,000; "10%" is
# 2,400 points, which is not a stop, it is a different trade. Futures move on
# POINTS and his whole futures book is already written in them: entries snap
# to the 25-point grid, the default bracket is 25 risk / 50 reward, and MES
# gets its own 10-point stop.
#
# The futures ratchet takes the ONE number that trade already has — its own stop
# width (the caller's posted stop, theirs first; else the house default) — and
# derives the ladder from it with the SAME SHAPE as the options ratchet.
#
# 9/9 — DECOUPLED to match the options settle. The options ladder is born 7.5% /
# arm 5% / step 2%, so as fractions of the RISK: arm = 2/3 of the stop, rung =
# ~27% of the stop. Applied to futures with the stop as the born:
#
#     arm  = 2/3 of the stop-width in profit  -> lock BREAKEVEN
#     then = a rung every ~27% of the stop    -> lock another rung
#
# NQ/MNQ on a 30-pt caller stop: +20 locks BE, +28 locks +8, +36 locks +16, ...
#   (the 30/20/8 ladder, anchored to QQQ<->NQ = ~41 pts/$ — see HANDOFF.md 9/9).
# MES on his 10-pt stop:         +6.7 locks BE, +9.3 locks +2.7, ...
#
# Still no new numbers from him — it scales off whatever risk the trade carries.

FUT_DEFAULT_STOP_PTS = 25.0
FUT_STOP_PTS_BY_SYMBOL = {"MES": 10.0, "ES": 10.0}
# 9/9: arm/step as fractions of the risk, straight from the options ladder
# (born 7.5 / arm 5 / step 2): arm = 5/7.5 of the stop, rung = 2/7.5 of the stop.
FUT_ARM_FRACTION = 5.0 / 7.5     # lock BREAKEVEN at 2/3 of the risk in profit
FUT_STEP_FRACTION = 2.0 / 7.5    # then a rung every ~27% of the risk


def futures_stop_points(symbol, their_stop=None, entry=None):
    """How many points this trade risks — the rung size for its ratchet.

    The caller's OWN stop wins when they posted one (his standing rule:
    "theirs first, mine as fallback"), so a room that risks 12 points
    ratchets in 12s and a room that posts nothing uses the house 25.
    """
    if their_stop is not None and entry is not None:
        try:
            d = abs(float(entry) - float(their_stop))
            if d > 0:
                return d
        except (TypeError, ValueError):
            pass
    return FUT_STOP_PTS_BY_SYMBOL.get(str(symbol or "").upper()[:3],
                                      FUT_DEFAULT_STOP_PTS)


def futures_locked_points(gain_points, stop_pts):
    """Points of profit the stop should be locking, or None before the first
    rung. 9/9: DECOUPLED to the options ladder's shape — arm at 2/3 of the risk
    to BREAKEVEN, then a rung every ~27% of the risk. stop_pts is the risk
    (caller's own stop, theirs first; else the house default)."""
    if gain_points is None or not stop_pts or stop_pts <= 0:
        return None
    g = float(gain_points)
    arm = stop_pts * FUT_ARM_FRACTION
    step = stop_pts * FUT_STEP_FRACTION
    if step <= 0 or g < arm - 1e-9:
        return None
    k = int((g - arm + 1e-9) // step)
    return step * k


def futures_stop_price(entry, locked_points, direction=1, current_stop=None,
                       tick=0.25):
    """Where the futures stop belongs, in price. None if it isn't an
    improvement. direction +1 long, -1 short. Index futures tick 0.25."""
    try:
        e = float(entry)
    except (TypeError, ValueError):
        return None
    if locked_points is None:
        return None
    dirn = -1 if int(direction or 1) < 0 else 1
    want = e + dirn * float(locked_points)
    if tick and tick > 0:
        want = round(round(want / tick) * tick, 4)
    if current_stop is not None:
        try:
            cur = float(current_stop)
            if dirn == 1 and want <= cur + 1e-9:
                return None
            if dirn == -1 and want >= cur - 1e-9:
                return None
        except (TypeError, ValueError):
            pass
    return want


# ---------------------------------------------------------------- anti-clip
ANTI_CLIP_K = 0.40      # the stop keeps at least this share of the gain as room


def anti_clip(locked_pct, gain_pct, k=ANTI_CLIP_K):
    """THE ANTI-CLIP RULE (9/2, from the 520-trade / 4,000-resample study):
    the stop may never sit closer than k of the gain already made, i.e.
    locked <= (1 - k) * gain. With the live +2% rungs (arm +5% -> breakeven)
    that cap starts biting around +13% gain and holds from there up — much
    sooner than under the old 5% rungs — keeping the stop a proportional
    distance back so a runner is never strangled. k=0.40 and 0.60 tied in
    the study; 0.40 gives back less on a reversal. Not a tuned optimum.
    9/9: this is dead code in live — the bridge runs with anticlip False."""
    if locked_pct is None or gain_pct is None:
        return locked_pct
    cap = (1.0 - float(k)) * float(gain_pct)
    return min(float(locked_pct), round(cap, 2))
