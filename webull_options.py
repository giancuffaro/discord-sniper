"""
webull_options.py — places the room's calls in your Webull account.

Options only. If Webull hands back a futures account this refuses to use it
and says so, because a futures account will happily take an order that has
nothing to do with what the room called.

This file is standalone on purpose. It does not import a single line from
MARKET SNIPER — different folder, different settings file, different account
selection. You can delete either one without touching the other.

The important difference from MARKET SNIPER: there, the app picks the strike
and expiry. Here the ROOM picks them. "in AMD 7/31 480P" means the 480 put
expiring July 31st and nothing else, so this never substitutes a contract it
liked better. If it can't build exactly what they called, it refuses.
"""

import datetime as dt
import re
import uuid

try:
    from webull.core.client import ApiClient
    from webull.trade.trade_client import TradeClient
    from webull.data.data_client import DataClient
    SDK_OK = True
    SDK_WHY = ""
except Exception as e:                                  # noqa: BLE001
    ApiClient = TradeClient = DataClient = None
    SDK_OK = False
    SDK_WHY = str(e)

REGION = "us"
LIVE_ENDPOINT = "api.webull.com"

# NYSE closures. Only used to sanity-check an expiry the room gave us.
HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


class Refused(Exception):
    """Something is wrong and no order went out. The message is written to be
    read by you, not by a developer."""


# --- turning the room's shorthand into a real contract -----------------------

def expiry_to_date(expiry, today=None):
    """"7/31" -> "2026-07-31". "0dte" -> today. Anything it can't be sure
    about raises, because guessing an expiry means buying a contract nobody
    called."""
    today = today or dt.date.today()
    if not expiry:
        raise Refused("they didn't say which expiry, so there's no way to know "
                      "which contract they meant. Nothing was sent.")
    e = str(expiry).strip().lower()

    if e.endswith("dte"):
        n = e[:-3].strip()
        days = int(n) if n.isdigit() else 0
        return (today + dt.timedelta(days=days)).isoformat()

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", e)
    if not m:
        raise Refused("couldn't make sense of the expiry \"%s\". Nothing was sent."
                      % expiry)
    mo, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
    if yr:
        year = int(yr)
        if year < 100:
            year += 2000
    else:
        # No year given, which is the normal case. Assume the next time that
        # date comes around — in late December, "1/2" means January.
        year = today.year
        try:
            cand = dt.date(year, mo, day)
        except ValueError:
            raise Refused("%s isn't a real date. Nothing was sent." % expiry)
        if (cand - today).days < -7:
            year += 1
    try:
        d = dt.date(year, mo, day)
    except ValueError:
        raise Refused("%s isn't a real date. Nothing was sent." % expiry)

    if d < today:
        raise Refused("that expiry (%s) is already in the past. Nothing was sent."
                      % d.isoformat())
    if d.weekday() > 4 or d.isoformat() in HOLIDAYS:
        raise Refused("%s is not a trading day, so that contract doesn't exist. "
                      "Nothing was sent." % d.isoformat())
    return d.isoformat()


def occ_symbol(symbol, expiration, option_type, strike):
    """SPY + 2026-07-28 + PUT + 745 -> SPY260728P00745000"""
    d = expiration.replace("-", "")[2:]
    cp = "C" if option_type == "CALL" else "P"
    return "%s%s%s%08d" % (symbol.upper(), d, cp, int(round(float(strike) * 1000)))


def _find(obj, *names):
    """Webull's field naming drifts between endpoints, so look for any of them
    anywhere in the response rather than trusting one exact path."""
    if isinstance(obj, dict):
        for n in names:
            if n in obj and obj[n] not in (None, ""):
                return obj[n]
        for v in obj.values():
            got = _find(v, *names)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find(v, *names)
            if got is not None:
                return got
    return None


# --- the account -------------------------------------------------------------

