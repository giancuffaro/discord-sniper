"""
webull_futures.py — real futures orders, behind the switch and behind honesty.

This file only ever runs when ALL of these are true: live mode is on, the
futures switch in settings.json is on, and a futures call came in. Until his
Webull futures data subscription exists none of it can be exercised for real,
so it is built the same way order_status and cancel were built in
webull_options.py: the SDK's endpoint names for futures are not stable or
documented well, so every call PROBES a list of plausible names and shapes,
uses the first one that answers, and refuses loudly — nothing sent, position
untouched — when none do. A refused order is a message; a guessed one is a
margin position you didn't mean to have.

Deliberate choices, written down so they're not rediscovered the hard way:

  - Quantity is ONE contract, always, whatever the book or the browser says.
    NQ is $20 a point; the first live futures trades should be too small to
    hurt while the plumbing proves itself. Raising this is a one-line change
    that should be made on purpose, after supervised fills.
  - The front-month contract is resolved from the SDK's instrument list and
    nearest expiry. If that can't be worked out with certainty, refuse —
    trading the wrong month is a real position in the wrong thing.
"""

from datetime import datetime

import positions


class FuturesRefused(Exception):
    """Nothing was sent, and here's why, in English."""


def _try(wb, holders, verbs, *args, **kw):
    """Probe the SDK through the connection webull_options already made.
    Returns (body, why_it_failed). Mirrors WebullOptions._try_calls."""
    try:
        return wb._try_calls(holders, verbs, *args, **kw)   # noqa: SLF001
    except Exception as e:                                  # noqa: BLE001
        return None, str(e)


# CME month codes and the quarterly cycle the index futures roll on (Mar, Jun,
# Sep, Dec = H, M, U, Z). Used both to read the SDK's contract codes and to
# compute a front month when the SDK says nothing.
_MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
               7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
_QUARTERLY = {3, 6, 9, 12}
# The index futures the rooms actually call. These roll on the quarterly cycle,
# so a code can be computed for them safely. Anything else (CL, GC, …) has its
# own cycle and is left to the SDK — guessing there could pick the wrong month.
_INDEX_ROOTS = {"NQ", "MNQ", "ES", "MES", "RTY", "M2K", "YM", "MYM"}


def _fut_rows(wb, root):
    """Pull this root's contract list from the SDK. The futures-instrument call
    lives on the DATA client (market data), not the trade client, and it wants
    category=US_FUTURES plus a code/symbols — the old code passed a bare symbol
    to the trade client, which is why it came back with nothing. Probe both
    clients, every plausible method name, every plausible arg shape."""
    objs = []
    for attr in ("_data", "trade", "_api"):
        o = getattr(wb, attr, None)
        if o is not None:
            objs.append(o)
    objs.append(wb)
    holders = []
    for o in objs:
        holders.append(o)
        for a in dir(o):
            if a.startswith("_"):
                continue
            low = a.lower()
            if "futur" in low or "instrument" in low or "market" in low:
                try:
                    holders.append(getattr(o, a))
                except Exception:                       # noqa: BLE001
                    pass
    shapes = [((), {"category": "US_FUTURES", "code": root}),
              ((), {"category": "US_FUTURES", "symbols": root}),
              (("US_FUTURES",), {"code": root}),
              (("US_FUTURES", root), {}),
              ((root,), {})]
    for h in holders:
        for m in dir(h):
            low = m.lower()
            if m.startswith("_") or "futur" not in low or "instrument" not in low:
                continue
            fn = getattr(h, m, None)
            if not callable(fn):
                continue
            for args, kw in shapes:
                try:
                    res = fn(*args, **kw)
                except TypeError:
                    continue
                except Exception:                       # noqa: BLE001
                    continue
                body = res.json() if hasattr(res, "json") else res
                rows = body.get("data") if isinstance(body, dict) else body
                if rows:
                    return rows
    return []


def _computed_front(root):
    """The standard quarterly front-month code for an index root, from today's
    date. As of Aug 2026 MNQ -> MNQU6 (Sep). Only used as a fallback when the
    SDK won't answer, and only for the quarterly index roots — so a real call
    goes out instead of being missed for a data hiccup."""
    if root not in _INDEX_ROOTS:
        return None
    now = datetime.utcnow()
    for add in range(0, 13):
        m = (now.month - 1 + add) % 12 + 1
        yy = now.year + (now.month - 1 + add) // 12
        if m in _QUARTERLY:
            # If we're already past this quarter's expiry (~3rd Friday, day 18),
            # it's rolling — skip to the next quarter.
            if add == 0 and now.day > 18:
                continue
            return "%s%s%d" % (root, _MONTH_CODE[m], yy % 10)
    return None


