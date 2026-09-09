"""market_hours.py — THE one place market hours live. Everything reads here.

Options and futures keep different clocks, and getting it wrong means either
expecting a fill that can't happen or skipping one that can. So the hours live
in ONE file and every other module imports this instead of hardcoding 9:30 /
16:15 / a futures session of its own.

ALL TIMES ARE NEW YORK (ET). Built on eastern.now() so the clock is right on
Windows too. Nothing here raises — if anything goes sideways it errs toward
"closed", which is the safe default.

WHAT'S TRUE (recorded 2026-09-08, sources in MARKET-HOURS.md):

  EQUITY / ETF OPTIONS   9:30 AM - 4:00 PM ET, Mon-Fri.
      SPY, QQQ, IWM and cash index options (SPX, NDX, RUT, VIX) run to 4:15 PM.
      No overnight — after the bell nothing options-side can fill.
      Half-days: 1:00 PM close (index/ETF options 1:15 PM).

  FUTURES (CME Globex:   Sunday 6:00 PM ET  ->  Friday 5:00 PM ET,
   ES/NQ/MES/MNQ,        nearly 24h, with ONE daily halt 5:00-6:00 PM ET.
   metals GC/MGC/SI)     So a weekday-evening futures alert (e.g. the 9:25 PM NQ
                         long) IS in session — that's the after-hours edge.

  Holidays below are equities/options full closes + half-days. CME futures also
  early-close on holidays; those aren't all encoded — treat futures near a
  holiday as approximate. UPDATE THE HOLIDAY TABLE EACH YEAR.
"""
import datetime as _dt

try:
    import eastern

    def _now():
        return eastern.now()
except Exception:                                       # noqa: BLE001
    def _now():
        return _dt.datetime.now().astimezone()

# ---- the numbers (ET), as (hour, minute) ----
OPTIONS_OPEN = (9, 30)
OPTIONS_CLOSE = (16, 0)              # most single-name equity options
OPTIONS_CLOSE_LATE = (16, 15)        # SPY/QQQ/IWM + cash index options
LATE_CLOSE_SYMBOLS = {"SPY", "QQQ", "IWM", "SPX", "SPXW", "XSP",
                      "NDX", "RUT", "VIX"}
HALF_DAY_EQUITY_CLOSE = (13, 0)
HALF_DAY_LATE_CLOSE = (13, 15)

FUTURES_OPEN = (18, 0)               # Sunday 6:00 PM ET
FUTURES_CLOSE = (17, 0)              # Friday 5:00 PM ET
FUTURES_HALT = ((17, 0), (18, 0))    # daily maintenance 5:00-6:00 PM ET

# ===========================================================================
# HOLIDAYS  ***UPDATE THIS EVERY YEAR***  (table currently runs through 2027)
# ---------------------------------------------------------------------------
# US market holidays can't be one simple rule: fixed-date ones shift when they
# land on a weekend, and Good Friday moves with Easter. So they're listed out
# explicitly and verified against the NYSE calendar. When a new year is needed,
# regenerate with the dated Python snippet saved in MARKET-HOURS.md and paste
# the year in below, then bump HOLIDAYS_THROUGH. If the running year is past
# HOLIDAYS_THROUGH the code treats every weekday as a normal session and
# status() raises the "holiday_table_stale" flag — so don't let it lapse.
#   FULL_CLOSE = market fully closed.
#   HALF_DAY   = 1:00 PM ET close (SPY/QQQ/IWM + index options 1:15 PM).
# A date is never in both.
# ===========================================================================
HOLIDAYS_THROUGH = 2027
FULL_CLOSE = {
    2025: {"2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
           "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
           "2025-11-27", "2025-12-25"},
    2026: {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
           "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
           "2026-11-26", "2026-12-25"},
    2027: {"2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
           "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
           "2027-11-25", "2027-12-24"},
}
HALF_DAY = {
    2025: {"2025-07-03", "2025-11-28", "2025-12-24"},
    2026: {"2026-11-27", "2026-12-24"},
    2027: {"2027-11-26"},
}


def _hm(t):
    return t.hour * 60 + t.minute


def _mk(pair):
    return pair[0] * 60 + pair[1]


def now_et():
    return _now()


def is_holiday(dt=None):
    d = dt or _now()
    return d.strftime("%Y-%m-%d") in FULL_CLOSE.get(d.year, set())


def is_half_day(dt=None):
    d = dt or _now()
    return d.strftime("%Y-%m-%d") in HALF_DAY.get(d.year, set())


def _late(symbol):
    return bool(symbol) and str(symbol).upper() in LATE_CLOSE_SYMBOLS


def options_close_minute(symbol=None, dt=None):
    """Minute-of-day the options session ends for this symbol on this date."""
    d = dt or _now()
    if is_half_day(d):
        return _mk(HALF_DAY_LATE_CLOSE) if _late(symbol) else _mk(HALF_DAY_EQUITY_CLOSE)
    return _mk(OPTIONS_CLOSE_LATE) if _late(symbol) else _mk(OPTIONS_CLOSE)


def options_open(symbol=None, dt=None):
    """Is the OPTIONS market open right now (for this symbol)?"""
    d = dt or _now()
    if d.weekday() >= 5 or is_holiday(d):
        return False
    m = _hm(d)
    return _mk(OPTIONS_OPEN) <= m < options_close_minute(symbol, d)


def futures_open(dt=None):
    """Is the CME equity-index / metals futures session open right now?
    (Base weekly session; holiday early-closes are not fully encoded.)"""
    d = dt or _now()
    wd = d.weekday()          # Mon=0 .. Sun=6
    m = _hm(d)
    if wd == 5:                                   # Saturday: closed all day
        return False
    if wd == 6:                                   # Sunday: opens 6:00 PM ET
        return m >= _mk(FUTURES_OPEN)
    if wd == 4:                                   # Friday: closes 5:00 PM ET
        return m < _mk(FUTURES_CLOSE)
    # Mon-Thu: open except the daily 5:00-6:00 PM ET maintenance halt
    return not (_mk(FUTURES_HALT[0]) <= m < _mk(FUTURES_HALT[1]))


def is_open(kind="option", symbol=None, dt=None):
    """One call for the bridge: kind 'future'/'futures' -> futures session,
    anything else -> options session for `symbol`."""
    if str(kind).lower().startswith("fut"):
        return futures_open(dt)
    return options_open(symbol, dt)


def session_bounds(dt=None):
    """Regular options session as 'HH:MM' strings, for minute-bar capture
    (09:30 .. 16:15). Half-days shorten the close."""
    d = dt or _now()
    close = HALF_DAY_LATE_CLOSE if is_half_day(d) else OPTIONS_CLOSE_LATE
    return ("%02d:%02d" % OPTIONS_OPEN, "%02d:%02d" % close)


def restart_safe_open(dt=None):
    """The padded window the bridge uses to decide it's mid-market and should
    hold a code restart until the close: weekdays 09:20-16:15, and now also
    False on holidays so a restart can happen freely on a closed day."""
    d = dt or _now()
    if d.weekday() >= 5 or is_holiday(d):
        return False
    m = _hm(d)
    return (9 * 60 + 20) <= m <= (16 * 60 + 15)


def status(dt=None):
    d = dt or _now()
    return {
        "et": d.strftime("%Y-%m-%d %H:%M %a"),
        "options_open": options_open(None, d),
        "futures_open": futures_open(d),
        "holiday": is_holiday(d),
        "half_day": is_half_day(d),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2))
