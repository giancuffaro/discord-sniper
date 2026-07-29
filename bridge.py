"""
bridge.py — the only thing on your PC that is allowed to spend money.

The extension in your browser reads the room and decides "this is an order".
It then posts a plain description of that order here, and this file is what
talks to the broker.

The split is deliberate. Anything that can read your extension folder can read
everything inside it, and a browser extension folder is not a safe place for
account keys. So the browser holds no credentials at all — worst case, someone
who got into it can make this program place a one-contract order on a symbol
you allow-listed, during market hours, up to your daily cap. That is a bad
afternoon, not a drained account.

Menu number 5 starts it, hidden, and leaves it running. It listens on
127.0.0.1 only, which means nothing outside this machine can reach it — not your router, not
your wifi, not the internet.
"""

import json
import os
import time
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The book of what actually filled. Since entries sit on the bid, "an order went
# out" and "you own it" are two different events, and only this file knows which
# one has happened. Everything that closes a position asks it first.
import positions
from urllib.parse import urlparse, parse_qs

# Not `from zoneinfo import ZoneInfo` directly: Windows ships no timezone
# database, so that line takes the whole bridge down on a fresh PC. eastern.py
# uses the real one when it's there and falls back to the rule when it isn't.
from eastern import ET

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "trades.log")
DAYS = os.path.join(HERE, "days")
PORT = 8787

# Second opinion on size. The extension already caps this, but the extension
# is the part that lives in a browser, so it does not get the last word.
# Test mode runs the room's full pattern — 5 in, 5 more on an add — so its
# ceiling is higher than live's, where 2 is still the most a browser message
# is allowed to buy with real money.
HARD_MAX_QTY = 2
HARD_MAX_QTY_DRY = 10
# Exits get their own, higher ceiling. Average in twice and you hold three
# contracts; "all out" has to mean all three. Capping a sell at the buy limit
# would leave you still holding the rest and not know it.
HARD_MAX_SELL_QTY = 20

# The test-mode sizing pattern, which is his, not the room's: every entry is
# taken as 5 contracts, every add as 5 more, every trim sells 3, and "all out"
# sells whatever is left. Fixed numbers on purpose — the day is only
# comparable to yesterday if the sizing never moves.
DRY_ENTRY_QTY = 5
DRY_ADD_QTY = 5
DRY_TRIM_QTY = 3


def build_stamp():
    """A short fingerprint of the extension folder.

    Chrome can't notice on its own that you changed a file — an unpacked
    extension is only re-read when something tells it to. So this program, which
    is already sitting on the same disk, watches the folder instead and hands the
    extension a fingerprint. When the fingerprint changes, the extension knows
    its own files are stale and reloads itself.

    Name, size and last-modified time is enough. Reading every file to hash it
    would be slower for no practical gain — nothing edits these files except you.
    """
    ext = os.path.join(HERE, "extension")
    bits = []
    try:
        for name in sorted(os.listdir(ext)):
            if name.startswith("."):
                continue
            p = os.path.join(ext, name)
            if not os.path.isfile(p):
                continue
            s = os.stat(p)
            bits.append("%s:%d:%d" % (name, s.st_size, int(s.st_mtime)))
    except OSError:
        # No extension folder next to this file — the bridge can be run from
        # anywhere. Say so plainly instead of pretending nothing ever changes.
        return ""
    return "%08x" % (zlib.crc32("|".join(bits).encode("utf-8")) & 0xFFFFFFFF)


