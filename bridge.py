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
import sys
import threading
import time
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The book of what actually filled. Since entries sit on the bid, "an order went
# out" and "you own it" are two different events, and only this file knows which
# one has happened. Everything that closes a position asks it first.
import positions
import pullback as _pullback
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
# taken as 5 contracts, every add as 5 more, every trim sells ONE, and "all
# out" sells whatever is left. Trims moved from 3 to 1 on his word ("maybe in
# every trim we can sell 1 contract instead of 3") after day one showed the
# 3-lot ladder selling out before the room's big runners — the last SPY went
# at +30% while Brett rode to +65%. One per trim keeps runners on.
DRY_ENTRY_QTY = 5
DRY_ADD_QTY = 5
DRY_TRIM_QTY = 1

# Futures sizing runs smaller on purpose: one NQ point is $20 and Felony's
# trades swing hundreds of points, so 3 contracts trimmed one at a time
# mirrors his trim / 2nd trim / runner pattern without pretending a $4k
# account trades 5 NQ.
DRY_FUT_QTY = 3
# Equity test size, in DOLLARS: qty = round($1000 / share price). "we arnt
# working with real money anyways so might aswell start testing it out."
DRY_EQ_USD = 1000.0
DRY_FUT_TRIM_QTY = 1

# What one point of price movement is worth, per contract. THIS is the number
# that makes futures money real: get it wrong and the whole day is off by 5x.
FUT_MULT = {"NQ": 20.0, "MNQ": 2.0, "ES": 50.0, "MES": 5.0,
            "YM": 5.0, "MYM": 0.5, "RTY": 50.0, "M2K": 5.0,
            "CL": 1000.0, "MCL": 100.0, "GC": 100.0, "MGC": 10.0,
            "SI": 5000.0, "SIL": 1000.0, "NG": 10000.0}


# ---- honest fill + his two tactics -----------------------------------------
# All OFF by default: nothing here changes a single number until he turns it
# on, so the scoreboard he's already reading stays comparable. These are the
# knobs behind "make the test tell the truth" and his two ideas.
def _sim():
    return CFG.get("simulation", {}) if isinstance(CFG, dict) else {}


def realism_on():
    # honest fills: cross the spread, pay fees. The default once he flips it.
    return bool(_sim().get("realistic_fills", False))


def fee_per(kind):
    s = _sim()
    if kind == "future":
        return float(s.get("fee_per_future", 1.24))   # ~ Webull futures/side
    if kind == "equity":
        return float(s.get("fee_per_share_lot", 0.0))
    return float(s.get("fee_per_contract", 0.65))      # ~ options exchange/OCC


def entry_offset(kind):
    """His nickel-under idea: bid this much BELOW their price. In dollars —
    0.05 on an option is his '5 bucks lower' (x100). Off = 0."""
    s = _sim()
    if kind == "future":
        return float(s.get("entry_offset_points", 0.0))
    return float(s.get("entry_offset_dollars", 0.0))


def ladder_cfg():
    """His trim ladder from settings. Default is his stated plan: +10% same
    stop, +20% breakeven, +30% lock +10%, keep 2 runners."""
    s = _sim().get("auto_ladder", {})
    on = bool(s.get("enabled", False))
    keep = int(s.get("keep_runners", 2))
    rungs = s.get("rungs") or [
        {"at": 10.0, "sell": 1, "stop_to": None},
        {"at": 20.0, "sell": 1, "stop_to": 0.0},
        {"at": 30.0, "sell": 1, "stop_to": 10.0},
    ]
    return on, keep, rungs


def auto_be_cfg():
    """His secure-the-trade idea: after +N%, sell a slice and move the stop to
    breakeven so the rest can't lose. {enabled, at_pct, sell_frac}."""
    s = _sim().get("auto_breakeven", {})
    return (bool(s.get("enabled", False)),
            float(s.get("at_pct", 10.0)),
            float(s.get("sell_fraction", 0.10)))


def paper_on():
    """Webull PAPER trading (launched July 2026): route orders to Webull's
    simulated account for HONEST fills instead of our own model. It's the
    gold-standard test — real engine, real prices — while the per-room book
    still tags every fill to its channel. One flag in settings; needs WB
    connected to the paper endpoint. Falls back to the in-house sim if paper
    isn't reachable, which is exactly why that sim stays."""
    w = (CFG.get("execution", {}) or {}).get("webull", {}) or {}
    # Paper is the DEFAULT test engine now: once a sandbox key is saved it's on
    # automatically, no toggle needed. paper_trading can still be set false by
    # hand to force the in-house sim. Only actually "on" when the sandbox client
    # connected — otherwise the in-house sim carries it.
    default_on = bool(w.get("paper_app_key") and w.get("paper_app_secret"))
    return bool(w.get("paper_trading", default_on)) and WB_PAPER is not None


def futures_on():
    """THE switch. execution.futures_enabled in settings.json, off by
    default. Until it's true, a live futures order is refused at the door —
    everything else (parser, book, dry run) already works, which is the whole
    point: flipping this is the only thing left to do."""
    # The switch is retired — "i dont want extra switches,, everything
    # should be either testing or live." Futures follow their room's toggle
    # like everything else; his CME data is confirmed live.
    return True


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
# THE MASTER SWITCH IS RETIRED — his word: "remove the main big switch since
# i want every room to act individually. its either testing or they are
# live.. just like that." Execution is decided per ORDER now (order["live"],
# set by the room's own toggle in the popup); the bridge itself always keeps
# the dry book and connects to Webull whenever keys are in. A settings.json
# still saying mode=webull is treated as dryrun so an old file can't arm
# anything by itself.
if MODE == "webull":
    MODE = "dryrun"

WB = None           # the PRIMARY Webull connection (paper if present, else live)
WB_ERROR = ""
WB_ACCOUNT = ""
# Two connections, held at once, so a live room and a paper room can run side by
# side: a live order goes to the real account, a test order to the sandbox. WB
# above points at whichever is the primary (paper while he's testing) for quotes
# and no-position calls.
WB_PAPER = None     # the sandbox client — every TEST room fills here
WB_LIVE = None      # the real-money client — only a room flipped LIVE routes here
BOOK = None         # positions.Book — what filled, what didn't, and the stops


def _sync_stop_pct(pct):
    """The bracket's stop % lives in THREE places that must agree: the Book
    (watchdog + the number it prints) and each Webull executor (which is what
    actually places the resting stop order via place_stop). Set the strategy's
    stop and the resting Webull stop drifts to its own default unless we push
    it onto every live executor too."""
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return
    for _w in (WB, WB_PAPER, WB_LIVE):
        if _w is not None:
            try:
                _w.stop_pct = pct
            except Exception:                               # noqa: BLE001
                pass