class WebullOptions:
    def __init__(self, cfg):
        w = (cfg.get("execution", {}) or {}).get("webull", {}) or {}
        self.app_key = w.get("app_key", "")
        self.app_secret = w.get("app_secret", "")
        self.account_id = w.get("account_id") or None
        # Webull labels futures accounts as MARGIN, so the only reliable way to
        # keep off one is to name it. Put the tail of your futures account id
        # here and it will never be picked.
        self.futures_suffixes = [str(s).upper() for s in
                                 w.get("futures_account_suffixes", ["3T0B"])]
        # How far above the price they quoted you're willing to pay. Their fill
        # is not your fill; by the time you see the message the ask has often
        # moved. Past this, it skips rather than chasing.
        self.max_chase_pct = float(w.get("max_chase_pct", 15))
        # Pay a hair over the ask so a marketable limit actually fills instead
        # of resting while the move happens without you.
        self.buffer_pct = float(w.get("marketable_buffer_pct", 2))
        self.trade = None
        self._data = None
        self._fns = None

    # -- connect --------------------------------------------------------------
    def connect(self):
        if not SDK_OK:
            raise Refused("the Webull SDK isn't installed. Run SETUP.bat in this "
                          "folder, then start the bridge again. (%s)" % SDK_WHY[:120])
        if not self.app_key or not self.app_secret:
            raise Refused("no Webull API key saved yet. Double-click KEYS.bat and "
                          "put your app key and secret in.")

        api = ApiClient(self.app_key, self.app_secret, REGION)
        api.add_endpoint(REGION, LIVE_ENDPOINT)
        self._api = api
        self.trade = TradeClient(api)
        self._data = DataClient(api)

        res = self.trade.account_v2.get_account_list()
        if getattr(res, "status_code", None) != 200:
            raise Refused("Webull wouldn't list your accounts (HTTP %s). Usually "
                          "that's a wrong or expired API key."
                          % getattr(res, "status_code", "?"))
        data = res.json()
        accounts = data if isinstance(data, list) else (
            data.get("data") or data.get("accounts") or data.get("account_list") or [])
        if isinstance(accounts, dict):
            accounts = [accounts]
        if not accounts:
            raise Refused("connected to Webull, but it returned no accounts.")

        def aid(a):
            return str(_find(a, "account_id", "accountId", "secAccountId") or "")

        if self.account_id:
            match = [a for a in accounts if aid(a) == str(self.account_id)]
            if not match:
                raise Refused("account %s isn't in your Webull account list."
                              % self.account_id)
            chosen = match[0]
        else:
            options_accounts = [
                a for a in accounts
                if not any(aid(a).upper().endswith(s) for s in self.futures_suffixes)]
            if not options_accounts:
                raise Refused("the only Webull account I can see looks like your "
                              "FUTURES account. This bot trades options only, so "
                              "nothing was sent. Run KEYS.bat and set the account "
                              "id you want it to use.")
            if len(options_accounts) > 1:
                ids = ", ".join(aid(a) for a in options_accounts)
                raise Refused("you have more than one Webull account (%s). Run "
                              "KEYS.bat and pick which one this bot uses." % ids)
            chosen = options_accounts[0]

        self.account_id = aid(chosen)
        if any(self.account_id.upper().endswith(s) for s in self.futures_suffixes):
            raise Refused("account %s is your futures account. This bot is options "
                          "only — nothing was sent." % self.account_id)
        return self.account_id

    # -- quotes ---------------------------------------------------------------
    def _quote_fns(self):
        if self._fns is not None:
            return self._fns
        found, holders = [], [("data_client", self._data)]
        for attr in dir(self._data):
            if attr.startswith("_"):
                continue
            if "option" in attr.lower() or "market" in attr.lower():
                try:
                    holders.append((attr, getattr(self._data, attr)))
                except Exception:                       # noqa: BLE001
                    pass
        for hname, h in holders:
            for m in dir(h):
                low = m.lower()
                if m.startswith("_"):
                    continue
                if "option" in low and ("snapshot" in low or "quote" in low):
                    fn = getattr(h, m, None)
                    if callable(fn):
                        found.append(("%s.%s" % (hname, m), fn))
        self._fns = found
        return found

    def ask_bid(self, occ):
        fns = self._quote_fns()
        if not fns:
            raise Refused("couldn't find Webull's option-quote method in the SDK. "
                          "Run SETUP.bat again.")
        errors = []
        shapes = [((occ,), {}), (([occ],), {}), ((occ, "US_OPTION"), {}),
                  (([occ], "US_OPTION"), {}), ((), {"symbols": occ}),
                  ((), {"symbols": [occ]}),
                  ((), {"symbols": [occ], "category": "US_OPTION"})]
        for name, fn in fns:
            for args, kw in shapes:
                try:
                    res = fn(*args, **kw)
                except TypeError:
                    continue
                except Exception as e:                  # noqa: BLE001
                    errors.append("%s: %s" % (name, str(e)[:100]))
                    continue
                code = getattr(res, "status_code", 200)
                if code == 403:
                    raise Refused("Webull returned 403 for market data. That's the "
                                  "$4.99/mo OPRA options-data subscription — it has "
                                  "to be active on the API, separately from the app.")
                if code != 200:
                    errors.append("%s: HTTP %s" % (name, code))
                    continue
                body = res.json() if hasattr(res, "json") else res
                row = body[0] if isinstance(body, list) and body else body
                a = _find(row, "ask", "ask_price", "askPrice")
                b = _find(row, "bid", "bid_price", "bidPrice")
                try:
                    return (float(a) if a else None), (float(b) if b else None), row
                except (TypeError, ValueError):
                    continue
        joined = " | ".join(errors[:3])
        if "INVALID_SYMBOL" in joined or "Invalid Symbol" in joined:
            raise Refused("Webull doesn't have a contract called %s. Either the "
                          "strike or the expiry in that message isn't real, or the "
                          "market is closed. Nothing was sent." % occ)
        raise Refused("couldn't get a quote for %s right now. Nothing was sent. (%s)"
                      % (occ, joined[:120]))

    # -- orders ---------------------------------------------------------------
    def _order(self, symbol, expiration, option_type, strike, side, qty, limit):
        leg = {"side": side, "quantity": str(qty), "symbol": symbol,
               "strike_price": "%.2f" % float(strike),
               "option_expire_date": expiration, "instrument_type": "OPTION",
               "option_type": option_type, "market": "US"}
        return [{"client_order_id": uuid.uuid4().hex[:32], "combo_type": "NORMAL",
                 "option_strategy": "SINGLE", "order_type": "LIMIT",
                 "limit_price": "%.2f" % float(limit), "quantity": str(qty),
                 "side": side, "time_in_force": "DAY", "entrust_type": "QTY",
                 "instrument_type": "OPTION", "market": "US", "symbol": symbol,
                 "legs": [leg]}]

    def _send(self, orders, what):
        res = self.trade.order_v3.place_order(self.account_id, orders)
        try:
            body = res.json()
        except Exception:                               # noqa: BLE001
            body = {}
        code = getattr(res, "status_code", "?")
        if code != 200:
            raise Refused("Webull rejected %s (HTTP %s): %s"
                          % (what, code, str(body)[:180]))
        return str(body)[:200]

    def buy(self, symbol, side, strike, expiry, qty, their_price=None):
        """side is CALLS or PUTS, the way the room writes it."""
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        occ = occ_symbol(symbol, expiration, option_type, strike)
        ask, bid, _ = self.ask_bid(occ)
        if not ask or ask <= 0:
            raise Refused("no live ask on %s, so there's nothing safe to price "
                          "against. Nothing was sent." % occ)

        if their_price:
            over = (ask - float(their_price)) / float(their_price) * 100
            if over > self.max_chase_pct:
                raise Refused("they got in at %.2f but the ask is already %.2f — "
                              "that's %.0f%% worse and past your %.0f%% chase "
                              "limit. Skipped on purpose."
                              % (float(their_price), ask, over, self.max_chase_pct))

        limit = round(ask * (1 + self.buffer_pct / 100) + 0.01, 2)
        what = "BUY %d %s %g%s %s @ %.2f" % (qty, symbol, float(strike),
                                             option_type[0], expiration, limit)
        body = self._send(self._order(symbol, expiration, option_type, strike,
                                      "BUY", qty, limit), what)
        return "%s — %s" % (what, body)

    def sell(self, symbol, side, strike, expiry, qty):
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        occ = occ_symbol(symbol, expiration, option_type, strike)
        ask, bid, _ = self.ask_bid(occ)
        ref = bid or ask
        if not ref or ref <= 0:
            raise Refused("no live bid on %s to price the exit against. Nothing "
                          "was sent — close it in the Webull app." % occ)
        # Sell a shade under the bid. Getting out matters more than the last
        # cent, and a limit sitting above the bid is how you end up still
        # holding it at 4pm.
        limit = max(0.01, round(ref * (1 - self.buffer_pct / 100) - 0.01, 2))
        what = "SELL %d %s %g%s %s @ %.2f" % (qty, symbol, float(strike),
                                              option_type[0], expiration, limit)
        body = self._send(self._order(symbol, expiration, option_type, strike,
                                      "SELL", qty, limit), what)
        return "%s — %s" % (what, body)
