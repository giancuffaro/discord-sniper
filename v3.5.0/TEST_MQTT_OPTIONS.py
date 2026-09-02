"""TEST: does Webull's streaming feed carry US OPTIONS?

Double-click TEST STREAMING.bat, or run:  python TEST_MQTT_OPTIONS.py

WHY THIS TEST EXISTS
--------------------
The bot POLLS Webull for prices. Polling is capped at 300 requests per 60
seconds, and every position you hold spends more of that cap. Streaming is
the opposite deal: you SUBSCRIBE once and Webull PUSHES every price change
to you, with no per-request limit at all.

If streaming carries options, the whole polling problem disappears. Webull's
docs never say whether it does. This finds out.

RUNNING IT WITH THE MARKET CLOSED — READ THIS
---------------------------------------------
Nothing trades when the market is shut, so NO PRICES WILL ARRIVE. That is
expected and it is NOT a failure. This test is built so a closed market still
gives a real answer, because it does not judge on whether prices show up.

It judges on the SUBSCRIPTION being ACCEPTED. Subscribing is a control
message — Webull either accepts your request for option data or refuses it,
and it answers that question at 3am on a Sunday exactly like it does at noon
on a Tuesday.

So:
    subscribe ACCEPTED  -> options ARE carried. Build it.
    subscribe REFUSED   -> options are NOT carried (or not entitled).
    no prices arriving  -> means NOTHING while closed. Ignore it.

THE CONTROL TEST
----------------
A failed option subscribe could mean two very different things: options
aren't supported, or your streaming setup is broken in general. So the script
ALSO subscribes to plain SPY stock. Comparing the two is the whole trick:

    OPTION ok  + STOCK ok   -> options are carried. Green light.
    OPTION bad + STOCK ok   -> streaming works, options specifically are not.
    OPTION bad + STOCK bad  -> your streaming setup/entitlement is the problem,
                               this says nothing about options either way.

It also asks Webull, over plain HTTP, for a real option contract symbol
before subscribing to it. A made-up or expired contract would be refused and
would look exactly like "options not supported" — this removes that trap.
"""

import datetime as dt
import json
import os
import sys
import threading
import time

REGION = "us"
WAIT_FOR_TICKS = 25          # seconds to listen. Only meaningful when OPEN.

# ---------------------------------------------------------------- settings
HERE = os.path.dirname(os.path.abspath(__file__))


def load_keys():
    path = os.path.join(HERE, "settings.json")
    if not os.path.exists(path):
        sys.exit("Can't find settings.json next to this script. Run it from "
                 "inside the discord-sniper folder.")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    w = (cfg.get("execution", {}) or {}).get("webull", {}) or {}
    key, secret = w.get("app_key", ""), w.get("app_secret", "")
    if not key or not secret:
        sys.exit("No app_key / app_secret in settings.json under "
                 "execution.webull. Nothing to test with.")
    return key, secret


def market_state():
    """(is_open, words). Regular US hours only — good enough for the caveat."""
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                                   # noqa: BLE001
        now = dt.datetime.now()
    if now.weekday() >= 5:
        return False, "CLOSED (weekend) — %s ET" % now.strftime("%a %H:%M")
    mins = now.hour * 60 + now.minute
    if 9 * 60 + 30 <= mins < 16 * 60:
        return True, "OPEN — %s ET" % now.strftime("%a %H:%M")
    return False, "CLOSED (outside 9:30-16:00) — %s ET" % now.strftime("%a %H:%M")


def next_friday():
    d = dt.date.today()
    ahead = (4 - d.weekday()) % 7
    return d + dt.timedelta(days=ahead or 7)


def occ(symbol, expiry, cp, strike):
    """SPY  260904C00650000 — the standard OCC contract symbol."""
    return "%-6s%s%s%08d" % (symbol.upper(), expiry.strftime("%y%m%d"),
                             cp.upper()[0], int(round(float(strike) * 1000)))