def build_book():
    """One book per run of this program.

    It is built in every mode, including dry run, because the question it
    answers — did that entry actually fill? — is exactly the question a dry run
    exists to answer. In dry run it is `simulated`, which means it can read
    quotes but is not allowed to send anything.
    """
    global BOOK
    # G's standing rule (Aug 2026): entries fill at the ASK for SPEED, not the
    # bid. Bidding at the bid is what left orders resting and filling a minute
    # late (or never) -- the root of the position desync. Forced onto every
    # executor at each bridge start so a stale settings.json "bid" can't undo
    # it. Trade-off he chose: pay the spread to actually get in.
    for _w in (WB, WB_PAPER, WB_LIVE):
        if _w is not None:
            try:
                _w.entry_price = "ask"
            except Exception:                           # noqa: BLE001
                pass
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
        fill_seconds=float(w.get("entry_fill_seconds", 180)),
        poll_seconds=float(w.get("fill_poll_seconds", 5)),
        simulated=(MODE != "webull"),
        unlimited=(MODE != "webull"))
    BOOK.save_day = save_day
    # Clear the paper/dry-run book at NY midnight so the popup starts each day
    # clean; live (real-money) holds are never touched. Default ON.
    BOOK.reset_paper_daily = bool((CFG.get("execution") or {}).get("reset_paper_daily", True))
    # Two-connection routing: a live position is managed on the real account, a
    # paper one on the sandbox. broker_for defaults everything not-explicitly-
    # live to paper, so the real account is never touched by accident.
    BOOK.broker_resolver = broker_for
    # Manual-vs-bot guard: anything bigger than the bot would ever trade
    # (1 contract in, a couple after adds) is HIS hand trade — never adopted,
    # so a room's "all out" can never sell it. Tune with execution.adopt_max_qty.
    BOOK.adopt_max_qty = int((CFG.get("execution") or {}).get("adopt_max_qty", 3))

    # Lets the book recognise an already-expired option (adopt-skip + purge).
    def _exp_date(e):
        from webull_options import expiry_to_date as _e2d
        import datetime as _d
        return _d.date.fromisoformat(str(_e2d(e)))
    BOOK.expiry_parser = _exp_date

    # Adopted positions need a real OCC symbol or the TP/trim watchdog is
    # blind (the 8/11 NVDA +20% that never fired).
    def _occ_build(sym, side, strike, expiry):
        from webull_options import occ_symbol, expiry_to_date
        kind = "CALL" if str(side).upper().startswith("C") else "PUT"
        return occ_symbol(sym, expiry_to_date(expiry), kind, strike)
    BOOK.occ_builder = _occ_build
    # Points x multiplier for adopted futures (MNQ 2, NQ 20, ES 50...).
    BOOK.fut_mult = FUT_MULT
    # Honest fills + his two tactics, read from settings (all default OFF).
    BOOK.realistic = realism_on()
    BOOK.fee_option = fee_per("option")
    BOOK.fee_future = fee_per("future")
    _lad_on, _lad_keep, _lad_rungs = ladder_cfg()
    BOOK.ladder_on = _lad_on
    BOOK.ladder_keep = _lad_keep
    BOOK.ladder_rungs = _lad_rungs
    _abe_on, _abe_pct, _abe_frac = auto_be_cfg()
    BOOK.auto_be_on = _abe_on
    BOOK.auto_be_pct = _abe_pct
    BOOK.auto_be_frac = _abe_frac
    # One-click bracket strategy — LIVE-safe: 1 contract in, close the whole
    # position at +take_profit_pct, stop at -stop_loss_pct. Applies on top of
    # everything else; when it's on, that's the plan.
    _strat = (CFG.get("strategy") or {})
    # G's standing rule: the one-click bracket must ALWAYS come up ON when the
    # bridge starts. On 8/10 it booted OFF and left live positions with no stop.
    # build_book() runs only at startup, so forcing it here sets the BOOT state
    # (protected every time) while turning it OFF from the popup mid-session
    # still works.
    _strat["enabled"] = True
    _strat.setdefault("take_profit_pct", 20.0)
    _strat.setdefault("stop_loss_pct", 10.0)
    CFG["strategy"] = _strat
    BOOK.take_profit_on = True
    BOOK.take_profit_pct = float(_strat.get("take_profit_pct", 20.0))
    BOOK.stop_pct = float(_strat.get("stop_loss_pct", 10.0))
    _sync_stop_pct(BOOK.stop_pct)
    note("STRATEGY forced ON at bridge start: 1 contract, +%.0f%% take-profit, "
         "-%.0f%% stop" % (BOOK.take_profit_pct, BOOK.stop_pct))
    if MODE != "webull":
        note("test account: unlimited. Nothing is refused for money — instead "
             "I keep the most cash that was ever tied up at once, which is the "
             "number that tells you what funding this really takes.")


def reload_settings():
    """Pick up the keys having been typed in while the bridge was running, so you
    don't have to restart it to see that they're in."""
    global CFG, EXEC
    CFG = load_settings()
    EXEC = CFG.get("execution", {})
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


# The date the scoreboard currently belongs to. The bridge runs 24/7 now, so
# midnight has to actually mean something: without this, Wednesday's two wins
# were still on Thursday's scoreboard and "the day" was really two days.
CUR_DAY = None


def roll_day():
    """Called before every day-file write and every /fills poll. The moment
    the New York date changes, yesterday's scoreboard is retired — its file
    is already complete on disk — and today starts at zero."""
    global CUR_DAY
    d = today_str()
    if CUR_DAY is None:
        CUR_DAY = d
    elif d != CUR_DAY:
        CUR_DAY = d
        if BOOK is not None:
            BOOK.new_day()


STATE_PATH = os.path.join(HERE, "state.json")


def save_state():
    """The book's memory, written beside every day file. This is what lets a
    swing trade survive a bridge restart — and what stops a mid-day restart
    from wiping the morning off the scoreboard."""
    if BOOK is None:
        return
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"date": today_str(), "state": BOOK.export_state()}, f)
    except OSError:
        pass


def load_state():
    if BOOK is None:
        return
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    BOOK.restore_state(d.get("state") or {}, d.get("date") == today_str())


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
    roll_day()
    save_state()
    try:
        os.makedirs(DAYS, exist_ok=True)
        path = os.path.join(DAYS, today_str() + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": today_str(), "mode": MODE,
                       "table": BOOK.table(), "wallet": BOOK.wallet()}, f)
    except OSError:
        pass        # a full disk must never take down the trading path
    # journal.csv — the same record flattened to one line per trade, all days,
    # openable in Excel: who called it, the contract, every exit, how it
    # ended, and whether YOU closed it at Webull yourself.
    try:
        import csv
        import datetime as _dt
        allrows = []
        for fn in sorted(os.listdir(DAYS)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(DAYS, fn), encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            for r in (d.get("table") or []):
                allrows.append((d.get("date", fn[:-5]), r))

        def _hhmm(t):
            if not t:
                return ""
            return _dt.datetime.fromtimestamp(t).strftime("%H:%M")

        with open(os.path.join(HERE, "journal.csv"), "w", newline="",
                  encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "room", "caller", "symbol", "contract", "qty",
                        "avg_in", "exits", "P&L", "opened", "closed", "status",
                        "closed_by_you", "account"])
            for date, r in allrows:
                ct = ""
                if r.get("strike") is not None:
                    ct = "%s%s %s" % (
                        r.get("strike"),
                        "C" if str(r.get("side") or "").upper().startswith("C")
                        else "P", r.get("expiry") or "")
                elif r.get("kind") == "future":
                    ct = "futures"
                ex = "; ".join(
                    "%s@%s%s" % (e.get("qty"), e.get("price"),
                                 "" if e.get("pl") is None
                                 else " (%+.0f)" % e["pl"])
                    for e in (r.get("exits") or []))
                w.writerow([date, r.get("room") or "", r.get("who") or "?",
                            r.get("symbol") or "", ct, r.get("qty") or 0,
                            r.get("avg") if r.get("avg") is not None else "",
                            ex, r.get("pl"), _hhmm(r.get("opened")),
                            _hhmm(r.get("closed")), r.get("state") or "",
                            "YES" if r.get("manual") else "",
                            "live" if r.get("live") else "paper"])
    except Exception:                                   # noqa: BLE001
        pass    # the journal must never take down the trading path


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
    # A futures entry has no OCC symbol and, until the data subscription
    # exists, no quote to check against. It tracks at the price they posted,
    # with the multiplier that makes its points worth real dollars.
    if order.get("kind") == "future":
        if not limit:
            note("DRY RUN  %s futures call came with no price — not tracked"
                 % order.get("symbol"))
            return
        order["mult"] = FUT_MULT.get(str(order.get("symbol", "")).upper(), 1.0)
        BOOK.entry_sent(order, {"order_id": None, "occ": None,
                                "limit": float(limit), "bid": None, "ask": None,
                                "qty": int(order.get("qty") or 1)})
        return
    # Equity — plain shares, his Swing Trades / Long Term style ("Entered
    # BULL equity @ 7.24"). One share is one share: multiplier 1, no OCC,
    # no expiry. Test-sized in dollars, not contracts — about $1000 worth —
    # because 100 shares of NFLX and 100 of a $7 stock are different bets.
    if order.get("kind") == "equity":
        if not limit:
            note("DRY RUN  %s equity call came with no price — not tracked"
                 % order.get("symbol"))
            return
        order["mult"] = 1.0
        BOOK.entry_sent(order, {"order_id": None, "occ": None,
                                "limit": float(limit), "bid": None, "ask": None,
                                "qty": int(order.get("qty") or 1)})
        return
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
    # HIS nickel-under idea: bid below their posted price. A resting limit that
    # only fills if the ask comes down to it — misses the runaways, catches
    # the pullbacks. The fill-watcher already refuses it if nobody sells there.
    off = entry_offset(order.get("kind"))
    if off and limit:
        limit = round(max(0.01, float(limit) - off), 4)
        order["bid_under"] = off
        note("DRY RUN  bidding %.2f under their price -> %.2f (his rule)"
             % (off, limit))
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
    # Futures exits are priced off THEIR dollars: "Target hit $1700 a
    # contract" means the market moved 1700/mult points your way from your
    # entry. No quote feed exists yet, so his number is the honest one — and
    # with no number, the trade stays unsettled rather than guessed at.
    if p.get("kind") == "future":
        fill = p.get("fill") or p.get("their_price")
        usd = order.get("usd")
        if usd not in (None, "") and fill is not None:
            mult = float(p.get("mult") or 1.0)
            dirn = int(p.get("direction") or 1)
            return (round(float(fill) + dirn * float(usd) / mult, 4),
                    " at their $%.0f a contract" % float(usd))
        return None, ""
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


