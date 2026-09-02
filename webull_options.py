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
# Webull launched OpenAPI paper trading (six asset classes, options + futures)
# in July 2026. The exact host isn't in the public docs yet; this is the
# documented sandbox base and is OVERRIDABLE from settings
# (execution.webull.paper_endpoint) the moment his account names the real one.
PAPER_ENDPOINT = "api.sandbox.webull.com"

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


class _ComboUnsupported(Exception):
    """The broker/SDK wouldn't take a linked order group — internal signal
    only: the caller falls back to the plain single-order path and says so."""


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

    # ISO date, year first: "2026-08-07". The parser hands back a fully
    # resolved date this way for calls like Bullwinkle's "NEXT WEEK", so we
    # have to be able to read it straight back or we refuse a real contract.
    iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", e)
    if iso:
        y, mo, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
        try:
            d = dt.date(y, mo, day)
        except ValueError:
            raise Refused("%s isn't a real date. Nothing was sent." % expiry)
        if d < today:
            raise Refused("that expiry (%s) is already in the past. Nothing "
                          "was sent." % d.isoformat())
        if d.weekday() > 4 or d.isoformat() in HOLIDAYS:
            raise Refused("%s is not a trading day, so that contract doesn't "
                          "exist. Nothing was sent." % d.isoformat())
        return d.isoformat()

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", e)
    if not m:
        raise Refused("couldn't make sense of the expiry \"%s\". Nothing was sent."
                      % expiry)
    mo, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
    # Day-first dates ("26/8" — TradeLikeGates writes them European style,
    # cost a META entry 8/25): a "month" over 12 with a sane day after it
    # can only mean day/month. Swap instead of refusing a real contract.
    if mo > 12 and day <= 12:
        mo, day = day, mo
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


def stop_below(reference, pct, symbol=None):
    """A protective stop strictly BELOW the reference price: pct down, tick
    rounded, and NEVER at or above the reference. 8/31 IWM lesson: 0.22 bid
    * 0.90 = 0.198 nearest-rounded UP to 0.20 — the exact fill — and the
    trade stopped out 7 seconds after filling on a single downtick. Cheap
    contracts round on a coarse grid, so the guard drops one full step
    whenever rounding lands at/above the reference."""
    ref = float(reference)
    raw = ref * (1 - float(pct) / 100.0)
    px = max(0.01, float(tick_round(raw, symbol)))
    step = tick_step(ref, symbol)
    if px >= ref - 1e-9:
        px = max(0.01, round(ref - step, 2))
    return px


# TICK CLASSES (9/2, v3.5.0/OPTIONS-BROKER-REFERENCE.md, Cboe notice 57916 +
# SEC 34-104157): SPY/QQQ/IWM quote in $0.01 at EVERY price. Penny Interval
# Program names quote $0.01 under $3.00 and $0.05 at/above. Everything else
# is $0.05 under $3.00 / $0.10 at/above. Rounding a penny name to nickels is
# legal but gives cents away on every stop and limit; rounding a non-penny
# name to pennies is a 417 OPTION_PRICE_STEP_LT. Unknown symbol = the old
# conservative $0.05/$0.10 (always legal). The full ~300-name Cboe list
# rotates each January/April; this is the slice the rooms actually call.
PENNY_ALWAYS = {"SPY", "QQQ", "IWM"}
PENNY_PROGRAM = {
    "AAPL", "TSLA", "NVDA", "META", "AMZN", "MSFT", "GOOGL", "GOOG", "AMD",
    "NFLX", "INTC", "BAC", "F", "PLTR", "SOFI", "HOOD", "COIN", "MSTR", "DIA",
    "GLD", "SLV", "TLT", "XLF", "XLE", "UBER", "BA", "DIS", "NKE", "PYPL",
    "SNAP", "RIVN", "LCID", "NIO", "MARA", "RIOT", "SMCI", "ARM", "AVGO",
    "CRM", "ORCL", "QCOM", "MU", "WMT", "COST", "JPM", "C", "WFC", "GS",
    "XOM", "CVX", "PFE", "MRNA", "ABT", "KWEB", "FXI", "EEM", "EFA", "HYG",
    "UVXY", "VXX", "SQQQ", "TQQQ", "SOXL", "SOXS", "SPXL", "ARKK", "XBI",
    "IBIT", "GME", "AMC", "T", "VZ", "KO", "PEP", "MCD", "SBUX", "V", "MA",
    "HD", "LOW", "TGT", "CVS", "UNH", "LLY", "JNJ", "MRK", "CAT", "DE", "GE",
    "GM", "AAL", "DAL", "UAL", "CCL", "NCLH", "RCL", "PYPL", "SQ", "SHOP",
    "ROKU", "ZM", "DKNG", "ABNB", "LYFT", "RBLX", "U", "NET", "CRWD", "PANW",
    "SNOW", "DDOG", "MDB", "ZS", "OKTA", "TTD", "SPOT", "PINS", "BABA", "JD",
    "PDD", "TSM", "ASML", "LRCX", "AMAT", "KLAC", "ON", "MRVL", "MPWR", "TXN",
    "ADBE", "NOW", "INTU", "IBM", "CSCO", "HPQ", "DELL", "WDC", "STX",
}


def tick_step(px, symbol=None):
    """The legal price increment for this contract at this price."""
    sym = str(symbol or "").upper().split()[0] if symbol else ""
    if sym in PENNY_ALWAYS:
        return 0.01
    if sym in PENNY_PROGRAM:
        return 0.01 if float(px) < 3.0 else 0.05
    return 0.05 if float(px) < 3.0 else 0.10


def tick_round(px, symbol=None):
    """Snap an option price to the exchange's legal increment. Webull rejects a
    limit that isn't on the price step — HTTP 417 OPTION_PRICE_STEP_LT — and the
    rooms post odd-cent premiums all the time (AAOI 170C @ 2.38, QQQ @ 4.66).
    Symbol-aware since 9/2 (see tick_step); without a symbol it falls back to
    the always-legal $0.05/$0.10. A price that rounds to 0 is floored to one
    tick so it's still a real order."""
    try:
        p = float(px)
    except (TypeError, ValueError):
        return px
    if p <= 0:
        return tick_step(0.01, symbol)
    step = tick_step(p, symbol)
    snapped = round(round(p / step) * step, 2)
    return snapped if snapped > 0 else step


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

def _looks_like_futures_code(sym):
    """"MESU6" / "MNQU6" / "ESZ26" yes; "SPY" / "AAPL" no.

    A CME contract code is a root followed by a month letter (FGHJKMNQUVXZ)
    and one or two year digits. Equity tickers never end that way, which is
    what keeps an options row from being adopted as a phantom future."""
    s = str(sym or "").upper()
    if len(s) < 3:
        return False
    t = s
    digits = 0
    while t and t[-1].isdigit():
        t = t[:-1]
        digits += 1
    if digits < 1 or digits > 2 or not t:
        return False
    return t[-1] in "FGHJKMNQUVXZ" and len(t) >= 2


