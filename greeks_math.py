"""greeks_math.py — turn an underlying move into an expected premium move.

WHY (9/6/26)
------------
G asked for greeks so the machine could reason about BREATHING ROOM instead
of guessing at it. This is that math, and it is deliberately small.

READ THIS BEFORE USING IT — a correction to what I told him
-----------------------------------------------------------
Research said our stops were "8 cents too tight because we use a linear
delta conversion." I then read our own source: **we have no delta conversion
at all.** The ratchet works in premium percent (born -7.5%, arm +5% to
breakeven, then +2% rungs) and
`_underlying_stop_watch` fires on the caller's stated STOCK level. Neither
one converts between the two. So the 8-cent claim did not apply to us as
stated, and I am not going to pretend it did.

What IS true, and is worth having, is the thing underneath it: a premium
stop and an underlying level are two different units, and we currently have
no way to say what one is worth in the other. That means we cannot answer
the question that decides whether a stop is any good:

    "How far does the stock have to move to hit my -7.5% premium stop?"

If the answer is 0.15 SPY points, that stop is inside the noise and will be
taken out by a market maker breathing. If it is 2.00 points, it is a real
level. Same -7.5%, completely different trade. Today we cannot tell them
apart, so this module exists to tell us — as a MEASUREMENT first.

THE MATH
--------
Second-order Taylor expansion of the option price (delta-gamma-theta):

    dC ~= delta*dS  +  0.5*gamma*dS^2  +  theta*dt

The gamma term ALWAYS ADDS for a long option, both directions: delta shrinks
as a call falls and grows as it rises. So the naive linear estimate
`entry - delta*distance` predicts a BIGGER premium loss than actually
happens, i.e. it places a converted stop too tight. The correction is signed
and on a stop it always works in your favour.

Worked example, real numbers off our own greeks_tape:
    SPY 640, 0DTE 640C at 2.10, delta .52, gamma .11, stop 1.20 pts lower
        linear          2.10 - 0.624                    = 1.476
        gamma-corrected 2.10 - 0.624 + 0.5*0.11*1.44    = 1.555
    Nearly 8 cents, about three ticks, on every trade.

WHERE IT BREAKS — do not skip this
----------------------------------
  * Taylor is a LOCAL approximation. It is good for a fraction of a
    percent of underlying movement and degrades fast beyond that. Past
    roughly 1.5% of spot the error grows faster than the term you added,
    so `premium_at` refuses and returns None rather than lying.
  * Gamma is not constant. ATM 0DTE gamma runs 2-5x a 7DTE contract in the
    morning and 10x+ into the close. Greeks read at 10:00 are wrong by
    a factor of several at 15:30. RE-READ THEM; never cache them for a day.
  * Vega is omitted on purpose. An IV crush moves premium with the stock
    dead flat, and this function cannot see it. That is precisely why an
    underlying-referenced stop needs a premium-based disaster floor under
    it — see the note in UPGRADES.md.
  * Theta on a 0DTE is not the quoted number. The whole remaining extrinsic
    value is gone by the close, and decay accelerates after 15:30. Use
    `theta_per_minute_0dte()` below, which reads it off extrinsic value
    instead of trusting the quoted daily figure.

NOTHING HERE PLACES AN ORDER. It is arithmetic with guard rails.
"""

MAX_MOVE_FRAC = 0.015      # Taylor is local; past ~1.5% of spot, refuse.


def premium_at(spot_now, spot_then, premium_now, delta, gamma=0.0,
               theta=0.0, minutes=0.0):
    """What the contract should be worth if the underlying goes to
    `spot_then`. Returns None when the move is too big for the expansion to
    be honest, or when an input is missing.

    theta is the QUOTED PER-DAY value (negative for a long option) and
    `minutes` is how long you expect to be in the trade; 390 minutes is one
    session. Pass minutes=0 to ask "what is it worth right now at that
    price", ignoring decay.
    """
    try:
        s0, s1 = float(spot_now), float(spot_then)
        c0, d = float(premium_now), float(delta)
        g = float(gamma or 0.0)
    except (TypeError, ValueError):
        return None
    if s0 <= 0 or c0 <= 0:
        return None
    ds = s1 - s0
    if abs(ds) > MAX_MOVE_FRAC * s0:
        return None                     # out of the approximation's range
    out = c0 + d * ds + 0.5 * g * ds * ds
    if minutes:
        try:
            out += float(theta or 0.0) * (float(minutes) / 390.0)
        except (TypeError, ValueError):
            pass
    return max(0.0, out)