def _expiry_recently_past(exp):
    """'' or a reason string. "7/31" read on Aug 3 is 3 days dead — refuse.
    "1/15" read in August most recently passed ~200 days ago, which means
    the caller means NEXT January — roll forward, allow. The line between
    the two is 60 days: nobody posts a two-month-old weekly by accident and
    means it. Unparseable dates return '' — the SDK's contract resolution
    is the authority on formats this doesn't know."""
    import eastern
    try:
        s = str(exp).strip()
        m = None
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d"):
            try:
                m = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if m is None:
            return ""
        today = eastern.now()
        if "%Y" in fmt or "%y" in fmt:
            d = m.date()
            days = (today.date() - d).days
            return ("expired %d day(s) ago" % days) if days > 0 else ""
        # Month/day only: how long ago did it most recently pass?
        d = m.replace(year=today.year).date()
        if d > today.date():
            return ""                       # later this year — fine
        days = (today.date() - d).days
        if days == 0:
            return ""                       # 0DTE, expires today — fine
        if days <= 60:
            return "expired %d day(s) ago" % days
        return ""                           # long past = next year's date
    except Exception:                       # noqa: BLE001
        return ""


def _futures_brokers_safe():
    """The futures-broker config for the popup, with every password/secret
    stripped — the browser sees which brokers are on and the non-secret fields
    (account name, folder, demo flag), never a credential."""
    fb = CFG.get("futures_brokers") or {}
    out = {"webull": bool(fb.get("webull"))}
    nt = fb.get("ninjatrader") or {}
    out["ninjatrader"] = {"enabled": bool(nt.get("enabled")),
                          "account": nt.get("account", ""),
                          "incoming_dir": nt.get("incoming_dir", "")}
    tv = fb.get("tradovate") or {}
    out["tradovate"] = {"enabled": bool(tv.get("enabled")),
                        "username": tv.get("username", ""),
                        "demo": bool(tv.get("demo")),
                        "has_password": bool(tv.get("password"))}
    ts = fb.get("topstep") or {}
    out["topstep"] = {"enabled": bool(ts.get("enabled")),
                      "username": ts.get("username", ""),
                      "base_url": ts.get("base_url", "https://api.topstepx.com"),
                      "has_password": bool(ts.get("api_key"))}
    return out


def _book_futures(order, key):
    """Keep the book in step for a futures order that went to a prop broker
    (NinjaTrader/Tradovate) rather than Webull. Webull's own path updates the
    book itself; this covers the prop legs so a NinjaTrader-only trader still
    sees the position open, trim down, and close on the room's calls."""
    if BOOK is None:
        return
    act = order.get("action")
    if act in ("OPEN", "ADD"):
        BOOK.entry_sent(order, {"order_id": None, "occ": None,
                                "limit": order.get("limit"), "bid": None,
                                "ask": None, "qty": int(order.get("qty") or 1),
                                "live": True})
    elif act == "TRIM":
        held = int((BOOK.info(key) or {}).get("qty") or 0)
        if held > 0:
            BOOK.trim(key, 1, None, "their trim (futures) —")
    elif act == "CLOSE":
        if BOOK.claim(key):
            import positions
            BOOK.finish(key, positions.CLOSED,
                        "closed on their call (futures)", price=None)


_RECENT_COIDS = {}          # coid -> (timestamp, (ok, msg)) — retry dedup


# --- round-number pullback (HIS strategy, 8/11/26) ---------------------------
# Two entry modes now, chosen PER ROOM in the popup: "instant" (the normal
# at-the-ask fill) and "pullback" (wait for the stock to touch the next whole
# dollar, then buy). A pullback order is PAPER no matter what the room's live
# toggle says — his rule: off real money until he's watched it work.
_PULLBACK = None


def _pullback_quote(sym):
    """Underlying stock price, borrowed from whichever client can answer."""
    last = None
    for c in (WB_LIVE, WB, WB_PAPER):
        if c is None:
            continue
        fn = getattr(c, "stock_price", None)
        if not callable(fn):
            continue
        try:
            return fn(sym)
        except Exception as e:                          # noqa: BLE001
            last = e
    raise RuntimeError(str(last) if last else "no Webull connection for stock quotes")


def _pullback_enter(order):
    o = dict(order)
    o.pop("entry_mode", None)     # so it can't loop back into the watcher
    o["live"] = False             # paper-only until proven, no exceptions
    return _place_impl(o)


def _pullback_close(order, why):
    return _place_impl({
        "action": "CLOSE", "symbol": order.get("symbol"),
        "side": order.get("side"), "strike": order.get("strike"),
        "expiry": order.get("expiry"), "trader": order.get("trader"),
        "kind": order.get("kind") or "option", "live": False,
        "raw": "pullback exit: " + str(why), "source": "pullback"})


def pullback_manager():
    global _PULLBACK
    if _PULLBACK is None:
        pcfg = (CFG.get("pullback") or {})
        _PULLBACK = _pullback.Pullback(
            _pullback_quote, _pullback_enter, _pullback_close, note,
            timeout_seconds=float(pcfg.get("timeout_seconds", 300)),
            poll_seconds=float(pcfg.get("poll_seconds", 2)))
    return _PULLBACK


def place(order):
    """Retry-safe wrapper around the real placement. The extension retries an
    order the socket refused (a bridge restart). If a retry lands after a first
    copy was already handled, return that first result instead of placing the
    same real trade twice. Only OPEN/ADD are deduped — trims/closes are already
    idempotent against the book (nothing to sell twice)."""
    coid = str(order.get("coid") or "").strip()
    dedupe = coid and order.get("action") in ("OPEN", "ADD")
    if dedupe:
        now = time.time()
        for _c in [c for c, (t, _r) in list(_RECENT_COIDS.items()) if now - t > 60]:
            _RECENT_COIDS.pop(_c, None)
        prior = _RECENT_COIDS.get(coid)
        if prior is not None:
            note("DEDUP    ignored a repeat of %s (retry) — not placed twice"
                 % coid)
            return prior[1]
    result = _place_impl(order)
    if dedupe:
        try:
            _RECENT_COIDS[coid] = (time.time(), result)
        except Exception:                               # noqa: BLE001
            pass
    return result