def front_month(wb, symbol):
    """The contract code actually trading right now for this root — MNQ means
    MNQU6 or MNQZ6 depending on the week. Nearest tradable expiry in the future
    wins; if the SDK won't say, the quarterly code is computed for index roots so
    the trade still goes out."""
    root = str(symbol).upper()
    rows = _fut_rows(wb, root)
    best = None
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for r in rows:
        if not isinstance(r, dict):
            continue
        # Tradable only: OC = open/tradable, CO = liquidate-only, NT = no-trade.
        if str(r.get("status", "OC")).upper() not in ("OC", ""):
            continue
        code = (r.get("symbol") or r.get("contract_code") or
                r.get("instrument_id") or "")
        if not code:
            continue
        rc = str(r.get("code", "")).upper()
        if rc and rc != root and not str(code).upper().startswith(root):
            continue
        exp = str(r.get("last_trading_date") or r.get("settlement_date") or
                  r.get("expire_date") or r.get("expiration_date") or
                  r.get("last_trade_date") or "")
        if exp and exp < today:
            continue
        if best is None or (exp and exp < best[1]):
            best = (code, exp or "9999-99-99")
    if best:
        return best[0]
    comp = _computed_front(root)
    if comp:
        return comp
    raise FuturesRefused(
        "couldn't work out which %s contract is front month (SDK gave nothing "
        "usable and it's not a quarterly index root I can compute). No order "
        "was sent — trading the wrong month is a real position in the wrong "
        "thing." % symbol)


def _place(wb, contract, side, qty, limit=None):
    """One order, probed across the plausible endpoint names. Returns the
    order id, or raises FuturesRefused with every reason collected."""
    shapes = []
    base = {"symbol": contract, "qty": int(qty), "quantity": int(qty),
            "side": side, "order_type": "LIMIT" if limit else "MARKET"}
    # The FUTURES account, picked automatically when the keys went in — his
    # rule: options ride the MARGIN account, futures ride the FUTURES one,
    # nobody picks anything twice.
    fut_acct = getattr(wb, "futures_account_id", None)
    if fut_acct:
        base["account_id"] = base["accountId"] = str(fut_acct)
    if limit:
        base["limit_price"] = base["price"] = float(limit)
    shapes.append((base,))
    body, why = _try(wb, ["trade", "order_v3", "order", "futures"],
                     ["place_futures_order", "futures_place_order",
                      "place_order_v3", "place_order"], *shapes[0])
    if body is None:
        raise FuturesRefused(
            "Webull wouldn't take the futures order the ways I know how to "
            "send one (%s). Nothing went out. This is exactly why the first "
            "live futures trade is a supervised one — send me what the "
            "bridge log says." % (why or "no endpoint answered")[:200])
    oid = None
    if isinstance(body, dict):
        oid = (body.get("order_id") or body.get("orderId") or
               (body.get("data") or {}).get("order_id")
               if isinstance(body.get("data"), dict) else body.get("order_id"))
    return oid or "unknown"


def execute(wb, book, order, key, note):
    """The whole live futures path: entry, trim, or close. Returns (ok, msg).
    Sizing is pinned to one contract on purpose — see the file docstring."""
    action = order.get("action")
    sym = str(order.get("symbol", "")).upper()
    direction = str(order.get("direction") or "").upper()
    contract = front_month(wb, sym)

    if action == "OPEN":
        side = "SELL" if direction == "SHORT" else "BUY"
        oid = _place(wb, contract, side, 1, order.get("limit"))
        note("FUTURES  ORDER IN %s %s x1 (%s), their stop %s target %s"
             % (side, contract, oid, order.get("their_stop"),
                order.get("their_target")))
        if book is not None:
            order = dict(order, mult=None)
            from bridge import FUT_MULT
            order["mult"] = FUT_MULT.get(sym, 1.0)
            book.entry_sent(order, {"order_id": oid, "occ": None,
                                    "limit": order.get("limit"),
                                    "bid": None, "ask": None, "qty": 1})
        return True, ("futures order in: %s %s, one contract. Their stop is "
                      "%s — watch it, the room's calls are the stop for now."
                      % (side, contract, order.get("their_stop") or "unposted"))

    if action in ("TRIM", "CLOSE"):
        p = (book.info(key) if book is not None else None) or {}
        held = int(p.get("qty") or 0)
        if held <= 0:
            return False, "you're not in %s, nothing to sell" % sym
        n = held if action == "CLOSE" else 1
        # Closing a short means buying back.
        side = "BUY" if int(p.get("direction") or 1) < 0 else "SELL"
        oid = _place(wb, contract, side, n)
        note("FUTURES  %s %s x%d (%s)" % (side, contract, n, oid))
        if book is not None:
            if action == "CLOSE" and book.claim(key):
                book.finish(key, positions.CLOSED,
                            "closed on their call (futures)", price=None)
            elif action == "TRIM":
                book.trim(key, n, None, "their trim (futures) —")
        return True, "futures %s sent: %s x%d" % (action.lower(), contract, n)

    return False, "nothing to do for futures action %r" % action
