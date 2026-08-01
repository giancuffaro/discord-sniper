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


def front_month(wb, symbol):
    """The contract code actually trading right now for this root — NQ means
    NQZ5 or NQH6 depending on the week. Nearest expiry that is still in the
    future wins. Refuses when the SDK won't say."""
    body, why = _try(wb, ["quote", "market_data", "instrument", "futures"],
                     ["get_futures_instruments", "futures_instruments",
                      "get_instruments", "instruments"], symbol)
    rows = []
    if isinstance(body, dict):
        rows = body.get("data") or body.get("instruments") or []
    elif isinstance(body, list):
        rows = body
    best = None
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = (r.get("symbol") or r.get("contract_code") or
                r.get("instrument_id") or "")
        exp = str(r.get("expire_date") or r.get("expiration_date") or
                  r.get("last_trade_date") or "")
        if not code or not str(code).upper().startswith(str(symbol).upper()):
            continue
        if exp and exp < today:
            continue
        if best is None or (exp and exp < best[1]):
            best = (code, exp or "9999-99-99")
    if not best:
        raise FuturesRefused(
            "couldn't work out which %s contract is front month (%s). No "
            "order was sent — trading the wrong month is a real position in "
            "the wrong thing." % (symbol, why or "SDK gave nothing usable"))
    return best[0]


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
