"""TRADIER broker adapter (9/3/26).

The second implementation of broker.BrokerBase. Written against Tradier's
documented REST API (docs.tradier.com). It exists so the machine can run
Tradier ALONGSIDE Webull and be compared on real fills — see
v3.5.0/BROKER-TOP4-2026-09.md for why Tradier and not Schwab.

>>> STATUS: UNTESTED AGAINST A LIVE ACCOUNT. <<<
No Tradier key exists yet, so not one line of this has touched a real
server. It is structurally complete and compile-checked, and every endpoint
and field name is taken from the published docs — but until G adds a key and
the first sandbox order comes back, treat every response shape here as a
hypothesis. `verify()` at the bottom is the checklist to run first.

Nothing imports this unless settings say {"execution": {"broker": "tradier"}}.
Webull is untouched and remains the default.

What Tradier gives us that Webull cannot:
  * otoco — a real conditional entry with the stop attached, triggered
    broker-side instead of by our poll loop.
  * streaming option quotes — the ratchet stops running on a 1/s photo.
"""
import json
import threading
import time
import urllib.parse
import urllib.request

from webull_options import Refused, occ_symbol
from broker import BrokerBase

LIVE = "https://api.tradier.com"
SANDBOX = "https://sandbox.tradier.com"
STREAM = "https://stream.tradier.com"


