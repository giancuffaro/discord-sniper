"""entry_slack.py — would crossing the ask have got us in? ONE implementation.

THE PROBLEM (G, 9/15). The bot bids the caller's price or better and never
chases (HANDOFF.md, ENTRIES · PRICE). On 9/15 MuggZone posted "BOUGHT CRWD
250C at 3.50", the bot's bid went in at 3.50 two seconds later, and the market
was ALREADY 3.55 x 3.65 — it never came back, the 90-second window expired,
and the contract ran to 3.90. Same shape on CRWD at 10:14 (bid 4.25, market
4.40 x 4.50) and on CRWD 9/14 (bid 2.35, market 2.41 x 2.52).

THE OTHER SIDE, which is the reason the rule exists. Every one of 9/15's six
fills came in BETTER than the caller's price — META 1.88 vs 1.94, TSLA 1.19 vs
1.34, TSLA 3.25 vs 3.40, QQQ 0.61 vs 0.64, AMD 5.45 vs 5.60. Crossing the ask
buys the misses by giving that improvement away on everything else.

So this file holds the RULE and nothing else, and nothing here is switched on:

    if ask <= caller_price * (1 + slack)   ->  take the ask (a legal tick)
    otherwise                              ->  rest at the caller's price,
                                               exactly as the bot does today

slack = 0 IS today's behaviour: a resting limit at the caller's price is
already marketable when the ask has come to it, which is where the
better-than-posted fills above come from. Every larger slack is a chase.

TWO HALVES, and only one of them can ever spend money:

  decide()   THE RULE — pure, no I/O, no settings, no clock. The replay
             (reference/entry_slack_replay.py) and any future live path both
             call this, so the thing that is measured and the thing that would
             trade can never drift apart.

  armed()    THE SWITCH — execution.entry_slack_pct, DEFAULT 0. A non-zero
             value REFUSES TO ARM and returns the reason to log, exactly like
             index_mirror's activation block. The entry still goes out under
             today's rule; the setting changes nothing until G turns it on
             deliberately and the replay has earned it.

WHY IT SHIPS BLOCKED (9/15): activation waits on evidence, not on argument.
52 grep-level NOFILL hits in trades.log are 47 real no-fill events, 20 of them
futures; the option population is 27 of 201 ORDER INs, and only a handful of
those have a real recorded bid/ask at read time. Until
reference/entry_slack_replay.py shows a NET gain — rescued trades minus the
price improvement given up on the fills — outside its own error bar, this
stays off.
"""

from collections import namedtuple

from webull_options import tick_ceil, tick_floor

# The sweep the replay scores every day. 0 first: it is today's rule and the
# baseline every other level is measured against.
SLACK_LEVELS = (0.0, 2.0, 3.0, 5.0, 7.5, 10.0)

Decision = namedtuple("Decision",
                      "cross price threshold rest why")


def _f(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out          # NaN is not a price


def decide(caller_price, bid, ask, slack_pct=0.0, symbol=None):
    """THE RULE. Would we cross, and at what price?

    caller_price  what the room posted (and therefore what we bid today)
    bid, ask      the contract's real market at READ time
    slack_pct     percent above the caller's price we are willing to pay
    symbol        the underlying, so the tick grid is the right one
                  (webull_options.tick_step: SPY/QQQ/IWM a penny always,
                  Penny Program names a penny under $3, everything else a
                  nickel/dime — never invent a tick)

    Returns a Decision:
      cross      True when we would take the offer instead of resting
      price      the legal-tick price we would pay, or None when we rest
      threshold  caller_price * (1 + slack), the number the ask is tested
                 against, or None when there is nothing to test
      rest       the resting limit we use when we do not cross — the
                 caller's price floored to the legal tick, which is what
                 webull_options.buy() sends today
      why        one short phrase, for the log and the replay table

    NEVER CROSSES on a missing, zero or inverted quote. A price we did not
    record is not a price we can claim to have paid.
    """
    price = _f(caller_price)
    b = _f(bid)
    a = _f(ask)
    slack = _f(slack_pct) or 0.0
    if slack < 0:
        slack = 0.0                              # a negative slack is not a rule

    if price is None or price <= 0:
        return Decision(False, None, None, None, "no caller price")

    rest = max(0.01, float(tick_floor(round(price, 2), symbol)))

    if a is None or a <= 0:
        return Decision(False, None, None, rest, "no ask at read time")
    if b is not None and b > 0 and a < b:
        return Decision(False, None, None, rest, "crossed quote — not a market")

    threshold = price * (1.0 + slack / 100.0)
    if a > threshold + 1e-9:
        return Decision(False, None, threshold, rest,
                        "ask %.2f is over the %.1f%% line (%.4f)"
                        % (a, slack, threshold))
    # Cross at the offer, snapped UP to the legal tick: a marketable buy that
    # rounds DOWN through the ask turns straight back into a resting bid,
    # which is the thing this rule exists to stop (webull_options.tick_ceil,
    # the same call the round-number pullback's ask-cross uses).
    return Decision(True, max(0.01, float(tick_ceil(a, symbol))), threshold,
                    rest, "ask %.2f is inside the %.1f%% line (%.4f)"
                    % (a, slack, threshold))


# ------------------------------------------------------- the switch, blocked
def live_ready():
    """Activation is blocked until the replay earns it.

    reference/entry_slack_replay.py must show a NET gain — the rescued
    no-fills minus the price improvement crossing gives away on the orders
    that DO fill — outside its paired bootstrap band. It does not yet.
    """
    return False


def slack_pct(cfg):
    """execution.entry_slack_pct as a number. 0 (today's rule) for anything
    missing, unreadable or negative. Never raises, never reads a file."""
    try:
        raw = (cfg or {}).get("execution", {}).get("entry_slack_pct", 0)
    except Exception:                                   # noqa: BLE001
        return 0.0
    value = _f(raw)
    if value is None or value <= 0:
        return 0.0
    return value


def armed(cfg):
    """(armed, why). ``armed`` is False in every state this ships in.

    0 (the default) is silent — it is the rule the bot already runs. Any
    other value gets ONE line saying it did not arm and what would unblock
    it, so a setting that is quietly doing nothing can never look like a
    setting that is quietly doing something.
    """
    pct = slack_pct(cfg)
    if pct <= 0:
        return False, ""
    if not live_ready():
        return False, ("SLACK    execution.entry_slack_pct=%g refused to arm — "
                       "entry slack is measurement only until "
                       "reference/entry_slack_replay.py shows a net gain "
                       "outside its error bar. This entry rests at the "
                       "caller's price, as always." % pct)
    return True, ""
