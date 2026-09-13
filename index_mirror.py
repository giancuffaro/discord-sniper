"""index_mirror.py — SPY/QQQ option alerts traded as the micro index future.

G's idea (9/13): a SPY call is a bet the S&P goes up and a QQQ put is a bet
the Nasdaq goes down. The option is only the wrapper — it costs a spread, it
bleeds theta, and it needs a strike guess. So trade the index itself instead:

    SPY CALLS -> LONG  MES        QQQ CALLS -> LONG  MNQ
    SPY PUTS  -> SHORT MES        QQQ PUTS  -> SHORT MNQ

One contract, the existing futures route. Conversion is blocked by the bridge
until that route can enforce protective exits. Nothing here places an order.

Two halves, and only one of them can ever spend money:

  convert()  THE SWITCH — execution.index_mirror.enabled, DEFAULT OFF. While
             it is off this returns False before it looks at anything else and
             the order is left byte-for-byte alone. While it is on it REPLACES
             the option order with a futures order in place, so everything
             downstream (hours guard, entry-clears-stop, hand-trade
             coexistence, the echo lock, the room's own LIVE/TESTING toggle)
             runs exactly as it does for a futures call a room posted. The
             option is NOT bought — this is a replacement, not an addition.

  record()   THE SHADOW — ALWAYS ON, switch or no switch. Every SPY/QQQ entry
             the bridge sees writes one row to futures_mirror_shadow.csv,
             whatever happened to the option order (filled, refused for money,
             pullback armed, TEST room). futures_mirror_daily.py scores those
             rows against real ES/NQ bars every evening, so the idea is
             measured every day whether or not it is switched on.

WHY IT SHIPS OFF (9/13): a hypothetical 25/50 replay of 149 alerts lost $721
gross, and live futures stops/ratchets are not yet enforced by a broker order
or quote watcher. The bridge refuses activation until that is fixed.

RTH ONLY (09:30-15:45 ET), same window the replay measured. Futures trade
nearly around the clock and the option market does not, so without this a
7 p.m. SPY alert would become an overnight MES position that no replay has
ever scored. Outside the window the option order is left alone.
"""

import csv
import datetime as dt
import os
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SHADOW_CSV = os.path.join(HERE, "futures_mirror_shadow.csv")
SHADOW_HEADER = ["ts_iso", "date", "time_et", "sym", "dirn", "micro",
                 "room", "caller", "their_price", "outcome"]

# The replay's window, to the minute: RTH, and early enough that there is a
# trading day left to be in. reference/futures_mirror_alerts.py is the source.
OPEN_MINUTE = 9 * 60 + 30
LAST_MINUTE = 15 * 60 + 45

DEFAULT_MAP = {"SPY": "MES", "QQQ": "MNQ"}
ET = ZoneInfo('America/New_York')


def live_exit_ready():
    """The futures route currently records levels but does not enforce them.

    Keep mirror activation blocked until a broker-confirmed protective exit
    and target/ratchet path exists and has its own execution tests.
    """
    return False


def settings(cfg):
    """execution.index_mirror, or an empty dict. Never raises."""
    try:
        return (cfg or {}).get("execution", {}).get("index_mirror", {}) or {}
    except Exception:                                   # noqa: BLE001
        return {}


def symbol_map(cfg):
    m = settings(cfg).get("map")
    if not isinstance(m, dict) or not m:
        return dict(DEFAULT_MAP)
    return {str(k).upper(): str(v).upper() for k, v in m.items()}


def enabled(cfg):
    return bool(settings(cfg).get("enabled"))


def direction_of(order):
    """LONG for calls, SHORT for puts, None for anything else."""
    side = str(order.get("side") or "").upper()
    if side.startswith("C"):
        return "LONG"
    if side.startswith("P"):
        return "SHORT"
    return None