def load_settings():
    for name in ("settings.json", "settings.example.json"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


CFG = load_settings()
EXEC = CFG.get("execution", {})
MODE = str(EXEC.get("mode", "dryrun")).lower()
ALLOWED = set(str(s).upper() for s in CFG.get("allowed_symbols", []))

WB = None           # the Webull connection, made once at startup
WB_ERROR = ""
WB_ACCOUNT = ""
BOOK = None         # positions.Book — what filled, what didn't, and the stops


def build_book():
    """One book per run of this program.

    It is built in every mode, including dry run, because the question it
    answers — did that entry actually fill? — is exactly the question a dry run
    exists to answer. In dry run it is `simulated`, which means it can read
    quotes but is not allowed to send anything.
    """
    global BOOK
    # Flipping live/dry-run rebuilds this. It must not do that while something
    # is still open: the old book's watchdog is the only thing holding the stop
    # on that position, and a fresh book wouldn't know it existed. So an open
    # position keeps the book it was opened with.
    if BOOK is not None and BOOK.open_count():
        note("keeping the position book — %d still open, so the stop on it "
             "stays where it is" % BOOK.open_count())
        return
    w = EXEC.get("webull", {}) or {}
    # The test account is now UNLIMITED, on purpose. Nothing gets refused for
    # money; instead the book keeps the high-water mark of cash tied up at
    # once, because "how much would I actually need to fund this" is the
    # question the test days exist to answer, and a cap answers a different
    # one. In live mode there's no pretend account at all — Webull is the
    # authority on what you have.
    BOOK = positions.Book(
        WB, note,
        stop_pct=float(w.get("stop_loss_pct", 20)),
        fill_seconds=float(w.get("entry_fill_seconds", 90)),
        poll_seconds=float(w.get("fill_poll_seconds", 5)),
        simulated=(MODE != "webull"),
        unlimited=(MODE != "webull"))
    BOOK.save_day = save_day
    if MODE != "webull":
        note("test account: unlimited. Nothing is refused for money — instead "
             "I keep the most cash that was ever tied up at once, which is the "
             "number that tells you what funding this really takes.")


def reload_settings():
    """Pick up the keys having been typed in while the bridge was running, so you
    don't have to restart it to see that they're in."""
    global CFG, EXEC, ALLOWED
    CFG = load_settings()
    EXEC = CFG.get("execution", {})
    ALLOWED = set(str(s).upper() for s in CFG.get("allowed_symbols", []))
    EXEC["mode"] = MODE          # the running mode wins; the file may be behind


def save_mode(new_mode):
    """Flip live/dry-run and write it down, so restarting the bridge doesn't
    quietly put you back where you were an hour ago.

    Only settings.json is touched, and only the one field. Your keys are left
    exactly as they are — this switch is about whether they get used, not about
    what they are."""
    global MODE
    path = os.path.join(HERE, "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        # No settings.json yet, or it's unreadable. Flip in memory so the button
        # still does something, but say plainly that it won't survive a restart.
        MODE = new_mode
        CFG.setdefault("execution", {})["mode"] = new_mode
        return False, ("switched to %s for now, but there's no readable "
                       "settings.json to write it to — START HERE, 2, and it "
                       "will stick next time." % new_mode.upper())

    data.setdefault("execution", {})["mode"] = new_mode
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.chmod(path, 0o600)
    except OSError as e:
        return False, "couldn't write settings.json: %s" % e

    MODE = new_mode
    CFG.setdefault("execution", {})["mode"] = new_mode
    return True, "saved"


def note(line):
    stamp = datetime.now(ET).strftime("%H:%M:%S")
    print("%s  %s" % (stamp, line), flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s\t%s\n" % (datetime.now(ET).isoformat(timespec="seconds"), line))
    except OSError:
        pass


def today_str():
    return datetime.now(ET).strftime("%Y-%m-%d")


def save_day():
    """Write today's whole trading day to days/YYYY-MM-DD.json, every time
    anything changes.

    This is the backtesting record: who called what, what you paid, every
    partial sale, how each trade ended, and what the day cost to be in. It's
    rewritten on every event rather than saved at some end-of-day moment,
    because a bridge that crashes at 11am should still leave the morning on
    disk. The popup's "previous days" view reads these files; so can
    replay.py."""
    if BOOK is None:
        return
    try:
        os.makedirs(DAYS, exist_ok=True)
        path = os.path.join(DAYS, today_str() + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": today_str(), "mode": MODE,
                       "table": BOOK.table(), "wallet": BOOK.wallet()}, f)
    except OSError:
        pass        # a full disk must never take down the trading path


def tkey(order):
    """The book's key for the trade this order is about: who called it, plus
    the ticker. Brett's SPY and Unraveler's SPY are two different trades."""
    return positions.key_of(order.get("trader"), order.get("symbol"))


def describe(o):
    bits = [o.get("action", "?"), o.get("symbol", "?")]
    if o.get("trader"):
        bits.append("(%s's call)" % o["trader"])
    if o.get("strike"):
        bits.append("%s%s" % (o["strike"], "C" if o.get("side") == "CALLS" else "P"))
    if o.get("expiry"):
        bits.append(str(o["expiry"]))
    bits.append("x%s" % o.get("qty", 1))
    if o.get("limit"):
        bits.append("@ %.2f" % float(o["limit"]))
    if o.get("reenter"):
        bits.append("(and straight back in)")
    return " ".join(bits)


def entry_words(ticket):
    """How an entry gets described back to the browser.

    It deliberately never says "bought". Your bid sitting on the book is an
    offer, and on the fast ones nobody takes it. The popup finds out what
    became of it from /fills a few seconds later, not from this line.
    """
    side = "C" if str(ticket.get("side", "")).upper().startswith("C") else "P"
    return ("bid is in at %.2f on %s %s%s — you're not in it until somebody "
            "sells to you" % (float(ticket.get("limit") or 0),
                              ticket.get("symbol"), ticket.get("strike"), side))


def dry_entry(order):
    """Track a dry-run entry in the book the same way a real one is tracked.

    With keys saved it prices off the live bid and then watches the real quote,
    so tomorrow's log tells you which of these bids a seller would actually
    have come down to. Without keys there's nothing to ask, and the book says
    so on the line where it assumes the fill.
    """
    if BOOK is None:
        return
    limit = order.get("limit")
    occ = bid = ask = None
    if WB is not None:
        try:
            from webull_options import occ_symbol, expiry_to_date
            kind = ("CALL" if str(order.get("side", "")).upper().startswith("C")
                    else "PUT")
            occ = occ_symbol(order["symbol"], expiry_to_date(order.get("expiry")),
                             kind, order.get("strike"))
            ask, bid, _ = WB.ask_bid(occ)
            limit = WB.entry_limit(bid, ask)
        except Exception as e:                          # noqa: BLE001
            note("DRY RUN  no live quote for %s (%s) — using the price they "
                 "posted instead" % (order.get("symbol"), str(e)[:90]))
    if not limit:
        note("DRY RUN  %s came with no price and there's no quote, so there's "
             "nothing to follow — not tracked" % order.get("symbol"))
        return
    BOOK.entry_sent(order, {"order_id": None, "occ": occ, "limit": float(limit),
                            "bid": bid, "ask": ask,
                            "qty": int(order.get("qty") or 1)})


def exit_price(order, key):
    """(price, note) — what one contract sold for on a dry run.

    Nothing was really sold, so this has to be worked out, and it decides
    whether the pretend account moves at all. Three sources, best first:

      1. The live bid. Selling means hitting the bid, so that is the price —
         never the ask, which you would not get. The watchdog has been writing
         down the last one it saw on every poll.
      2. Their posted percentage on their running average. "all out @ 45%" off
         an average they've built to 2.66 means the contract was worth 3.86.
         That is a real number about the market, and comparing it against YOUR
         fill is what shows the cost of getting in late.
      3. Nothing. Then it says so and leaves the balance alone, because a
         made-up exit price turns the one number he's checking into fiction.
    """
    if BOOK is None:
        return None, ""
    p = BOOK.info(key) or {}
    # Ask right now, at the moment they called it. This is the whole answer to
    # "how much did that actually make" — not their percentage, not the last
    # thing the watchdog happened to see five seconds ago, but what the contract
    # was worth when the message landed.
    if WB is not None and p.get("occ"):
        try:
            _ask, bid, _row = WB.ask_bid(p["occ"])
            if bid:
                return float(bid), ""
        except Exception:                                   # noqa: BLE001
            pass                # fall through to the older numbers below
    bid = p.get("last_bid")
    if bid:
        return float(bid), " (last quote I saw)"
    pct = order.get("pct")
    theirs = p.get("their_avg") or p.get("their_price")
    if pct not in (None, "") and theirs:
        return round(float(theirs) * (1 + float(pct) / 100.0), 2), \
            " at their %+.0f%%" % float(pct)
    return None, ""


def implied_add_price(pos, new_avg):
    """The reverse math. They held n units averaging a, added one more, and
    posted the new average — so the one they just bought cost
    new_avg*(n+1) - a*n. 2.88 becoming 2.55 means the add went off at 2.22.

    That number is a fact about the market, not about their account: it's what
    the contract genuinely traded at the moment they added, which is exactly
    why it's the right price to bid. Returns None whenever the arithmetic
    can't be trusted — no starting average, or an answer at or below zero,
    which means the message didn't mean what it looked like it meant.
    """
    if not new_avg or not pos:
        return None
    a = pos.get("their_avg") or pos.get("their_price")
    if not a:
        return None
    n = max(1, int(pos.get("their_units") or 1))
    x = float(new_avg) * (n + 1) - float(a) * n
    if x < 0.02:
        return None
    return round(x, 2)


def find_key(order):
    """Which trade is this order about. The trader's own first; failing that,
    the only live trade in that ticker; failing that, the trader key as-is
    (which will read as "not in it" downstream, and say so)."""
    key = tkey(order)
    if BOOK is None or BOOK.state_of(key) is not None:
        return key
    others = BOOK.find_by_symbol(order.get("symbol"))
    if len(others) == 1:
        return others[0]
    return key


def plan_exit(order, key):
    """Work out whether there is anything to sell, before anything is sent.

    This is the whole reason the book exists. Sitting on the bid, an entry can
    still be resting — or can never have filled at all — by the time the room
    posts their trim. Selling on either of those sends an order for contracts
    you don't own. Only the book knows which, so it gets asked first, and what
    it says about size beats what the browser thinks.

    Returns (go_ahead, claimed, reply). `claimed` means the book handed this
    position over to us and is expecting to be told how it ended.
    """
    sym = str(order.get("symbol", "")).upper()
    st = BOOK.state_of(key)
    if st is None:
        # Nothing on record. Usually this bridge was restarted mid-day, so the
        # browser remembers a position this program never saw. Sending the
        # exit is the right call — the worst case is Webull refusing a sell of
        # something you don't hold, which is a message, not a loss.
        return True, False, None

    if st == positions.WORKING:
        held = BOOK.cancel_entry(key, "their exit landed before your bid filled")
        if not held:
            return False, False, (True,
                "your bid on %s never filled, so there was nothing to sell. "
                "It's been pulled and you're flat on it." % sym)
        st = BOOK.state_of(key)

    if st != positions.FILLED:
        return False, False, (True,
            "you're not in %s (%s), so nothing was sent." % (sym, st))

    if not BOOK.claim(key):
        return False, False, (True,
            "%s is already being closed — the stop got there first." % sym)

    held = BOOK.qty_of(key)
    asked = int(order.get("qty") or 1)
    if held and held != asked:
        note("size: the browser said %d on %s, you actually hold %d — selling "
             "what you hold" % (asked, sym, held))
        order["qty"] = held
    return True, True, None


def place(order):
    """Returns (ok, message). Never raises — a crash here would look to the
    extension exactly like a rejected order, and you'd never know which."""
    sym = str(order.get("symbol", "")).upper()
    action = order.get("action")
    key = find_key(order) if BOOK is not None else tkey(order)

    # The reverse math, before any mode branch, because it improves the order
    # in both. They posted the new average their add produced; the add itself
    # went off at new_avg*(n+1) - old_avg*n, and THAT is the price worth
    # bidding — it's where the contract actually just traded.
    if action == "ADD" and BOOK is not None and order.get("avg"):
        pos = BOOK.info(key)
        imp = implied_add_price(pos, order["avg"])
        if imp:
            order["limit"] = imp
            note("reverse math: their average moved to %.2f across %d fills, "
                 "so the add went off at ~%.2f — bidding that"
                 % (float(order["avg"]),
                    max(1, int((pos or {}).get("their_units") or 1)) + 1, imp))

    claimed = False
    if action == "CLOSE" and BOOK is not None:
        go, claimed, reply = plan_exit(order, key)
        if not go:
            note("EXIT     %s" % reply[1])
            return reply
    what = describe(order)

    # TRIM — sell some, keep the rest. Test mode only for now: in live he's
    # still set to hold until "all out", and a browser message must not gain
    # the power to sell real contracts before he's said so.
    if action == "TRIM":
        if MODE != "dryrun":
            return False, ("trims don't sell in live mode — you're set to hold "
                           "until \"all out\". Nothing was sent.")
        if BOOK is None:
            return False, "no book yet, nothing to trim"
        st = BOOK.state_of(key)
        if st == positions.WORKING:
            return False, ("their trim landed while your bid on %s was still "
                           "resting — leaving it; their \"all out\" will pull "
                           "it if it never fills" % sym)
        held = BOOK.qty_of(key)
        if not held:
            return False, ("you're not in %s, so there was nothing to trim"
                           % sym)
        want = min(int(order.get("qty") or DRY_TRIM_QTY), held)
        got, how = exit_price(order, key)
        sold = BOOK.trim(key, want, got, "their trim" + how + " —")
        if not sold:
            return False, ("couldn't put a price on that trim (no quote, no "
                           "percentage), so nothing was sold — still holding "
                           "%d" % held)
        return True, "dry run — sold %d, holding the rest" % sold

    if MODE == "dryrun":
        # Money is never the reason a test trade gets refused any more. The
        # unlimited book keeps the high-water mark instead — the answer to
        # "how much would I need" — and every entry goes through at the
        # standard test size.
        if action in ("OPEN", "ADD"):
            order["qty"] = int(order.get("qty")
                               or (DRY_ADD_QTY if action == "ADD"
                                   else DRY_ENTRY_QTY))
        note("DRY RUN  %s   (nothing was sent to a broker)" % what)
        if action in ("OPEN", "ADD"):
            dry_entry(order)
            if action == "ADD" and order.get("avg"):
                BOOK.their_add(key, order["avg"])
        if claimed:
            got, how = exit_price(order, key)
            BOOK.finish(key, positions.CLOSED,
                        "sold on their call (dry run)" + how, price=got)
        if order.get("reenter"):
            note("DRY RUN  then straight back in on the same contract%s"
                 % ("" if not order.get("reenter_limit")
                    else " around %.2f" % float(order["reenter_limit"])))
            dry_entry(dict(order, action="OPEN",
                           limit=order.get("reenter_limit")))
        return True, "dry run — logged, not sent"

    if MODE == "webhook":
        url = EXEC.get("webhook_url", "")
        if not url:
            return False, "webhook mode is on but no webhook_url is set in settings.json"
        try:
            import requests
            r = requests.post(url, json=order,
                              headers=EXEC.get("headers", {}),
                              timeout=float(EXEC.get("timeout_seconds", 4)))
            ok = 200 <= r.status_code < 300
            note("%s  %s  ->  HTTP %s" % ("SENT" if ok else "REJECTED", what, r.status_code))
            return ok, "HTTP %s %s" % (r.status_code, r.text[:120])
        except Exception as e:
            note("FAILED  %s  ->  %s" % (what, e))
            return False, "the webhook didn't answer: %s" % e

    if MODE == "webull":
        if WB is None:
            return False, ("not connected to Webull: %s" % (WB_ERROR or "unknown"))
        from webull_options import Refused
        qty = int(order.get("qty") or 1)
        try:
            # ADD is a buy like any other — a second contract of something
            # you're already holding. The averaging decision was made upstream;
            # by the time it gets here it's just an order.
            if action in ("OPEN", "ADD"):
                ticket = WB.buy(order["symbol"], order.get("side"),
                                order.get("strike"), order.get("expiry"), qty,
                                their_price=order.get("limit"))
                # "ORDER IN", not "BOUGHT". Webull has accepted a resting bid;
                # nobody has sold you anything yet.
                note("ORDER IN %s" % ticket["what"])
                if BOOK is not None:
                    BOOK.entry_sent(order, ticket)
                    if action == "ADD" and order.get("avg"):
                        BOOK.their_add(key, order["avg"])
                return True, entry_words(ticket)

            if action == "CLOSE":
                res = WB.sell(order["symbol"], order.get("side"),
                              order.get("strike"), order.get("expiry"), qty)
                msg = res["what"]
                note("SOLD     %s" % msg)
                if claimed:
                    BOOK.finish(key, positions.CLOSED,
                                "sold on their call at %.2f" % float(res["limit"]))

                # "exited SPY, and back in @ 2.84" — they sold and bought the
                # same contract straight back. Both legs happen here rather
                # than as two round-trips from the browser, so the gap between
                # them is as small as it can be.
                if order.get("reenter"):
                    try:
                        back = WB.buy(order["symbol"], order.get("side"),
                                      order.get("strike"), order.get("expiry"),
                                      qty,
                                      their_price=order.get("reenter_limit"))
                        note("ORDER IN %s   (back in)" % back["what"])
                        if BOOK is not None:
                            BOOK.entry_sent(order, back)
                        return True, msg + "  ||  " + entry_words(back)
                    except Refused as e:
                        # The sell already went through. Say so plainly, because
                        # "failed" here would read as if you were still holding.
                        note("SOLD but could NOT get back in: %s" % e)
                        return False, ("the exit went through, but getting back "
                                       "in did not: %s  You are FLAT on %s."
                                       % (e, order["symbol"]))
                return True, msg

            return False, "nothing to do for action '%s'" % order.get("action")

        except Refused as e:
            # Nothing was sent, so the position is exactly where it was. Hand it
            # back, or the stop that was watching it stays switched off.
            if claimed:
                BOOK.release(key)
            note("REFUSED  %s  ->  %s" % (what, e))
            return False, str(e)
        except Exception as e:                          # noqa: BLE001
            if claimed:
                BOOK.release(key)
            note("ERROR    %s  ->  %s" % (what, e))
            return False, ("something went wrong talking to Webull: %s. The "
                           "order may not have gone out — check the Webull app."
                           % str(e)[:160])

    return False, ("execution mode '%s' isn't a thing. Use dryrun, webull or "
                   "webhook." % MODE)


_BP = {"t": 0.0, "v": None}


def real_buying_power():
    """The margin account's real buying power, or None when there's nothing
    honest to report. Cached ~30s on top of the SDK's own cache — the popup
    asks every few seconds and the broker doesn't need to hear about it."""
    if WB is None:
        return None
    now = time.time()
    if now - _BP["t"] < 30:
        return _BP["v"]
    try:
        v = WB.buying_power()
    except Exception:                                   # noqa: BLE001
        v = None
    _BP["t"], _BP["v"] = now, v
    return v


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, msg):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The browser extension is a different origin, so without this the
        # order never arrives and Chrome tells you nothing useful.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._reply(code, json.dumps(obj))

    def do_OPTIONS(self):
        self._reply(204, "")

    def _status(self):
        reload_settings()
        keys_in = bool((EXEC.get("webull") or {}).get("app_key"))
        return {"mode": MODE,
                "live": MODE == "webull",
                "connected": WB is not None,
                "account": WB_ACCOUNT,
                "error": WB_ERROR,
                "has_keys": keys_in,
                # The real margin account's buying power, straight from Webull,
                # cached for half a minute because the popup asks every few
                # seconds and the broker doesn't need to hear from us that
                # often. None whenever there's nothing honest to say.
                "buying_power": real_buying_power(),
                "stopped": os.path.exists(os.path.join(HERE, "STOP")) or
                           os.path.exists(os.path.join(HERE, "STOP.txt"))}

    def do_GET(self):
        if self.path.startswith("/mode"):
            return self._json(200, self._status())
        if self.path.startswith("/fills"):
            # What actually happened to the orders the browser sent. It asks
            # with the id of the last thing it saw, so it only gets what's new.
            # The mode rides along so the extension always knows whether it's
            # in test or real without a second call — the trim and sizing
            # rules on its side hang off that answer.
            if BOOK is None:
                return self._json(200, {"positions": {}, "events": [],
                                        "seq": 0, "mode": MODE})
            since = parse_qs(urlparse(self.path).query).get("since", ["0"])[0]
            BOOK.sweep()
            try:
                return self._json(200, dict(BOOK.snapshot(since), mode=MODE))
            except (TypeError, ValueError):
                return self._json(200, dict(BOOK.snapshot(0), mode=MODE))
        if self.path.startswith("/days"):
            # The dated files this bridge has been writing — one per trading
            # day. This is the backtesting shelf.
            try:
                names = sorted(n[:-5] for n in os.listdir(DAYS)
                               if n.endswith(".json"))
            except OSError:
                names = []
            return self._json(200, {"days": names})
        if self.path.startswith("/day"):
            # One previous day, whole. ?date=2026-07-29
            q = parse_qs(urlparse(self.path).query).get("date", [""])[0]
            safe = "".join(ch for ch in q if ch.isdigit() or ch == "-")
            path = os.path.join(DAYS, (safe or today_str()) + ".json")
            try:
                with open(path, encoding="utf-8") as f:
                    return self._json(200, json.load(f))
            except (OSError, ValueError):
                return self._json(200, {"date": safe, "table": [],
                                        "wallet": None,
                                        "missing": True})
        if self.path.startswith("/build"):
            # Asked every half minute by the extension. Deliberately does not
            # touch settings or the broker — it's the cheapest call here.
            return self._json(200, {"stamp": build_stamp()})
        self._reply(200, "bridge is up, mode=%s" % MODE)

    def _set_mode(self):
        """The live / dry-run switch, driven from the popup so you don't have to
        find this window and restart it."""
        global WB_ERROR
        reload_settings()
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"ok": False, "message": "unreadable request"})

        want = "webull" if body.get("live") else "dryrun"
        if want == MODE:
            return self._json(200, dict(self._status(), ok=True,
                                        message="already there"))

        if want == "webull":
            if not (EXEC.get("webull") or {}).get("app_key"):
                return self._json(400, dict(self._status(), ok=False,
                    message="there are no Webull keys saved yet. Open START "
                            "HERE and press 2 first, then flip this."))

        ok, msg = save_mode(want)
        if want == "webull":
            connect_broker(quiet=True)
            if WB is None:
                # It's on, but it can't reach the broker. Better to say so now
                # than to let you find out on the first call of the day.
                note("LIVE MODE ON but Webull isn't connected — %s" % WB_ERROR)
                return self._json(200, dict(self._status(), ok=False,
                    message="live mode is on, but it couldn't connect: %s"
                            % WB_ERROR))
            note("LIVE MODE ON — real orders, account %s" % WB_ACCOUNT)
            return self._json(200, dict(self._status(), ok=True,
                message="LIVE. Real orders, account %s.%s"
                        % (WB_ACCOUNT, "" if ok else "  (" + msg + ")")))

        WB_ERROR = ""       # a stale connection error is noise once you're safe
        # Back to pretend fills and pretend stops — unless something is still
        # open, in which case build_book leaves the real one alone.
        build_book()
        note("DRY RUN — nothing real will be sent")
        return self._json(200, dict(self._status(), ok=True,
            message="dry run. Orders are logged, nothing is sent."))

    def _mark(self):
        """What is this contract worth right now, and what is that to you.

        No order, no money, no side effects — it asks the broker for a quote and
        does the arithmetic against what you paid. It exists because a trim is
        the room telling you the trade is up 23%, and 23% of THEIR entry is not
        23% of yours. The only way to know what a trim was really worth is to
        look at the price at the moment they said it, which is what this does.
        """
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False})
        sym = str(body.get("symbol", "")).upper()
        if BOOK is None or not sym:
            return self._json(200, {"ok": False})
        key = find_key({"trader": body.get("trader"), "symbol": sym})
        p = BOOK.info(key)
        if not p or not p.get("occ") or WB is None:
            return self._json(200, {"ok": False})
        try:
            _ask, bid, _row = WB.ask_bid(p["occ"])
        except Exception:                                   # noqa: BLE001
            return self._json(200, {"ok": False})
        if not bid:
            return self._json(200, {"ok": False})
        bid = float(bid)
        out = {"ok": True, "symbol": sym, "bid": round(bid, 2),
               "fill": p.get("fill"), "qty": p.get("qty") or 0}
        if p.get("fill"):
            paid = float(p["fill"])
            out["pct"] = round((bid - paid) / paid * 100.0, 1)
            out["pl"] = round((bid - paid) * 100 * int(p.get("qty") or 0), 2)
        return self._json(200, out)

    def do_POST(self):
        if self.path.startswith("/mode"):
            return self._set_mode()
        if self.path.startswith("/mark"):
            return self._mark()

        if os.path.exists(os.path.join(HERE, "STOP")) or \
           os.path.exists(os.path.join(HERE, "STOP.txt")):
            note("BLOCKED  the STOP file is here, so nothing goes out")
            return self._reply(423, "the STOP file is in the folder — nothing fires")

        try:
            n = int(self.headers.get("Content-Length", 0))
            order = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._reply(400, "that wasn't a readable order")

        sym = str(order.get("symbol", "")).upper()
        if not sym:
            return self._reply(400, "no symbol in that order")
        if ALLOWED and sym not in ALLOWED:
            note("BLOCKED  %s isn't on the allowed list in settings.json" % sym)
            return self._reply(403, "%s isn't on your allowed-symbols list" % sym)

        cap = (HARD_MAX_SELL_QTY
               if order.get("action") in ("CLOSE", "TRIM")
               else (HARD_MAX_QTY_DRY if MODE == "dryrun" else HARD_MAX_QTY))
        try:
            qty = max(1, min(int(order.get("qty") or 1), cap))
        except (TypeError, ValueError):
            qty = 1
        order["qty"] = qty

        # A broker needs the exact contract. The room's "all out of AMD" doesn't
        # have one, so the extension fills it in from what you're holding — if
        # it arrives here empty, something upstream lost track and the right
        # answer is to send nothing.
        # "in SPY 747C @ 3.00" — a real entry with no date on it. The room's own
        # rules message says contracts are weekly unless they spell out 0DTE or
        # a date, so the date isn't missing, it's implied. Filled in here rather
        # than in the parser so there's exactly one copy of the calendar, and
        # only ever for an entry that already named a strike — a close still
        # gets its contract from the position you're holding, never from a
        # guess. Set assume_weekly_expiry to false in settings.json to turn this
        # off and have those calls refused instead.
        if (order.get("action") in ("OPEN", "ADD") and order.get("strike")
                and not order.get("expiry")
                and EXEC.get("assume_weekly_expiry", True)):
            try:
                from webull_options import weekly_expiry
                order["expiry"] = weekly_expiry()
                note("no date in that call, so using this week's Friday (%s) — "
                     "the room's stated default" % order["expiry"])
            except Exception:
                pass

        if MODE != "dryrun" and order.get("action") != "TRIM" \
                and not (order.get("strike") and order.get("expiry")):
            note("BLOCKED  %s %s arrived with no strike/expiry" %
                 (order.get("action"), sym))
            return self._reply(400,
                "that order didn't say which contract (no strike or expiry), so "
                "nothing was sent. Close it in the Webull app if you're in it.")

        ok, msg = place(order)
        self._reply(200 if ok else 502, msg)

    def log_message(self, *a):
        pass    # the default logger prints a line per request; note() is enough