# ------------------------------------------------------- step 1: a real one
def find_real_contract(api, log):
    """Ask Webull for a contract that actually EXISTS right now.

    Guessing a strike and getting refused would look identical to "options
    aren't supported", which is the exact false negative this test cannot
    afford. So the strike comes from a live SPY quote, and the contract is
    confirmed by an HTTP snapshot before streaming is asked about it.
    """
    from webullsdkmdata.common.category import Category
    from webullsdkmdata.quotes.market_data import MarketData

    md = MarketData(api)

    spot = None
    try:
        snap = md.get_snapshot("SPY", Category.US_STOCK.name)
        body = snap.json() if hasattr(snap, "json") else snap
        spot = _dig(body, "close", "last", "price", "lastPrice", "preClose")
        log("SPY last price from Webull: %s" % spot)
    except Exception as e:                              # noqa: BLE001
        log("could not read a SPY price (%s) — falling back to a guess" %
            str(e)[:80])

    if not spot:
        return None, None
    strike = round(float(spot))            # ATM, the most liquid strike there is
    exp = next_friday()

    for k in (strike, strike + 1, strike - 1, strike + 5, strike - 5):
        sym = occ("SPY", exp, "C", k)
        try:
            r = md.get_snapshot(sym, Category.US_OPTION.name)
            body = r.json() if hasattr(r, "json") else r
            if body and _dig(body, "close", "last", "price", "askPrice",
                             "ask_price", "bidPrice", "bid_price") is not None:
                log("HTTP snapshot OK for %s  <- this contract is real" % sym)
                return sym, body
        except Exception:                               # noqa: BLE001
            continue
    log("no HTTP option snapshot came back for any strike near %s exp %s"
        % (strike, exp))
    return occ("SPY", exp, "C", strike), None


def _dig(obj, *names):
    if isinstance(obj, dict):
        for n in names:
            if n in obj and obj[n] not in (None, ""):
                return obj[n]
        for v in obj.values():
            got = _dig(v, *names)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _dig(v, *names)
            if got is not None:
                return got
    return None


# ------------------------------------------------- step 2: the subscribe test
def try_subscribe(app_key, app_secret, symbol, category_name, label, log):
    """Subscribe and report ACCEPTED / REFUSED. Works with the market shut.

    Returns (accepted, messages_received, detail).
    """
    from webullsdkmdata.common.category import Category
    from webullsdkmdata.common.subscribe_type import SubscribeType
    from webullsdkmdata.quotes.subscribe.default_client import (
        DefaultQuotesClient)

    accepted = threading.Event()
    failed = {"why": None}
    got = {"n": 0, "first": None}

    client = DefaultQuotesClient(app_key, app_secret, REGION)
    client.init_default_settings(
        [symbol], getattr(Category, category_name).name,
        [SubscribeType.QUOTE.name, SubscribeType.SNAPSHOT.name])

    def _ok(_client, _grpc, _token):
        # Webull only calls this after the subscribe request returns 200.
        # THIS is the verdict, and it does not need a single price to fire.
        accepted.set()

    def _msg(_client, payload_type, message):
        got["n"] += 1
        if got["first"] is None:
            got["first"] = "%s: %s" % (payload_type, str(message)[:160])

    client.on_subscribe_success = _ok
    client.on_quotes_message = _msg

    log("")
    log("--- %s : subscribing to %s (%s)" % (label, symbol.strip(),
                                             category_name))
    try:
        client.connect_and_loop_start()
    except Exception as e:                              # noqa: BLE001
        return False, 0, "could not connect at all: %s" % str(e)[:200]

    if not accepted.wait(20.0):
        try:
            client.loop_stop()
        except Exception:                               # noqa: BLE001
            pass
        return (False, got["n"],
                failed["why"] or "no acceptance within 20s — treat as REFUSED")

    log("    SUBSCRIBE ACCEPTED by Webull")
    log("    listening %ds for pushed prices..." % WAIT_FOR_TICKS)
    time.sleep(WAIT_FOR_TICKS)
    try:
        client.loop_stop()
    except Exception:                                   # noqa: BLE001
        pass
    return True, got["n"], got["first"]