def _place_impl(order):
    """Returns (ok, message). Never raises — a crash here would look to the
    extension exactly like a rejected order, and you'd never know which."""
    sym = str(order.get("symbol", "")).upper()
    action = order.get("action")
    key = find_key(order) if BOOK is not None else tkey(order)

    # Round-number pullback mode, per-room. Only OPENs on the managed symbols
    # are deferred to the watcher; anything else (futures, equities, unlisted
    # tickers) falls straight through to the normal instant path — that IS the
    # rule for them. The watcher enters (paper) when the stock touches the
    # level, then manages the exit off the underlying.
    if (action == "OPEN" and str(order.get("entry_mode") or "") == "pullback"
            and order.get("kind") not in ("future", "equity")
            and sym in _pullback.MANAGED):
        order["live"] = False          # paper-only until proven
        okp, msgp = pullback_manager().start(order)
        note(("PULLBACK  " if okp else "PULLBACK refused  ") + msgp)
        return okp, msgp

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

    # Whether THIS order is real money — the room's own toggle, not a global.
    live_order = bool(order.get("live")) and MODE != "webhook"
    # Paper routes an ENTRY through Webull's SANDBOX for a real fill; it is NOT
    # real money, so the wallet still scores it. A LIVE order is never paper —
    # the two are mutually exclusive, which is what lets a live room and a test
    # room run at once: live -> real account, paper -> sandbox.
    paper = paper_on() and not live_order and MODE != "webhook"
    if paper:
        order["paper"] = True

    # TRIM — sell some, keep the rest. His call, reversed: trims now DO sell in a
    # LIVE room ("they trimmed 10% and it didn't fire on my broker — I want the
    # trim to trigger"). A room's trim is the take-profit, so it sells a contract
    # at the broker the moment they call it, and the runners ride on.
    if action == "TRIM":
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
        # The trim size is decided HERE, by what kind of trade it is — 3 of 5
        # on options, 1 at a time on futures (his trim / 2nd trim / runner
        # pattern) — not by whatever number the browser guessed.
        pos_k = BOOK.info(key) or {}
        fut = pos_k.get("kind") == "future" or order.get("kind") == "future"
        want = min(DRY_FUT_TRIM_QTY if fut else DRY_TRIM_QTY, held)
        got, how = exit_price(order, key)
        sold = BOOK.trim(key, want, got, "their trim" + how + " —")
        if not sold:
            return False, ("couldn't put a price on that trim (no quote, no "
                           "percentage), so nothing was sold — still holding "
                           "%d" % held)
        # BOOK.trim places the real sandbox sell for a paper position (paper is
        # no longer simulated), or the real sell for a live one; only a pure
        # dry-run book with no broker models it.
        where = ("sandbox" if paper else ("LIVE" if live_order else "dry run"))
        return True, "%s — sold %d, holding the rest" % (where, sold)

    if paper and action in ("OPEN", "ADD"):
        # Paper uses the same test size as the dry book, so the two are
        # comparable — then it routes to Webull below for the real fill.
        if order.get("kind") == "future":
            order["qty"] = DRY_FUT_QTY
        elif order.get("kind") == "equity":
            px = float(order.get("limit") or 0)
            order["qty"] = max(1, int(round(DRY_EQ_USD / px))) if px else 100
        else:
            order["qty"] = int(order.get("qty")
                               or (DRY_ADD_QTY if action == "ADD"
                                   else DRY_ENTRY_QTY))
    if MODE == "webhook":
        pass          # falls through to the webhook branch below
    elif not live_order and not (paper and action in ("OPEN", "ADD", "CLOSE")):
        # THE IN-HOUSE SIM IS OFF — his word: "kill all the fake simulations,
        # from now on only Webull paper for options and futures." So a real
        # order with no sandbox behind it is REFUSED, never faked. (With the
        # sandbox connected this branch isn't reached; paper routes below.)
        if action in ("OPEN", "ADD", "CLOSE", "TRIM"):
            if claimed:
                BOOK.release(key)
            w = EXEC.get("webull") or {}
            has_key = bool(w.get("paper_app_key") and w.get("paper_app_secret"))
            note("REFUSED  %s  ->  no Webull paper connection" % what)
            if has_key:
                return False, ("your Webull PAPER (sandbox) key is saved but not "
                               "connected right now — reconnect and try again. "
                               "The in-house sim is off, so nothing was faked. "
                               "(%s)" % (WB_ERROR or "sandbox unreachable"))
            return False, ("nothing was sent: connect your Webull PAPER "
                           "(sandbox) key in the popup. The in-house sim is off "
                           "— it's Webull paper only now, for options and "
                           "futures.")
        return True, "read and logged"

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

    if live_order or (paper and action in ("OPEN", "ADD", "CLOSE")):
        # Route to the right connection: real account for a live order, sandbox
        # for a paper one. This is the money-safety fork — a live order can only
        # ever reach WB_LIVE. Paper entries AND exits both go to the sandbox now
        # (no in-house model for the exit).
        client = WB_LIVE if live_order else WB_PAPER
        if client is None:
            if live_order:
                return False, ("this room is LIVE but there's no real-money "
                               "Webull connection — add your live keys and "
                               "restart. Nothing was sent.")
            return False, ("can't reach the Webull sandbox to place this paper "
                           "order: %s" % (WB_ERROR or "unknown"))

        # Futures, real money. Two locks on this door: the futures switch in
        # settings (off until he flips it), and webull_futures itself, which
        # sizes at ONE contract and refuses loudly rather than guessing at an
        # endpoint. The first live futures order is a supervised event, not a
        # surprise.
        if order.get("kind") == "future" or \
                (BOOK is not None and (BOOK.info(key) or {}).get("kind") == "future"):
            if not futures_on():
                if claimed:
                    BOOK.release(key)
                note("FUTURES  %s refused — the switch is off" % what)
                return False, ("his futures call was read and logged, but the "
                               "futures switch is off. Flip it in the popup's "
                               "Settings once your Webull futures data "
                               "subscription is live.")
            # Where futures trade, his call: Webull, NinjaTrader, Tradovate —
            # each an independent toggle, so an order fans out to all of them or
            # just one. futures_brokers holds it all; when it's unset we keep the
            # old rule (Webull unless a legacy prop is armed). Refusals are
            # always sentences, never silence.
            fb = CFG.get("futures_brokers") or {}
            armed_props = []
            if fb:
                use_webull = bool(fb.get("webull"))
                nt = fb.get("ninjatrader") or {}
                if nt.get("enabled"):
                    armed_props.append({"name": "NinjaTrader",
                        "platform": "ninjatrader",
                        "username": nt.get("account", ""),
                        "extra": nt.get("incoming_dir", ""), "enabled": True})
                tv = fb.get("tradovate") or {}
                if tv.get("enabled"):
                    armed_props.append({"name": "Tradovate",
                        "platform": "tradovate",
                        "username": tv.get("username", ""),
                        "password": tv.get("password", ""),
                        "extra": "demo" if tv.get("demo") else "",
                        "enabled": True})
                ts = fb.get("topstep") or {}
                if ts.get("enabled"):
                    armed_props.append({"name": "Topstep",
                        "platform": "projectx",
                        "username": ts.get("username", ""),
                        "password": ts.get("api_key", ""),
                        "extra": ts.get("base_url") or "https://api.topstepx.com",
                        "enabled": True})
                # Any hand-added prop accounts still ride along when armed.
                armed_props += [p for p in (CFG.get("props") or [])
                                if p.get("enabled")]
            else:
                armed_props = [p for p in (CFG.get("props") or [])
                               if p.get("enabled")]
                use_webull = not armed_props        # legacy default

            results, any_sent, book_done = [], False, False

            # Webull leg first — it's the book-of-record when it's on.
            if use_webull:
                try:
                    import webull_futures
                    ok, msg = webull_futures.execute(client, BOOK, order, key, note)
                    results.append(msg)
                    if ok:
                        any_sent, book_done = True, True
                except Exception as e:                  # noqa: BLE001
                    note("FUTURES  Webull ERROR %s -> %s" % (what, e))
                    results.append("Webull futures didn't take it: %s" % str(e)[:120])

            # NinjaTrader / Tradovate legs — also send; they only touch the book
            # if Webull didn't already (so the position is never counted twice).
            if armed_props:
                import props as prop_mod
                sent, refused = prop_mod.execute_all(armed_props, order, note)
                results += sent + refused
                if sent:
                    any_sent = True
                    if BOOK is not None and not book_done:
                        _book_futures(order, key)
                        book_done = True

            if not any_sent and claimed:
                BOOK.release(key)
            summary = "; ".join(r for r in results if r)
            if not any_sent and not summary:
                summary = ("no futures broker is turned on — pick Webull, "
                           "NinjaTrader or Tradovate under 'Trade futures from'.")
            return any_sent, summary

        from webull_options import Refused
        qty = int(order.get("qty") or 1)
        # One-click bracket strategy forces ONE contract on every entry, no
        # matter what the alert or the browser said. Clamped here too (not just
        # in the extension) so real money can never size up by accident.
        if action in ("OPEN", "ADD") and (CFG.get("strategy") or {}).get("enabled"):
            qty = 1
        try:
            # ADD is a buy like any other — a second contract of something
            # you're already holding. The averaging decision was made upstream;
            # by the time it gets here it's just an order.
            if action in ("OPEN", "ADD"):
                ticket = client.buy(order["symbol"], order.get("side"),
                                    order.get("strike"), order.get("expiry"), qty,
                                    their_price=order.get("limit"))
                ticket["live"] = bool(live_order)   # real money?
                ticket["paper"] = bool(paper)       # or Webull's sim engine
                # "ORDER IN", not "BOUGHT". Webull has accepted a resting bid;
                # nobody has sold you anything yet.
                note("ORDER IN %s" % ticket["what"])
                if BOOK is not None:
                    BOOK.entry_sent(order, ticket)
                    if action == "ADD" and order.get("avg"):
                        BOOK.their_add(key, order["avg"])
                return True, entry_words(ticket)

            if action == "CLOSE":
                # "OUT HALF" / "all out" often carry no strike or expiry — the
                # position they mean is the one on the book. Backfill from it so
                # the sell knows which contract, instead of refusing with
                # "they didn't say which expiry". The book is the authority on
                # what's actually held.
                held_pos = (BOOK.info(key) or {}) if BOOK is not None else {}
                if not order.get("expiry") and held_pos.get("expiry"):
                    order["expiry"] = held_pos.get("expiry")
                if order.get("strike") in (None, "") and held_pos.get("strike") is not None:
                    order["strike"] = held_pos.get("strike")
                if not order.get("side") and held_pos.get("side"):
                    order["side"] = held_pos.get("side")
                # An exit reference so the sell never hinges on a live quote:
                # their posted %, the last bid the watchdog saw, or — failing
                # everything — the entry fill, so the exit records ~breakeven
                # rather than refusing. Getting out is the point.
                exref, _hownote = exit_price(order, key)
                if exref is None:
                    exref = held_pos.get("fill") or held_pos.get("their_price")
                res = client.sell(order["symbol"], order.get("side"),
                                  order.get("strike"), order.get("expiry"), qty,
                                  ref_price=exref)
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
                        back = client.buy(order["symbol"], order.get("side"),
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
_FBP = {"t": 0.0, "v": None}
_POS = {"t": 0.0, "v": []}


def broker_positions():
    """The REAL open positions from Webull — BOTH accounts, each tagged live vs
    paper, so the popup shows a live MSFT and a sandbox MSFT for what they are
    instead of one confusing blob. Cached ~8s so a 4s poll doesn't hammer the
    broker. Empty list when there's no connection."""
    if WB is None:
        return []
    now = time.time()
    if now - _POS["t"] < 8:
        return _POS["v"]

    def _refresh():
        rows = []
        seen = set()
        try:
            for wb, is_live in ((WB_LIVE, True), (WB_PAPER, False)):
                if wb is None or id(wb) in seen or not hasattr(wb, "positions"):
                    continue
                seen.add(id(wb))
                try:
                    for p in (wb.positions() or []):
                        d = dict(p)
                        d["live"] = is_live  # which Webull account it's in
                        rows.append(d)
                except Exception:                       # noqa: BLE001
                    pass
                # The FUTURES account is a separate Webull account, so it needs
                # its own call — without this his futures positions were
                # invisible everywhere (8/12). Always real money.
                try:
                    for p in (wb.futures_positions() or []):
                        d = dict(p)
                        d["live"] = True
                        rows.append(d)
                except Exception:                       # noqa: BLE001
                    pass
            _POS["t"], _POS["v"] = time.time(), rows
        finally:
            _POS["busy"] = False

    # Serve what we have and fetch fresh in the background — the popup's
    # poll must never sit inside a broker call (8/11: a network blip turned
    # that into a 4-minute hang and "couldn't reach the bridge"). Only the
    # very first call, with nothing cached yet, waits for the answer.
    if _POS.get("busy"):
        return _POS["v"]
    _POS["busy"] = True
    if _POS["t"] == 0:
        _refresh()
    else:
        threading.Thread(target=_refresh, daemon=True).start()
    return _POS["v"]


def real_buying_power():
    """The margin account's real buying power, or None when there's nothing
    honest to report. Cached ~30s on top of the SDK's own cache — the popup
    asks every few seconds and the broker doesn't need to hear about it."""
    if WB is None:
        return None
    now = time.time()
    if now - _BP["t"] < 30:
        return _BP["v"]

    def _refresh():
        try:
            v = WB.buying_power()
        except Exception:                               # noqa: BLE001
            v = None
        _BP["t"], _BP["v"] = time.time(), v
        _BP["busy"] = False

    if _BP.get("busy"):
        return _BP["v"]
    _BP["busy"] = True
    if _BP["t"] == 0:
        _refresh()
    else:
        threading.Thread(target=_refresh, daemon=True).start()
    return _BP["v"]


def real_futures_buying_power():
    """The FUTURES account's buying power, or None. Same 30s cache idea, so the
    popup can show margin and futures side by side without hammering Webull."""
    if WB is None:
        return None
    now = time.time()
    if now - _FBP["t"] < 30:
        return _FBP["v"]

    def _refresh():
        try:
            v = (WB.futures_buying_power()
                 if hasattr(WB, "futures_buying_power") else None)
        except Exception:                               # noqa: BLE001
            v = None
        _FBP["t"], _FBP["v"] = time.time(), v
        _FBP["busy"] = False

    if _FBP.get("busy"):
        return _FBP["v"]
    _FBP["busy"] = True
    if _FBP["t"] == 0:
        _refresh()
    else:
        threading.Thread(target=_refresh, daemon=True).start()
    return _FBP["v"]


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
        return {"mode": "per-room",
                # No global live any more — rooms go live one by one in the
                # popup, and each ORDER carries its own flag.
                "live": False,
                "connected": WB is not None,
                "account": WB_ACCOUNT,
                # The futures account, auto-picked next to the margin one.
                "futures_account": getattr(WB, "futures_account_id", None)
                                   if WB is not None else None,
                # Prop accounts: names only, never credentials.
                "simulation": CFG.get("simulation", {}),
                # The one-click bracket strategy (1 contract, +15%/-15%), so the
                # popup toggle can show its true state after a reload.
                "strategy": CFG.get("strategy", {}),
                # Where futures route (Webull/NinjaTrader/Tradovate), so the
                # popup toggles show their true state after a reload. Passwords
                # are stripped — never send a credential back to a browser.
                "futures_brokers": _futures_brokers_safe(),
                "paper": paper_on(),
                "paper_available": (WB is not None and getattr(WB, "paper", False)),
                # Why paper isn't running, in plain words (missing sandbox key).
                "paper_warning": getattr(WB, "paper_warning", "") if WB is not None else "",
                "paper_keys_in": bool((EXEC.get("webull") or {}).get("paper_app_key")),
                # AI reader on/off (never returns the key itself).
                "ai_enabled": bool((EXEC.get("ai_reader") or {}).get("enabled")
                                   and (EXEC.get("ai_reader") or {}).get("api_key")),
                "props": [{"name": p.get("name"),
                           "platform": p.get("platform"),
                           "enabled": bool(p.get("enabled"))}
                          for p in (CFG.get("props") or [])],
                "error": WB_ERROR,
                "has_keys": keys_in,
                # Just the tail, so the popup can say "keys in, ...4859"
                # without the key itself ever going back to a browser.
                "key_tail": str((EXEC.get("webull") or {})
                               .get("app_key", ""))[-4:] if keys_in else "",
                # The real margin account's buying power, straight from Webull,
                # cached for half a minute because the popup asks every few
                # seconds and the broker doesn't need to hear from us that
                # often. None whenever there's nothing honest to say.
                "buying_power": real_buying_power(),
                "futures_buying_power": real_futures_buying_power(),
                # The futures switch, so the popup can show which side it's on.
                "futures": futures_on(),
                "stopped": os.path.exists(os.path.join(HERE, "STOP")) or
                           os.path.exists(os.path.join(HERE, "STOP.txt"))}

    def _flatten(self):
        """Close a REAL Webull position by symbol — the popup's one-click exit of
        a position the book may have lost track of (a restart). Sells at the
        market via the broker directly; also clears it from the book so the popup
        updates. Local-only (127.0.0.1)."""
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "message": "unreadable"})
        sym = str(body.get("symbol") or "").upper()
        if not sym:
            return self._json(400, {"ok": False, "message": "no symbol"})
        # Close on the SAME account it lives in — a paper ✕ must not fire a real
        # order, and a live ✕ must not hit the sandbox. Falls back sensibly.
        want_live = bool(body.get("live"))
        wb = (WB_LIVE if want_live else WB_PAPER) or WB
        if wb is None or not hasattr(wb, "flatten"):
            return self._json(200, {"ok": False,
                "message": "no Webull connection to close it — do it in the app."})
        try:
            msg = wb.flatten(sym)
            _POS["t"] = 0.0                     # force the next /positions to refetch
            # If the book is tracking it, mark it closed too so the popup agrees.
            if BOOK is not None:
                try:
                    for k in [k for k, p in list(getattr(BOOK, "_pos", {}).items())
                              if str((p or {}).get("symbol") or "").upper() == sym]:
                        if BOOK.claim(k):
                            BOOK.finish(k, positions.CLOSED,
                                        "closed from the popup", price=None)
                except Exception:               # noqa: BLE001
                    pass
            note("FLATTEN  %s -> %s" % (sym, msg))
            return self._json(200, {"ok": True, "message": msg})
        except Exception as e:                              # noqa: BLE001
            note("FLATTEN  %s FAILED -> %s" % (sym, e))
            return self._json(200, {"ok": False,
                "message": "couldn't close %s: %s" % (sym, str(e)[:140])})

    def do_GET(self):
        if self.path.startswith("/mode"):
            return self._json(200, self._status())
        if self.path.startswith("/positions"):
            # The real Webull account positions, so the popup mirrors the broker.
            return self._json(200, {"positions": broker_positions(),
                                    "connected": WB is not None})
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
            roll_day()
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
        if self.path.startswith("/scoreboard"):
            # Every room's whole record, across every day file on disk.
            # This is his "stay with the best performers" chart: wins,
            # losses, net pretend dollars, days seen — per room, all time.
            rooms = {}
            try:
                for fn in sorted(os.listdir(DAYS)):
                    if not fn.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(DAYS, fn), encoding="utf-8") as f:
                            d = json.load(f)
                    except (OSError, ValueError):
                        continue
                    seen_rooms = set()
                    for tr in ((d.get("wallet") or {}).get("trades") or []):
                        r = tr.get("room") or "(before room tags)"
                        s = rooms.setdefault(r, {"w": 0, "l": 0, "pl": 0.0,
                                                 "days": 0})
                        if float(tr.get("pl") or 0) >= 0:
                            s["w"] += 1
                        else:
                            s["l"] += 1
                        s["pl"] += float(tr.get("pl") or 0)
                        seen_rooms.add(r)
                    for r in seen_rooms:
                        rooms[r]["days"] += 1
            except OSError:
                pass
            return self._json(200, {"rooms": rooms})
        if self.path.startswith("/build"):
            # Asked every half minute by the extension. Deliberately does not
            # touch settings or the broker — it's the cheapest call here.
            return self._json(200, {"stamp": build_stamp()})
        self._reply(200, "bridge is up, mode=%s" % MODE)

    def _set_mode(self):
        """RETIRED. The master switch is gone — rooms go live one at a time
        in the popup, and every order carries its own live flag. This answers
        politely so an old popup can't flip anything."""
        return self._json(200, dict(self._status(), ok=False,
            message="the master switch is retired — each room has its own "
                    "TESTING/LIVE toggle in the popup now"))

    def _set_mode_retired(self):
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

    def _set_keys(self):
        """Webull keys, typed into the extension popup instead of a console.

        He asked for this by name — "if i have to enter the api keys in the
        extension to work thats better. i like to lean more to the UI side."
        The security shape is unchanged: the keys are POSTed once over
        127.0.0.1 (never leaves this machine), written straight into
        settings.json with owner-only permissions, and NOT kept anywhere in
        the browser — the popup forgets them the moment they're sent, and all
        it ever gets back is the last four characters.
        """
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "message": "unreadable"})
        key = str(body.get("app_key", "")).strip()
        secret = str(body.get("app_secret", "")).strip()
        p_key = str(body.get("paper_app_key", "")).strip()
        p_secret = str(body.get("paper_app_secret", "")).strip()
        saving_live = bool(key and secret)
        saving_paper = bool(p_key and p_secret)
        if not saving_live and not saving_paper:
            return self._json(400, {"ok": False,
                                    "message": "give a key and secret — either "
                                               "your live pair or the paper pair"})
        path = os.path.join(HERE, "settings.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            # No settings.json yet — a brand-new PC. Start from the example,
            # which is exactly what the old menu's install step did.
            try:
                with open(os.path.join(HERE, "settings.example.json"),
                          encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
        w = data.setdefault("execution", {}).setdefault("webull", {})
        # Save only what was actually sent, so a paper-only save keeps the live
        # keys and vice-versa.
        if saving_live:
            w["app_key"], w["app_secret"] = key, secret
        if saving_paper:
            w["paper_app_key"], w["paper_app_secret"] = p_key, p_secret
            # Paper is the test engine, so saving a sandbox key turns it ON —
            # overriding any leftover paper_trading:false from an old settings
            # file. He can still flip it off by hand later.
            w["paper_trading"] = True
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.chmod(path, 0o600)
        except OSError as e:
            return self._json(200, {"ok": False,
                                    "message": "couldn't save them: %s" % e})
        reload_settings()
        # Prove whatever was saved, straight away. The answer lands in the popup.
        msgs, ok_all = [], True
        have_paper = bool((EXEC.get("webull") or {}).get("paper_app_key")
                          and (EXEC.get("webull") or {}).get("paper_app_secret"))
        # Reconnect with the new settings. With a sandbox key present paper is
        # the default test engine, so this connects to the sandbox and the test
        # side is live on paper immediately — no extra toggle to flip.
        connect_broker(quiet=True)
        if saving_paper:
            ok_p, pmsg = prove_paper_keys()
            ok_all = ok_all and ok_p
            msgs.append(pmsg)
        if saving_live:
            if have_paper:
                # Paper owns the active connection now; the live keys wait until
                # a room is flipped REAL, so there's nothing to connect-test yet.
                msgs.append("Live keys saved — used when you flip a room REAL.")
            elif WB is not None:
                msgs.append("Live keys working — account %s." % WB_ACCOUNT)
            else:
                ok_all = False
                msgs.append("Live keys didn't connect: %s"
                            % (WB_ERROR or "unknown")[:120])
        note("KEYS     new Webull keys from the popup (%s%s) — %s"
             % ("live …%s " % key[-4:] if saving_live else "",
                "paper …%s" % p_key[-4:] if saving_paper else "",
                "ok" if ok_all else "problem"))
        return self._json(200, dict(self._status(), ok=ok_all,
                                    message=" ".join(msgs)))

    def _ai_read(self):
        """READING intelligence for a message the regex parser gave up on.
        The extension only calls this on a miss. We hand the one message to
        Claude, validate its read against the literal text (anti-hallucination),
        and return a CLEAN canonical call for the extension to run back through
        the same parser + guards. We never trade here — we only read."""
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "why": "unreadable"})
        text = str(body.get("text") or "").strip()
        if not text:
            return self._json(200, {"ok": False, "why": "no text"})
        try:
            import ai_reader
        except Exception as e:                              # noqa: BLE001
            return self._json(200, {"off": True, "why": "ai_reader missing: %s" % e})
        if not ai_reader.available(CFG):
            return self._json(200, {"off": True})
        allowed = CFG.get("allowed_symbols", []) or []
        read = ai_reader.read_signal(text, allowed, CFG)
        ok, why, cleaned = ai_reader.validate(read, text, allowed)
        if not ok:
            note("AI READ  no call — %s" % (why or "")[:80])
            return self._json(200, {"ok": False, "why": why})
        canon = ai_reader.canonical(cleaned)
        note("AI READ  '%s'  ->  %s" % (text[:50], canon))
        return self._json(200, {"ok": True, "canonical": canon,
                                "read": cleaned,
                                "confidence": cleaned.get("confidence", 0)})

    def _self_update(self):
        """Pull the latest build from GitHub and restart the bridge onto it —
        this is the popup's Update button, so he never has to open START HERE
        for an update again. Local-only (the server binds 127.0.0.1). Keys, day
        files and logs are gitignored, so the hard reset never touches them.

        If the pull fails, nothing restarts and the reason goes back to the
        popup. If the pull works but the re-exec somehow doesn't, the new files
        are already on disk, so the next normal restart (START HERE / the 9:25
        alarm) picks them up — no worse off than before."""
        import subprocess
        try:
            old = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                                 capture_output=True, text=True, timeout=20)
            fetch = subprocess.run(["git", "fetch", "origin", "main"], cwd=HERE,
                                   capture_output=True, text=True, timeout=90)
            if fetch.returncode != 0:
                return self._json(200, {"ok": False,
                    "message": "couldn't reach GitHub: %s"
                               % (fetch.stderr or fetch.stdout or "")[:150]})
            reset = subprocess.run(["git", "reset", "--hard", "origin/main"],
                                   cwd=HERE, capture_output=True, text=True,
                                   timeout=60)
            if reset.returncode != 0:
                return self._json(200, {"ok": False,
                    "message": "downloaded it, but couldn't apply it: %s"
                               % (reset.stderr or "")[:150]})
            new = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                                 capture_output=True, text=True, timeout=20)
        except FileNotFoundError:
            return self._json(200, {"ok": False,
                "message": "git isn't installed on this PC, so the popup can't "
                           "self-update. Double-click START HERE once instead."})
        except Exception as e:                              # noqa: BLE001
            return self._json(200, {"ok": False,
                                    "message": "update failed: %s" % str(e)[:150]})

        if old.stdout.strip() == new.stdout.strip():
            return self._json(200, {"ok": True,
                "message": "already on the latest — nothing to update."})

        # Reply FIRST, then restart a beat later so this response reaches the
        # popup before the process is replaced.
        def _restart():
            time.sleep(1.2)
            try:
                os.execv(sys.executable,
                         [sys.executable, os.path.join(HERE, "bridge.py")])
            except Exception as e:                          # noqa: BLE001
                note("self-update: restart failed, staying on old code (%s). "
                     "The new files are on disk for the next START HERE." % e)
        threading.Thread(target=_restart, daemon=True).start()
        note("SELF-UPDATE pulled %s..%s — restarting the bridge"
             % (old.stdout.strip()[:7], new.stdout.strip()[:7]))
        return self._json(200, {"ok": True,
            "message": "Update downloaded — restarting the bridge. Give it "
                       "~10 seconds, then you're on the new version."})

    def _set_config(self):
        """The futures switch, flipped from the popup. One field, written to
        settings.json so it survives restarts, effective immediately."""
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "message": "unreadable"})
        _known = ("futures_enabled", "simulation", "paper_trading",
                  "ai_enabled", "ai_api_key", "ai_model", "strategy",
                  "futures_brokers")
        if not any(k in body for k in _known):
            return self._json(400, {"ok": False, "message": "nothing to set"})
        path = os.path.join(HERE, "settings.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        want = None
        if "futures_enabled" in body:
            want = bool(body["futures_enabled"])
            data.setdefault("execution", {})["futures_enabled"] = want
        if "paper_trading" in body:
            w = data.setdefault("execution", {}).setdefault("webull", {})
            w["paper_trading"] = bool(body["paper_trading"])
            CFG.setdefault("execution", {}).setdefault("webull", {})["paper_trading"] = w["paper_trading"]
            note("PAPER    Webull paper trading %s — reconnecting"
                 % ("ON" if w["paper_trading"] else "OFF"))
            want = want if want is not None else None
        if isinstance(body.get("simulation"), dict):
            sim = data.setdefault("simulation", {})
            sim.update(body["simulation"])
            # apply live so the next trade already obeys it
            if BOOK is not None:
                CFG["simulation"] = sim
                BOOK.realistic = bool(sim.get("realistic_fills", False))
                BOOK.fee_option = float(sim.get("fee_per_contract", 0.65))
                BOOK.fee_future = float(sim.get("fee_per_future", 1.24))
                if isinstance(sim.get("auto_ladder"), dict):
                    ld = sim["auto_ladder"]
                    BOOK.ladder_on = bool(ld.get("enabled", False))
                    BOOK.ladder_keep = int(ld.get("keep_runners", 2))
                    if ld.get("rungs"):
                        BOOK.ladder_rungs = ld["rungs"]
                ab = sim.get("auto_breakeven", {})
                BOOK.auto_be_on = bool(ab.get("enabled", False))
                BOOK.auto_be_pct = float(ab.get("at_pct", 10.0))
                BOOK.auto_be_frac = float(ab.get("sell_fraction", 0.10))

        # The one-click bracket strategy (LIVE-safe). Applied live so the next
        # trade already obeys it: 1 contract, +N% take-profit, -N% stop.
        if isinstance(body.get("strategy"), dict):
            st = dict(CFG.get("strategy") or {}); st.update(body["strategy"])
            data["strategy"] = st
            CFG["strategy"] = st
            if BOOK is not None:
                BOOK.take_profit_on = bool(st.get("enabled"))
                BOOK.take_profit_pct = float(st.get("take_profit_pct", 20.0))
                if st.get("enabled") and st.get("stop_loss_pct"):
                    BOOK.stop_pct = float(st["stop_loss_pct"])
                    _sync_stop_pct(BOOK.stop_pct)
            note("STRATEGY %s: 1 contract, +%.0f%% TP, -%.0f%% SL"
                 % ("ON" if st.get("enabled") else "off",
                    float(st.get("take_profit_pct", 20)),
                    float(st.get("stop_loss_pct", 10))))

        # Where futures trade: Webull / NinjaTrader / Tradovate toggles plus
        # each one's account details. Merged (not replaced) so toggling one
        # broker never wipes another's saved credentials. Effective immediately.
        if isinstance(body.get("futures_brokers"), dict):
            fb = dict(CFG.get("futures_brokers") or {})
            incoming = body["futures_brokers"]
            if "webull" in incoming:
                fb["webull"] = bool(incoming["webull"])
            for bk in ("ninjatrader", "tradovate", "topstep"):
                if bk in incoming and isinstance(incoming[bk], dict):
                    cur = dict(fb.get(bk) or {})
                    cur.update(incoming[bk])
                    fb[bk] = cur
            data["futures_brokers"] = fb
            CFG["futures_brokers"] = fb
            _on = ["webull"] if fb.get("webull") else []
            if (fb.get("ninjatrader") or {}).get("enabled"):
                _on.append("ninjatrader")
            if (fb.get("tradovate") or {}).get("enabled"):
                _on.append("tradovate")
            if (fb.get("topstep") or {}).get("enabled"):
                _on.append("topstep")
            note("FUTURES  trade from: %s" % (", ".join(_on) or "nothing selected"))

        # AI reader — reading intelligence on the misses. The key is a secret,
        # so it lives in settings.json (gitignored, chmod 600), never the
        # browser. Empty key just turns it off.
        if any(k in body for k in ("ai_enabled", "ai_api_key", "ai_model")):
            ar = data.setdefault("execution", {}).setdefault("ai_reader", {})
            if "ai_api_key" in body:
                ar["api_key"] = str(body.get("ai_api_key") or "").strip()
            if "ai_model" in body:
                ar["model"] = str(body.get("ai_model") or "").strip()
            if "ai_enabled" in body:
                ar["enabled"] = bool(body["ai_enabled"])
            # Can't be on without a key.
            if not ar.get("api_key"):
                ar["enabled"] = False
            CFG.setdefault("execution", {})["ai_reader"] = dict(ar)
            note("AI READ  reader %s" % ("ON" if ar.get("enabled") else "off"))

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.chmod(path, 0o600)
        except OSError as e:
            return self._json(200, {"ok": False,
                                    "message": "couldn't save it: %s" % e})
        reload_settings()
        if "paper_trading" in body:
            try:
                connect_broker(quiet=True)   # re-point at paper/live endpoint
            except Exception:                # noqa: BLE001
                pass
        if want is not None:
            note("FUTURES  switch %s from the popup"
                 % ("ON — real futures orders are now allowed when live"
                    if want else "OFF"))

        return self._json(200, dict(self._status(), ok=True,
                                    message=("futures ON — his futures calls "
                                             "can now place real orders in "
                                             "live mode" if want else
                                             "saved")))

    def _set_props(self):
        """Prop-firm accounts, managed from the popup. Ops: add (full entry
        with credentials), toggle (enable/disable by name), remove (by name).
        Credentials are written to settings.json (chmod 600) and NEVER echoed
        back — the popup only ever sees name/platform/enabled."""
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "message": "unreadable"})
        path = os.path.join(HERE, "settings.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        props = data.get("props") or []
        msg = "saved"
        if isinstance(body.get("add"), dict):
            a = body["add"]
            entry = {"name": str(a.get("name") or "prop")[:40],
                     "platform": str(a.get("platform") or "webhook").lower(),
                     "username": str(a.get("username") or ""),
                     "password": str(a.get("password") or ""),
                     "extra": str(a.get("extra") or ""),
                     # armed by hand, later, on purpose — never at creation
                     "enabled": False}
            props = [p for p in props if p.get("name") != entry["name"]]
            props.append(entry)
            msg = "%s saved — it starts DISABLED; arm it in the list" % entry["name"]
        elif body.get("toggle"):
            for p in props:
                if p.get("name") == body["toggle"]:
                    p["enabled"] = not p.get("enabled")
                    msg = "%s is now %s" % (p["name"],
                                            "ARMED — real orders" if p["enabled"]
                                            else "disabled")
        elif body.get("remove"):
            props = [p for p in props if p.get("name") != body["remove"]]
            msg = "removed"
        data["props"] = props
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.chmod(path, 0o600)
        except OSError as e:
            return self._json(200, {"ok": False,
                                    "message": "couldn't save it: %s" % e})
        reload_settings()
        note("PROPS    %s" % msg)
        return self._json(200, dict(self._status(), ok=True, message=msg))

    def do_POST(self):
        if self.path.startswith("/mode"):
            return self._set_mode()
        if self.path.startswith("/flatten"):
            return self._flatten()
        if self.path.startswith("/mark"):
            return self._mark()
        if self.path.startswith("/keys"):
            return self._set_keys()
        if self.path.startswith("/config"):
            return self._set_config()
        if self.path.startswith("/props"):
            return self._set_props()
        if self.path.startswith("/update"):
            return self._self_update()
        if self.path.startswith("/read"):
            return self._ai_read()

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
        # No ticker is ever blocked — the allowed-list filter is deleted, on
        # his word: "no filters wanted." The one check left isn't a filter:
        # a futures root has to be in the multiplier table, because without
        # its multiplier the money math would be fiction.
        if order.get("kind") == "future" and sym not in FUT_MULT:
            note("BLOCKED  %s isn't a futures contract I know the "
                 "multiplier for" % sym)
            return self._reply(403, "%s isn't a futures product I know — "
                                    "not sent" % sym)

        cap = (HARD_MAX_SELL_QTY
               if order.get("action") in ("CLOSE", "TRIM")
               else (HARD_MAX_QTY if order.get("live") else HARD_MAX_QTY_DRY))
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

        if order.get("live") and order.get("action") != "TRIM" \
                and order.get("kind") != "future" \
                and not (order.get("strike") and order.get("expiry")):
            note("BLOCKED  %s %s arrived with no strike/expiry" %
                 (order.get("action"), sym))
            return self._reply(400,
                "that order didn't say which contract (no strike or expiry), so "
                "nothing was sent. Close it in the Webull app if you're in it.")

        # An expiry in the recent past is never a real call — it's a stale
        # repost, a scrape of an old message, or a typo. On Aug 3 a July 31
        # contract got bought three days dead in the dry run. Recent-past
        # only: "1/15" posted in August correctly means NEXT January (the
        # rooms trade LEAPs), so a date more than 60 days gone rolls forward
        # instead of refusing. One copy of this calendar, here, so every
        # source that can reach the bridge — extension, replay, anything —
        # goes through it in dry run and real alike.
        if order.get("action") in ("OPEN", "ADD") and order.get("expiry") \
                and order.get("kind") != "future":
            stale = _expiry_recently_past(order.get("expiry"))
            if stale:
                note("BLOCKED  %s %s %s — expiry %s already passed (%s)" %
                     (order.get("action"), sym, order.get("strike"),
                      order.get("expiry"), stale))
            if stale:
                return self._reply(400,
                    "that contract's expiry (%s) %s — an expired option can't "
                    "be opened, so nothing was sent. If this was a fresh call, "
                    "the date was a typo; take it by hand if you mean it."
                    % (order.get("expiry"), stale))

        ok, msg = place(order)
        self._reply(200 if ok else 502, msg)

    def log_message(self, *a):
        pass    # the default logger prints a line per request; note() is enough


def prove_paper_keys():
    """Connect to the Webull sandbox with the saved paper keys and confirm it
    actually lands in PAPER. A bad sandbox key 401s and WebullOptions.connect()
    quietly falls back to the live connection, so the real test isn't 'did it
    connect' — it's 'is it still paper afterward'. Places no orders."""
    w = EXEC.get("webull") or {}
    if not (w.get("paper_app_key") and w.get("paper_app_secret")):
        return False, "No paper (sandbox) key saved."
    try:
        import copy
        from webull_options import WebullOptions
        pcfg = copy.deepcopy(CFG)
        pcfg.setdefault("execution", {}).setdefault("webull", {})[
            "paper_trading"] = True
        pc = WebullOptions(pcfg)
        acct = pc.connect()
    except Exception as e:                              # noqa: BLE001
        return False, "Paper keys saved, but didn't connect: %s" % str(e)[:120]
    if getattr(pc, "paper", False):
        return True, ("Paper keys saved and working — simulated account %s. "
                      "Paper is your test engine, so it's already ON." % acct)
    return False, ("Paper keys saved, but were REJECTED (it fell back to live). "
                   "The sandbox key is a SEPARATE key from your live one — "
                   "re-check it.")


def broker_for(pos):
    """The client that owns a position. SAFE BY CONSTRUCTION: the live,
    real-money client is returned ONLY for a position explicitly flagged live;
    everything else routes to paper (or the primary/sim when there's no paper
    client). A position can therefore never reach the real account by accident."""
    if pos and pos.get("live"):
        return WB_LIVE
    return WB_PAPER if WB_PAPER is not None else WB


def connect_broker(quiet=False):
    """Build BOTH Webull connections — the sandbox (paper) client and the real
    (live) client — so a live room and a test room can run at the same time. WB
    is the primary (paper while testing) for quotes and no-position calls. Done
    at startup and whenever keys change."""
    global WB, WB_ERROR, WB_ACCOUNT, WB_PAPER, WB_LIVE
    import copy
    w = EXEC.get("webull") or {}
    have_live = bool(w.get("app_key") and w.get("app_secret"))
    have_paper = bool(w.get("paper_app_key") and w.get("paper_app_secret"))

    WB_PAPER = None
    WB_LIVE = None
    errs = []
    if have_live or have_paper:
        from webull_options import WebullOptions
        # Paper (sandbox) client — the test engine, built whenever a sandbox key
        # is in. Forced into paper mode regardless of the toggle.
        if have_paper:
            try:
                pc = copy.deepcopy(CFG)
                pc.setdefault("execution", {}).setdefault(
                    "webull", {})["paper_trading"] = True
                wbp = WebullOptions(pc)
                acctp = wbp.connect()
                if getattr(wbp, "paper", False):
                    # Paper pays the ASK (marketable), never sits on the bid —
                    # the sandbox has liquidity, so an entry should fill the
                    # instant it's read, not miss like a resting bid does live.
                    wbp.entry_price = "ask"
                    WB_PAPER = wbp
                    note("Webull PAPER connected — sim account %s (fills at ask)"
                         % acctp)
                else:
                    errs.append("the sandbox key didn't land in paper")
            except Exception as e:                      # noqa: BLE001
                errs.append("paper: %s" % str(e)[:90])
        # Live (real-money) client — built whenever live keys are in, kept ready
        # so a room flipped LIVE routes there instantly. Connecting reads the
        # account list only; it never places an order.
        if have_live:
            try:
                lc = copy.deepcopy(CFG)
                lc.setdefault("execution", {}).setdefault(
                    "webull", {})["paper_trading"] = False
                wbl = WebullOptions(lc)
                acctl = wbl.connect()
                if not getattr(wbl, "paper", False):
                    WB_LIVE = wbl
                    note("Webull LIVE connected — real account %s (no orders "
                         "until a room is flipped REAL)" % acctl)
                else:
                    errs.append("the live keys came up paper")
            except Exception as e:                      # noqa: BLE001
                errs.append("live: %s" % str(e)[:90])

    # Options data (OPRA) rides on the LIVE account, not the sandbox. So when
    # both are connected, the paper client borrows the live client's quotes —
    # real ask/bid — while still filling on the sandbox. This is what makes
    # paper an honest test instead of a data-starved one. Read-only: quotes
    # only, never an order through the live connection.
    if WB_PAPER is not None and WB_LIVE is not None:
        WB_PAPER.quote_client = WB_LIVE
        note("paper quotes now come from the LIVE data feed (real OPRA prices, "
             "sandbox fills)")

    # Primary: prefer paper while testing, else live, else None (pure sim).
    WB = WB_PAPER or WB_LIVE
    # A fresh connection resets each executor's stop_pct to the config default,
    # so if the bracket strategy is on, push its stop back onto the new clients.
    _st = (CFG.get("strategy") or {})
    if _st.get("enabled") and _st.get("stop_loss_pct"):
        _sync_stop_pct(float(_st["stop_loss_pct"]))
    WB_ACCOUNT = str(getattr(WB, "account_id", "") or "") if WB is not None else ""
    WB_ERROR = "; ".join(errs)
    if not quiet:
        if WB is not None:
            print("  Webull connected%s%s"
                  % (" (paper)" if WB_PAPER is not None else "",
                     " + live ready" if WB_LIVE is not None else ""))
        elif have_live or have_paper:
            print("  Webull: NOT CONNECTED — %s" % (WB_ERROR or "unknown"))
        else:
            print("  Webull: no keys — the dry run assumes every bid filled.")
    build_book()
    load_state()      # swings survive restarts


def _install_network_failfast():
    """8/11: his internet blipped at 10:05 and 10:20 (DNS dead, host
    unreachable). Every Webull call then hung ~4 MINUTES inside the SDK — no
    default timeout — the popup's polls wedged behind them, the extension
    said "couldn't reach the bridge", and the XOM and GM entries died waiting.
    A connection that can't be made in 4 seconds isn't going to be made; a
    fast honest error beats a frozen bridge. This puts a default timeout on
    every requests call in the process (the Webull SDK rides on requests).
    Anything that passes its own timeout keeps it."""
    try:
        import requests
        if getattr(requests.sessions.Session.request, "_failfast", False):
            return
        _orig = requests.sessions.Session.request

        def _timed(self, method, url, **kw):
            if kw.get("timeout") is None:
                kw["timeout"] = (4, 8)          # connect, read — seconds
            return _orig(self, method, url, **kw)
        _timed._failfast = True
        requests.sessions.Session.request = _timed
    except Exception:                                   # noqa: BLE001
        pass


def main():
    import eastern
    _install_network_failfast()
    print("=" * 62)
    print("  DISCORD SNIPER BRIDGE")
    print("  started %s New York time" % eastern.now().strftime("%a %d %b %H:%M:%S"))
    # Worth printing: when this runs hidden by the morning alarm, bridge.log is
    # the only place you can find out what it thought the time was.
    print("  clock: %s" % eastern.source())
    print("  listening on http://127.0.0.1:%d  (this PC only)" % PORT)
    print("  mode: %s%s" % (MODE, "   <- nothing real is being sent"
                            if MODE == "dryrun" else "   <- REAL ORDERS"))
    print("  symbols: everything trades - no filters, his rule")
    print("  panic button: make a file called STOP in this folder")
    connect_broker()
    # Keep the book in step with the REAL Webull account: adopt any open position
    # the book doesn't know about (one it never placed, or lost on a restart) so
    # a room's "all out" can actually flatten it. Runs once now and every 20s.
    def _reconcile_loop():
        while True:
            try:
                if BOOK is not None and WB is not None:
                    BOOK.purge_expired(note)
                    BOOK.adopt(broker_positions(), note)
                    # the other direction: positions HE closed at Webull
                    if BOOK.reconcile_gone(broker_positions(), note):
                        save_day()
            except Exception:                           # noqa: BLE001
                pass
            time.sleep(20)
    threading.Thread(target=_reconcile_loop, daemon=True).start()
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