class WebullOptions:
    def __init__(self, cfg):
        w = (cfg.get("execution", {}) or {}).get("webull", {}) or {}
        self.app_key = w.get("app_key", "")
        self.app_secret = w.get("app_secret", "")
        self.account_id = w.get("account_id") or None
        self.account_kind = ""
        # Paper trading routes to Webull's simulated account for HONEST fills
        # instead of our own model. The docs settled it (Aug 2026): paper IS the
        # sandbox host, and Webull's two environments are FULLY ISOLATED — the
        # sandbox needs its OWN app key/secret from a separate (auto-approved,
        # few-minute) sandbox API application. His production keys 401 there not
        # because the host is wrong but because prod creds don't exist in the
        # sandbox at all. Paper mode therefore uses paper_app_key/secret; it
        # falls back to the live keys only so an old config still connects.
        self.paper_app_key = w.get("paper_app_key", "")
        self.paper_app_secret = w.get("paper_app_secret", "")
        # Paper is the DEFAULT test engine: a saved sandbox key turns it on with
        # no toggle. paper_trading can still be forced false by hand.
        _paper_default = bool(self.paper_app_key and self.paper_app_secret)
        self.paper = bool(w.get("paper_trading", _paper_default))
        self.paper_warning = ""     # set on connect when paper can't run yet
        # SANDBOX FULLY RETIRED (8/29, G: "deactivate every single thing that
        # has to do with the sandbox"): paper mode now connects to the LIVE
        # endpoint with the live keys — real quotes, real account list — and
        # the paper flag keeps every order LOCAL (SIM tickets, assumed fills)
        # and the balance read offline. Not one byte goes to the sandbox.
        self.endpoint = LIVE_ENDPOINT
        self.paper_account_id = w.get("paper_account_id") or None
        # Webull labels futures accounts as MARGIN, so the only reliable way to
        # keep off one is to name it. Put the tail of your futures account id
        # here and it will never be picked.
        self.futures_suffixes = [str(s).upper() for s in
                                 w.get("futures_account_suffixes", ["3T0B"])]
        # An explicit futures account id/suffix wins over guessing - the
        # reliable way when Webull labels the futures account as MARGIN.
        self.futures_account_id_cfg = (str(w.get("futures_account_id") or "")
                                       .strip() or None)
        # How far above the price they quoted you're willing to pay. Their fill
        # is not your fill; by the time you see the message the ask has often
        # moved. Past this, it skips rather than chasing.
        # Pay a hair over the ask so a marketable limit actually fills instead
        # of resting while the move happens without you.
        self.buffer_pct = float(w.get("marketable_buffer_pct", 2))
        # Absolute spread cap (his rule, 8/20): an entry whose bid/ask spread
        # is wider than this many PREMIUM dollars ($0.20 = $20 a contract) is
        # refused, however cheap or expensive the contract. Rides alongside
        # the 35%-of-mid relative guard; exits are never blocked by either.
        self.max_spread_dollars = float(w.get("max_spread_dollars", 0.20))
        # Where the entry limit is priced. "bid" sits and waits for a seller to
        # come to you — you never overpay, and you don't always get in. "ask"
        # crosses the spread and fills nearly every time. "mid" splits it.
        # Webull takes no market orders on options at all, so all three of these
        # are limit orders; this only decides the number on it.
        # DEFAULT is "bid" now, his standing rule (8/13): "always buy the bid and
        # sell the ask." Entries rest on the bid and wait for a seller to come
        # down — you never overpay, at the cost of missing a call that runs
        # straight off the message. Settings can still override to ask/mid.
        self.entry_price = str(w.get("entry_price", "bid")).lower()
        # When a call posts NO price and there's no quote either, take it at the
        # market that instant rather than miss it — a marketable buy capped at
        # this ceiling (dollars per contract). The cap is a fat-finger guard,
        # not the price paid; the broker's real fill is read back afterward. Set
        # 0 to go back to refusing a price-less, quote-less entry.
        self.blind_entry_max = float(w.get("blind_entry_max", 15.0))
        # Quotes can be borrowed from ANOTHER client. Webull's options data
        # (OPRA) rides on the LIVE account, not the sandbox — so the paper
        # client asks the live client for the ask/bid (read-only, no orders),
        # then fills on the sandbox. Real prices, pretend money. Left None on a
        # client that quotes for itself.
        self.quote_client = None
        # How long an unfilled entry is allowed to sit there before it's pulled.
        # This is the number that stops a bid from filling at 3:55pm into a
        # trade the room called at 9:40 and closed at 10:05.
        self.fill_seconds = float(w.get("entry_fill_seconds", 180))
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
    def _creds(self):
        """(key, secret) — ALWAYS the live keys since the sandbox retirement
        (8/29). Paper mode is a local behavior flag, not an environment:
        live data in, SIM fills out. The old paper_app_key settings are dead
        config, kept only so old settings.json files still load."""
        return self.app_key, self.app_secret

    def connect(self):
        if not SDK_OK:
            raise Refused("the Webull SDK isn't installed. Open START HERE in "
                          "this folder - it installs what's missing and starts the bridge "
                          "again. (%s)" % SDK_WHY[:120])
        if not self.app_key or not self.app_secret:
            raise Refused("no Webull API key saved yet. Open START HERE, press "
                          "2, and put your app key and secret in.")
        # (The old "paper needs its own sandbox key" warning is gone with the
        # sandbox itself — paper always runs now, on live data + local fills.)
        key, secret = self._creds()
        api = ApiClient(key, secret, REGION)
        api.add_endpoint(REGION, self.endpoint)
        # Full request/response logging, built into the SDK (v3.5.0 A2):
        # this is what answers a 404 or a crash instead of tea leaves in
        # bridge.log. *.log is gitignored.
        # One log file PER PROCESS (9/2): the bridge and the announcer both
        # opening webull_api.log tripped Windows' file lock 11,795 times in
        # a morning and buried the announcer's loop in stack traces.
        try:
            api.set_file_logger(getattr(self, "sdk_log_name", "webull_api.log"))
        except Exception:                               # noqa: BLE001
            pass
        self._api = api
        self.trade = TradeClient(api)
        self._data = DataClient(api)

        # No fallback that flips paper off any more: since the sandbox
        # retirement paper IS the live connection + local fills, so the old
        # "sandbox 401 -> quietly go live" branch would have turned one
        # flaky boot request into REAL orders from testing rooms. A failure
        # here is a failure, loudly, in both modes.
        accounts = _unpack_accounts(self.trade.account_v2.get_account_list())

        def is_futures(a):
            return (_acct_kind(a) == "FUTURES"
                    or any(_acct_id(a).upper().endswith(s)
                           for s in self.futures_suffixes))

        # Paper mode since the sandbox retirement (8/29): the account list is
        # the REAL one (live keys, live endpoint), so pick exactly the way
        # live does — margin for options, named futures kept apart — and let
        # the paper flag keep every order local. Realistic ids, pretend money.
        if self.paper:
            if not accounts:
                raise Refused("connected to Webull but no account came back — "
                              "check the keys and reconnect.")
            _margins = [a for a in accounts if not is_futures(a)
                        and "MARGIN" in _acct_kind(a).upper()]
            chosen = (_margins[0] if _margins
                      else next((a for a in accounts if not is_futures(a)),
                                accounts[0]))
            self.account_id = _acct_id(chosen)
            self.account_kind = "PAPER"
            _fut = next((a for a in accounts if is_futures(a)), None)
            self.futures_account_id = _acct_id(_fut) if _fut else self.account_id
            return self.account_id
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
        # Every account these keys can see - logged below so a missing or
        # mislabeled futures account is visible instead of guessed at.
        self.accounts_seen = [(_acct_id(a), _acct_kind(a)) for a in accounts]
        if self.futures_account_id_cfg:
            fmatch = [a for a in accounts
                      if _acct_id(a) == self.futures_account_id_cfg
                      or _acct_id(a).upper().endswith(
                          self.futures_account_id_cfg.upper())]
            self.futures_account_id = _acct_id(fmatch[0]) if fmatch else None
        else:
            futs = [a for a in accounts if is_futures(a)]
            if not futs:
                # Webull often labels the futures account MARGIN, just like the
                # options one, so a type/suffix match finds nothing. Pick it by
                # elimination: the account that is neither the options account
                # we just chose nor a CASH/IRA one. With one margin (options),
                # one cash and one futures linked, that leaves exactly futures.
                leftover = [a for a in accounts
                            if _acct_id(a) != self.account_id
                            and _acct_kind(a) not in ("CASH", "IRA")]
                futs = leftover if len(leftover) == 1 else []
            self.futures_account_id = _acct_id(futs[0]) if futs else None
        try:
            print("[webull] accounts visible to these keys: " +
                  ("; ".join("%s=%s" % (k, i) for i, k in self.accounts_seen)
                   or "none"))
            print("[webull] FUTURES account -> " +
                  (self.futures_account_id or "NONE DETECTED - set "
                   "execution.webull.futures_account_id to your futures "
                   "account number"))
        except Exception:                               # noqa: BLE001
            pass
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

    def _pace(self):
        """Webull rate-limits bursts — the 8/9 log is wall-to-wall 429
        TOO_MANY_REQUESTS from ten stops placed in one second. A breath of
        spacing between calls on the same connection keeps every one of them
        under the limit. Never retries anything — it only spaces."""
        now = time.time()
        # 0.20 = Webull's documented 300 requests / 60 seconds = 5 per second.
        # The old 0.15 was 6.67/sec — OVER the published limit, which is where
        # the 8/9 wall of 429s came from. Slower here means fewer refusals.
        # (v3.5.0 A1, 9/2)
        wait = 0.20 - (now - getattr(self, "_last_call", 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def ask_bid(self, occ):
        self._pace()
        # Borrow quotes from the live client when this one can't get them (the
        # sandbox has no OPRA entitlement). Read-only — it never places an order
        # through the live connection, only reads the ask/bid.
        if self.quote_client is not None and self.quote_client is not self:
            return self.quote_client.ask_bid(occ)
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

    # -- underlying (stock) quote --------------------------------------------
    # NEW (8/11/26) for the round-number pullback strategy: it needs the price
    # of the UNDERLYING STOCK, which the option path never fetched. Built the
    # same resilient "hunt the SDK by name" way as option quotes. NOT yet
    # verified against the live Webull SDK — MUST be confirmed on-computer
    # (call stock_price("AAPL") and check it returns a real number) before the
    # strategy is trusted to enter.
    # ---- v3.5.0 Block C: batched quotes (one call for the whole book) ----
    def ask_bid_many(self, occs):
        """Quotes for MANY contracts in ONE call. Returns {occ: (ask, bid, row)}.

        Webull's option snapshot endpoint is /market-data/options/snapshots/
        LIST — it takes a list. The single-symbol ask_bid() already probes a
        list shape ([occ]) among its candidates, so the SDK method behind it
        accepts one; this hands it the whole book at once instead.

        Six open positions used to cost six calls per poll. Now they cost one.
        That is the whole reason a 250ms sweep fits inside a 300-per-minute
        limit that a 1-second per-symbol poll would have blown straight past.

        Falls back to looping ask_bid() one at a time if the batched shape is
        refused, so this can never be the reason a stop goes unwatched. The
        working shape is remembered after the first success — the shape hunt
        does not re-run on every sweep.
        """
        occs = [str(o) for o in (occs or []) if o]
        if not occs:
            return {}
        if self.quote_client is not None and self.quote_client is not self:
            return self.quote_client.ask_bid_many(occs)

        # Webull's option snapshot list takes MAX 20 symbols per call
        # (developer.webull.com reference/option-snapshot, checked 9/2).
        if len(occs) > 20:
            out = {}
            for i in range(0, len(occs), 20):
                out.update(self.ask_bid_many(occs[i:i + 20]))
            return out

        fns = self._quote_fns()
        if not fns:
            return {}

        joined = ",".join(occs)
        # 9/2 (from the SDK's own request log): the single-quote call that
        # WORKS sends symbols="<occ>", category="US_OPTION" — a comma-joined
        # STRING plus the category. That exact pair leads the hunt now; the
        # old first guesses (a bare list) were what got refused.
        shapes = [((), {"symbols": joined, "category": "US_OPTION"}),
                  ((joined, "US_OPTION"), {}),
                  ((occs,), {}), ((joined,), {}),
                  ((), {"symbols": occs}), ((), {"symbols": joined}),
                  ((occs, "US_OPTION"), {}),
                  ((), {"symbols": occs, "category": "US_OPTION"})]
        # Remember the shape that worked (the 8/24 lesson: a full shape hunt
        # on every call is a dozen real failing HTTP requests a second).
        remembered = getattr(self, "_batch_shape", None)
        if remembered is not None:
            shapes = [remembered] + [s for s in shapes if s != remembered]

        for _name, fn in fns:
            for shape in shapes:
                args, kwargs = shape
                try:
                    self._pace_batch()
                    body = fn(*args, **kwargs)
                except Exception:                       # noqa: BLE001
                    continue
                parsed = self._parse_batch(body, occs)
                if parsed:
                    self._batch_shape = shape
                    return parsed

        # Batched form unavailable on this SDK — fall back one at a time, and
        # say so ONCE so the log explains why sweeps got expensive.
        if not getattr(self, "_warned_no_batch", False):
            self._warned_no_batch = True
            print("[webull] batched option quotes not available on this SDK - "
                  "falling back to one call per contract. Sweeps will be "
                  "slower and eat more of the rate limit.")
        out = {}
        for occ in occs:
            try:
                out[occ] = self.ask_bid(occ)
            except Exception:                           # noqa: BLE001
                continue
        return out

    def _pace_batch(self):
        """Budget-aware spacing.

        When a Budget is attached (the quote bus supplies one) it is the
        authority. Otherwise fall back to an HONEST 200ms — Webull documents
        300 requests per 60 seconds, which is 5 per second, NOT the 6.67 per
        second the old 150ms spacer was quietly producing. That overshoot is
        where the 8/9 wall of 429s came from.
        """
        b = getattr(self, "budget", None)
        if b is not None:
            b.take(1, priority=False, timeout=5.0)
            return
        now = time.time()
        wait = 0.20 - (now - getattr(self, "_last_call", 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _parse_batch(self, body, occs):
        """Pull {occ: (ask, bid, row)} out of whatever shape came back.

        Each snapshot row names its contract in one of several fields
        depending on endpoint version. A row we cannot match to a REQUESTED
        contract is dropped, never guessed at — a price attached to the wrong
        contract would sell the wrong position.
        """
        rows = body
        if isinstance(body, dict):
            for k in ("data", "result", "list", "snapshots", "items"):
                if isinstance(body.get(k), list):
                    rows = body[k]
                    break
        if not isinstance(rows, list):
            return {}
        want = {o.upper(): o for o in occs}
        out = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = None
            for k in ("symbol", "instrument_id", "instrumentId", "occ",
                      "option_symbol", "optionSymbol", "tickerId", "ticker"):
                v = row.get(k)
                if v is not None and str(v).upper() in want:
                    sym = want[str(v).upper()]
                    break
            if sym is None:
                continue
            ask = _find(row, "ask_price", "askPrice", "ask", "bestAsk",
                        "best_ask")
            bid = _find(row, "bid_price", "bidPrice", "bid", "bestBid",
                        "best_bid")
            try:
                ask = float(ask) if ask not in (None, "") else None
            except (TypeError, ValueError):
                ask = None
            try:
                bid = float(bid) if bid not in (None, "") else None
            except (TypeError, ValueError):
                bid = None
            if ask is None and bid is None:
                continue
            out[sym] = (ask, bid, row)
        return out


    def _stock_fns(self):
        if getattr(self, "_sfns", None) is not None:
            return self._sfns
        found, holders = [], [("data_client", self._data)]
        for attr in dir(self._data):
            if attr.startswith("_"):
                continue
            low = attr.lower()
            if any(w in low for w in ("market", "quote", "stock", "snapshot")):
                try:
                    holders.append((attr, getattr(self._data, attr)))
                except Exception:                       # noqa: BLE001
                    pass
        for hname, h in holders:
            for m in dir(h):
                low = m.lower()
                if m.startswith("_") or "option" in low:
                    continue
                if "quote" in low or "snapshot" in low:
                    fn = getattr(h, m, None)
                    if callable(fn):
                        found.append(("%s.%s" % (hname, m), fn))
        self._sfns = found
        return found

    def stock_price(self, symbol):
        """Current price of the UNDERLYING stock (last, or bid/ask mid).
        Read-only; paper borrows the live client, exactly like option quotes.
        Returns a float, or raises Refused."""
        if self.quote_client is not None and self.quote_client is not self:
            return self.quote_client.stock_price(symbol)
        self._pace()
        sym = str(symbol).upper()
        fns = self._stock_fns()
        if not fns:
            raise Refused("couldn't find Webull's stock-quote method in the SDK.")
        errors = []
        shapes = [((sym,), {}), (([sym],), {}), ((sym, "US_STOCK"), {}),
                  (([sym], "US_STOCK"), {}), ((), {"symbols": sym}),
                  ((), {"symbols": [sym]}),
                  ((), {"symbols": [sym], "category": "US_STOCK"})]
        # 8/24: remember the combo that worked. The hunt used to run in FULL
        # on every call — each wrong shape a real HTTP request that 417'd and
        # logged an error. A 1s pullback poll turned that into ~13 failing
        # requests a second (9,690 errors in 12 min) and chewed rate limit.
        _w = getattr(self, "_stock_quote_winner", None)
        if _w is not None:
            _wname, _wsi = _w
            _wfn = dict(fns).get(_wname)
            if _wfn is not None and _wsi < len(shapes):
                _pairs = [(_wname, _wfn, shapes[_wsi])]
            else:
                _pairs = None
        else:
            _pairs = None
        hunt = _pairs or [(n, f, sh) for n, f in fns
                          for sh in shapes]
        for _hi, (name, fn, (args, kw)) in enumerate(hunt):
            if True:
                try:
                    res = fn(*args, **kw)
                except TypeError:
                    continue
                except Exception as e:                  # noqa: BLE001
                    errors.append("%s: %s" % (name, str(e)[:100]))
                    continue
                if getattr(res, "status_code", 200) != 200:
                    errors.append("%s: HTTP %s" % (name, getattr(res, "status_code", "?")))
                    continue
                body = res.json() if hasattr(res, "json") else res
                row = body[0] if isinstance(body, list) and body else body
                px = _find(row, "close", "last", "lastPrice", "price", "deal",
                           "pPrice", "close_price", "last_price")
                if px in (None, "", 0, "0", 0.0):
                    a = _find(row, "ask", "askPrice", "ask_price")
                    b = _find(row, "bid", "bidPrice", "bid_price")
                    try:
                        px = (float(a) + float(b)) / 2 if (a and b) else None
                    except (TypeError, ValueError):
                        px = None
                try:
                    if px not in (None, "", 0, "0", 0.0):
                        self._stock_quote_winner = (name, shapes.index((args, kw)))
                        return float(px)
                except (TypeError, ValueError):
                    continue
        if _pairs:
            # the remembered winner went stale — forget it and hunt fresh once
            self._stock_quote_winner = None
            return self.stock_price(symbol)
        raise Refused("couldn't get a stock quote for %s. (%s)"
                      % (sym, " | ".join(errors[:3])[:120]))

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
        return self._balance_for(self.account_id, "_bal")

    def futures_buying_power(self):
        """Same read for the FUTURES account, or None if Webull won't say or
        there's no futures account. Never blocks a trade — it's a readout."""
        acct = getattr(self, "futures_account_id", None)
        if not acct:
            return None
        return self._balance_for(acct, "_fbal")

    def _balance_for(self, account_id, cache_key):
        """Buying power for one account id, cached ~8s per account. Factored out
        so the margin and futures accounts can each be read without stepping on
        the other's cache."""
        if getattr(self, "paper", False):
            # PAPER IS LOCAL (8/29): the sandbox serves no /account/balance
            # (404 Route Not Found — 211 of them in one quiet Saturday's log)
            # and paper money is unlimited by design. Never ask the network;
            # None reads as "don't block the trade", which is exactly right.
            return None
        now = time.time()
        at = getattr(self, cache_key + "_at", 0)
        # 8s cache on a good read; FIVE MINUTES on a failed one (8/24). The
        # sandbox account answers /account/balance with errors for every
        # method the hunt tries, so a fresh hunt every 8s was hundreds of
        # failing requests an hour chewing the rate limit for a number that
        # is never coming.
        _ttl = getattr(self, cache_key + "_ttl", 8)
        if at and now - at < _ttl:
            return getattr(self, cache_key, None)
        val = None
        for _name, fn in self._balance_fns():
            for args in ((account_id,), (), (account_id, "USD")):
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
        setattr(self, cache_key, val)
        setattr(self, cache_key + "_at", now)
        setattr(self, cache_key + "_ttl", 8 if val is not None else 300)
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
        # Snap every price to a legal exchange tick right before it goes out —
        # the single choke point every order passes through, so no odd-cent
        # premium (2.38, 4.66) can ever reach Webull and 417 on the price step.
        limit = tick_round(limit)
        leg = {"side": side, "quantity": str(qty), "symbol": symbol,
               "strike_price": "%.2f" % float(strike),
               "option_expire_date": expiration, "instrument_type": "OPTION",
               "option_type": option_type, "market": "US"}
        _cid = uuid.uuid4().hex[:32]
        o = {"client_order_id": _cid, "combo_type": "NORMAL",
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
            o["stop_price"] = "%.2f" % float(tick_round(stop))
            o["time_in_force"] = "GTC"
        return [o]

    def _send_combo(self, orders, combo_id, what):
        """Send a linked order group (MASTER entry + its stop leg) in ONE
        request — his ask, 8/19: 'group orders... limit with take profit /
        stoploss... instead of having the watchdog go crazy'. The SDK's
        place_order has grown parameters across versions, so the known
        signatures are tried in turn; when none fits, _ComboUnsupported tells
        the caller to fall back to the plain two-step (entry now, stop after
        the fill) — a combo the broker can't take must never cost an entry."""
        # PAPER IS LOCAL NOW (8/28): the Webull sandbox has no options
        # entitlement — every options order sent there died with
        # OPTION_STRATEGY_NOT_MATCH_ANY (all 12 of 8/28's "rejections" were
        # sandbox, not his real account). A testing room's order is
        # simulated here instead: real quotes (they already ride the LIVE
        # feed), assumed fills, zero API calls, zero rejection noise.
        if getattr(self, "paper", False):
            import uuid as _uuid
            return {"order_id": "SIM-" + _uuid.uuid4().hex[:12],
                    "client_order_id": combo_id, "simulated": True}
        holder = getattr(self.trade, "order_v3", None) \
            or getattr(self.trade, "order", None)
        fn = getattr(holder, "place_order", None) if holder else None
        if fn is None:
            raise _ComboUnsupported("this SDK build has no place_order")
        attempts = (
            lambda: fn(self.account_id, orders, combo_id),
            lambda: fn(self.account_id, orders,
                       client_combo_order_id=combo_id),
        )
        last = None
        for a in attempts:
            try:
                res = a()
            except TypeError as e:
                last = e
                continue
            except Exception as e:                      # noqa: BLE001
                # Newer SDK builds RAISE on an HTTP error instead of returning
                # a response — the raw exception escaping here is exactly how
                # 'invalid order_type' killed five entries on 8/21 with the
                # fallback never engaging. Wrap it so the caller's retry and
                # fall-back logic actually get to run.
                raise Refused(str(e)[:220])
            try:
                body = res.json()
            except Exception:                           # noqa: BLE001
                body = {}
            code = getattr(res, "status_code", "?")
            if code != 200:
                blob = str(body)
                up = blob.upper()
                if "COMBO" in up or "NOT_SUPPORT" in up or "NOT SUPPORT" in up:
                    raise _ComboUnsupported(blob[:160])
                raise Refused("Webull rejected %s (HTTP %s): %s"
                              % (what, code, blob[:180]))
            return body if isinstance(body, (dict, list)) else {}
        raise _ComboUnsupported(
            "place_order accepted no combo signature (%s)" % str(last)[:80])

    def _send(self, orders, what):
        # PAPER IS LOCAL (8/28) — see _send_combo. No sandbox, no 417s.
        if getattr(self, "paper", False):
            import uuid as _uuid
            return {"order_id": "SIM-" + _uuid.uuid4().hex[:12],
                    "simulated": True}
        res = self.trade.order_v3.place_order(self.account_id, orders)
        try:
            body = res.json()
        except Exception:                               # noqa: BLE001
            body = {}
        code = getattr(res, "status_code", "?")
        if code != 200:
            blob = str(body)
            # Webull's account-eligibility rejections read like machine codes.
            # Translate the common one into what to actually DO, since no retry
            # or code change can place an order the account isn't approved for.
            if ("OPTION_STRATEGY_NOT_MATCH_ANY" in blob
                    or "not eligible to trade options" in blob.lower()):
                raise Refused(
                    "Webull won't let this account trade options yet — the order "
                    "was read and priced correctly, but your Webull account isn't "
                    "approved for options trading. Open the Webull app -> your "
                    "account -> apply for/enable OPTIONS trading (you need the "
                    "level that allows buying calls & puts), then retry. Nothing "
                    "was sent. (%s)" % blob[:120])
            # Cash-index options (SPX/NDX/RUT/VIX/XSP) aren't tradeable on Webull
            # the standard way — the room posts them but Webull returns a param
            # error every time. Say so plainly instead of a raw machine code.
            if ("PARAM_ERR" in blob or "invalid market" in blob.lower()) \
                    and "OPTION" in blob:
                raise Refused(
                    "that's a cash-index option (SPX/NDX/RUT-style) — Webull "
                    "doesn't offer those to trade the normal way, so it can't be "
                    "placed. Nothing was sent; skip that room's index calls.")
            raise Refused("Webull rejected %s (HTTP %s): %s"
                          % (what, code, blob[:180]))
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
        # No id, no answer. An entry that never got placed (futures rejected on
        # funds, 8/21 MNQ) reaches here with order_id None -- and the "query"
        # endpoint ignores a None id and hands back the account's RECENT ORDER
        # LIST, whose row 0 is somebody else's trade. That is how a phantom
        # MNQ "filled 3.0 at 1.41" was really the SPY x3 adopted four minutes
        # earlier, which then armed a stop and sent a CLOSE for the wrong size.
        # Unknown is the honest answer and is never read as a fill upstream.
        if not order_id:
            return "unknown", 0, None
        if str(order_id).startswith("SIM-"):
            # a local paper order — filled at its stated price by definition
            return "filled", None, None
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

    def last_sell_fill(self, symbol, side, strike, expiry, since=None):
        """What this contract ACTUALLY last sold for at Webull, or None.

        Built 8/27 for the phantom-exit bug. When a position disappears from
        the account the bot has no order_id to ask about — it never placed the
        sell. Something else did: a resting bracket stop, a GTC stop from an
        earlier session, or him tapping Close on his phone. The book used to
        fill that hole with the last quoted BID, which is how a QQQ that made
        $8 got written down as +$290 and a TSLA that lost $45 got written down
        as +$70.

        So: ask the broker. Order HISTORY (not open orders, not order_status —
        both need an id we don't have) knows every fill on the account. Find
        the newest FILLED sell leg on this exact contract and hand back its
        price. Never raises; None means "still don't know", and the caller is
        expected to stay silent rather than guess.

        `since` is an epoch seconds floor — pass the position's open time so an
        older round trip on the same strike can't be mistaken for this exit.
        """
        want = str(symbol or "").upper()
        if not want:
            return None
        # A day either side: Webull rejects single-day ranges, and a stop that
        # was placed yesterday but filled today has to fall inside the window.
        import datetime as _dt
        today = _dt.date.today()
        start = (today - _dt.timedelta(days=1)).isoformat()
        end = (today + _dt.timedelta(days=1)).isoformat()
        # 8/28: the dates MUST go in by keyword. Passed positionally they land
        # in the SDK's (account_id, page_size, last_client_order_id, ...) slots
        # instead — Webull answered every one of those with HTTP 500
        # INTERNAL_ERROR, and the only reason this function still worked was
        # the bare (account_id,) fallback below, which returns TODAY's orders
        # only. That silently reopened the hole this whole function exists to
        # close: an exit that filled today off a stop resting since yesterday
        # falls outside "today" and comes back None.
        body = None
        for args, kw in (((self.account_id,), {"start_date": start,
                                               "end_date": end}),
                         ((self.account_id, start, end), {}),
                         ((self.account_id,), {})):
            body, _why = self._try_calls(
                ["order_v3", "order", "trade", "account_v2"],
                ["history", "list_orders", "orders", "query_orders"],
                *args, **kw)
            if body is not None:
                break
        if body is None:
            return None
        items = body if isinstance(body, list) else \
            ((body or {}).get("orders") or (body or {}).get("data") or [])

        def _num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        want_c = str(side or "").upper().startswith("C")
        want_k = _num(strike)
        want_x = str(expiry or "")[:10]
        best_t, best_px = None, None
        for grp in (items or []):
            # order history nests: {orders:[{legs:[...], filled_price, ...}]}
            for o in (grp.get("orders") if isinstance(grp, dict)
                      and isinstance(grp.get("orders"), list) else [grp]):
                if not isinstance(o, dict):
                    continue
                try:
                    st = str(_find(o, "status", "order_status") or "").upper()
                    if "FILL" not in st or "PART" in st:
                        continue
                    if str(_find(o, "side", "action") or "").upper() != "SELL":
                        continue
                    legs = o.get("legs") or [o]
                    leg = legs[0] if legs else {}
                    if str(leg.get("symbol") or o.get("symbol")
                           or "").upper() != want:
                        continue
                    ot = str(leg.get("option_type")
                             or o.get("option_type") or "").upper()
                    if ot and bool(ot.startswith("C")) != want_c:
                        continue
                    k = _num(leg.get("option_exercise_price")
                             or leg.get("strike_price") or leg.get("strike"))
                    if want_k is not None and k is not None \
                            and abs(k - want_k) > 0.001:
                        continue
                    x = str(leg.get("option_expire_date")
                            or o.get("option_expire_date") or "")[:10]
                    if want_x and x and x != want_x:
                        continue
                    px = _num(_find(o, "filled_price", "avg_fill_price",
                                    "avgFillPrice", "average_price"))
                    if px is None or px <= 0:
                        continue
                    t = _num(_find(o, "filled_time", "filledTime")) or 0
                    if t > 1e12:            # Webull hands these back in ms
                        t /= 1000.0
                    if since and t and t < float(since) - 5:
                        continue
                    if best_t is None or t >= best_t:
                        best_t, best_px = t, px
                except Exception:                          # noqa: BLE001
                    continue
        return best_px

    def open_orders(self, symbol=None):
        """Every order still WORKING at Webull, normalised to
        [{order_id, symbol, strike, side, action, qty}].

        This is the gap that cost him all day on 8/12: the bot can only cancel
        an order it has the id of, so an orphan left by an earlier session (or
        by a place_stop that half-succeeded) sat on the contract and refused
        every sell and every new stop after it — 233 rejections, a +32% SPCX
        winner that would not close. Same probe-and-refuse-quietly style as the
        rest of this file: unknown endpoint names, so try the plausible ones and
        return [] rather than raise."""
        # The endpoint is real (/openapi/trade/order/open) — the trap is WHICH
        # account id goes with it. On 8/12 the SDK's own default id came back
        # 403 ACCOUNT_ACCESS_DENIED 716 times in one minute, so the orphan
        # sweep silently found nothing. Try this client's account first, then
        # every account these keys actually proved they can see.
        tries = []
        if self.account_id:
            tries.append(self.account_id)
        for _acct, _kind in (getattr(self, "accounts_seen", None) or []):
            if _acct and _acct not in tries:
                tries.append(_acct)
        verbsets = ((["order_v3", "order"],
                     ["list_open_orders", "open_orders", "list_orders",
                      "orders", "query_open"]),
                    (["trade", "account_v2"],
                     ["list_open_orders", "open_orders", "list_orders"]))
        body = None
        for acct in (tries or [None]):
            for holders, verbs in verbsets:
                body, _why = self._try_calls(holders, verbs, acct) if acct \
                    else self._try_calls(holders, verbs)
                if body is not None:
                    break
            if body is not None:
                break
        if body is None:
            return []
        items = body if isinstance(body, list) else \
            ((body or {}).get("orders") or (body or {}).get("data") or [])
        want = str(symbol or "").upper()
        out = []
        for it in (items or []):
            try:
                legs = it.get("legs") or [it]
                leg = legs[0] if legs else {}
                sym = str(it.get("symbol") or leg.get("symbol") or "").upper()
                if want and sym != want:
                    continue
                st = str(_find(it, "status", "order_status", "orderStatus")
                         or "").upper()
                # Only things that can still block a new order.
                if st and not any(k in st for k in
                                  ("WORK", "PEND", "OPEN", "SUBMIT", "PART",
                                   "QUEUE", "ACCEPT")):
                    continue
                oid = (_find(it, "order_id", "orderId", "client_order_id")
                       or _find(leg, "order_id", "orderId"))
                if not oid:
                    continue
                out.append({
                    "order_id": oid, "symbol": sym,
                    "strike": (leg.get("option_exercise_price")
                               or leg.get("strike")
                               or it.get("option_exercise_price")),
                    "side": leg.get("option_type") or it.get("option_type"),
                    "action": str(it.get("side") or leg.get("side") or "").upper(),
                    "qty": leg.get("quantity") or it.get("quantity")})
            except Exception:                              # noqa: BLE001
                continue
        return out

    def cancel(self, order_id):
        """True if Webull took the cancel. False is not a crisis on its own —
        it usually means the order already filled or was already gone."""
        if str(order_id or "").startswith("SIM-") or getattr(self, "paper", False):
            return True
        body, _why = self._try_calls(["order_v3", "order"], ["cancel"],
                                     self.account_id, order_id)
        if body is None:
            body, _why = self._try_calls(["order_v3", "order"], ["cancel"], order_id)
        return body is not None

    def positions(self):
        self._pace()
        """The account's REAL open positions, straight from Webull, normalised to
        the shape the popup and book use — so the popup can mirror the broker
        instead of only what the bot itself placed. Never raises: on any trouble
        it returns an empty list and the caller keeps its own view."""
        body, _why = self._try_calls(
            ["position_v2", "position", "account_v2", "trade"],
            ["position"], self.account_id)
        if body is None:
            body, _why = self._try_calls(
                ["position_v2", "position", "account_v2", "trade"], ["position"])
        items = body if isinstance(body, list) else \
            ((body or {}).get("positions") or (body or {}).get("data") or [])
        rows = []
        for it in (items or []):
            try:
                legs = it.get("legs") or [it]
                leg = legs[0] if legs else {}
                sym = str(it.get("symbol") or leg.get("symbol") or "").upper()
                if not sym:
                    continue
                qty = int(float(it.get("quantity") or leg.get("quantity") or 0))
                if qty == 0:
                    continue
                otype = str(leg.get("option_type") or it.get("option_type") or "").upper()
                strike = (leg.get("option_exercise_price") or leg.get("strike")
                          or it.get("option_exercise_price"))
                expiry = leg.get("option_expire_date") or it.get("option_expire_date")
                is_opt = bool(otype) or bool(strike)
                fill = float(it.get("cost_price") or leg.get("cost") or 0) or None
                last = float(it.get("last_price") or leg.get("last_price") or 0) or None
                pl = it.get("unrealized_profit_loss")
                plr = it.get("unrealized_profit_loss_rate")
                rows.append({
                    "symbol": sym,
                    "side": (("CALLS" if otype.startswith("C") else "PUTS")
                             if is_opt else None),
                    "strike": float(strike) if strike else None,
                    "expiry": expiry, "qty": qty, "fill": fill, "last": last,
                    "pl": float(pl) if pl not in (None, "") else None,
                    "pl_pct": (float(plr) * 100) if plr not in (None, "") else None,
                    "kind": "option" if is_opt else "stock"})
            except Exception:                              # noqa: BLE001
                continue
        return rows

    def futures_positions(self):
        """Open positions in the FUTURES account.

        Futures live in a DIFFERENT Webull account from options/margin, and
        positions() only ever asked about self.account_id — which is why his
        futures trades were invisible in the popup on 8/12: no display, no
        watchdog, no bracket. Same probe style as positions(); never raises.

        Shape differences that matter downstream: no strike, no expiry, no
        option type, quantity can be NEGATIVE for a short, and the money is
        points x multiplier rather than premium x 100. Rows come back tagged
        kind="future" so the book and the popup can tell them apart."""
        acct = getattr(self, "futures_account_id", None)
        if not acct:
            return []
        self._pace()
        body, _why = self._try_calls(
            ["position_v2", "position", "account_v2", "trade"],
            ["position"], acct)
        if body is None:
            return []
        items = body if isinstance(body, list) else \
            ((body or {}).get("positions") or (body or {}).get("data") or [])
        rows = []
        for it in (items or []):
            try:
                legs = it.get("legs") or [it]
                leg = legs[0] if legs else {}
                sym = str(it.get("symbol") or leg.get("symbol") or "").upper()
                if not sym:
                    continue
                # PROVE it's a future before calling it one. Passing the futures
                # account id doesn't always take — the SDK can answer with the
                # OPTIONS account instead, and on 8/12 that relabelled a SPY
                # option (premium 1.06) as a futures contract with no strike:
                # an un-clearable ghost, because the reconciler skips futures.
                # An option row carries a strike/type/expiry; a futures contract
                # code is a root plus a month letter and year ("MESU6").
                if (leg.get("option_type") or it.get("option_type")
                        or leg.get("strike") or leg.get("option_exercise_price")
                        or it.get("option_exercise_price")
                        or leg.get("option_expire_date")
                        or it.get("option_expire_date")):
                    continue
                itype = str(it.get("instrument_type") or it.get("asset_type")
                            or leg.get("instrument_type") or "").upper()
                if "FUTURE" not in itype and not _looks_like_futures_code(sym):
                    continue
                raw_q = (it.get("quantity") or leg.get("quantity") or
                         it.get("position") or 0)
                qty = int(float(raw_q))
                if qty == 0:
                    continue
                # A short can arrive as a negative quantity OR as a side field.
                side_txt = str(it.get("side") or it.get("direction") or
                               leg.get("side") or "").upper()
                direction = -1 if (qty < 0 or side_txt.startswith("S")) else 1
                fill = float(it.get("cost_price") or leg.get("cost")
                             or it.get("avg_price") or 0) or None
                last = float(it.get("last_price") or leg.get("last_price") or 0) or None
                pl = it.get("unrealized_profit_loss")
                plr = it.get("unrealized_profit_loss_rate")
                rows.append({
                    "symbol": sym, "side": None, "strike": None, "expiry": None,
                    "qty": abs(qty), "direction": direction,
                    "fill": fill, "last": last,
                    "pl": float(pl) if pl not in (None, "") else None,
                    "pl_pct": (float(plr) * 100) if plr not in (None, "") else None,
                    "kind": "future"})
            except Exception:                              # noqa: BLE001
                continue
        return rows

    def flatten(self, symbol):
        """Sell whatever the account is holding of `symbol`, right now — the
        popup's one-click close of a REAL Webull position, including one the book
        lost track of on a restart. Reads the live position for its exact
        contract, then exits it at the market. Returns a short message."""
        symbol = str(symbol or "").upper()
        for p in self.positions():
            if str(p.get("symbol") or "").upper() != symbol:
                continue
            qty = int(p.get("qty") or 0)
            if qty <= 0:
                continue
            if p.get("kind") == "future":
                raise Refused("that's a futures position — close it in NinjaTrader "
                              "or the broker; the Webull close path is options only")
            self.sell(symbol, p.get("side") or "CALLS", p.get("strike"),
                      p.get("expiry"), qty, ref_price=p.get("last"))
            return "closed %s x%d at Webull" % (symbol, qty)
        return "no open %s position at Webull to close" % symbol

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price,
                    stop_price=None):
        self._pace()
        """The resting stop, sent right after an entry fills — or replaced at
        a new price by the ratchet as a winning trade climbs.

        Priced off what you actually paid, not off what the room said they paid.
        `stop_price` overrides the normal fill*(1-stop_pct/100) calculation
        with an exact dollar price — used by the ratchet to move the stop to a
        LOCKED-IN-PROFIT level as a position climbs; every other caller leaves
        this None and gets the plain percentage-off-fill stop, unchanged.
        Returns (order_id, stop_price). Raises Refused if Webull won't take it —
        the caller keeps trading and leans on the watchdog, because a missing
        resting stop is a reason to warn you, not a reason to be in a position
        with nothing watching it at all.
        """
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        if stop_price is not None:
            stop = max(0.01, round(float(stop_price), 2))
        else:
            stop = stop_below(fill_price, self.stop_pct, symbol)
        # Webull validates a SELL stop against the LIVE market, not your fill.
        # On a wide options spread the bid right after you buy at the ask is
        # often already below a fill-based stop, so Webull 417s it
        # (STOP_PRICE_MUST_BE_LESS_THAN_MARKET_PRICE) and you are left with only
        # the PC watchdog. Clamp the stop to sit one tick under the live market
        # so the broker holds a REAL resting stop that survives the PC going
        # down. This only ever TIGHTENS the stop; it never loosens the intended
        # one, and with no quote it behaves exactly as before.
        occ = occ_symbol(symbol, expiration, option_type, strike)
        mkt = None
        try:
            ask_q, bid_q, _ = self.ask_bid(occ)
            mkt = bid_q if (bid_q and float(bid_q) > 0) else (
                  ask_q if (ask_q and float(ask_q) > 0) else None)
        except Exception:                               # noqa: BLE001
            mkt = None
        stop_clamped = False
        if mkt and float(mkt) > 0:
            step = tick_step(float(mkt), symbol)
            ceiling = round(float(mkt) - step, 2)
            if ceiling < 0.01:
                ceiling = 0.01
            # BREACHED vs ARTIFACT (9/1, the S-swing lesson): a market a
            # hair under the intended stop right after a wide-spread entry
            # is an artifact — clamp and carry on. A market DEEP below the
            # intended stop means the stop condition has ALREADY happened
            # (S opened at ~0.45 bid vs a 0.75 intended stop; the clamp
            # re-anchored to 0.40 and rode it down to a -59% fill). More
            # than 10% below intended = breached: refuse to rest a lower
            # stop so the caller's watchdog SELLS instead of re-anchoring.
            if float(mkt) <= stop * 0.90:
                raise Refused(
                    "the market (%.2f) is already well below the intended "
                    "stop (%.2f) — that stop is BREACHED, not clamp-able. "
                    "No lower stop was rested; the watchdog should sell."
                    % (float(mkt), stop))
            if stop >= ceiling:
                stop = max(0.01, float(tick_round(ceiling)))
                stop_clamped = True
        # The price that actually RESTS at Webull is the tick-rounded one —
        # _order() snaps stop_price to the exchange step on the way out. Round
        # here too, so the value returned (then logged, journaled, and used by
        # the watchdog) is the broker's number and not a phantom penny off it.
        # 8/25 SLV: the log said 2.46 while the resting order was 2.45.
        stop = max(0.01, float(tick_round(stop, symbol)))
        what = "STOP %d %s %g%s %s @ %.2f%s" % (qty, symbol, float(strike),
                                                option_type[0], expiration, stop,
                                                " (clamped under market)" if stop_clamped else "")
        # The limit sits under the trigger so a fast drop still clears.
        limit = max(0.01, round(stop * 0.90, 2))
        _orders = self._order(symbol, expiration, option_type, strike,
                                      "SELL", qty, limit, stop=stop)
        body = self._send(_orders, what)
        # Cancel looks an order up by the CLIENT id we generated —
        # the SDK puts whatever it is handed into client_order_id.
        # Returning Webull's own order_id here meant every cancel
        # came back ORDER_NOT_FOUND, so the resting stop never died
        # and then blocked every sell on that contract (8/12, all
        # day: META, QQQ, NVDA, SPCX...). Prefer ours; fall back to
        # whatever the response carries.
        oid = ((_orders[0] or {}).get("client_order_id")
               if _orders else None) or _find(
            body, "client_order_id", "clientOrderId", "order_id", "orderId")
        return (str(oid) if oid else None), stop

    def replace_stop(self, old_oid, symbol, side, strike, expiry, qty,
                     fill_price, stop_price):
        """v3.5.0 B4: move a resting stop IN PLACE — one call, no naked
        moment. The ratchet used to cancel the old stop and then place the
        new one; a failed placement between those two lines left the
        position with no broker-side stop while the log claimed otherwise.
        Sends the same order body as place_stop through the SDK's replace
        verb with the EXISTING client_order_id. Raises if the SDK has no
        replace verb or refuses — the caller then falls back to the old
        cancel-then-place path, so a bad replace can never cost a stop."""
        if getattr(self, "paper", False):
            return str(old_oid), max(0.01, round(float(stop_price), 2))
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        stop = max(0.01, float(tick_round(float(stop_price), symbol)))
        limit = max(0.01, round(stop * 0.90, 2))
        _orders = self._order(symbol, expiration, option_type, strike,
                              "SELL", qty, limit, stop=stop)
        for o in _orders:
            o["client_order_id"] = str(old_oid)
        self._pace()
        body, why = self._try_calls(["order_v3", "order"],
                                    ["replace_option", "replace_order",
                                     "replace"],
                                    self.account_id, _orders)
        if body is None:
            raise Refused("replace not available (%s)" % str(why)[:80])
        blob = str(body)
        if "error" in blob.lower() and "code" in blob.lower():
            raise Refused("replace refused: %s" % blob[:120])
        return str(old_oid), stop

    def buy(self, symbol, side, strike, expiry, qty, their_price=None,
            price_mode=None, bracket_stop_pct=None):
        """side is CALLS or PUTS, the way the room writes it.

        price_mode overrides the global entry_price for THIS order only.
        The one user today is the round-number pullback (8/17): its entries
        cross the ask (marketable — Webull takes no true market orders on
        options), because the discount was already earned waiting for the
        touch. None = the normal setting (bid) applies.

        bracket_stop_pct (his ask, 8/19): send the entry as a LINKED GROUP —
        MASTER limit buy + a stop-loss leg born WITH it, held broker-side.
        There is no naked moment between the fill and the stop, and when the
        stop fills the group is done (no orphan orders to 417 a later sell).
        If the broker/SDK won't take the group, this falls back to the plain
        single order and the book arms the stop after the fill, as before."""
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        occ = occ_symbol(symbol, expiration, option_type, strike)
        ask = bid = None
        try:
            ask, bid, _ = self.ask_bid(occ)
        except Refused:
            # No live quote — most often the OpenAPI options-data (OPRA)
            # subscription isn't active on the keys. We do NOT refuse for lack of
            # a quote: fall back to the posted price, or — his call — take it at
            # the market that instant. See the blind-entry branch below.
            pass

        # The chase limit that used to sit here is DELETED, on his word:
        # "no filters wanted. id like to follow everything to the tee as they
        # do." If the room is in it, he's in it, whatever the ask has done
        # since. Entries are marketable (priced at the ask) so they fill the
        # moment they go out instead of resting on the bid.

        # SPREAD GUARD (8/18, the VXX lesson): bid 0.17 / ask ~1.50 on an
        # illiquid strike — a resting bid there only fills when the price is
        # collapsing through it, and the moment it fills you're marked -30%
        # against the bid. A market that wide isn't a price, it's a trap:
        # refuse the ENTRY loudly. Exits are never touched by this — getting
        # out is allowed at any spread.
        if ask and bid and float(ask) > 0 and float(bid) > 0:
            _a, _b = float(ask), float(bid)
            _mid = (_a + _b) / 2.0
            # 20% ceiling (8/22, was 35%): past ~20% of the price you're
            # donating, not trading — the pros' consensus and his call.
            if _mid > 0 and (_a - _b) / _mid > 0.20:
                raise Refused(
                    "the spread on %s is %.2f/%.2f — %.0f%% of the price (20%% cap). A "
                    "fill inside that is an instant paper loss, so nothing "
                    "was sent. (Their call may be fine; this contract just "
                    "isn't tradeable at a sane price right now.)"
                    % (occ, _b, _a, 100.0 * (_a - _b) / _mid))
            # HIS absolute cap (8/20), widened 8/21 after it collided with the
            # NO-OTM rule: ITM contracts on expensive names carry wide DOLLAR
            # spreads even when they're normal in percent (MSFT 480C at
            # 6.40/7.05 is ~9% but $65) — the flat $20 cap was refusing every
            # translated entry. The cap is now $20 OR 10% of the mid,
            # whichever is LARGER: cheap contracts stay strictly protected, a
            # $7 contract may spread to ~70 cents (MSFT-class ITM territory),
            # and true garbage still dies on the 35% guard above.
            if self.max_spread_dollars:
                _cap = max(self.max_spread_dollars, 0.10 * _mid)
                if (_a - _b) > _cap + 1e-9:
                    raise Refused(
                        "the spread on %s is %.2f/%.2f — $%.0f a contract to "
                        "cross it, over your cap ($%.0f for a contract this "
                        "price). Nothing was sent."
                        % (occ, _b, _a, 100.0 * (_a - _b), 100.0 * _cap))
        blind = False
        if ask and ask > 0:
            if price_mode == "ask":
                # Pullback entry at the touch: marketable at the ask, no
                # their-price cap — capping would turn it back into a resting
                # bid, which is exactly what waiting for the level was meant
                # to end. The buffer makes it fill through a moving quote.
                limit = max(0.01, round(
                    float(ask) * (1 + self.buffer_pct / 100) + 0.01, 2))
            else:
                limit = self.entry_limit(bid, ask)
                # "Match their avg or better" (his ask, 8/13): never pay above
                # the price the caller posted. entry_limit already rests at the
                # bid, so this only bites when the bid has run ABOVE their avg —
                # then we cap at their avg and wait for it to come to us. A
                # resting entry, not a chase: it may not fill if price keeps
                # running, the trade-off he chose over overpaying.
                if their_price:
                    try:
                        limit = min(limit, float(their_price))
                    except (TypeError, ValueError):
                        pass
                limit = max(0.01, round(limit, 2))
        elif their_price:
            # No live ask: take the room's posted premium as the limit.
            limit = max(0.01, round(float(their_price), 2))
        elif self.blind_entry_max and self.blind_entry_max > 0:
            # No quote AND no posted price — "make the entry instant, a bid at
            # that moment." Place a marketable BUY at a bounded ceiling: a limit
            # ABOVE the market fills at the current ask right now, so this takes
            # the trade immediately instead of missing it. The ceiling only
            # stops a fat-finger contract from costing a fortune; the watchdog
            # reads the broker's ACTUAL fill afterward, so the price on record
            # is what the market gave, not the ceiling.
            limit = float(self.blind_entry_max)
            blind = True
        else:
            raise Refused("no live ask on %s and no posted price to fall back "
                          "on. Nothing was sent." % occ)
        # Checked here rather than earlier because this is the first point the
        # real price is known — their quoted 2.80 and the live ask are not the
        # same number, and it's the live one you'd be paying.
        self.afford_check(limit, qty)
        if blind:
            what = "BUY %d %s %g%s %s @ market (take it now, ≤%.2f)" % (
                qty, symbol, float(strike), option_type[0], expiration, limit)
        else:
            what = "BUY %d %s %g%s %s @ %.2f" % (qty, symbol, float(strike),
                                                 option_type[0], expiration, limit)
        # ---- linked entry+stop group (his ask, 8/19) ----
        stop_child = stop_born = None
        _orders = None
        if bracket_stop_pct and not blind:
            try:
                # Tick-rounded HERE, not just inside _order(): what gets
                # recorded as bracket_stop must be the price actually resting,
                # or the book carries a stop that doesn't exist (8/25 SLV: the
                # log said "stop 2.51 born with it", the resting leg was 2.50).
                stop_born = stop_below(limit, bracket_stop_pct, symbol)
                slim = max(0.01, round(stop_born * 0.90, 2))

                def _combo_try(child_type):
                    """Fresh ids every attempt — a rejected group may still
                    have consumed its client ids at the broker."""
                    m = self._order(symbol, expiration, option_type, strike,
                                    "BUY", qty, limit)[0]
                    m["combo_type"] = "MASTER"
                    c = self._order(symbol, expiration, option_type, strike,
                                    "SELL", qty, slim, stop=stop_born)[0]
                    c["combo_type"] = "STOP_LOSS"
                    c["time_in_force"] = "DAY"  # option SELL legs are DAY-only
                    if child_type == "STOP_LOSS":
                        # plain stop (market on trigger) — Webull refused the
                        # stop-LIMIT flavor inside a group on 8/20 ("invalid
                        # order_type, value: STOP_LOSS_LIMIT", 4 entries lost)
                        c["order_type"] = "STOP_LOSS"
                        c.pop("limit_price", None)
                    _b = self._send_combo([m, c], uuid.uuid4().hex[:32],
                                          what + " +stop %.2f (one group)"
                                          % stop_born)
                    return m, c, _b
                try:
                    master, child, body = _combo_try("STOP_LOSS_LIMIT")
                except Refused as _rf:
                    up = str(_rf).upper()
                    if "ORDER_TYPE" in up or "STOP_LOSS" in up:
                        master, child, body = _combo_try("STOP_LOSS")
                    else:
                        raise
                _orders = [master]
                stop_child = child.get("client_order_id")
            except Exception as _cu:                    # noqa: BLE001
                # ANY failure of the linked group — refused, unsupported, or
                # an SDK exception shape we've never seen — falls through to
                # the plain single order below. THE ENTRY IS NEVER LOST TO
                # THE BRACKET (8/20 and again 8/21, the lesson twice). A real
                # problem with the order itself resurfaces on the plain
                # attempt and is reported honestly there.
                # THE ENTRY IS NEVER LOST TO THE BRACKET (the 8/20 lesson:
                # NVDA/BABA/TM/BAC all died when a group rejection was allowed
                # to escape). Whatever the group's problem was, fall through
                # to the plain single order; a real problem with the ORDER
                # itself (price, affordability) will resurface there and be
                # reported honestly.
                stop_child = stop_born = None
                _orders = None
                # remembered so the caller can say it once, not every trade
                self._combo_no = str(_cu)[:120]
        if _orders is None:
            _orders = self._order(symbol, expiration, option_type, strike,
                                          "BUY", qty, limit)
            body = self._send(_orders, what)
        # Cancel looks an order up by the CLIENT id we generated —
        # the SDK puts whatever it is handed into client_order_id.
        # Returning Webull's own order_id here meant every cancel
        # came back ORDER_NOT_FOUND, so the resting stop never died
        # and then blocked every sell on that contract (8/12, all
        # day: META, QQQ, NVDA, SPCX...). Prefer ours; fall back to
        # whatever the response carries.
        oid = ((_orders[0] or {}).get("client_order_id")
               if _orders else None) or _find(
            body, "client_order_id", "clientOrderId", "order_id", "orderId")
        # This returns the moment Webull accepts the order, NOT when it fills.
        # On a resting bid those are different events minutes apart, and
        # sometimes the second one never happens — so nothing downstream is
        # allowed to read this as "you own it". bridge.py watches the ticket.
        if stop_child:
            what += "  [stop %.2f born with it]" % stop_born
        return {"ok": True, "state": "working", "order_id": str(oid) if oid else None,
                "occ": occ, "what": what, "limit": limit, "bid": bid, "ask": ask,
                "blind": blind, "symbol": symbol, "side": side, "strike": strike,
                "expiry": expiry, "qty": qty,
                "stop_child": stop_child, "stop_born": stop_born}

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

    def sell(self, symbol, side, strike, expiry, qty, ref_price=None,
             urgent=False):
        """Exit a position. Getting OUT matters more than pricing it to the
        cent — when the room says "all out", you're out.

        The exit must NOT hinge on a live quote. The sandbox has no OPRA
        entitlement, so ask_bid 403s all day, and the old code refused every
        single "all out" because of it — the position just sat there while the
        room was long gone. Now: use the live quote if it comes, else the
        reference the bridge worked out (their posted %, the last bid the
        watchdog saw, or the entry as breakeven), else a floor limit that still
        clears at the market. A sell LIMIT below the market fills at the bid,
        not at the limit, so a low number means "get me out", not "sell for a
        penny"."""
        option_type = "CALL" if str(side).upper().startswith("C") else "PUT"
        expiration = expiry_to_date(expiry)
        occ = occ_symbol(symbol, expiration, option_type, strike)
        # Never sell more than the account actually holds of THIS contract — a
        # book/broker drift (or a "trim half" of one contract) otherwise trips
        # Webull's "order in excess of current holding" reject and the exit
        # fails. Clamp to the real holding.
        try:
            want = int(qty)
            side_word = "CALLS" if option_type == "CALL" else "PUTS"
            for p in (self.positions() or []):
                if str(p.get("symbol") or "").upper() != str(symbol).upper():
                    continue
                if p.get("side") and p.get("side") != side_word:
                    continue
                try:
                    if p.get("strike") is not None and \
                            abs(float(p["strike"]) - float(strike)) > 0.001:
                        continue
                except (TypeError, ValueError):
                    pass
                held = int(p.get("qty") or 0)
                if held > 0 and want > held:
                    qty = held           # sell exactly what you hold, no more
                break
        except Exception:                                   # noqa: BLE001
            pass
        ask = bid = None
        try:
            ask, bid, _ = self.ask_bid(occ)
        except Refused:
            pass                # no live quote — we still get out, see below
        ref = bid or ask or ref_price
        if urgent and bid and float(bid) > 0:
            # STOP-OUT pricing (8/21, the CLF/MP/TSLA lesson): on a collapsing
            # contract an ask-priced sell RESTS above the market and never
            # fills — the book says stopped while the broker says holding.
            # An urgent exit CROSSES the bid so it clears right now; a sell
            # limit under the bid fills AT the bid, not at the limit.
            limit = max(0.01, round(float(bid) * (1 - self.buffer_pct / 100)
                                    - 0.01, 2))
        elif ask and ask > 0:
            # His call (8/13): exit AT the ask instead of discounting to the
            # bid — stop handing the spread to the market maker on every trim.
            # This is a resting limit at the offer: it captures the full ask
            # when a buyer lifts it. Trade-off he accepted: on a fast move it
            # can fill slower than the old bid-side exit, or not until price
            # comes back up. Only applies when a live ask exists.
            limit = max(0.01, round(float(ask), 2))
        elif ref and ref > 0:
            # No live ask (sandbox 403s, etc.): keep a marketable limit off the
            # reference so the exit still clears instead of resting above the
            # market and missing it.
            limit = max(0.01, round(float(ref) * (1 - self.buffer_pct / 100)
                                    - 0.01, 2))
        else:
            # No quote and nothing to reference at all. Place a floor limit that
            # is marketable against any real bid, so the exit clears instead of
            # refusing. The recorded price is honest about being unknown.
            limit = 0.01
        what = "SELL %d %s %g%s %s @ %.2f" % (qty, symbol, float(strike),
                                              option_type[0], expiration, limit)
        _orders = self._order(symbol, expiration, option_type, strike,
                                      "SELL", qty, limit)
        body = self._send(_orders, what)
        # Cancel looks an order up by the CLIENT id we generated —
        # the SDK puts whatever it is handed into client_order_id.
        # Returning Webull's own order_id here meant every cancel
        # came back ORDER_NOT_FOUND, so the resting stop never died
        # and then blocked every sell on that contract (8/12, all
        # day: META, QQQ, NVDA, SPCX...). Prefer ours; fall back to
        # whatever the response carries.
        oid = ((_orders[0] or {}).get("client_order_id")
               if _orders else None) or _find(
            body, "client_order_id", "clientOrderId", "order_id", "orderId")
        # For the book's P&L, the honest exit price is the live bid if we had
        # one, otherwise the reference the bridge handed in. Never the floor.
        recorded = bid or ask or ref_price or limit
        return {"ok": True, "state": "sent", "order_id": str(oid) if oid else None,
                "occ": occ, "what": what, "limit": recorded, "order_limit": limit,
                "bid": bid, "ask": ask, "symbol": symbol, "qty": qty}