# ----------------------------------------------------------------- the run
def main():
    is_open, when = market_state()
    log = print

    log("=" * 68)
    log("WEBULL STREAMING TEST — do options come through?")
    log("Market: %s" % when)
    if not is_open:
        log("")
        log("  MARKET IS CLOSED. No prices will arrive, and that is FINE.")
        log("  The answer comes from whether the SUBSCRIPTION is accepted,")
        log("  which Webull answers whether the market is open or not.")
    log("=" * 68)

    app_key, app_secret = load_keys()

    try:
        from webullsdkcore.client import ApiClient
    except ImportError:
        sys.exit("The Webull market-data SDK isn't installed. Run:\n"
                 "    pip install webull-python-sdk-mdata "
                 "webull-python-sdk-quotes-core")

    api = ApiClient(app_key, app_secret, REGION)

    log("")
    log("STEP 1 — find a real option contract (over plain HTTP)")
    # TEST_OCC=<occ symbol> skips the HTTP hunt with a contract we KNOW is
    # real (9/2: the mdata snapshot answered INVALID_SYMBOL for plain SPY on
    # this SDK family, which says nothing about streaming).
    if os.environ.get("TEST_OCC"):
        symbol, snap = os.environ["TEST_OCC"].strip(), None
        log("    using known-real contract from TEST_OCC: %s" % symbol)
    else:
        symbol, snap = find_real_contract(api, lambda m: log("    " + m))
    if not symbol:
        log("    couldn't resolve a contract. Check your keys and that the")
        log("    OPRA option-data subscription is active on this app key.")
        return
    if snap is None:
        log("    WARNING: no HTTP snapshot confirmed this contract. A refused")
        log("    subscribe below might just mean this contract is wrong.")

    log("")
    log("STEP 2 — subscribe to that OPTION over streaming")
    opt_ok, opt_n, opt_detail = try_subscribe(
        app_key, app_secret, symbol, "US_OPTION", "OPTION", log)

    log("")
    log("STEP 3 — subscribe to plain SPY stock (the control)")
    stk_ok, stk_n, stk_detail = try_subscribe(
        app_key, app_secret, "SPY", "US_STOCK", "STOCK ", log)

    # ------------------------------------------------------------ verdict
    log("")
    log("=" * 68)
    log("VERDICT")
    log("=" * 68)
    log("  option subscribe : %s" % ("ACCEPTED" if opt_ok else "REFUSED"))
    log("  stock  subscribe : %s" % ("ACCEPTED" if stk_ok else "REFUSED"))
    log("  prices pushed    : %d option, %d stock%s"
        % (opt_n, stk_n, "   (market closed — expected 0)" if not is_open
           else ""))
    if opt_detail and opt_ok:
        log("  first option msg : %s" % opt_detail)
    log("")

    if opt_ok and stk_ok:
        log("  >> OPTIONS ARE CARRIED ON STREAMING. This is the green light.")
        log("     Build the bot's price feed on this and polling stops")
        log("     mattering — no 300/minute cap, no 429s, prices pushed the")
        log("     instant they change instead of every 300ms.")
        if not is_open:
            log("")
            log("     Run this once more during market hours to confirm real")
            log("     prices actually flow. Acceptance is proven; delivery is")
            log("     the one thing a closed market cannot show you.")
    elif stk_ok and not opt_ok:
        log("  >> STREAMING WORKS, BUT NOT FOR OPTIONS.")
        log("     Stock subscribed fine and the option did not, so this is")
        log("     about options specifically, not your setup.")
        log("     Stay on batched polling (v3.5.0). For a real push feed on")
        log("     options you would need a second source such as")
        log("     tastytrade's DXLink — keep executing at Webull either way,")
        log("     their $0/contract is worth more than the feed.")
        log("     detail: %s" % (opt_detail or "no reason given"))
    elif not stk_ok and not opt_ok:
        log("  >> STREAMING ISN'T WORKING AT ALL — this says NOTHING about")
        log("     options yet. Most likely the app key has no market-data")
        log("     subscription, or streaming isn't enabled on it.")
        log("     option: %s" % (opt_detail or "-"))
        log("     stock : %s" % (stk_detail or "-"))
        log("     Check the Webull developer portal, then run this again.")
    else:
        log("  >> ODD RESULT: the option subscribed and plain stock did not.")
        log("     Worth a second run before trusting it either way.")
    log("")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped.")
    print("")
    input("Press Enter to close...")