class TradierOptions(BrokerBase):
    name = "tradier"
    supports_bracket_entry = True
    supports_conditional_on_underlying = True    # otoco
    supports_option_streaming = True
    option_quote_limit_per_min = None            # no published hard cap

    def __init__(self, access_token, account_id, sandbox=False, log=None,
                 timeout=8.0):
        if not access_token:
            raise Refused("no Tradier access token in settings "
                          "(execution.tradier.access_token)")
        self.token = str(access_token)
        self.account_id = str(account_id or "")
        self.base = SANDBOX if sandbox else LIVE
        self.timeout = float(timeout)
        self.log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._last_call = 0.0

    # ---- plumbing -------------------------------------------------------
    def _pace(self, gap=0.12):
        """Tradier publishes no hard cap, but a bot hammering any broker is
        how rate limits get discovered the expensive way (the 8/9 Webull
        lesson). A small floor between calls costs nothing."""
        with self._lock:
            wait = gap - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    def _req(self, path, params=None, method="GET"):
        self._pace()
        url = self.base + path
        data = None
        if method == "GET" and params:
            url += "?" + urllib.parse.urlencode(params)
        elif params:
            data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace") or "{}")
        except Exception as e:                          # noqa: BLE001
            raise Refused("Tradier %s %s failed: %s"
                          % (method, path, str(e)[:120]))

    def _acct(self, tail):
        if not self.account_id:
            raise Refused("no Tradier account_id in settings")
        return "/v1/accounts/%s%s" % (self.account_id, tail)

    @staticmethod
    def _one(node, key):
        """Tradier returns a bare object for one result and a list for many;
        every caller wants a list. This is the single most common source of
        bugs in Tradier integrations."""
        if not node or node in ("null", "none"):
            return []
        inner = node.get(key) if isinstance(node, dict) else node
        if inner is None:
            return []
        return inner if isinstance(inner, list) else [inner]

    # ---- market data ----------------------------------------------------
    def ask_bid(self, occ):
        got = self.ask_bid_many([occ])
        if occ not in got:
            raise Refused("no Tradier quote for %s" % occ)
        return got[occ]

    def ask_bid_many(self, occs):
        occs = [str(o) for o in (occs or []) if o]
        if not occs:
            return {}
        out = {}
        for i in range(0, len(occs), 50):
            chunk = occs[i:i + 50]
            body = self._req("/v1/markets/quotes",
                             {"symbols": ",".join(chunk), "greeks": "false"})
            for row in self._one((body or {}).get("quotes"), "quote"):
                sym = str(row.get("symbol") or "")
                if sym in chunk:
                    out[sym] = (_f(row.get("ask")), _f(row.get("bid")), row)
        return out

    def stock_price(self, symbol):
        body = self._req("/v1/markets/quotes", {"symbols": str(symbol).upper()})
        for row in self._one((body or {}).get("quotes"), "quote"):
            px = _f(row.get("last")) or _f(row.get("close"))
            if px:
                return float(px)
            a, b = _f(row.get("ask")), _f(row.get("bid"))
            if a and b:
                return (a + b) / 2.0
        raise Refused("no Tradier stock quote for %s" % symbol)

    # ---- account --------------------------------------------------------
    def positions(self):
        """MUST NOT RAISE — [] means 'no verdict', never 'you are flat'."""
        try:
            body = self._req(self._acct("/positions"))
        except Exception:                               # noqa: BLE001
            return []
        out = []
        for p in self._one((body or {}).get("positions"), "position"):
            try:
                sym = str(p.get("symbol") or "")
                qty = int(float(p.get("quantity") or 0))
                if not sym or qty == 0:
                    continue
                cost = _f(p.get("cost_basis"))
                d = {"symbol": sym, "qty": abs(qty), "kind": "stock",
                     "side": None, "strike": None, "expiry": None,
                     "fill": None, "last": None, "pl": None, "pl_pct": None}
                parsed = _parse_occ(sym)
                if parsed:
                    d.update(parsed)
                    d["kind"] = "option"
                    if cost:
                        d["fill"] = round(abs(cost) / (100.0 * abs(qty)), 4)
                elif cost:
                    d["fill"] = round(abs(cost) / abs(qty), 4)
                out.append(d)
            except Exception:                           # noqa: BLE001
                continue
        return out

    def buying_power(self):
        try:
            body = self._req(self._acct("/balances"))
            bal = (body or {}).get("balances") or {}
            for k in ("option_buying_power", "stock_buying_power",
                      "total_cash", "cash_available"):
                v = bal.get(k)
                if v is None and isinstance(bal.get("cash"), dict):
                    v = bal["cash"].get(k)
                if v is not None:
                    return float(v)
        except Exception:                               # noqa: BLE001
            pass
        return None

    # ---- orders ---------------------------------------------------------
    def entry_limit(self, bid, ask):
        """Same house rule as Webull: pay the bid, never chase the ask."""
        b, a = _f(bid), _f(ask)
        if b:
            return float(b)
        if a:
            return float(a)
        raise Refused("no book to price the entry from")

    def order_status(self, order_id):
        if not order_id:
            return "unknown", 0, None
        try:
            body = self._req(self._acct("/orders/%s" % order_id))
        except Exception:                               # noqa: BLE001
            return "unknown", 0, None
        o = (body or {}).get("order") or {}
        st = str(o.get("status") or "").lower()
        fq = int(float(o.get("exec_quantity") or 0))
        px = _f(o.get("avg_fill_price"))
        if st == "filled":
            return "filled", fq, px
        if st in ("partially_filled",):
            return "partial", fq, px
        if st in ("open", "pending"):
            return "working", fq, px
        if st in ("canceled", "cancelled", "expired", "rejected", "error"):
            return "dead", fq, px
        return "unknown", fq, px

    def open_orders(self, symbol=None):
        try:
            body = self._req(self._acct("/orders"))
        except Exception:                               # noqa: BLE001
            return []
        rows = self._one((body or {}).get("orders"), "order")
        if symbol:
            s = str(symbol).upper()
            rows = [o for o in rows if str(o.get("symbol") or "").upper() == s]
        return rows

    def cancel(self, order_id):
        if not order_id:
            return
        self._req(self._acct("/orders/%s" % order_id), method="DELETE")

    def sell(self, symbol, side, strike, expiry, qty, ref_price=None,
             urgent=False):
        occ = occ_symbol(symbol, expiry,
                         "CALL" if str(side).upper().startswith("C") else "PUT",
                         strike)
        params = {"class": "option", "symbol": str(symbol).upper(),
                  "option_symbol": occ, "side": "sell_to_close",
                  "quantity": str(int(qty)), "duration": "day"}
        if urgent or ref_price is None:
            params["type"] = "market"
        else:
            params["type"] = "limit"
            params["price"] = "%.2f" % float(ref_price)
        body = self._req(self._acct("/orders"), params, method="POST")
        oid = ((body or {}).get("order") or {}).get("id")
        if not oid:
            raise Refused("Tradier refused the sell: %s" % str(body)[:140])
        return str(oid)

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price,
                   stop_price=None):
        occ = occ_symbol(symbol, expiry,
                         "CALL" if str(side).upper().startswith("C") else "PUT",
                         strike)
        stop = float(stop_price if stop_price is not None
                     else float(fill_price) * 0.90)
        stop = max(0.01, round(stop, 2))
        params = {"class": "option", "symbol": str(symbol).upper(),
                  "option_symbol": occ, "side": "sell_to_close",
                  "quantity": str(int(qty)), "type": "stop",
                  "stop": "%.2f" % stop,
                  # Tradier allows GTC on option sells — unlike Webull, where
                  # every protective stop is DAY-only and dies at the close.
                  # That alone removes the 9:31 re-arm dance.
                  "duration": "gtc"}
        body = self._req(self._acct("/orders"), params, method="POST")
        oid = ((body or {}).get("order") or {}).get("id")
        if not oid:
            raise Refused("Tradier refused the stop: %s" % str(body)[:140])
        return str(oid), stop

    def last_sell_fill(self, symbol, side, strike, expiry, since=None):
        """What this contract ACTUALLY last sold for. None when unsure —
        never a quoted price standing in for a fill (the 8/27 lesson)."""
        occ = occ_symbol(symbol, expiry,
                         "CALL" if str(side).upper().startswith("C") else "PUT",
                         strike)
        try:
            body = self._req(self._acct("/orders"))
        except Exception:                               # noqa: BLE001
            return None
        best = None
        for o in self._one((body or {}).get("orders"), "order"):
            if str(o.get("option_symbol") or "") != occ:
                continue
            if str(o.get("status") or "").lower() != "filled":
                continue
            if "sell" not in str(o.get("side") or "").lower():
                continue
            px = _f(o.get("avg_fill_price"))
            if px:
                best = px
        return best

    def flatten(self, symbol):
        n = 0
        for p in self.positions():
            if str(p.get("symbol") or "").upper() != str(symbol).upper() \
                    and str(p.get("_occ") or "") != str(symbol):
                continue
            try:
                self.sell(p.get("symbol"), p.get("side"), p.get("strike"),
                          p.get("expiry"), p.get("qty"), urgent=True)
                n += 1
            except Exception:                           # noqa: BLE001
                continue
        return n

    # ---- THE reason this adapter exists ---------------------------------
    def place_conditional_entry(self, symbol, side, strike, expiry, qty,
                                limit_price, trigger_price, trigger_dir,
                                stop_price=None):
        """Broker-side round-number entry: an OTOCO whose first leg only
        fills at/through the level, with the protective stop attached.

        UNVERIFIED — the exact otoco leg encoding for options must be
        confirmed against a sandbox order before this is trusted with money.
        Until then pullback.py's polling hunt remains the live path.
        """
        raise Refused("Tradier conditional entry is written but NOT yet "
                      "verified against a live account — the polling hunt "
                      "stays in charge until a sandbox order proves it")

    # ---- first-run checklist --------------------------------------------
    def verify(self):
        """Run this the moment a key exists, BEFORE any real order.
        Returns a list of (check, ok, detail) — read-only, places nothing."""
        out = []
        try:
            bp = self.buying_power()
            out.append(("balances", bp is not None, "buying power = %s" % bp))
        except Exception as e:                          # noqa: BLE001
            out.append(("balances", False, str(e)[:90]))
        try:
            px = self.stock_price("SPY")
            out.append(("stock quote", bool(px), "SPY = %s" % px))
        except Exception as e:                          # noqa: BLE001
            out.append(("stock quote", False, str(e)[:90]))
        try:
            rows = self.positions()
            out.append(("positions", True, "%d row(s) — shape must be "
                        "eyeballed against the real account" % len(rows)))
        except Exception as e:                          # noqa: BLE001
            out.append(("positions", False, str(e)[:90]))
        out.append(("option quote", None,
                    "needs a live OCC symbol — run ask_bid('SPY26...C00650000')"))
        out.append(("otoco entry", None,
                    "place_conditional_entry is UNVERIFIED; prove it in the "
                    "sandbox before it ever sees real money"))
        return out


def _f(v):
    try:
        return float(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def _parse_occ(occ):
    """SPY260904P00771000 -> symbol/expiry/side/strike, or None."""
    s = str(occ or "")
    if len(s) < 15:
        return None
    try:
        i = 0
        while i < len(s) and not s[i].isdigit():
            i += 1
        root, rest = s[:i], s[i:]
        if len(rest) < 15 or not root:
            return None
        yy, mm, dd = rest[0:2], rest[2:4], rest[4:6]
        cp, strike = rest[6], rest[7:15]
        if cp not in ("C", "P"):
            return None
        return {"symbol": root.upper(),
                "expiry": "20%s-%s-%s" % (yy, mm, dd),
                "side": "CALLS" if cp == "C" else "PUTS",
                "strike": int(strike) / 1000.0}
    except Exception:                                   # noqa: BLE001
        return None
