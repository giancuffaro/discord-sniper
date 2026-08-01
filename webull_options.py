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
import time
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

def weekly_expiry(today=None):
    """This week's Friday, as an ISO date — the room's stated default.

    Their own pinned rules message says it outright: "contracts are weekly exp,
    unless specified IE (0DTE or specific date)". So when a call arrives as
    "in SPY 747C @ 3.00" with no date on it, the date is not actually missing —
    it's the one they said applies unless they say otherwise.

    When that Friday is a market holiday the week's contracts expire on the
    Thursday before it, not the following week — a July 4th week expires on the
    3rd's Thursday. So the walk is backwards, not forwards. If walking back
    would land before today the week is already spent, and it moves on to the
    next Friday instead. Nothing else is inferred: if the strike is missing, or
    the call is a close, this is not used."""
    today = today or dt.date.today()
    friday = today + dt.timedelta(days=(4 - today.weekday()) % 7)
    for _ in range(6):
        d = friday
        # Back up off a holiday Friday, but never past today — a contract that
        # already expired is not the one they meant.
        while d >= today and (d.weekday() > 4 or d.isoformat() in HOLIDAYS):
            d -= dt.timedelta(days=1)
        if d >= today:
            return d.isoformat()
        friday += dt.timedelta(days=7)
    return friday.isoformat()


def expiry_to_date(expiry, today=None):
    """"7/31" -> "2026-07-31". "0dte" -> today. Anything it can't be sure
    about raises, because guessing an expiry means buying a contract nobody
    called."""
    today = today or dt.date.today()
    if not expiry:
        raise Refused("they didn't say which expiry, so there's no way to know "
                      "which contract they meant. Nothing was sent.")
    e = str(expiry).strip().lower()

    # "Loading 205 calls Friday expiration on NVDA" — they named the weekly
    # rather than a date. Not a guess, so this works whether or not
    # assume_weekly_expiry is on.
    if e == "weekly":
        return weekly_expiry(today)

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


def affordability(limit, qty, have, buffer=0.0):
    """(cost, ok, message). One options contract is 100 shares, so a $2.80
    contract costs $280 — which is the whole reason this exists.

    Lives out here as a plain function so the real broker path and the dry-run
    path produce the exact same sentence. There is no worse way to learn what
    this does than to have dry run tell you one thing and live tell you
    another."""
    cost = float(limit) * 100 * int(qty)
    room = float(have) - float(buffer or 0)
    if cost <= room:
        return cost, True, ""
    tail = (" to spend" if not buffer else
            " free after the $%.0f you asked me to leave alone" % buffer)
    return cost, False, (
        "that one costs $%.0f and you've got $%.0f%s. Skipped on purpose — no "
        "order was sent and you're not in it."
        % (cost, max(0.0, room), tail))


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


# --- reading the account list ------------------------------------------------
# Menu 2 shows you this list and makes you pick. Everything in here is shared
# with connect() below so the setup screen and the bridge can never disagree
# about what your accounts are called.

def _acct_id(a):
    return str(_find(a, "account_id", "accountId", "secAccountId") or "")


def _acct_kind(a):
    """MARGIN / CASH / FUTURES / IRA, as best as Webull will admit to."""
    t = str(_find(a, "account_type", "accountType", "acct_type") or "").upper()
    if "FUTUR" in t:
        return "FUTURES"
    if "IRA" in t or "ROTH" in t:
        return "IRA"
    if "MARGIN" in t:
        return "MARGIN"
    if "CASH" in t:
        return "CASH"
    return t or "UNKNOWN"


def _unpack_accounts(res):
    if getattr(res, "status_code", None) != 200:
        raise Refused("Webull wouldn't list your accounts (HTTP %s). Usually "
                      "that's a wrong or expired API key, or the key and the "
                      "secret got swapped." % getattr(res, "status_code", "?"))
    data = res.json()
    accounts = data if isinstance(data, list) else (
        data.get("data") or data.get("accounts") or data.get("account_list") or [])
    if isinstance(accounts, dict):
        accounts = [accounts]
    if not accounts:
        raise Refused("connected to Webull, but it says you have no accounts.")
    return accounts


