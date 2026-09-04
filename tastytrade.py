"""TASTYTRADE broker adapter (9/3/26, G: "I like the greeks thing that tasty
has.. so maybe do 2.. tasty and tradier").

Third implementation of broker.BrokerBase, alongside webull_options.py and
tradier.py. Written against tastytrade's public API (developer.tastytrade.com).

>>> STATUS: UNTESTED AGAINST A LIVE ACCOUNT. <<<
No tastytrade credentials exist yet. Structurally complete and compile-checked;
every endpoint and field name comes from the published docs. Until the first
sandbox call comes back, treat every response shape as a hypothesis.
`verify()` is the read-only first-run checklist. Nothing imports this unless
settings say {"execution": {"broker": "tastytrade"}}. Webull remains default.

WHY TASTYTRADE IS WORTH A SECOND ADAPTER
  * **Streaming GREEKS, not just quotes.** Its dxfeed stream carries delta,
    gamma, theta, vega and IV per contract, live. Every other broker here
    makes us infer from price. With real greeks the ratchet could know that a
    position is only up because IV popped, or that theta is about to eat a
    0DTE faster than the stop can walk — decisions the machine literally
    cannot make today. This is the one capability that changes what the bot
    can THINK, not just how fast it reacts.
  * **$1.00/contract to OPEN, $0.00 to CLOSE**, capped $10/leg. A bot that
    exits everything it opens pays once, not twice.
  * **OTOCO on options is supported** (confirmed in their docs and SDK), so
    the round-number conditional entry has a real home here too.

CREDENTIALS — READ THIS
tastytrade authenticates with your ACCOUNT LOGIN, not an API key: it exchanges
username+password for a session token. That password lives in settings.json,
which is gitignored and must never be committed or pasted anywhere. G enters
it himself. `remember_token` is preferred once obtained — it avoids keeping
the password on disk at all.
"""
import json
import threading
import time
import urllib.error
import urllib.request

from webull_options import Refused
from broker import BrokerBase

LIVE = "https://api.tastyworks.com"
CERT = "https://api.cert.tastyworks.com"          # sandbox