def connect_broker(quiet=False):
    """Done at startup, and again whenever you flip to live, so the first call
    of the day doesn't spend three seconds logging in while the move happens."""
    global WB, WB_ERROR, WB_ACCOUNT
    live = MODE == "webull"
    keys_in = bool((EXEC.get("webull") or {}).get("app_key"))
    # A dry run connects too, when the keys are there. Not to send anything —
    # it can't, the mode gate is above every order — but to read real quotes,
    # so that "would this bid have filled?" gets answered by the actual market
    # instead of by an assumption.
    if not live and not keys_in:
        WB, WB_ACCOUNT, WB_ERROR = None, "", ""
        build_book()
        return
    try:
        from webull_options import WebullOptions
        wb = WebullOptions(CFG)
        acct = wb.connect()
        WB, WB_ACCOUNT, WB_ERROR = wb, str(acct), ""
        line = ("Webull connected, options account %s" % acct if live else
                "Webull connected for quotes only — dry run, nothing can be sent")
        if not quiet:
            print("  %s" % line)
        else:
            note(line)
    except Exception as e:                              # noqa: BLE001
        WB, WB_ACCOUNT = None, ""
        WB_ERROR = str(e)
        if not quiet:
            print("  Webull: NOT CONNECTED — %s" % WB_ERROR)
            print("          nothing will fire until this is fixed."
                  if live else
                  "          the dry run will assume every bid filled, and say "
                  "so on each line.")
        else:
            note("Webull NOT connected — %s" % WB_ERROR)
    build_book()


def main():
    import eastern
    print("=" * 62)
    print("  DISCORD SNIPER BRIDGE")
    print("  started %s New York time" % eastern.now().strftime("%a %d %b %H:%M:%S"))
    # Worth printing: when this runs hidden by the morning alarm, bridge.log is
    # the only place you can find out what it thought the time was.
    print("  clock: %s" % eastern.source())
    print("  listening on http://127.0.0.1:%d  (this PC only)" % PORT)
    print("  mode: %s%s" % (MODE, "   <- nothing real is being sent"
                            if MODE == "dryrun" else "   <- REAL ORDERS"))
    print("  allowed symbols: %s" % (", ".join(sorted(ALLOWED)) or "any"))
    print("  panic button: make a file called STOP in this folder")
    connect_broker()
    print("=" * 62)
    print("Leave this window open. Close it and the extension can't trade.")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError as e:
        print("\nCouldn't start: %s" % e)
        print("Usually that means a bridge is already running in another "
              "window. Close it and try again.")
    except KeyboardInterrupt:
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