def list_accounts(app_key, app_secret):
    """[{'id': ..., 'kind': 'MARGIN', 'label': 'MARGIN  ...1234'}, ...]

    Used by menu 2. Read-only — it cannot place anything."""
    if not SDK_OK:
        raise Refused("the Webull SDK isn't installed. Open START HERE in this "
                      "folder first - it installs what's missing. (%s)" % SDK_WHY[:120])
    if not app_key or not app_secret:
        raise Refused("no app key and secret to log in with yet.")
    api = ApiClient(app_key, app_secret, REGION)
    api.add_endpoint(REGION, LIVE_ENDPOINT)
    out = []
    for a in _unpack_accounts(TradeClient(api).account_v2.get_account_list()):
        aid = _acct_id(a)
        kind = _acct_kind(a)
        currency = str(_find(a, "currency") or "")
        out.append({"id": aid, "kind": kind,
                    "label": "%-8s %s%s" % (kind, aid,
                                            ("  " + currency) if currency else "")})
    return out


# --- the account -------------------------------------------------------------

class WebullOptions:
    def __init__(self, cfg):
        w = (cfg.get("execution", {}) or {}).get("webull", {}) or {}
        self.app_key = w.get("app_key", "")
        self.app_secret = w.get("app_secret", "")
        self.account_id = w.get("account_id") or None
        self.account_kind = ""
        # Webull labels futures accounts as MARGIN, so the only reliable way to
        # keep off one is to name it. Put the tail of your futures account id
        # here and it will never be picked.
        self.futures_suffixes = [str(s).upper() for s in
                                 w.get("futures_account_suffixes", ["3T0B"])]
        # How far above the price they quoted you're willing to pay. Their fill
        # is not your fill; by the time you see the message the ask has often
        # moved. Past this, it skips rather than chasing.
        # Pay a hair over the ask so a marketable limit actually fills instead
        # of resting while the move happens without you.
        self.buffer_pct = float(w.get("marketable_buffer_pct", 2))
        # Where the entry limit is priced. "bid" sits and waits for a seller to
        # come to you — you never overpay, and you don't always get in. "ask"
        # crosses the spread and fills nearly every time. "mid" splits it.
        # Webull takes no market orders on options at all, so all three of these
        # are limit orders; this only decides the number on it.
        self.entry_price = str(w.get("entry_price", "bid")).lower()
        # How long an unfilled entry is allowed to sit there before it's pulled.
        # This is the number that stops a bid from filling at 3:55pm into a
        # trade the room called at 9:40 and closed at 10:05.
        self.fill_seconds = float(w.get("entry_fill_seconds", 90))
        # The protective stop, as a percentage of what you actually paid.
        self.stop_pct = float(w.get("stop_loss_pct", 20))
        # Dollars to leave untouched no matter what. 0 means "spend it all".
        self.cash_buffer = float(w.get("keep_cash_buffer", 0))
        self.trade = None
        self._data = None
        self._fns = None
        self._bal_fns = None
        self._bal = None
        self._bal_at = 0.0

    # -- connect --------------------------------------------------------------
    def connect(self):
        if not SDK_OK:
            raise Refused("the Webull SDK isn't installed. Open START HERE in "
                          "this folder - it installs what's missing and starts the bridge "
                          "again. (%s)" % SDK_WHY[:120])
        if not self.app_key or not self.app_secret:
            raise Refused("no Webull API key saved yet. Open START HERE, press "
                          "2, and put your app key and secret in.")

        api = ApiClient(self.app_key, self.app_secret, REGION)
        api.add_endpoint(REGION, LIVE_ENDPOINT)
        self._api = api
        self.trade = TradeClient(api)
        self._data = DataClient(api)

        accounts = _unpack_accounts(self.trade.account_v2.get_account_list())

        def is_futures(a):
            return (_acct_kind(a) == "FUTURES"
                    or any(_acct_id(a).upper().endswith(s)
                           for s in self.futures_suffixes))

        if self.account_id:
            match = [a for a in accounts if _acct_id(a) == str(self.account_id)]
            if not match:
                raise Refused("account %s isn't in your Webull account list any "
                              "more. EXTRAS.bat, keys option, picks it again."
                              % self.account_id)
            chosen = match[0]
        else:
            options_accounts = [a for a in accounts if not is_futures(a)]
            if not options_accounts:
                raise Refused("the only Webull account I can see looks like your "
                              "FUTURES account. This bot trades options only, so "
                              "nothing was sent. Run EXTRAS.bat, keys option, and pick "
                              "the account you want it to use.")
            # His rule now: MARGIN automatically. "i would like for it to
            # choose the margin account automatically for options" — no
            # EXTRAS step, no picking. Margin first; if there's no margin
            # account, the biggest non-futures one; a genuine tie still
            # refuses loudly rather than guessing between equals.
            margins = [a for a in options_accounts
                       if "MARGIN" in _acct_kind(a).upper()]
            if len(margins) == 1:
                chosen = margins[0]
            elif len(options_accounts) == 1:
                chosen = options_accounts[0]
            elif margins:
                ids = ", ".join("%s (%s)" % (_acct_id(a), _acct_kind(a))
                                for a in margins)
                raise Refused("you have more than one MARGIN account — %s. "
                              "Open EXTRAS.bat, keys option, and pick one."
                              % ids)
            else:
                ids = ", ".join("%s (%s)" % (_acct_id(a), _acct_kind(a))
                                for a in options_accounts)
                raise Refused("you have more than one Webull account and none "
                              "is MARGIN — %s. Open EXTRAS.bat, keys option, "
                              "and pick one." % ids)

        self.account_id = _acct_id(chosen)
        self.account_kind = _acct_kind(chosen)
        # And the FUTURES account rides along, picked automatically — "use
        # the futures one" — so MNQ/MES orders know where they live without
        # anyone choosing anything twice.
        futs = [a for a in accounts if is_futures(a)]
        self.futures_account_id = _acct_id(futs[0]) if futs else None
        if is_futures(chosen):
            raise Refused("account %s is a FUTURES account. This bot is options "
                          "only — nothing was sent. Run EXTRAS.bat, keys option, and "
                          "pick your margin or cash account instead."
                          % self.account_id)
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
                          "Double-click START HERE again - it reinstalls what's missing.")
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

    # -- what you can actually afford -----------------------------------------
    def _balance_fns(self):
        """Webull has renamed this endpoint more than once, so it gets hunted
        for by name the same way the quote method does."""
        if self._bal_fns is not None:
            return self._bal_fns
        found, holders = [], [("trade_client", self.trade)]
        for attr in dir(self.trade):
            if attr.startswith("_"):
                continue
            if "account" in attr.lower():
                try:
                    holders.append((attr, getattr(self.trade, attr)))
                except Exception:                       # noqa: BLE001
                    pass
        for hname, h in holders:
            for m in dir(h):
                if m.startswith("_"):
                    continue
                if "balance" in m.lower():
                    fn = getattr(h, m, None)
                    if callable(fn):
                        found.append(("%s.%s" % (hname, m), fn))
        self._bal_fns = found
        return found

    def buying_power(self):
        """Dollars available to open an options position, or None if Webull
        won't say.

        Cached for a few seconds. A burst of five messages in ten seconds
        shouldn't turn into five balance calls, and the number can't have moved
        much in between.

        None means "couldn't read it", and the caller treats that as "don't
        block the trade" — a balance endpoint that changed shape overnight
        should not quietly stop him trading. Webull will still reject an order
        he can't afford; this check exists to catch it earlier and say so in
        English, not to be the only thing standing in the way."""
        now = time.time()
        if self._bal_at and now - self._bal_at < 8:
            return self._bal
        val = None
        for _name, fn in self._balance_fns():
            for args in ((self.account_id,), (), (self.account_id, "USD")):
                try:
                    res = fn(*args)
                except TypeError:
                    continue
                except Exception:                       # noqa: BLE001
                    break
                if getattr(res, "status_code", 200) != 200:
                    continue
                body = res.json() if hasattr(res, "json") else res
                # Most specific first: the options-specific figure beats the
                # general one, and both beat plain settled cash.
                got = _find(body, "option_buying_power", "optionBuyingPower",
                            "buying_power", "buyingPower", "day_buying_power",
                            "dayBuyingPower", "available_funds", "availableFunds",
                            "settled_funds", "settledFunds", "cash_balance",
                            "cashBalance", "net_cash_balance", "usable_cash")
                try:
                    if got is not None:
                        val = float(got)
                        break
                except (TypeError, ValueError):
                    continue
            if val is not None:
                break
        self._bal, self._bal_at = val, now
        return val

    def afford_check(self, limit, qty):
        """Raises if the order costs more than the account has."""
        have = self.buying_power()
        if have is None:
            return float(limit) * 100 * int(qty)
        cost, ok, msg = affordability(limit, qty, have, self.cash_buffer)
        if not ok:
            raise Refused(msg)
        return cost

    # -- orders ---------------------------------------------------------------
    def _order(self, symbol, expiration, option_type, strike, side, qty, limit,
               stop=None):
        """One options order, ready to send.

        Every order this file builds is a LIMIT order or a STOP order with a
        limit on it. Webull does not accept market orders on options — there is
        no code path here that could send one even by accident.
        """
        leg = {"side": side, "quantity": str(qty), "symbol": symbol,
               "strike_price": "%.2f" % float(strike),
               "option_expire_date": expiration, "instrument_type": "OPTION",
               "option_type": option_type, "market": "US"}
        o = {"client_order_id": uuid.uuid4().hex[:32], "combo_type": "NORMAL",
             "option_strategy": "SINGLE", "order_type": "LIMIT",
             "limit_price": "%.2f" % float(limit), "quantity": str(qty),
             "side": side, "time_in_force": "DAY", "entrust_type": "QTY",
             "instrument_type": "OPTION", "market": "US", "symbol": symbol,
             "legs": [leg]}
        if stop is not None:
            # A stop with a limit under it rather than a plain stop: when this
            # triggers it becomes a sell order priced a little below the stop,
            # so it clears in a fast drop instead of resting above the market
            # while the contract keeps falling.
            o["order_type"] = "STOP_LOSS_LIMIT"
            o["stop_price"] = "%.2f" % float(stop)
            o["time_in_force"] = "GTC"
        return [o]

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
        return body if isinstance(body, (dict, list)) else {}

    # -- knowing what happened to an order ------------------------------------
    def _try_calls(self, holder_names, verbs, *args, **kw):
        """Webull has renamed these endpoints between SDK versions, so they get
        hunted the same way the quote and balance endpoints already are. Returns
        (body, name) for the first call that answers, or (None, errors)."""
        errors = []
        holders = []
        for hn in holder_names:
            h = getattr(self.trade, hn, None)
            if h is not None:
                holders.append((hn, h))
        for hname, h in holders:
            for m in dir(h):
                if m.startswith("_"):
                    continue
                low = m.lower()
                if not any(v in low for v in verbs):
                    continue
                fn = getattr(h, m, None)
                if not callable(fn):
                    continue
                try:
                    res = fn(*args, **kw)
                except TypeError:
                    continue
                except Exception as e:                  # noqa: BLE001
                    errors.append("%s.%s: %s" % (hname, m, str(e)[:80]))
                    continue
                if getattr(res, "status_code", 200) != 200:
                    errors.append("%s.%s: HTTP %s"
                                  % (hname, m, getattr(res, "status_code", "?")))
                    continue
                body = res.json() if hasattr(res, "json") else res
                return body, "%s.%s" % (hname, m)
        return None, " | ".join(errors[:3])

    def order_status(self, order_id):
        """(state, filled_qty, avg_price). state is one of working, filled,
        partial, dead, unknown.

        "unknown" is deliberately not treated as "filled" anywhere upstream. If
        this can't tell, the safe reading is that you might be in it, which is
        why the caller checks your actual positions before deciding."""
        body, _why = self._try_calls(
            ["order_v3", "order"], ["detail", "query", "get_order"],
            self.account_id, order_id)
        if body is None:
            body, _why = self._try_calls(
                ["order_v3", "order"], ["detail", "query", "get_order"], order_id)
        if body is None:
            return "unknown", 0, None
        row = body[0] if isinstance(body, list) and body else body
        st = str(_find(row, "status", "order_status", "orderStatus") or "").upper()
        try:
            fq = float(_find(row, "filled_quantity", "filledQuantity",
                             "cumulative_quantity", "filled_qty") or 0)
        except (TypeError, ValueError):
            fq = 0
        try:
            avg = _find(row, "avg_fill_price", "avgFillPrice", "average_price",
                        "avgPrice", "filled_price")
            avg = float(avg) if avg not in (None, "") else None
        except (TypeError, ValueError):
            avg = None
        if "FILL" in st and "PART" not in st:
            return "filled", fq, avg
        if "PART" in st:
            return "partial", fq, avg
        if any(k in st for k in ("CANCEL", "REJECT", "FAIL", "EXPIRE")):
            return "dead", fq, avg
        if st:
            return "working", fq, avg
        return "unknown", fq, avg

    def cancel(self, order_id):
        """True if Webull took the cancel. False is not a crisis on its own —
        it usually means the order already filled or was already gone."""
        body, _why = self._try_calls(["order_v3", "order"], ["cancel"],
                                     self.account_id, order_id)
        if body is None:
            body, _why = self._try_calls(["order_v3", "order"], ["cancel"], order_id)
        return body is not None

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price):
        """The resting 20% stop, sent right after an entry fills.

        Priced off what you actually paid, not off what the room said they paid.
        Returns (order_id, stop_price). Raises Refused if Webull won't take it —
        the caller keeps trading and leans on the watchdog, because a missing
        resting stop is a reason to warn you, not a reason to be in a position
        with nothing watching it at all.
        """
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        stop = max(0.01, round(float(fill_price) * (1 - self.stop_pct / 100), 2))
        what = "STOP %d %s %g%s %s @ %.2f" % (qty, symbol, float(strike),
                                              option_type[0], expiration, stop)
        # The limit sits under the trigger so a fast drop still clears.
        limit = max(0.01, round(stop * 0.90, 2))
        body = self._send(self._order(symbol, expiration, option_type, strike,
                                      "SELL", qty, limit, stop=stop), what)
        oid = _find(body, "order_id", "orderId", "client_order_id", "clientOrderId")
        return (str(oid) if oid else None), stop

    def buy(self, symbol, side, strike, expiry, qty, their_price=None):
        """side is CALLS or PUTS, the way the room writes it."""
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        occ = occ_symbol(symbol, expiration, option_type, strike)
        ask, bid, _ = self.ask_bid(occ)
        if not ask or ask <= 0:
            raise Refused("no live ask on %s, so there's nothing safe to price "
                          "against. Nothing was sent." % occ)

        # The chase limit that used to sit here is DELETED, on his word:
        # "no filters wanted. id like to follow everything to the tee as they
        # do." If the room is in it, he's in it, whatever the ask has done
        # since — the bid-sitting entry style is still what protects the
        # price actually paid.

        limit = self.entry_limit(bid, ask)
        # Checked here rather than earlier because this is the first point the
        # real price is known — their quoted 2.80 and the live ask are not the
        # same number, and it's the live one you'd be paying.
        self.afford_check(limit, qty)
        what = "BUY %d %s %g%s %s @ %.2f" % (qty, symbol, float(strike),
                                             option_type[0], expiration, limit)
        body = self._send(self._order(symbol, expiration, option_type, strike,
                                      "BUY", qty, limit), what)
        oid = _find(body, "order_id", "orderId", "client_order_id", "clientOrderId")
        # This returns the moment Webull accepts the order, NOT when it fills.
        # On a resting bid those are different events minutes apart, and
        # sometimes the second one never happens — so nothing downstream is
        # allowed to read this as "you own it". bridge.py watches the ticket.
        return {"ok": True, "state": "working", "order_id": str(oid) if oid else None,
                "occ": occ, "what": what, "limit": limit, "bid": bid, "ask": ask,
                "symbol": symbol, "side": side, "strike": strike,
                "expiry": expiry, "qty": qty}

    def entry_limit(self, bid, ask):
        """The number that goes on the entry.

        All three settings are limit orders — Webull takes nothing else on
        options. "bid" is the patient one: you are the resting order and you
        only get in if a seller comes down to you. On a call that runs straight
        from the message you will not fill, and that is the trade-off, chosen
        on purpose.
        """
        bid = float(bid or 0)
        ask = float(ask or 0)
        if self.entry_price == "ask" or not bid:
            return round(ask * (1 + self.buffer_pct / 100) + 0.01, 2)
        if self.entry_price == "mid":
            return max(0.01, round((bid + ask) / 2, 2))
        return max(0.01, round(bid, 2))

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
        oid = _find(body, "order_id", "orderId", "client_order_id", "clientOrderId")
        return {"ok": True, "state": "sent", "order_id": str(oid) if oid else None,
                "occ": occ, "what": what, "limit": limit, "bid": bid, "ask": ask,
                "symbol": symbol, "qty": qty}