def eligible(order, cfg, now=None):
    """(micro, direction) when this order is a SPY/QQQ option ENTRY inside the
    measured window, else None. Reads only — never touches the order."""
    if str(order.get("action") or "").upper() != "OPEN":
        return None                                     # a CLOSE/TRIM/ADD never mirrors
    if (order.get("kind") or "option") == "future":
        return None                                     # already a futures call
    micro = symbol_map(cfg).get(str(order.get("symbol") or "").upper())
    if not micro:
        return None
    dirn = direction_of(order)
    if dirn is None:
        return None
    now = now or dt.datetime.now(ET)
    mins = now.hour * 60 + now.minute
    if mins < OPEN_MINUTE or mins > LAST_MINUTE:
        return None
    return micro, dirn


def convert(order, cfg, note=None, now=None):
    """Turn this option order INTO a futures order, in place. Returns True if
    it did. Returns False — having touched nothing — whenever the switch is
    off, which is the only state this ships in."""
    if not enabled(cfg):
        return False
    hit = eligible(order, cfg, now=now)
    if hit is None:
        return False
    micro, dirn = hit
    was = "%s %s%s" % (order.get("symbol"), order.get("strike") or "",
                       "C" if dirn == "LONG" else "P")
    try:
        qty = max(1, int(settings(cfg).get("qty") or 1))
    except (TypeError, ValueError):
        qty = 1
    # What the room actually posted, kept for the shadow row — the futures
    # order below has no price of its own.
    order["mirror_their_price"] = order.get("limit")
    order["kind"] = "future"
    order["symbol"] = micro
    order["direction"] = dirn
    order["qty"] = qty
    # No option premium can survive into a futures order: the alert's $3.10 is
    # a contract price, not an index level, and webull_futures would snap it to
    # the 25-point grid and bid 0. No price = a market entry, which is exactly
    # what the replay measured. The bracket is born off the fill (positions.
    # _arm_stop) at the house 25/50, the same numbers a room that posts no stop
    # already gets.
    order["limit"] = None
    order["their_stop"] = None
    order["their_target"] = None
    order["side"] = ""
    order["strike"] = None
    order["expiry"] = None
    # A 30-day SPY call is a swing; a one-contract MES long is not. The swing
    # rules (wide -25% premium stop, the 9:31 re-arm, swings_paused) are all
    # about option premium and none of them can describe this trade.
    order["swing"] = False
    order["mirrored_from"] = was
    if note:
        note("MIRROR   %s -> %s %s x%d (index mirror is ON; the option was "
             "NOT bought). Market entry, house 25/50 bracket, futures ratchet "
             "owns the exit." % (was, dirn, micro, qty))
    return True


def record(order, outcome, note=None, path=None, now=None):
    """One shadow row per SPY/QQQ entry, switch or no switch. Append-only, and
    never allowed to affect the order — every failure is swallowed."""
    try:
        sym = str(order.get("symbol") or "").upper()
        if sym not in DEFAULT_MAP:
            # Read the map off the ORIGINAL symbol. A converted order already
            # says MES/MNQ, so mirrored orders are recorded by their caller's
            # symbol via mirrored_from instead (see below).
            src = str(order.get("mirrored_from") or "").split(" ")[0].upper()
            if src not in DEFAULT_MAP:
                return False
            sym = src
        if str(order.get("action") or "").upper() != "OPEN":
            return False
        if order.get("mirrored_from"):
            dirn = "L" if str(order.get("direction") or "").upper() == "LONG" else "S"
        else:
            d = direction_of(order)
            if d is None:
                return False
            dirn = "L" if d == "LONG" else "S"
        now = now or dt.datetime.now(ET)
        row = [now.isoformat(timespec="seconds"), now.date().isoformat(),
               now.strftime("%H:%M:%S"), sym, dirn, DEFAULT_MAP[sym],
               str(order.get("room") or order.get("room_label") or ""),
               str(order.get("trader") or ""),
               order.get("mirror_their_price", order.get("limit")),
               str(outcome or "")[:200]]
        p = path or SHADOW_CSV
        new = not os.path.exists(p)
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(SHADOW_HEADER)
            w.writerow(row)
        return True
    except Exception as e:                              # noqa: BLE001
        if note:
            try:
                note("MIRROR   shadow row not written: %s" % str(e)[:90])
            except Exception:                           # noqa: BLE001
                pass
        return False