def underlying_for_premium(spot_now, premium_now, target_premium, delta,
                           gamma=0.0, is_call=True):
    """THE ONE THAT MATTERS: how far does the STOCK have to move for the
    contract to be worth `target_premium`? Returns the underlying price, or
    None if it can't be solved inside the approximation's range.

    This is what turns "-7.5% premium stop" into "SPY 638.85", which is the
    only form in which a stop can be judged against the chart.

    Solves 0.5*g*ds^2 + d*ds + (c0 - target) = 0 for ds, taking the root
    nearest zero (the near-side crossing is the one you hit first).
    """
    try:
        s0, c0 = float(spot_now), float(premium_now)
        tgt, d = float(target_premium), float(delta)
        g = float(gamma or 0.0)
    except (TypeError, ValueError):
        return None
    if s0 <= 0 or c0 <= 0 or d == 0:
        return None
    k = c0 - tgt                        # premium we need to give up
    if abs(g) < 1e-9:
        ds = -k / d                     # linear fallback
    else:
        a, b = 0.5 * g, d
        disc = b * b - 4.0 * a * k
        if disc < 0:
            # With this gamma the contract never reaches that premium on
            # underlying movement alone — it would take decay or vol.
            return None
        r = disc ** 0.5
        r1, r2 = (-b + r) / (2 * a), (-b - r) / (2 * a)
        ds = r1 if abs(r1) <= abs(r2) else r2
    if abs(ds) > MAX_MOVE_FRAC * s0:
        return None
    # A long call loses value as the stock FALLS; a put as it RISES. If the
    # algebra hands back the wrong direction the inputs disagree with the
    # side, and a wrong-signed stop is worse than none.
    if tgt < c0:
        if is_call and ds > 0:
            return None
        if not is_call and ds < 0:
            return None
    return s0 + ds


def stop_room(spot_now, premium_now, stop_pct, delta, gamma=0.0,
              is_call=True):
    """Breathing room, in the units a chart is drawn in.

    Returns {points, pct, level} — how far the underlying must travel to
    take out a stop set `stop_pct` percent below the current premium.

    Use it as a SANITY GATE, not as the stop itself: if `points` is smaller
    than the stock's typical wiggle, the stop is noise-tight and will be
    taken out by ordinary two-sided trading, no thesis required.
    """
    try:
        target = float(premium_now) * (1.0 - abs(float(stop_pct)) / 100.0)
    except (TypeError, ValueError):
        return None
    lvl = underlying_for_premium(spot_now, premium_now, target, delta,
                                 gamma, is_call)
    if lvl is None:
        return None
    try:
        pts = abs(float(lvl) - float(spot_now))
        return {"points": round(pts, 4),
                "pct": round(pts / float(spot_now) * 100.0, 4),
                "level": round(float(lvl), 4)}
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def theta_per_minute_0dte(premium, spot, strike, is_call, minutes_left):
    """Honest 0DTE decay: read it off EXTRINSIC value, not off quoted theta.

    Every cent of extrinsic is gone by the close, so extrinsic/minutes_left
    is the real burn rate. This UNDERSTATES decay after 15:30 — the curve is
    convex and this is a straight line through it. Treat it as a floor.
    """
    try:
        p, s, k = float(premium), float(spot), float(strike)
        m = float(minutes_left)
    except (TypeError, ValueError):
        return None
    if m <= 0 or p <= 0:
        return None
    intrinsic = max(0.0, (s - k) if is_call else (k - s))
    extrinsic = max(0.0, p - intrinsic)
    return extrinsic / m


def gamma_regime(gamma, spot, premium):
    """A plain-language read on how twitchy this contract is right now.

    Dimensionless: how much of the premium a one-point underlying move adds
    or removes through gamma alone. Rises hard through an expiration day,
    which is the practical warning — a stop distance computed at 10:00 is
    not the same risk at 15:30.
    """
    try:
        g, s, p = float(gamma), float(spot), float(premium)
        if p <= 0 or s <= 0:
            return None
    except (TypeError, ValueError):
        return None
    score = abs(g) / p
    if score >= 0.20:
        word = "VIOLENT — re-read greeks before trusting any stop distance"
    elif score >= 0.08:
        word = "hot"
    elif score >= 0.03:
        word = "normal"
    else:
        word = "sleepy"
    return {"score": round(score, 4), "read": word}
