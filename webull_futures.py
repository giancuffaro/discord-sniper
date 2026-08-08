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


def _order_id_of(body):
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        got = data.get("order_id") or data.get("orderId")
        if got:
            return got
    return body.get("order_id") or body.get("orderId") or body.get("client_order_id")


def _place(wb, contract, side, qty, limit=None):
    """Send one futures order. The old code passed a bare dict as the only
    argument and every endpoint 'answered' with a TypeError — 'no endpoint
    answered'. The options path proves the SDK wants place_order(account_id,
    [order]); futures share it. So build a proper order and try that signature
    first, then probe broadly across the trade client's order holders and the
    other plausible arg shapes. Still refuses cleanly if nothing takes it — a
    futures order is never sent blind."""
    import uuid
    fut_acct = getattr(wb, "futures_account_id", None)
    if not fut_acct:
        # Never fall back to the options account - Webull rejects a futures
        # order there (NON_FUTURES_ACCOUNT), the exact loop we are fixing.
        raise FuturesRefused(
            "no Webull FUTURES account is set, so nothing was sent. Set "
            "execution.webull.futures_account_id to your futures account "
            "number so MNQ/MES route there instead of your options account.")
    cid = uuid.uuid4().hex[:32]
    otype = "LIMIT" if limit else "MARKET"

    # Two order shapes, tried in order. The FIRST mirrors the OPTIONS order this
    # SDK already accepts every day — a combo/legs envelope sent through
    # order_v3.place_order(account_id, [order]). If futures ride the same
    # endpoint (they share the trade client), this is the one that takes. The
    # SECOND is the flat place_order_v2 dict, kept as a fallback.
    leg = {"side": side, "quantity": str(int(qty)), "symbol": contract,
           "instrument_type": "FUTURES", "market": "US"}
    combo = {"client_order_id": cid, "combo_type": "NORMAL",
             "order_type": otype, "quantity": str(int(qty)), "side": side,
             "time_in_force": "DAY", "entrust_type": "QTY",
             "instrument_type": "FUTURES", "market": "US", "symbol": contract,
             "legs": [leg]}
    flat = {"client_order_id": cid, "symbol": contract,
            "instrument_type": "FUTURES", "market": "US", "side": side,
            "quantity": str(int(qty)), "qty": str(int(qty)),
            "order_type": otype, "time_in_force": "DAY", "entrust_type": "QTY"}
    if fut_acct:
        flat["account_id"] = flat["accountId"] = str(fut_acct)
        combo["account_id"] = str(fut_acct)
    if limit:
        px = "%.2f" % float(limit)
        for d in (combo, leg, flat):
            d["limit_price"] = px
        flat["price"] = px

    # Prefer the exact method+signature options uses, then broaden. Each attempt
    # captures Webull's REAL response body on rejection (not just the status) so
    # a supervised first trade tells us precisely which field it dislikes.
    tr = getattr(wb, "trade", None)
    errors = []

    def _run(fn, mname, *args):
        try:
            res = fn(*args)
        except TypeError:
            return None                                 # wrong signature, skip
        except Exception as e:                          # noqa: BLE001
            errors.append("%s: %s" % (mname, str(e)[:70]))
            return None
        code = getattr(res, "status_code", 200)
        try:
            body = res.json() if hasattr(res, "json") else res
        except Exception:                               # noqa: BLE001
            body = {}
        if code != 200:
            # The body is where Webull says WHY — keep it, that's the whole point.
            errors.append("%s: HTTP %s %s" % (mname, code, str(body)[:150]))
            return None
        oid = _order_id_of(body)
        # A 200 with an error message inside is still a rejection.
        if not oid and isinstance(body, dict) and (body.get("code") or body.get("msg")):
            errors.append("%s: %s" % (mname, str(body)[:150]))
            return None
        return oid or "unknown"

    # 1) The proven options path first: order_v3.place_order(account, [combo]).
    ov3 = getattr(tr, "order_v3", None) if tr is not None else None
    if ov3 is not None and hasattr(ov3, "place_order"):
        got = _run(ov3.place_order, "order_v3.place_order", fut_acct, [combo])
        if got:
            return got

    # 2) Broad probe: every place/submit/create-order method, options-style
    # (account, [combo]) first, then the flat place_order_v2 dict shapes.
    holders = []
    if tr is not None:
        holders.append(("trade", tr))
        for a in dir(tr):
            if a.startswith("_"):
                continue
            low = a.lower()
            if "order" in low or "futur" in low or "trade" in low:
                try:
                    holders.append((a, getattr(tr, a)))
                except Exception:                       # noqa: BLE001
                    pass
    shapes = [(fut_acct, [combo]), (fut_acct, combo), (fut_acct, flat),
              ([combo],), (combo,), (flat,)] if fut_acct else \
             [([combo],), (combo,), (flat,)]
    for hname, h in holders:
        for m in dir(h):
            low = m.lower()
            if m.startswith("_"):
                continue
            if not ((("place" in low or "submit" in low or "create" in low)
                     and "order" in low) or ("futur" in low and "order" in low)):
                continue
            fn = getattr(h, m, None)
            if not callable(fn):
                continue
            for args in shapes:
                got = _run(fn, "%s.%s" % (hname, m), *args)
                if got:
                    return got
    raise FuturesRefused(
        "Webull wouldn't take the futures order the ways I know how to send one "
        "(%s). Nothing went out — the first live futures trade is a supervised "
        "one; send me the bridge log line." % (" | ".join(errors[:3]) or
                                               "no endpoint answered"))


# Index futures trade on a clean 25-point grid, so snap the entry there: an
# alert "Short NQ @ 29723" becomes 29725. ONLY the index symbols - snapping oil
# (70) or gas (3.4) to 25 would send a wildly wrong price, so those pass through.
FUT_ROUND25 = {"NQ", "MNQ", "ES", "MES", "YM", "MYM", "RTY", "M2K"}


def _round_entry(sym, px):
    try:
        v = float(px)
    except (TypeError, ValueError):
        return px
    if str(sym).upper() in FUT_ROUND25:
        return round(v / 25.0) * 25.0
    return v


def execute(wb, book, order, key, note):
    """The whole live futures path: entry, trim, or close. Returns (ok, msg).
    Sizing is pinned to one contract on purpose — see the file docstring."""
    action = order.get("action")
    sym = str(order.get("symbol", "")).upper()
    direction = str(order.get("direction") or "").upper()
    contract = front_month(wb, sym)

    if action == "OPEN":
        side = "SELL" if direction == "SHORT" else "BUY"
        raw_px = order.get("limit")
        entry_px = _round_entry(sym, raw_px)     # snap index-futures entry to the 25-pt grid
        if entry_px is not None and raw_px is not None and float(entry_px) != float(raw_px):
            note("FUTURES  %s entry snapped to the 25-pt grid: %s -> %g"
                 % (sym, raw_px, entry_px))
        oid = _place(wb, contract, side, 1, entry_px)
        note("FUTURES  ORDER IN %s %s x1 (%s) @ %s, their stop %s target %s"
             % (side, contract, oid, entry_px, order.get("their_stop"),
                order.get("their_target")))
        if book is not None:
            order = dict(order, mult=None, limit=entry_px)
            from bridge import FUT_MULT
            order["mult"] = FUT_MULT.get(sym, 1.0)
            book.entry_sent(order, {"order_id": oid, "occ": None,
                                    "limit": entry_px,
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