class TastytradeOptions(BrokerBase):
    name = "tastytrade"
    supports_bracket_entry = True
    supports_conditional_on_underlying = True      # OTOCO
    supports_option_streaming = True
    supports_streaming_greeks = True               # the reason it's here
    option_quote_limit_per_min = None

    def __init__(self, username=None, password=None, remember_token=None,
                 account_id=None, sandbox=False, log=None, timeout=8.0):
        if not username or not (password or remember_token):
            raise Refused("tastytrade needs execution.tastytrade.username "
                          "plus either password or remember_token")
        self.username = str(username)
        self._password = password
        self._remember = remember_token
        self.account_id = str(account_id or "")
        self.base = CERT if sandbox else LIVE
        self.timeout = float(timeout)
        self.log = log or (lambda *a, **k: None)
        self._tok = None
        self._tok_at = 0.0
        self._lock = threading.Lock()
        self._last_call = 0.0

    # ---- auth -----------------------------------------------------------
    def _session(self):
        """Session tokens are good for ~24h; refresh well before that."""
        with self._lock:
            if self._tok and (time.time() - self._tok_at) < 20 * 3600:
                return self._tok
        body = {"login": self.username, "remember-me": True}
        if self._remember:
            body["remember-token"] = self._remember
        else:
            body["password"] = self._password
        out = self._raw("POST", "/sessions", body, auth=False)
        data = (out or {}).get("data") or {}
        tok = data.get("session-token")
        if not tok:
            raise Refused("tastytrade login failed: %s" % str(out)[:140])
        with self._lock:
            self._tok = tok
            self._tok_at = time.time()
            # A remember-token lets the password come OUT of settings.json.
            if data.get("remember-token"):
                self._remember = data["remember-token"]
        return tok

    def _pace(self, gap=0.12):
        with self._lock:
            wait = gap - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    def _raw(self, method, path, body=None, auth=True):
        self._pace()
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "discord-sniper/1.0")
        if auth:
            # tastytrade takes the RAW session token — no "Bearer " prefix.
            req.add_header("Authorization", self._session())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:                           # noqa: BLE001
                detail = ""
            raise Refused("tastytrade %s %s -> HTTP %s %s"
                          % (method, path, e.code, detail))
        except Exception as e:                          # noqa: BLE001
            raise Refused("tastytrade %s %s failed: %s"
                          % (method, path, str(e)[:120]))

    def _get(self, path):
        return self._raw("GET", path)

    def _acct(self, tail=""):
        if not self.account_id:
            raise Refused("no tastytrade account_id in settings")
        return "/accounts/%s%s" % (self.account_id, tail)

    @staticmethod
    def _items(body):
        d = (body or {}).get("data") or {}
        it = d.get("items")
        if isinstance(it, list):
            return it
        return [d] if d else []

    # ---- lifecycle ------------------------------------------------------
    def connect(self):
        """Read-only. Logs in and settles the account number."""
        nums = []
        for a in self.accounts():
            n = a.get("account-number") or a.get("account_number")
            if n:
                nums.append(str(n))
        if not nums:
            raise Refused("tastytrade logged in but listed no accounts")
        if self.account_id and self.account_id in nums:
            return self.account_id
        if len(nums) == 1:
            self.account_id = nums[0]
            return self.account_id
        if self.account_id:
            raise Refused("tastytrade account %s not on this login (found %s)"
                          % (self.account_id, ", ".join(nums)))
        raise Refused("this tastytrade login has several accounts (%s) — put "
                      "the one to trade in execution.tastytrade.account_id"
                      % ", ".join(nums))

    # ---- symbols --------------------------------------------------------
    @staticmethod
    def tasty_occ(symbol, expiry, side, strike):
        """tastytrade pads the root to 6 chars: 'SPY   260904P00771000'."""
        root = str(symbol).upper()[:6].ljust(6)
        y, m, d = str(expiry)[2:4], str(expiry)[5:7], str(expiry)[8:10]
        cp = "C" if str(side).upper().startswith("C") else "P"
        return "%s%s%s%s%s%08d" % (root, y, m, d, cp,
                                   int(round(float(strike) * 1000)))

    # ---- market data ----------------------------------------------------
    def ask_bid(self, occ):
        got = self.ask_bid_many([occ])
        if occ not in got:
            raise Refused("no tastytrade quote for %s" % occ)
        return got[occ]

    def ask_bid_many(self, occs):
        """REST fallback. The REAL path is the dxfeed stream (see
        stream_note()) — this exists so the machine still works before the
        streamer is wired, exactly like Webull's 1/s bus does today."""
        occs = [str(o) for o in (occs or []) if o]
        out = {}
        for occ in occs:
            try:
                body = self._get("/market-data/by-type?equity-option=%s"
                                 % urllib.request.quote(occ))
                for row in self._items(body):
                    a, b = _f(row.get("ask")), _f(row.get("bid"))
                    if a or b:
                        out[occ] = (a, b, row)
                        break
            except Exception:                           # noqa: BLE001
                continue
        return out

    def stock_price(self, symbol):
        body = self._get("/market-data/by-type?equity=%s"
                         % str(symbol).upper())
        for row in self._items(body):
            px = _f(row.get("last")) or _f(row.get("close"))
            if px:
                return float(px)
            a, b = _f(row.get("ask")), _f(row.get("bid"))
            if a and b:
                return (a + b) / 2.0
        raise Refused("no tastytrade stock quote for %s" % symbol)

    def stream_note(self):
        """How the greeks stream is meant to be wired, when someone does it.

        GET /api-quote-tokens returns a dxfeed token + websocket url. Subscribe
        to the 'Greeks' event type per option symbol and you get delta, gamma,
        theta, vega and IV pushed live, alongside 'Quote' for bid/ask. That is
        the piece no other broker on the shortlist offers, and the reason to
        keep this adapter even if Tradier wins on cost.

        Deliberately NOT implemented yet: it needs a websocket client in the
        bridge's Python, and the last time a streaming SDK was installed into
        that environment it broke the bridge's pins (8/31, FIX SDK DEPS.bat).
        Wire it only after the REST path is proven, and prefer a dependency-
        free websocket over pulling in a whole SDK.
        """
        return self._get("/api-quote-tokens")

    # ---- account --------------------------------------------------------
    def accounts(self):
        return [a.get("account", a) for a in
                self._items(self._get("/customers/me/accounts"))]

    def positions(self):
        """MUST NOT RAISE — [] means 'no verdict', never 'you are flat'."""
        try:
            body = self._get(self._acct("/positions"))
        except Exception:                               # noqa: BLE001
            return []
        out = []
        for p in self._items(body):
            try:
                qty = int(float(p.get("quantity") or 0))
                if qty == 0:
                    continue
                itype = str(p.get("instrument-type") or "")
                sym = str(p.get("symbol") or "")
                d = {"symbol": str(p.get("underlying-symbol") or sym).upper(),
                     "qty": abs(qty), "kind": "stock", "side": None,
                     "strike": None, "expiry": None,
                     "fill": _f(p.get("average-open-price")),
                     "last": _f(p.get("close-price")),
                     "pl": None, "pl_pct": None}
                if "Option" in itype:
                    d["kind"] = "option"
                    parsed = _parse_tasty_occ(sym)
                    if parsed:
                        d.update(parsed)
                    # tastytrade quotes average-open-price PER SHARE already
                    # on options; if it looks like a contract price, scale it.
                    if d["fill"] and d["fill"] > 100:
                        d["fill"] = round(d["fill"] / 100.0, 4)
                out.append(d)
            except Exception:                           # noqa: BLE001
                continue
        return out

    def futures_positions(self):
        return []

    def buying_power(self):
        try:
            body = self._get(self._acct("/balances"))
            for row in self._items(body):
                for k in ("derivative-buying-power", "option-buying-power",
                          "cash-available-to-withdraw", "cash-balance"):
                    v = _f(row.get(k))
                    if v is not None:
                        return float(v)
        except Exception:                               # noqa: BLE001
            pass
        return None

    # ---- orders ---------------------------------------------------------
    def entry_limit(self, bid, ask):
        b, a = _f(bid), _f(ask)
        if b:
            return float(b)
        if a:
            return float(a)
        raise Refused("no book to price the entry from")

    def _leg(self, symbol, side, strike, expiry, qty, action):
        return {"instrument-type": "Equity Option",
                "symbol": self.tasty_occ(symbol, expiry, side, strike),
                "quantity": int(qty), "action": action}

    def order_status(self, order_id):
        if not order_id:
            return "unknown", 0, None
        try:
            body = self._get(self._acct("/orders/%s" % order_id))
        except Exception:                               # noqa: BLE001
            return "unknown", 0, None
        rows = self._items(body)
        o = rows[0] if rows else {}
        st = str(o.get("status") or "").lower()
        legs = o.get("legs") or []
        fq = 0
        px = None
        for lg in legs:
            for f in (lg.get("fills") or []):
                fq += int(float(f.get("quantity") or 0))
                px = _f(f.get("fill-price")) or px
        if st == "filled":
            return "filled", fq, px
        if st in ("live", "received", "routed", "in flight"):
            return "working", fq, px
        if fq:
            return "partial", fq, px
        if st in ("cancelled", "canceled", "rejected", "expired", "removed"):
            return "dead", fq, px
        return "unknown", fq, px

    def open_orders(self, symbol=None):
        try:
            rows = self._items(self._get(self._acct("/orders/live")))
        except Exception:                               # noqa: BLE001
            return []
        if symbol:
            s = str(symbol).upper()
            rows = [o for o in rows
                    if str(o.get("underlying-symbol") or "").upper() == s]
        return rows

    def cancel(self, order_id):
        if not order_id:
            return
        self._raw("DELETE", self._acct("/orders/%s" % order_id))

    def sell(self, symbol, side, strike, expiry, qty, ref_price=None,
             urgent=False):
        order = {"time-in-force": "Day",
                 "legs": [self._leg(symbol, side, strike, expiry, qty,
                                    "Sell to Close")]}
        if urgent or ref_price is None:
            order["order-type"] = "Market"
        else:
            order["order-type"] = "Limit"
            order["price"] = round(float(ref_price), 2)
            order["price-effect"] = "Credit"
        body = self._raw("POST", self._acct("/orders"), order)
        oid = (((body or {}).get("data") or {}).get("order") or {}).get("id")
        if not oid:
            raise Refused("tastytrade refused the sell: %s" % str(body)[:140])
        return str(oid)

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price,
                   stop_price=None):
        stop = float(stop_price if stop_price is not None
                     else float(fill_price) * 0.90)
        stop = max(0.01, round(stop, 2))
        order = {"order-type": "Stop", "time-in-force": "GTC",
                 "stop-trigger": stop,
                 "legs": [self._leg(symbol, side, strike, expiry, qty,
                                    "Sell to Close")]}
        body = self._raw("POST", self._acct("/orders"), order)
        oid = (((body or {}).get("data") or {}).get("order") or {}).get("id")
        if not oid:
            raise Refused("tastytrade refused the stop: %s" % str(body)[:140])
        return str(oid), stop

    def last_sell_fill(self, symbol, side, strike, expiry, since=None):
        occ = self.tasty_occ(symbol, expiry, side, strike)
        try:
            rows = self._items(self._get(self._acct("/orders")))
        except Exception:                               # noqa: BLE001
            return None
        best = None
        for o in rows:
            if str(o.get("status") or "").lower() != "filled":
                continue
            for lg in (o.get("legs") or []):
                if str(lg.get("symbol") or "") != occ:
                    continue
                if "sell" not in str(lg.get("action") or "").lower():
                    continue
                for f in (lg.get("fills") or []):
                    px = _f(f.get("fill-price"))
                    if px:
                        best = px
        return best

    def flatten(self, symbol):
        n = 0
        for p in self.positions():
            if str(p.get("symbol") or "").upper() != str(symbol).upper():
                continue
            try:
                self.sell(p.get("symbol"), p.get("side"), p.get("strike"),
                          p.get("expiry"), p.get("qty"), urgent=True)
                n += 1
            except Exception:                           # noqa: BLE001
                continue
        return n

    # ---- the capability that started all of this ------------------------
    def place_conditional_entry(self, symbol, side, strike, expiry, qty,
                                limit_price, trigger_price, trigger_dir,
                                stop_price=None):
        """OTOCO: entry leg, then a stop and (optionally) a target that
        cancel each other once the entry fills.

        tastytrade DOES support OTOCO on options (docs + SDK confirm it), so
        this has a real home here — but the exact complex-order envelope must
        be proven in the cert environment before it ever sees real money.
        Until then this refuses and pullback.py's polling hunt stays in
        charge, which is the safe default everywhere.
        """
        raise Refused("tastytrade OTOCO is supported by the API but this "
                      "encoding is UNVERIFIED — prove it in the cert "
                      "sandbox before it touches money; the polling hunt "
                      "stays in charge until then")

    # ---- first-run checklist --------------------------------------------
    def verify(self):
        """Read-only. Places nothing. Run this the moment credentials exist."""
        out = []
        try:
            self._session()
            out.append(("login", True, "session token obtained"))
        except Exception as e:                          # noqa: BLE001
            out.append(("login", False, str(e)[:110]))
            return out
        try:
            accts = self.accounts()
            out.append(("accounts", bool(accts),
                        ", ".join(str(a.get("account-number")) for a in accts)))
        except Exception as e:                          # noqa: BLE001
            out.append(("accounts", False, str(e)[:110]))
        try:
            bp = self.buying_power()
            out.append(("balances", bp is not None, "buying power = %s" % bp))
        except Exception as e:                          # noqa: BLE001
            out.append(("balances", False, str(e)[:110]))
        try:
            out.append(("stock quote", True, "SPY = %s" % self.stock_price("SPY")))
        except Exception as e:                          # noqa: BLE001
            out.append(("stock quote", False, str(e)[:110]))
        try:
            out.append(("positions", True, "%d row(s) — eyeball the shape "
                        "against the real account" % len(self.positions())))
        except Exception as e:                          # noqa: BLE001
            out.append(("positions", False, str(e)[:110]))
        try:
            self.stream_note()
            out.append(("greeks stream token", True,
                        "/api-quote-tokens answered — dxfeed reachable"))
        except Exception as e:                          # noqa: BLE001
            out.append(("greeks stream token", False, str(e)[:110]))
        out.append(("OTOCO entry", None,
                    "place_conditional_entry is UNVERIFIED — prove it in cert"))
        return out


def _f(v):
    try:
        return float(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def _parse_tasty_occ(sym):
    """'SPY   260904P00771000' -> symbol/expiry/side/strike, or None."""
    s = str(sym or "")
    if len(s) < 21:
        return None
    try:
        root = s[:6].strip().upper()
        rest = s[6:]
        yy, mm, dd = rest[0:2], rest[2:4], rest[4:6]
        cp, strike = rest[6], rest[7:15]
        if cp not in ("C", "P") or not root:
            return None
        return {"symbol": root, "expiry": "20%s-%s-%s" % (yy, mm, dd),
                "side": "CALLS" if cp == "C" else "PUTS",
                "strike": int(strike) / 1000.0}
    except Exception:                                   # noqa: BLE001
        return None
