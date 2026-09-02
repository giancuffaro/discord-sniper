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

# A Windows console (or the .bat's piped stdout) defaults to cp1252, and a
# caller name with an emoji in it — 👑KingBeeAri🐝, 8/25 — crashed entry_sent
# MID-ORDER on a bare print: the trade was PLACED at Webull and then never
# registered in the book, which is the worst possible order of events (the
# UBER triple). The stream itself is made unable to die on a character here,
# before anything else loads; note() below is belt-and-suspenders on top.
for _s in (sys.stdout, sys.stderr):
    try:
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(errors="replace")
    except Exception:                                   # noqa: BLE001
        pass

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

# The micro this bridge actually trades when a room calls the full-size root
# ("when felony mentions NQ and ES, we shoot the diminutive"). Same table the
# extension uses; kept here so an exit can find the position the entry made.
FUT_MICRO_OF = {"NQ": "MNQ", "ES": "MES", "YM": "MYM", "RTY": "M2K",
                "GC": "MGC", "CL": "MCL", "SI": "SIL"}


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
    # 8/12, his call: "don't execute trades in paper, but keep paper for
    # testing." So having sandbox keys is no longer enough to route real room
    # calls there — paper_trading must be switched ON deliberately. The client
    # still connects and the whole paper path stays intact, one flag away, for
    # a supervised test. Untouched keys + no flag = test rooms use the in-house
    # sim and the sandbox never sees an order it wasn't asked for.
    return bool(w.get("paper_trading", False)) and WB_PAPER is not None


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
# More Webull accounts firing from the same bot (his ask, 8/18). Each entry:
# {"name", "client", "book"} — a full live client AND a full book of its own,
# so every extra account gets its own resting stop, ratchet, trims, and
# manual-trade protection, not a blind copy of the main account's exits.
# Empty list (nothing configured) = the bridge behaves exactly as before.
WB_EXTRA = []
# Why an extra account did NOT connect, by name — shown in the popup row so
# the answer is in his face, not buried in trades.log (8/21).
WB_EXTRA_ERR = {}
# When one login has SEVERAL accounts: the probed candidates (id + buying
# power), served to the popup as CLICKABLE choices — click one and it's
# pinned, no re-typing anything (his ask, 8/21).
WB_EXTRA_CHOICES = {}


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
    for _w in [WB, WB_PAPER, WB_LIVE] + [x["client"] for x in WB_EXTRA]:
        if _w is not None:
            try:
                _w.stop_pct = pct
            except Exception:                               # noqa: BLE001
                pass
    for _x in WB_EXTRA:
        try:
            _x["book"].stop_pct = pct
        except Exception:                                   # noqa: BLE001
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
    # v3.5.0 BLOCK C (9/2, G: "do everything now"): ONE budget every Webull
    # call draws from (300/60s, 5% held back), and a QUOTE BUS that fetches
    # every watched contract in ONE batched call per sweep (~300ms) instead
    # of one call per position per poll. If the batched shape is refused,
    # ask_bid_many falls back to per-contract calls and says so once; the
    # watchdog additionally falls back to a direct quote whenever the bus
    # has nothing fresh, so the bus can never be the reason a stop is blind.
    try:
        from quote_bus import Budget, QuoteBus
        BUDGET = Budget()
        for _cli in (WB, WB_LIVE, WB_PAPER):
            if _cli is not None:
                _cli.budget = BUDGET
        QUOTES = QuoteBus(WB.ask_bid_many, budget=BUDGET, log=print)
        QUOTES.start()
        BOOK.quotes = QUOTES
        try:                     # OPTION TAPE: only record of our contracts' prints
            QUOTES.record_to(os.path.join(HERE, "option_tape.csv"))
        except Exception:                               # noqa: BLE001
            pass
        note("QUOTE BUS on — one batched quote call per second (Webull: 60/min, 20 contracts each), one budget for all calls")
        # STREAM BUS (9/2, G: "stream all data from the best source we can"):
        # Webull pushes stock/ETF prices over MQTT. Attach one StockStream
        # to every client so stock_price() answers from the push (3s fresh)
        # and only falls back to HTTP when nothing fresh is in hand.
        try:
            from stream_bus import StockStream
            _wcfg = ((CFG.get("execution") or {}).get("webull") or {})
            STREAM = StockStream(_wcfg.get("app_key", ""), _wcfg.get("app_secret", ""),
                                 log=print)
            STREAM.start()
            for _cli in (WB, WB_LIVE, WB_PAPER):
                if _cli is not None:
                    _cli.stream = STREAM
            for _s in ("SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMD", "META",
                       "AMZN", "MSFT", "GOOGL", "NFLX"):
                STREAM.watch(_s)
            note("STREAM on — stock/ETF prices pushed over MQTT (options stay on the 1/s bus)")
        except Exception as _se:                        # noqa: BLE001
            note("STREAM off (%s) — HTTP stock prices as before" % str(_se)[:80])
    except Exception as _qe:                            # noqa: BLE001
        BOOK.quotes = None
        note("QUOTE BUS off (%s) — per-position quotes as before" % str(_qe)[:80])
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
    #
    # 8/15: the hard take-profit close (sell everything the instant gain hits
    # +take_profit_pct) is replaced as the DEFAULT by the ratchet — the stop
    # walks up instead of the position closing, so a winner can keep running
    # and can never come back red once it locks in. take_profit_on stays a
    # real, working switch (settings.json or the popup can still turn the old
    # all-or-nothing close back on) — it's just no longer what boots by
    # default.
    _strat["enabled"] = True
    _strat.setdefault("take_profit_pct", 20.0)
    _strat.setdefault("stop_loss_pct", 10.0)
    _strat.setdefault("ratchet_enabled", True)
    CFG["strategy"] = _strat
    BOOK.take_profit_on = bool(_strat.get("take_profit_hard_close", False))
    BOOK.ratchet_on = bool(_strat.get("ratchet_enabled", True))
    BOOK.take_profit_pct = float(_strat.get("take_profit_pct", 20.0))
    BOOK.stop_pct = float(_strat.get("stop_loss_pct", 10.0))
    _sync_stop_pct(BOOK.stop_pct)
    if BOOK.ratchet_on:
        # The step is stop_loss_pct — same number ratchet_locked_pct() actually
        # uses. It used to be (take_profit_pct - stop_loss_pct) here, which was
        # right for the old 10/20 rung but printed a FLAT LIE on 8/25's 10/10
        # config: "+0% steps", i.e. the ratchet is dead, while the real math was
        # locking breakeven at +10% and another 10% every 10% after. Never let
        # the banner recompute the rule — read it off the function that owns it.
        note("STRATEGY forced ON at bridge start: 1 contract, -%.0f%% stop to "
             "start, then at +%.0f%% the stop goes to BREAKEVEN and every "
             "further +%.0f%% locks another %.0f%% — "
             "never sells outright, never comes back red once it locks"
             % (BOOK.stop_pct, BOOK.take_profit_pct,
                BOOK.stop_pct, BOOK.stop_pct))
    else:
        note("STRATEGY forced ON at bridge start: 1 contract, +%.0f%% take-profit, "
             "-%.0f%% stop" % (BOOK.take_profit_pct, BOOK.stop_pct))
    if MODE != "webull":
        note("test account: unlimited. Nothing is refused for money — instead "
             "I keep the most cash that was ever tied up at once, which is the "
             "number that tells you what funding this really takes.")


def _extra_month_now():
    import eastern
    return eastern.now().strftime("%Y-%m")


def _extra_active(x):
    """May this extra account take NEW entries right now? (His model, 8/20:
    the accounts are subscription-based — a toggle plus a month stamp. Flip
    it ON and it's paid through the END of the current month; when the month
    rolls over it EXPIRES by itself until it's flipped on again.) Exits,
    trims and stop management always keep working on anything already held —
    an expired subscription must never strand an open position."""
    nm = x.get("name")
    for a in (EXEC.get("webull_extra_accounts") or []):
        if str(a.get("name") or "").strip()[:24] == nm:
            if not a.get("enabled", True):
                return False
            return str(a.get("paid_month") or "") == _extra_month_now()
    return False


def _extra_state_path(name):
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                   for ch in str(name))[:32] or "acct"
    return os.path.join(HERE, "state-%s.json" % safe)


def _connect_extras():
    """More Webull accounts firing from the same bot (his ask, 8/18): every
    LIVE order — options and futures — mirrors 1:1 onto each account listed
    in execution.webull_extra_accounts, and each account runs its own full
    book: its own fill-watch, its own resting stop and ratchet, its own trims,
    its own adoption/protection of hand trades, and journal rows tagged with
    the account's name. TEST/paper rooms never touch these accounts.
    With the list empty this whole feature is dormant."""
    global WB_EXTRA
    old = {x["name"]: x for x in WB_EXTRA}
    fresh = []
    import copy
    for acc in (EXEC.get("webull_extra_accounts") or []):
        name = str(acc.get("name") or "acct%d" % (len(fresh) + 2)).strip()[:24]
        if not acc.get("enabled", True):
            continue
        if not (acc.get("app_key") and acc.get("app_secret")):
            note("ACCT %s skipped — no keys saved for it yet" % name)
            continue
        # Same rule as the main book: never rebuild under an open position —
        # the old book's watchdog is the only thing holding its stop.
        if name in old and old[name]["book"].open_count():
            fresh.append(old[name])
            note("ACCT %s kept as-is — %d position(s) still open on it"
                 % (name, old[name]["book"].open_count()))
            continue
        try:
            from webull_options import WebullOptions
            c = copy.deepcopy(CFG)
            wx = c.setdefault("execution", {}).setdefault("webull", {})
            wx["app_key"] = acc["app_key"]
            wx["app_secret"] = acc["app_secret"]
            wx["paper_trading"] = False
            # A login with SEVERAL margin accounts needs to be told which one
            # (8/21: L's login had two). The popup's optional account-id field
            # lands here; empty keeps the automatic pick.
            if acc.get("account_id"):
                wx["account_id"] = str(acc["account_id"]).strip()
            cli = WebullOptions(c)
            acct_no = cli.connect()
            if getattr(cli, "paper", False):
                note("ACCT %s NOT connected — its keys came up paper, and the "
                     "extra accounts are live-only" % name)
                continue
            cli.entry_price = "ask"     # same standing rule as every executor
            if WB_LIVE is not None:
                cli.quote_client = WB_LIVE   # one OPRA feed prices them all
            w = EXEC.get("webull", {}) or {}
            bk = positions.Book(
                cli, note,
                stop_pct=float(w.get("stop_loss_pct", 20)),
                fill_seconds=float(w.get("entry_fill_seconds", 180)),
                poll_seconds=float(w.get("fill_poll_seconds", 5)),
                simulated=False, unlimited=False)
            bk.save_day = save_day
            bk.broker_resolver = lambda pos, _c=cli: _c
            bk.adopt_max_qty = int(
                (CFG.get("execution") or {}).get("adopt_max_qty", 3))
            if BOOK is not None:
                bk.expiry_parser = BOOK.expiry_parser
                bk.occ_builder = BOOK.occ_builder
            bk.fut_mult = FUT_MULT
            _st = (CFG.get("strategy") or {})
            bk.take_profit_on = bool(_st.get("take_profit_hard_close", False))
            bk.ratchet_on = bool(_st.get("ratchet_enabled", True))
            bk.take_profit_pct = float(_st.get("take_profit_pct", 20.0))
            bk.stop_pct = float(_st.get("stop_loss_pct", 10.0))
            try:
                cli.stop_pct = bk.stop_pct
            except Exception:                           # noqa: BLE001
                pass
            # Its own memory file, so ITS swings survive a restart too.
            try:
                with open(_extra_state_path(name), encoding="utf-8") as f:
                    d = json.load(f)
                bk.restore_state(d.get("state") or {},
                                 d.get("date") == today_str())
                bk.purge_stale_futures(note)
            except Exception:                           # noqa: BLE001
                pass
            fresh.append({"name": name, "client": cli, "book": bk})
            WB_EXTRA_ERR.pop(name, None)
            WB_EXTRA_CHOICES.pop(name, None)
            note("ACCT %s connected — Webull account %s now mirrors every "
                 "LIVE order with its own stops and its own book"
                 % (name, acct_no))
        except Exception as e:                          # noqa: BLE001
            msg = str(e)
            # The "several accounts on one login" wall (8/21, L's login had
            # two MARGIN accounts): don't just refuse — PROBE each candidate
            # and report its buying power, so the popup row itself says which
            # id to paste. This runs once per connect attempt, not per trade.
            if "more than one" in msg.lower():
                try:
                    import re as _re
                    from webull_options import WebullOptions as _WO
                    ids = _re.findall(r"([A-Z0-9]{16,})\s*\(", msg)
                    choices = []
                    for _aid in ids[:4]:
                        try:
                            c2 = copy.deepcopy(CFG)
                            w2 = c2.setdefault("execution", {}).setdefault(
                                "webull", {})
                            w2["app_key"] = acc["app_key"]
                            w2["app_secret"] = acc["app_secret"]
                            w2["paper_trading"] = False
                            w2["account_id"] = _aid
                            _c2 = _WO(c2)
                            _c2.connect()
                            _bp = _c2.buying_power()
                            choices.append({"id": _aid,
                                            "bp": (round(float(_bp), 0)
                                                   if _bp is not None
                                                   else None)})
                        except Exception as _e2:        # noqa: BLE001
                            choices.append({"id": _aid, "bp": None,
                                            "err": str(_e2)[:60]})
                    WB_EXTRA_CHOICES[name] = choices
                    msg = ("this login has %d accounts — CLICK the one to "
                           "trade from:" % len(ids))
                except Exception:                       # noqa: BLE001
                    pass
            WB_EXTRA_ERR[name] = msg[:240]
            note("ACCT %s NOT connected — %s" % (name, msg[:220]))
    WB_EXTRA = fresh


AI_KEY_OK = None      # None = never probed; True/False = the last real answer


def probe_ai_key():
    """Actually ASK Anthropic whether the saved AI key works (his confusion,
    8/17: the popup showed AI ✅ for a key the API rejects — a checkmark that
    only meant "something is pasted in the box"). One tiny request, cached
    until the key changes; the status line now tells the truth."""
    global AI_KEY_OK
    key = ((EXEC.get("ai_reader") or {}).get("api_key") or "").strip()
    if not key:
        AI_KEY_OK = None
        return
    try:
        import requests
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key,
                                   "anthropic-version": "2023-06-01",
                                   "Content-Type": "application/json"},
                          json={"model": "claude-haiku-4-5-20251001",
                                "max_tokens": 1,
                                "messages": [{"role": "user", "content": "hi"}]},
                          timeout=(4, 8))
        AI_KEY_OK = bool(200 <= r.status_code < 300)
        if AI_KEY_OK:
            note("AI READ  key verified — reading is ON")
        else:
            note("AI READ  key INVALID (HTTP %s) — that's a pasted token, not "
                 "an API key? Get one at console.anthropic.com -> API Keys "
                 "(starts sk-ant-api03) and paste it in the popup."
                 % r.status_code)
    except Exception as e:                              # noqa: BLE001
        AI_KEY_OK = None      # network blip — unknown, not "broken"
        note("AI READ  couldn't verify the key (%s) — will act as if it "
             "works until proven otherwise" % str(e)[:80])


TS_KEY_OK = None      # None = never probed; True/False = Topstep's last answer


def probe_topstep_key():
    """Actually LOG IN to TopstepX with the saved username+key (his ask,
    8/17: a green '✓ Topstep connected' he can trust, like the Webull one).
    One request, cached until the credentials change."""
    global TS_KEY_OK
    ts = (CFG.get("futures_brokers") or {}).get("topstep") or {}
    user = str(ts.get("username") or "").strip()
    key = str(ts.get("api_key") or "").strip()
    if not (user and key):
        TS_KEY_OK = None
        return
    try:
        import requests
        base = str(ts.get("base_url") or "https://api.topstepx.com").rstrip("/")
        r = requests.post(base + "/api/Auth/loginKey",
                          json={"userName": user, "apiKey": key},
                          timeout=(4, 8))
        j = r.json() if r.status_code == 200 else {}
        TS_KEY_OK = bool(j.get("token"))
        note("TOPSTEP  key %s for %s"
             % ("VERIFIED — connected" if TS_KEY_OK
                else "REFUSED (errorCode %s) — check username/key on the "
                     "TopstepX API page" % j.get("errorCode"), user))
    except Exception as e:                              # noqa: BLE001
        TS_KEY_OK = None
        note("TOPSTEP  couldn't verify the key (%s) — network, not the key"
             % str(e)[:80])


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
    try:
        print("%s  %s" % (stamp, line), flush=True)
    except Exception:                                   # noqa: BLE001
        # A console that can't take a character must never kill the caller —
        # that's how the 8/25 UBER entries went unrecorded. The UTF-8 file
        # write below is the record that matters; try an ASCII-safe echo and
        # move on regardless.
        try:
            print(("%s  %s" % (stamp, line)).encode("ascii", "replace")
                  .decode("ascii"), flush=True)
        except Exception:                               # noqa: BLE001
            pass
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
    # Every extra account's book remembers its own swings the same way.
    for _x in WB_EXTRA:
        try:
            with open(_extra_state_path(_x["name"]), "w",
                      encoding="utf-8") as f:
                json.dump({"date": today_str(),
                           "state": _x["book"].export_state()}, f)
        except Exception:                               # noqa: BLE001
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
    # Day-old adopted futures the broker can't confirm are ghosts — his
    # "why is it holding MESU6, MNQU6?" (8/17). Cleared once per boot.
    try:
        BOOK.purge_stale_futures(note)
    except Exception:                                   # noqa: BLE001
        pass


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
        _tbl = BOOK.table()
        # Extra accounts' trades land in the same day file, each row tagged
        # with the account's name — that's what fills the journal's
        # "account" column so he can see per-account results.
        for _x in WB_EXTRA:
            try:
                for _r in _x["book"].table():
                    _rr = dict(_r)
                    _rr["account"] = _x["name"]
                    _tbl.append(_rr)
            except Exception:                           # noqa: BLE001
                pass
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": today_str(), "mode": MODE,
                       "table": _tbl, "wallet": BOOK.wallet()}, f)
    except OSError:
        pass        # a full disk must never take down the trading path
    # HANDOFF-<date>.md — his ask (8/18): "make a file handoff every single
    # day with the date on it." One page a fresh session (his, or a fresh
    # Claude) can stand on: what ran today, what traded, what's still open,
    # where the deeper records live. Rewritten on every event like the
    # journal, into handoffs\, and the auto-push carries it to GitHub.
    try:
        os.makedirs(os.path.join(HERE, "handoffs"), exist_ok=True)
        _rows = BOOK.table()
        _w = BOOK.wallet() or {}
        _open = [r for r in _rows if not r.get("all_out")]
        _done = [r for r in _rows if r.get("all_out")]

        def _ct(r):
            if r.get("strike") is not None:
                return "%g%s %s" % (r.get("strike"),
                                    "C" if str(r.get("side") or "")
                                    .upper().startswith("C") else "P",
                                    r.get("expiry") or "")
            return "futures" if r.get("kind") == "future" else "?"

        def _line(r):
            pl = r.get("pl")
            pct = r.get("pl_pct")
            return ("- %s **%s %s** x%s — %s%s · %s%s · %s" % (
                ("(Swing) " if r.get("swing") else ""),
                r.get("symbol") or "?", _ct(r), r.get("qty") or 0,
                ("%+.0f$" % pl) if pl is not None else "?",
                (" (%+.1f%%)" % pct) if pct is not None else "",
                r.get("who") or "?",
                (" · " + r.get("room")) if r.get("room") else "",
                r.get("exit_by") or r.get("state") or ""))

        _L = ["# Discord Sniper — handoff %s" % today_str(), ""]
        _L.append("Mode: %s · realised today: %+.0f$ · %d closed / %d open"
                  % (MODE, float(_w.get("realised") or 0),
                     len(_done), len(_open)))
        _L.append("")
        if _open:
            _L.append("## Still open")
            _L += [_line(r) for r in _open]
            _L.append("")
        if _done:
            _L.append("## Closed today")
            _L += [_line(r) for r in _done]
            _L.append("")
        _L += ["## Where everything lives",
               "- journal.csv — every trade, all days: who/room/side/%/exit_by/signal",
               "- days/%s.json — today's full table for replay" % today_str(),
               "- extension/rooms.txt — THE channel list (tabs + trading, one file)",
               "- settings.json — keys and rules; gitignored, never leaves this PC",
               "- trades.log / bridge.log — the raw story, minute by minute",
               "",
               "Rules of the house: entries bid at the caller's price or better; "
               "exits at the ask; RN pullback is one Strategies toggle; manual "
               "trades are never auto-stopped; Topstep obeys Combine rules with "
               "the consistency lock; every popup checkmark is verified by a "
               "real login."]
        with open(os.path.join(HERE, "handoffs",
                               "HANDOFF-%s.md" % today_str()),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(_L) + "\n")
    except Exception:                                   # noqa: BLE001
        pass        # the handoff is a convenience, never a trading risk

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
            # Built for filtering (his ask, 8/17): options fill "side"
            # (CALL/PUT), futures fill "direction" (LONG/SHORT), P&L also as
            # a percent, "exit_by" says what pulled the trigger (room call /
            # bot stop / bot take-profit / you at Webull), and "signal" is
            # the alert word for word.
            w.writerow(["date", "room", "caller", "symbol", "side", "direction",
                        "contract", "qty", "avg_in", "exits", "P&L", "P&L %",
                        "max run-up %", "max drawdown %",
                        "opened", "closed", "status", "exit_by",
                        "account", "signal"])
            for date, r in allrows:
                is_call = str(r.get("side") or "").upper().startswith("C")
                ct = ""
                side_col = ""
                direction = ""
                if r.get("strike") is not None:
                    ct = "%s%s %s" % (r.get("strike"), "C" if is_call else "P",
                                       r.get("expiry") or "")
                    side_col = "CALL" if is_call else "PUT"
                elif r.get("kind") == "future":
                    ct = "futures"
                    direction = ("SHORT" if int(r.get("direction") or 1) < 0
                                 else "LONG")
                ex = "; ".join(
                    "%s@%s%s" % (e.get("qty"), e.get("price"),
                                 "" if e.get("pl") is None
                                 else " (%+.0f)" % e["pl"])
                    for e in (r.get("exits") or []))
                pl_pct = r.get("pl_pct")
                hi = r.get("hi_pct")
                lo = r.get("lo_pct")
                w.writerow([date, r.get("room") or "", r.get("who") or "?",
                            r.get("symbol") or "", side_col, direction, ct,
                            r.get("qty") or 0,
                            r.get("avg") if r.get("avg") is not None else "",
                            ex, r.get("pl"),
                            ("%+.1f%%" % pl_pct) if pl_pct is not None else "",
                            ("%+.1f%%" % hi) if hi is not None else "",
                            ("%+.1f%%" % lo) if lo is not None else "",
                            _hhmm(r.get("opened")), _hhmm(r.get("closed")),
                            r.get("state") or "",
                            r.get("exit_by") or "",
                            r.get("account")
                            or ("live" if r.get("live") else "paper"),
                            r.get("raw") or ""])
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
    the only live trade in that ticker — but ONLY when that trade is this same
    trader's, or unattributed, or this order named no trader. A DIFFERENT named
    trader's percentage must never resolve onto your position (8/19: KingBeeAri's
    bare "10%" closed stockguy007's AAPL swing because this fell through to "the
    only AAPL, any trader"). Failing all that, the trader key as-is (reads as
    "not in it" downstream, and says so)."""
    key = tkey(order)
    if BOOK is None or BOOK.state_of(key) is not None:
        return key
    others = BOOK.find_by_symbol(order.get("symbol"))
    if len(others) == 1:
        cand = others[0]
        want = str(order.get("trader") or "").strip().lower()
        owner = cand.rsplit("|", 1)[0]          # key is "who|SYM"
        if not want or owner in ("", "?") or owner == want:
            return cand
        # a different named trader — don't hijack their trade
    return key


# ---- NO-OTM rule (his call, 8/20, replacing the 8/19 "3 strikes ITM"): -----
# No contract is bought OUT of the money. A called strike that's already ATM
# or ITM is bought exactly as called, at the caller's price cap. A called
# strike that's OTM snaps to the NEAREST qualifying strike (ATM or first ITM,
# quote-verified so it actually exists) — and since that contract costs more
# than their OTM one, the price cap comes off and the entry pays the ask.
# Applies to every options entry, every ticker, every expiry.
def _no_otm_translate(order, client):
    """Rewrite an OTM order['strike'] to the nearest ATM/ITM strike. Returns a
    note string when it translated, None when the strike already qualifies or
    the rule can't be applied. Never raises — trouble leaves the caller's
    strike untouched."""
    try:
        if order.get("action") not in ("OPEN", "ADD"):
            return None
        if order.get("kind") in ("future", "equity"):
            return None
        sym = str(order.get("symbol") or "").upper()
        if order.get("strike") is None or not sym:
            return None
        # An ADD onto something already held buys MORE OF THAT CONTRACT.
        if order.get("action") == "ADD" and BOOK is not None:
            held = BOOK.info(tkey(order)) or {}
            if held.get("strike") is not None:
                order["strike"] = held["strike"]
                return None
        px = None
        for _c in (client, WB_LIVE, WB):
            if _c is None:
                continue
            try:
                px = _c.stock_price(sym)
            except Exception:                   # noqa: BLE001
                px = None
            if px:
                break
        if not px:
            return None      # can't judge moneyness — the call stands as-is
        px = float(px)
        old = float(order.get("strike"))
        is_call = str(order.get("side") or "").upper().startswith("C")
        # Already ATM or ITM? Then it's THEIR contract, THEIR price — done.
        if (is_call and old <= px) or ((not is_call) and old >= px):
            return None
        from webull_options import expiry_to_date, occ_symbol
        import datetime as _dt
        import math
        exp = _dt.date.fromisoformat(str(expiry_to_date(order.get("expiry"))))
        kind = "CALL" if is_call else "PUT"
        _q = client or WB_LIVE or WB

        def _quotes(cand):
            try:
                occ = occ_symbol(sym, exp.isoformat(), kind, cand)
                ask, bid, _r = _q.ask_bid(occ)
                return ask is not None or bid is not None
            except Exception:                   # noqa: BLE001
                return False

        # ONE STRIKE OTM is allowed now (his call, 8/24: "1 strike above is
        # good" — the old snap-to-ITM was buying $750 contracts off $300
        # calls on Mag7 names). Find the first OTM rung beyond the stock:
        # smallest quoted strike above px on a call, largest below on a put.
        # Their strike AT that rung stands as called; anything deeper snaps
        # TO the rung — cheap, and still the closest thing to their intent.
        first_otm = None
        _steps = set()
        for inc in (0.5, 1.0, 2.5, 5.0):
            base = (math.floor(px / inc) + 1 if is_call
                    else math.ceil(px / inc) - 1) * inc
            c = round(base, 2)
            # skip rungs that land ATM/ITM by rounding
            if c > 0 and ((is_call and c > px) or ((not is_call) and c < px)):
                _steps.add(c)
        for cand in sorted(_steps, reverse=not is_call):
            if _quotes(cand):
                first_otm = cand
                break
        if first_otm is not None and                 ((is_call and old <= first_otm + 1e-9)
                 or ((not is_call) and old >= first_otm - 1e-9)):
            return None      # within one strike OTM — their contract stands
        best = first_otm
        why = "1 strike OTM"
        if best is None:
            # No OTM rung quotes — fall back to the old inward walk (ATM/ITM),
            # quote-verified. TWLO 2440C (8/21) lives in this branch.
            cands = set()
            for inc in (0.5, 1.0, 2.5, 5.0):
                base = (math.floor(px / inc) if is_call
                        else math.ceil(px / inc)) * inc
                for step in range(0, 4):
                    c = round(base - step * inc if is_call
                              else base + step * inc, 2)
                    if c > 0:
                        cands.add(c)
            for cand in sorted(cands, reverse=is_call):
                if _quotes(cand):
                    best = cand
                    break
            why = "nearest qualifying"
        if best is None:
            note("NO-OTM   %s — %g%s is too far OTM (stock %.2f) but no "
                 "closer strike answered a quote; the caller's strike stands"
                 % (sym, old, "C" if is_call else "P", px))
            return None
        order["strike"] = best
        order["limit"] = None       # their premium priced their OTM strike
        return ("NO-OTM   %s: their %g%s was too far OTM (stock %.2f) -> %s "
                "%g%s"
                % (sym, old, "C" if is_call else "P", px, why,
                   best, "C" if is_call else "P"))
    except Exception as _e:                     # noqa: BLE001
        try:
            note("NO-OTM   %s — check skipped (%s)"
                 % (order.get("symbol"), str(_e)[:80]))
        except Exception:                       # noqa: BLE001
            pass
        return None


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
        #
        # PHANTOM EXIT (9/2): unless the entry hunt for this exact contract is
        # still armed and waiting for its pullback. Nothing was ever bought,
        # so this is a retraction of the hunt — the same shape as RETRACT.
        # 9/2 11:13: Midas's NVDA 225C 9/4 close fired while the hunt was
        # still waiting for $225 (it later timed out unfilled); Webull
        # refused the sell with a 417 covered-call error.
        if _PULLBACK is not None:
            try:
                if _PULLBACK.cancel_order(order):
                    return False, False, (True,
                        "%s's entry hunt was still waiting for the pullback — "
                        "stood it down instead of selling a contract you "
                        "never bought." % sym)
            except Exception:                           # noqa: BLE001
                pass
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
                          "incoming_dir": nt.get("incoming_dir", ""),
                          "atm_template": nt.get("atm_template", "")}
    tv = fb.get("tradovate") or {}
    out["tradovate"] = {"enabled": bool(tv.get("enabled")),
                        "username": tv.get("username", ""),
                        "demo": bool(tv.get("demo")),
                        "has_password": bool(tv.get("password"))}
    ts = fb.get("topstep") or {}
    out["topstep"] = {"enabled": bool(ts.get("enabled")),
                      "username": ts.get("username", ""),
                      "base_url": ts.get("base_url", "https://api.topstepx.com"),
                      "has_password": bool(ts.get("api_key")),
                      # keys saved at all, and whether TopstepX actually
                      # ACCEPTED them (probe_topstep_key) — the popup's
                      # green box keys off these (8/17).
                      "keys_in": bool(ts.get("api_key") and ts.get("username")),
                      "verified": TS_KEY_OK}
    # Extra Webull accounts (8/18): what's configured and which of those the
    # bridge actually logged in to — the popup's green checks key off this.
    _live = {x["name"]: x for x in WB_EXTRA}
    out["webull_extras"] = []
    for a in (EXEC.get("webull_extra_accounts") or []):
        _nm = str(a.get("name") or "").strip()[:24]
        _bp = None
        if _nm in _live:
            try:      # cached ~8s inside the client — cheap on the 4s poll
                _bp = _live[_nm]["client"].buying_power()
            except Exception:                           # noqa: BLE001
                _bp = None
        out["webull_extras"].append(
            {"name": _nm,
             "enabled": bool(a.get("enabled", True)),
             "keys_in": bool(a.get("app_key") and a.get("app_secret")),
             "connected": _nm in _live,
             "why": WB_EXTRA_ERR.get(_nm, ""),
             "choices": WB_EXTRA_CHOICES.get(_nm, []),
             "buying_power": _bp,
             "paid_month": str(a.get("paid_month") or ""),
             "month_now": _extra_month_now(),
             "active": (bool(a.get("enabled", True))
                        and str(a.get("paid_month") or "")
                        == _extra_month_now())})
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
# ONE contract, ONE entry, 20 seconds (8/25, the UBER triple-buy): the same
# spoken line hit from three relays ~1s apart and the extension's echo-lock
# set too late while the AI reads were still running — three real buys.
# This is the bridge-side backstop every path must pass: an OPEN for a
# contract that was accepted in the last 20s is the echo, whoever sent it.
_RECENT_CONTRACTS = {}      # "SYM|side|strike|expiry" -> timestamp
WHOP_FEED = []              # whop-api reader queue: [{_i, platform, text...}]
WHOP_FEED_N = [0]           # monotonic counter for /whopfeed cursors
WHOP_FEED_OK = [0.0]        # ts of the last SUCCESSFUL room read — "active"
                            # means delivering, never just "a key exists"
                            # (8/30: key valid but member reads are walled;
                            # tabs must never stand down for a dead feed)


# --- round-number pullback (HIS strategy, 8/11/26) ---------------------------
# Two entry modes now, chosen PER ROOM in the popup: "instant" (the normal
# at-the-ask fill) and "pullback" (wait for the stock to touch the next whole
# dollar, then buy). The paper-force is LIFTED (his call, 8/17): a pullback
# entry now spends whatever the room's own TESTING/LIVE toggle says, exactly
# like an instant entry — RN wait on a LIVE room is real money.
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
    # live flag carries through from the room's own toggle now (8/17) —
    # the paper-force ("live"=False) is gone, his call.
    # At the touch, CROSS THE ASK (his call, 8/17): "change it to the ask
    # just in case — i would do market order but webull doesnt let you."
    # Waiting for the pullback already earned the discount; when the level
    # prints he wants the fill, not a resting bid that watches the bounce.
    o["price_mode"] = "ask"
    return _place_impl(o)


def _pullback_close(order, why):
    # LIVE FLAG CARRIES THROUGH (9/2). This used to hardcode live=False while
    # _pullback_enter passed the room's own toggle — so a REAL entry got a
    # PAPER exit, which fell into the "test room, paper execution is off"
    # branch and sent nothing. 9/2 11:35: SPY 766C 9/3 filled for real at
    # 2.18, the stock stop hit at 11:43, the exit was refused as paper, and
    # he had to close it by hand at 1.87 (-$31). An exit must always route to
    # the same account the entry went to — the position is real either way.
    return _place_impl({
        "action": "CLOSE", "symbol": order.get("symbol"),
        "side": order.get("side"), "strike": order.get("strike"),
        "expiry": order.get("expiry"), "trader": order.get("trader"),
        "kind": order.get("kind") or "option",
        "live": bool(order.get("live")),
        "raw": "pullback exit: " + str(why), "source": "pullback"})


def _underlying_stop_watch(order):
    """UNDERLYING hard stop for an OPTIONS position (his INTC alert, 8/18):
    'BTO INTC 115C @ 0.77, stop loss under 97 hard stop' — the 97 is INTC
    THE STOCK, not the premium. This watches the stock and closes the
    option the moment it crosses the level: calls close at/below the stop,
    puts at/above. Stands down by itself when the position is gone (their
    exit, the premium bracket, or you at Webull got there first)."""
    sym = str(order.get("symbol") or "").upper()
    stop = float(order.get("their_stop") or 0)
    side = str(order.get("side") or "").upper()
    if not (sym and stop > 0):
        return
    _wkey = find_key(order)
    is_call = side.startswith("C")
    note("UNDER-STOP %s: watching the STOCK — the option closes if %s "
         "prints %s %.2f (their hard stop)"
         % (sym, sym, "at/under" if is_call else "at/over", stop))
    misses = 0
    while True:
        time.sleep(2.0)
        # LIVE LEVEL (8/29, "351 new stop loss"): the trader moves their
        # stop mid-trade; the book carries the current number and this
        # watcher follows it instead of the level it was born with.
        try:
            _pp = BOOK.info(_wkey) if BOOK is not None else None
            if _pp and _pp.get("their_stop"):
                _ns = float(_pp["their_stop"])
                if _ns > 0 and abs(_ns - stop) > 1e-9:
                    note("UNDER-STOP %s: their stop MOVED %.2f -> %.2f — "
                         "following it" % (sym, stop, _ns))
                    stop = _ns
        except Exception:                               # noqa: BLE001
            pass
        try:
            if BOOK is None or not BOOK.holding(find_key(order)):
                return          # closed some other way — stand down quietly
        except Exception:                               # noqa: BLE001
            return
        try:
            px = float(_pullback_quote(sym))
            misses = 0
        except Exception as e:                          # noqa: BLE001
            misses += 1
            if misses >= 30:    # ~a minute of dead quotes
                note("UNDER-STOP %s: stock quotes stopped answering (%s) — "
                     "watcher standing down; the premium bracket still "
                     "guards the option." % (sym, str(e)[:60]))
                return
            continue
        hit = (px <= stop) if is_call else (px >= stop)
        if hit:
            note("UNDER-STOP %s: the stock printed %.2f — through their "
                 "%.2f hard stop. Closing the option now."
                 % (sym, px, stop))
            try:
                _place_impl({"action": "CLOSE", "symbol": sym,
                             "side": order.get("side"),
                             "strike": order.get("strike"),
                             "expiry": order.get("expiry"),
                             "trader": order.get("trader"),
                             "kind": order.get("kind") or "option",
                             "live": bool(order.get("live")),
                             "raw": "underlying hard stop %.2f hit "
                                    "(stock at %.2f)" % (stop, px),
                             "source": "under-stop"})
            except Exception as e:                      # noqa: BLE001
                note("UNDER-STOP %s: the close FAILED (%s) — go close it "
                     "in Webull." % (sym, str(e)[:80]))
            return


def pullback_manager():
    global _PULLBACK
    if _PULLBACK is None:
        pcfg = (CFG.get("pullback") or {})
        _PULLBACK = _pullback.Pullback(
            _pullback_quote, _pullback_enter, _pullback_close, note,
            timeout_seconds=float(pcfg.get("timeout_seconds", 300)),
            poll_seconds=float(pcfg.get("poll_seconds", 2)),
            # Entry wait polls every second (his ask, 8/17) — the touch is
            # the whole game there. Management keeps the calmer 2s above.
            entry_poll_seconds=float(pcfg.get("entry_poll_seconds", 1)))
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
    # UNDERLYING hard stop (his INTC alert, 8/18): an accepted OPTIONS entry
    # that carried "stop loss under $X" gets a stock watcher — see
    # _underlying_stop_watch. Futures keep their own broker-side levels.
    try:
        ok0 = bool(result[0]) if isinstance(result, tuple) else False
        if (ok0 and order.get("action") == "OPEN"
                and (order.get("kind") or "option") != "future"
                and order.get("their_stop")):
            threading.Thread(target=_underlying_stop_watch,
                             args=(dict(order),), daemon=True).start()
    except Exception:                                   # noqa: BLE001
        pass
    return result


def _place_impl(order):
    """Returns (ok, message). Never raises — a crash here would look to the
    extension exactly like a rejected order, and you'd never know which."""
    sym = str(order.get("symbol", "")).upper()
    action = order.get("action")
    key = find_key(order) if BOOK is not None else tkey(order)

    # STOPMOVE (8/29, his annotation: "Tesla three fifty one new stop
    # loss" = the UNDERLYING price 351 is the new stop). Updates the
    # trader's held position; the running underlying watcher follows the
    # book's number, and a position that had no stock-level watcher yet
    # gets one now. Never an exit, never an entry.
    if action == "STOPMOVE":
        if order.get("be"):
            _k2 = find_key(order)
            if BOOK is not None and BOOK.stop_to_breakeven(_k2):
                note("BE-STOP  %s — their call: breakeven stops. The resting "
                     "stop now sits AT the entry; scratch possible, loss "
                     "impossible." % sym)
                return True, ("stop moved to BREAKEVEN on %s — can't go "
                              "red from here" % sym)
            return False, ("no held %s position to set a breakeven stop on"
                           % sym)
        _lvl = order.get("their_stop")
        if not _lvl or BOOK is None:
            return False, "a stop move needs a level and a book"
        _k2 = find_key(order)
        _p2 = BOOK.info(_k2)
        if not _p2 or _p2.get("state") != positions.FILLED:
            return False, ("no held %s position of theirs to move a stop "
                           "on — noted, nothing done" % sym)
        _had = bool(_p2.get("their_stop"))
        BOOK.set_their_stop(_k2, float(_lvl))
        note("UNDER-STOP %s: %s set their stop at %.2f on the STOCK — %s"
             % (sym, order.get("trader") or "the trader", float(_lvl),
                "the watcher follows it" if _had
                else "arming a stock watcher on it now"))
        if not _had:
            threading.Thread(target=_underlying_stop_watch,
                             args=(dict(order,
                                        side=_p2.get("side"),
                                        strike=_p2.get("strike"),
                                        expiry=_p2.get("expiry"),
                                        live=bool(_p2.get("live"))),),
                             daemon=True).start()
        return True, ("their stop on %s is now %.2f on the stock — watched "
                      "on this PC" % (sym, float(_lvl)))

    # RETRACTION (8/26): "NOT READY YET REVISING" — pull the trader's
    # resting bids and kill their armed pullback hunts. Never touches a
    # FILLED position: a retraction cancels an entry, it doesn't exit one.
    if action == "RETRACT":
        _who = str(order.get("trader") or "")
        _pulled = BOOK.cancel_working_for(_who) if BOOK is not None else []
        _hunts = 0
        try:
            if _PULLBACK is not None:
                _hunts = _PULLBACK.cancel_for(_who)
        except Exception:                               # noqa: BLE001
            pass
        note("RETRACT  %s pulled their call — %s bid(s) cancelled%s"
             % (_who or "trader",
                ", ".join(_pulled) if _pulled else "no",
                (", %d hunt(s) stood down" % _hunts) if _hunts else ""))
        return True, ("retraction honoured — %s resting bid(s) pulled, %d "
                      "pullback hunt(s) cancelled. Held positions untouched."
                      % (len(_pulled), _hunts))

    # THE UBER RULE (8/25): one contract, one entry, whatever the path.
    # The pullback ARM pass is exempt — its real entry comes back through
    # here at the touch (sometimes seconds later) and must not be read as
    # its own echo; the watcher already refuses a duplicate arm.
    if action in ("OPEN", "ADD") \
            and str(order.get("entry_mode") or "") != "pullback":
        _ckey = "|".join(str(x) for x in (sym, order.get("side"),
                                          order.get("strike"),
                                          order.get("expiry")))
        _now = time.time()
        for _k in [k for k, t in list(_RECENT_CONTRACTS.items())
                   if _now - t > 60]:
            _RECENT_CONTRACTS.pop(_k, None)
        _t0 = _RECENT_CONTRACTS.get(_ckey)
        if _t0 and _now - _t0 < 20 and action == "OPEN":
            note("ECHO     OPEN %s refused — this exact contract was bought "
                 "%.0fs ago; the same call from another relay is an echo, "
                 "not a second trade" % (sym, _now - _t0))
            return False, ("that exact contract was entered %.0f seconds "
                           "ago — this copy of the call is an echo, nothing "
                           "was sent" % (_now - _t0))
        _RECENT_CONTRACTS[_ckey] = _now

    # THE POCKET (8/25, his call after the 2-year clock study: minutes
    # :45-:51 carry 27% more dollar-follow-through than the rest of the
    # hour). OFF by default — a popup switch. When ON, a SCALP entry
    # (non-swing option) outside minutes :43-:51 is refused with the clock
    # as the reason. Swings, futures, exits and adds-to-held all pass at
    # any minute — timing gates entries only, never protection.
    if action == "OPEN" and CFG.get("pocket_scalps_only")             and (order.get("kind") or "option") == "option"             and not order.get("swing"):
        try:
            import datetime as _dtp
            from zoneinfo import ZoneInfo as _ZI
            _mn = _dtp.datetime.now(_ZI("America/New_York")).minute
        except Exception:                               # noqa: BLE001
            _mn = None
        if _mn is not None and not (43 <= _mn <= 51):
            note("POCKET   OPEN %s held — it's :%02d and the pocket switch "
                 "is ON (scalps enter :43-:51 only)" % (sym, _mn))
            return False, ("pocket mode is ON: scalp entries only fire "
                           "minutes :43-:51 of each hour (it's :%02d). Flip "
                           "the switch off in the popup to trade any time."
                           % _mn)

    # Round-number pullback mode, per-room. Only OPENs on the managed symbols
    # are deferred to the watcher; anything else (futures, equities, unlisted
    # tickers) falls straight through to the normal instant path — that IS the
    # rule for them. The watcher enters (paper) when the stock touches the
    # level, then manages the exit off the underlying.
    if (action == "OPEN" and str(order.get("entry_mode") or "") == "pullback"
            and order.get("kind") not in ("future", "equity")
            and sym in _pullback.MANAGED):
        # Affordability is checked NOW, at arm time — not five minutes later
        # at the touch (his pick #3, 8/18: MSFT and TSLA both waited, touched
        # their level perfectly, then died on "$204 to spend"). If the money
        # isn't there, say so up front and never arm the watcher.
        try:
            _cli = WB_LIVE if order.get("live") else (WB_LIVE or WB)
            if (_cli is not None and order.get("limit")
                    and hasattr(_cli, "afford_check")):
                _cli.afford_check(float(order["limit"]),
                                  int(order.get("qty") or 1))
        except Exception as _e:                         # noqa: BLE001
            # Refused = the honest "can't afford it" sentence. Matched by
            # name because the class is imported further down this function.
            if _e.__class__.__name__ == "Refused":
                note("PULLBACK refused up front  %s — %s" % (sym, _e))
                return False, ("not arming the round-number wait: %s" % _e)
            # anything else (no quote, no client) -> arm anyway; the real
            # entry at the touch still runs the full checks
        # live flag rides through untouched (8/17, his call): RN wait spends
        # whatever the room's TESTING/LIVE toggle says, same as instant.
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
            # A futures CLOSE the book doesn't hold may still be a REAL
            # position at an armed prop broker (8/20: five NinjaTrader entries
            # went out while Webull had no cash, then every exit died right
            # here on "you're not in it"). Forward the close — NinjaTrader
            # gets CLOSEPOSITION (a no-op when flat), Topstep its own
            # closeContract — instead of stranding the prop position.
            _fb = CFG.get("futures_brokers") or {}
            _prop_on = any((_fb.get(_b) or {}).get("enabled")
                           for _b in ("ninjatrader", "tradovate", "topstep"))
            if order.get("kind") == "future" and _prop_on:
                note("EXIT     %s — not on the Webull book, but a prop broker "
                     "is armed; forwarding the close there" % sym)
                claimed = False
            else:
                note("EXIT     %s" % reply[1])
                return reply
    what = describe(order)

    # Whether THIS order is real money — the room's own toggle, not a global.
    live_order = bool(order.get("live")) and MODE != "webhook"
    # AN EXIT FOLLOWS THE POSITION, NOT THE CALLER (9/2). Every internal
    # watcher builds its own order dict, and one of them (the pullback's
    # stock-stop) carried the wrong live flag for weeks — a real position got
    # a paper exit and nothing was sent. The BOOK knows which account the
    # contracts actually sit in, so on a CLOSE or TRIM it wins over whatever
    # the caller passed. This can only ever turn an exit MORE real; it never
    # sends a live order for a paper position.
    if action in ("CLOSE", "TRIM") and not live_order and BOOK is not None \
            and MODE != "webhook":
        try:
            _hp = BOOK.info(key) or {}
            if _hp.get("live") and not _hp.get("paper"):
                note("EXIT-ROUTE %s — the book holds this one LIVE; sending "
                     "the exit to the real account, not paper"
                     % str(order.get("symbol", "")).upper())
                live_order = True
                order["live"] = True
        except Exception:                               # noqa: BLE001
            pass
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
        # Extra accounts trim too (8/18) — each one sells from ITS holding,
        # sized to what IT owns, through its own book (so its resting stop
        # is handled the same way the main account's is).
        if live_order:
            for _x in WB_EXTRA:
                try:
                    _held = _x["book"].qty_of(key)
                    if _held > 0:
                        _s2 = _x["book"].trim(key, min(want, _held), got,
                                              "their trim" + how + " —")
                        if _s2:
                            note("TRIMMED  [%s] %s — sold %d"
                                 % (_x["name"], sym, _s2))
                except Exception as _e:                 # noqa: BLE001
                    note("ACCT %s trim ERROR %s -> %s"
                         % (_x["name"], sym, str(_e)[:120]))
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
            # Paper execution switched OFF on purpose (8/12) is not a fault.
            # A test room simply has nowhere to send an order now — the
            # in-house sim was retired at his request and the sandbox is
            # deliberately not receiving trades. Say that plainly instead of
            # "reconnect and try again", which reads like something broke.
            if not w.get("paper_trading", False):
                note("TEST     %s  ->  test room, nothing sent (paper "
                     "execution is off)" % what)
                return False, ("%s is a TEST room and paper execution is off, "
                               "so nothing was sent. Flip this room to REAL in "
                               "the Channels tab if you want it to trade."
                               % (order.get("room") or "that room"))
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
                        "extra": nt.get("incoming_dir", ""),
                        # An ATM strategy TEMPLATE name (his ask, 8/19): set it
                        # and every entry is bracketed by NinjaTrader's own ATM
                        # engine (its stop + target), so an NT order is never
                        # naked. Made once in NT8 (Chart Trader/ATM > save a
                        # template) and named here. Blank = no NT-side stop.
                        "atm_template": nt.get("atm_template", ""),
                        "enabled": True})
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
                        # "URL|ACCOUNTNAME" pins WHICH Topstep account trades
                        # (8/23: the XFA arrived; without the pin, accounts[0]
                        # could be the old locked combine).
                        "extra": (ts.get("base_url") or "https://api.topstepx.com")
                                 + (("|" + ts["account_name"])
                                    if ts.get("account_name") else ""),
                        # The account-safety knobs (8/17): start_balance arms
                        # the consistency lock (put the account size there,
                        # e.g. 50000), daily_loss_stop is his own tighter
                        # daily stop, consistency_pct defaults to Topstep's
                        # 50% (set 0.40 on the stricter payout path).
                        "start_balance": ts.get("start_balance"),
                        "daily_loss_stop": ts.get("daily_loss_stop"),
                        "consistency_pct": ts.get("consistency_pct"),
                        # Futures ratchet (8/22): server-side TRAILING stop on
                        # every Topstep entry; set trail=false for fixed stops.
                        "trail": ts.get("trail", True),
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
                # Every extra Webull account fires the same futures order
                # (8/18), each into its own book. One account's refusal
                # (no cash, no subscription) never blocks the others.
                if live_order:
                    for _x in WB_EXTRA:
                        # subscription gates ENTRIES only — a close or trim on
                        # something already held always goes through
                        if order.get("action") in ("OPEN", "ADD") \
                                and not _extra_active(_x):
                            continue
                        # A login with no futures account can't take futures —
                        # skip quietly instead of logging the same routing
                        # error on every call (8/21, L's log noise).
                        if not getattr(_x["client"], "futures_account_id",
                                       None):
                            continue
                        try:
                            import webull_futures as _wf
                            _ok2, _msg2 = _wf.execute(
                                _x["client"], _x["book"], order, key, note)
                            results.append("[%s] %s" % (_x["name"], _msg2))
                            if _ok2:
                                any_sent = True
                        except Exception as _e:         # noqa: BLE001
                            note("FUTURES  [%s] ERROR %s -> %s"
                                 % (_x["name"], what, str(_e)[:120]))

            # NinjaTrader / Tradovate legs — also send; they only touch the book
            # if Webull didn't already (so the position is never counted twice).
            if armed_props:
                import props as prop_mod
                sent, refused = prop_mod.execute_all(armed_props, order, note)
                # Refusals land in trades.log too (8/18): the extension's
                # log got reset and took every "why didn't Topstep fire?"
                # answer with it. Never again — the reason is written where
                # nothing can erase it.
                for _r in refused:
                    note("PROP-NO  %s" % str(_r)[:220])
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
        # A futures root with a strike on it (Brett's "ES 768P", 8/20) is a
        # FUTURES OPTION — Webull's options endpoint can never take it, so it
        # died as a raw PARAM_ERR. Refuse it in words instead.
        if action in ("OPEN", "ADD") and order.get("strike") is not None \
                and str(order.get("symbol") or "").upper() in (
                    "ES", "NQ", "MES", "MNQ", "YM", "MYM", "RTY", "M2K",
                    "CL", "MCL", "GC", "MGC"):
            note("REFUSED  %s — that's an option on a FUTURES contract "
                 "(%s %sP/C); Webull's options API doesn't trade those. "
                 "Nothing was sent." % (what, order.get("symbol"),
                                        order.get("strike")))
            if claimed:
                BOOK.release(key)
            return False, ("that's a futures option (%s with a strike) — "
                           "Webull can't place those, so nothing was sent."
                           % order.get("symbol"))
        # NO-OTM rule (his call, 8/20) — an OTM strike snaps to the nearest
        # ATM/ITM one before anything is priced or sent. Runs here so instant
        # entries, the pullback's at-the-touch entry, AND every mirrored
        # extra account all buy the same qualifying contract.
        if action in ("OPEN", "ADD"):
            _t = _no_otm_translate(order, client)
            if _t:
                note(_t)
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
                # Linked entry+stop group on LIVE entries (his ask, 8/19):
                # the stop leg is born with the order, broker-side — no naked
                # moment, no watchdog scramble. Falls back to the plain order
                # by itself if Webull won't take the group.
                _brk = None
                if live_order and (CFG.get("execution", {}).get("webull", {})
                                   or {}).get("bracket_entries", True):
                    _brk = float((CFG.get("strategy") or {})
                                 .get("stop_loss_pct", 10))
                    # AUTO-SWING (8/25, the UBER lesson): an expiry 14+
                    # days out IS a swing whether or not the caller says the
                    # word — UBER 9/18 wicked out on a 25-cent stock move
                    # and reclaimed the level ten minutes later. Far-dated
                    # contracts get swing treatment by construction.
                    if not order.get("swing"):
                        try:
                            from webull_options import expiry_to_date
                            import datetime as _dt2
                            _ed = _dt2.date.fromisoformat(
                                str(expiry_to_date(order.get("expiry"))))
                            if (_ed - _dt2.date.today()).days >= 14:
                                order["swing"] = True
                                note("SWING    %s — expiry %s is %d days out"
                                     ": treated as a swing (wide stop), no"
                                     " matter what the call said"
                                     % (order["symbol"], _ed.isoformat(),
                                        (_ed - _dt2.date.today()).days))
                        except Exception:               # noqa: BLE001
                            pass
                    # SWING stops (his call, 8/24 — the HOOD lesson: a
                    # 3-week swing died in 3 minutes on a scalp's -10%).
                    # A swing with THEIR stock level runs on that level
                    # (the underlying watcher, armed in place()) and takes
                    # no premium stop; a swing without one gets a wide
                    # -25% so it can breathe. Scalps keep the -10%.
                    if order.get("swing"):
                        if order.get("their_stop"):
                            _brk = None
                            note("SWING    %s — no premium stop; running "
                                 "their stock level %g instead"
                                 % (order["symbol"],
                                    float(order["their_stop"])))
                        else:
                            _brk = 25.0
                            note("SWING    %s — wide -25%% stop (swing, no "
                                 "level given)" % order["symbol"])
                ticket = client.buy(order["symbol"], order.get("side"),
                                    order.get("strike"), order.get("expiry"), qty,
                                    their_price=order.get("limit"),
                                    # "ask" only on pullback entries (8/17):
                                    # the discount was earned waiting for the
                                    # touch — at the trigger he wants IN.
                                    price_mode=order.get("price_mode"),
                                    bracket_stop_pct=_brk)
                if _brk and not ticket.get("stop_child"):
                    _cn = getattr(client, "_combo_no", "")
                    if _cn:
                        note("BRACKET  %s — Webull wouldn't take the linked "
                             "group (%s); entry went plain and the stop arms "
                             "on the fill, as before" % (order["symbol"], _cn))
                ticket["live"] = bool(live_order)   # real money?
                ticket["paper"] = bool(paper)       # or Webull's sim engine
                # "ORDER IN", not "BOUGHT". Webull has accepted a resting bid;
                # nobody has sold you anything yet.
                note("ORDER IN %s" % ticket["what"])
                if BOOK is not None:
                    BOOK.entry_sent(order, ticket)
                    if action == "ADD" and order.get("avg"):
                        BOOK.their_add(key, order["avg"])
                # More accounts, same fire (8/18): every LIVE entry mirrors
                # 1:1 to each extra Webull account. Each account's own book
                # watches its own fill and arms its own stop — one account
                # refusing never stops the others.
                if live_order:
                    for _x in WB_EXTRA:
                        if not _extra_active(_x):
                            continue   # subscription off/expired: no NEW entries
                        try:
                            _t2 = _x["client"].buy(
                                order["symbol"], order.get("side"),
                                order.get("strike"), order.get("expiry"), qty,
                                their_price=order.get("limit"),
                                price_mode=order.get("price_mode"),
                                bracket_stop_pct=_brk)
                            _t2["live"] = True
                            note("ORDER IN [%s] %s" % (_x["name"], _t2["what"]))
                            _x["book"].entry_sent(order, _t2)
                            if action == "ADD" and order.get("avg"):
                                _x["book"].their_add(key, order["avg"])
                        except Exception as _e:         # noqa: BLE001
                            note("ACCT %s REFUSED %s -> %s"
                                 % (_x["name"], what, str(_e)[:140]))
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
                # Through the book's retry, not straight at the broker: a
                # room exit hitting a resting order used to just ERROR and
                # leave him holding it ("all out of AAPL @ 3.75", 8/12).
                try:
                    res = BOOK._sell_retry(client, key, order["symbol"],
                                           order.get("side"), order.get("strike"),
                                           order.get("expiry"), qty,
                                           ref_price=exref)
                except Exception:                       # noqa: BLE001
                    # TWO sellers can collide on the same second — the room's
                    # close and the pullback's stock-stop did exactly that on
                    # SPY 769C (8/18, 11:10:18): the loser 417'd against a
                    # position the winner had already sold, the ERROR read
                    # like he was still holding, and the resting stop was
                    # gone. If the broker shows nothing left, this trade is
                    # DONE — record the close instead of erroring while flat.
                    if BOOK is not None and BOOK._gone_at_broker(
                            client, order["symbol"], order.get("side"),
                            order.get("strike")):
                        note("SOLD     %s — the other seller won the race "
                             "(their close and a stop collided); nothing "
                             "left to sell" % order["symbol"])
                        if claimed:
                            BOOK.finish(key, positions.CLOSED,
                                        "sold in a two-seller collision — "
                                        "the other order won",
                                        price=exref)
                        return True, ("already sold — a stop and their close "
                                      "collided and the first one won. You "
                                      "are FLAT on %s." % order["symbol"])
                    raise
                msg = res["what"]
                note("SOLD     %s" % msg)
                if claimed:
                    BOOK.finish(key, positions.CLOSED,
                                "sold on their call at %.2f" % float(res["limit"]))

                # Mirror the exit onto every extra account that actually
                # holds this trade (8/18). Each one sells through its OWN
                # book's retry, so its own resting stop is pulled first; if
                # its stop already sold it, that's recorded, not an error.
                if live_order:
                    for _x in WB_EXTRA:
                        _xb, _xc = _x["book"], _x["client"]
                        try:
                            if _xb.qty_of(key) <= 0:
                                continue    # this account never got in
                            _r2 = _xb._sell_retry(
                                _xc, key, order["symbol"], order.get("side"),
                                order.get("strike"), order.get("expiry"), qty,
                                ref_price=exref)
                            note("SOLD     [%s] %s" % (_x["name"], _r2["what"]))
                            _xb.finish(key, positions.CLOSED,
                                       "sold on their call at %.2f"
                                       % float(_r2["limit"]))
                        except Exception as _e:         # noqa: BLE001
                            try:
                                if _xb._gone_at_broker(
                                        _xc, order["symbol"],
                                        order.get("side"), order.get("strike")):
                                    _xb.finish(key, positions.CLOSED,
                                               "sold in a two-seller collision "
                                               "— the other order won",
                                               price=exref)
                                    note("SOLD     [%s] %s — its own stop won "
                                         "the race" % (_x["name"],
                                                       order["symbol"]))
                                    continue
                            except Exception:           # noqa: BLE001
                                pass
                            note("ACCT %s exit ERROR %s -> %s — its stop is "
                                 "being re-armed"
                                 % (_x["name"], what, str(_e)[:120]))
                            try:
                                _xb.rearm_stop_after_failed_exit(key)
                            except Exception:           # noqa: BLE001
                                pass

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
                        if live_order:
                            for _x in WB_EXTRA:
                                if not _extra_active(_x):
                                    continue
                                try:
                                    _b2 = _x["client"].buy(
                                        order["symbol"], order.get("side"),
                                        order.get("strike"),
                                        order.get("expiry"), qty,
                                        their_price=order.get("reenter_limit"))
                                    _b2["live"] = True
                                    note("ORDER IN [%s] %s   (back in)"
                                         % (_x["name"], _b2["what"]))
                                    _x["book"].entry_sent(order, _b2)
                                except Exception as _e:  # noqa: BLE001
                                    note("ACCT %s back-in REFUSED -> %s"
                                         % (_x["name"], str(_e)[:120]))
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
            # A failed EXIT pulled the resting stop on its way in — if the
            # position survived, put the stop straight back (8/18: SPY 769C
            # sat 0DTE watchdog-only after a failed close). His pick #1.
            if action in ("CLOSE", "TRIM") and BOOK is not None:
                try:
                    BOOK.rearm_stop_after_failed_exit(key)
                except Exception:                       # noqa: BLE001
                    pass
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
            # With paper execution off there is nothing of ours in the
            # sandbox, and polling it was 79% of all Webull traffic on 8/12
            # (7,209 calls of 9,111). Skip it unless paper is actually on.
            _accts = [(WB_LIVE, True)]
            if paper_on():
                _accts.append((WB_PAPER, False))
            for wb, is_live in _accts:
                if wb is None or id(wb) in seen or not hasattr(wb, "positions"):
                    continue
                seen.add(id(wb))
                try:
                    for p in (wb.positions() or []):
                        d = dict(p)
                        d["live"] = is_live  # which Webull account it's in
                        rows.append(d)
                    # A SUCCESSFUL read that returns nothing is a real verdict:
                    # the account is FLAT. Without this flag, flat and
                    # unreachable looked identical and reconcile_gone refused
                    # to clear ghosts while he held nothing (8/31: the adopted
                    # SPY he'd sold at 11:20 haunted the book until 14:42).
                    if is_live:
                        _POS["ok_live"] = True
                except Exception:                       # noqa: BLE001
                    if is_live:
                        _POS["ok_live"] = False
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
                # Always on when keyed (his call, 8/17) — and the checkmark
                # now means the key actually ANSWERED (probe_ai_key), not
                # just that a box was filled. False the moment Anthropic
                # says 401, whatever is pasted.
                "ai_enabled": bool((EXEC.get("ai_reader") or {}).get("api_key"))
                              and AI_KEY_OK is not False,
                "pocket_scalps_only": bool(CFG.get("pocket_scalps_only")),
                "restart_check": (lambda _he=(BOOK.restart_exposure()
                                              if BOOK is not None
                                              else ([], []))
                                  : {"held": _he[0], "working": _he[1],
                                     "armed_pullbacks":
                                         (sorted(_PULLBACK._armed)
                                          if _PULLBACK is not None else [])})(),
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
        # Is the BROKER actually holding this? That decides what ✕ means:
        # a real position has to be sold; a book-only ghost just has to go.
        try:
            held = any(str(r.get("symbol") or "").upper() == sym
                       for r in (broker_positions() or []))
        except Exception:                                   # noqa: BLE001
            held = True         # can't tell -> assume real, never fake a sale
        err = None
        msg = ""
        try:
            msg = wb.flatten(sym)
        except Exception as e:                              # noqa: BLE001
            err = e
        _POS["t"] = 0.0                         # force the next /positions refetch
        if BOOK is not None:
            try:
                keys = [k for k, p in list(getattr(BOOK, "_pos", {}).items())
                        if str((p or {}).get("symbol") or "").upper() == sym]
                for k in keys:
                    if BOOK.claim(k):
                        BOOK.finish(k, positions.CLOSED,
                                    "closed from the popup", price=None)
                # Whatever the broker said, the book must not keep showing a
                # position ✕ was pressed on. claim() refuses a stuck "closing"
                # entry and flatten() REFUSES futures outright, which is how
                # ghosts became unclickable — so sweep the remainder by force.
                if not held or err is not None:
                    dropped = BOOK.force_drop(sym, live=want_live)
                    if dropped and not held:
                        note("FLATTEN  %s wasn't at the broker — removed %d "
                             "stale book entr%s" % (sym, dropped,
                                                    "y" if dropped == 1 else "ies"))
                        return self._json(200, {"ok": True,
                            "message": "%s wasn't open at Webull — cleared it "
                                       "from the book." % sym})
            except Exception:                   # noqa: BLE001
                pass
        if err is not None:
            note("FLATTEN  %s FAILED -> %s" % (sym, err))
            return self._json(200, {"ok": False,
                "message": "couldn't close %s: %s" % (sym, str(err)[:140])})
        note("FLATTEN  %s -> %s" % (sym, msg))
        return self._json(200, {"ok": True, "message": msg})

    def do_GET(self):
        if self.path.startswith("/mode"):
            return self._json(200, self._status())
        if self.path.startswith("/stream"):
            # Is the MQTT stock stream alive, what is it carrying, how fresh.
            try:
                st = getattr(WB, "stream", None)
                if st is None:
                    return self._json(200, {"ok": False, "why": "stream not attached"})
                out = st.status()
                out["ok"] = True
                qb = getattr(BOOK, "quotes", None)
                if qb is not None:
                    try:
                        out["option_bus"] = qb.status()
                    except Exception:                   # noqa: BLE001
                        pass
                return self._json(200, out)
            except Exception as _e:                     # noqa: BLE001
                return self._json(200, {"ok": False, "why": str(_e)[:120]})
        if self.path.startswith("/rooms"):
            # The one list of channels that trade (extension/rooms.txt),
            # parsed — so "what is the sniper actually listening to" is a
            # one-second curl instead of a screen-share (audit ask, 8/30).
            # Read-only, no secrets: ids/urls/labels only.
            rooms = []
            try:
                _rp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "extension", "rooms.txt")
                with open(_rp, encoding="utf-8") as _f:
                    for _ln in _f:
                        _ln = _ln.strip()
                        if not _ln or _ln.startswith("#"):
                            continue
                        _p = _ln.split("|")
                        if len(_p) >= 4:
                            rooms.append({"id": _p[0], "url": _p[1],
                                          "label": _p[2], "group": _p[3]})
            except Exception as _e:                     # noqa: BLE001
                return self._json(200, {"ok": False, "why": str(_e)[:120]})
            return self._json(200, {"ok": True, "count": len(rooms),
                                    "rooms": rooms})
        if self.path.startswith("/whopfeed"):
            # The whop-api reader's queue. The extension's offscreen page
            # polls this every ~2s with its last cursor; active only when
            # settings.json whop.api_key exists (otherwise always empty).
            q = parse_qs(urlparse(self.path).query)
            try:
                cur = int((q.get("cursor") or ["0"])[0])
            except ValueError:
                cur = 0
            items = [m for m in WHOP_FEED if m.get("_i", 0) > cur]
            return self._json(200, {"ok": True, "cursor": WHOP_FEED_N[0],
                                    "active": (time.time() - WHOP_FEED_OK[0]
                                               < 300),
                                    "items": items[-100:]})
        if self.path.startswith("/exchoices"):
            # Every account behind an extra login's keys, with buying power —
            # the popup's ✏️ uses this so switching accounts is one click
            # (his ask, 8/21). Read-only probing; nothing is placed.
            # Cached 60s per login — each probe is a full login + balance
            # read per account, and hammering it is how Webull answered
            # 429 TOO_MANY_REQUESTS (8/21).
            q = parse_qs(urlparse(self.path).query)
            nm = str((q.get("name") or [""])[0]).strip()[:24]
            _cch = getattr(Handler, "_exch_cache", None)
            if _cch is None:
                _cch = Handler._exch_cache = {}
            _hit = _cch.get(nm)
            if _hit and time.time() - _hit[0] < 60:
                return self._json(200, {"ok": True, "choices": _hit[1],
                                        "cached": True})
            acc = next((a for a in (EXEC.get("webull_extra_accounts") or [])
                        if str(a.get("name") or "").strip()[:24] == nm), None)
            if not acc or not (acc.get("app_key") and acc.get("app_secret")):
                return self._json(200, {"ok": False, "why": "no such account"})
            try:
                import webull_options as _wo
                import copy as _cp
                rows = _wo.list_accounts(acc["app_key"], acc["app_secret"])
                cur = str(acc.get("account_id") or "")
                choices = []
                for r0 in rows:
                    if "FUTURES" in str(r0.get("kind") or "").upper():
                        continue        # options bot — futures rides the main
                    _bp = None
                    time.sleep(0.5)     # pace the probes — 429 protection
                    try:
                        c2 = _cp.deepcopy(CFG)
                        w2 = c2.setdefault("execution", {}).setdefault(
                            "webull", {})
                        w2["app_key"] = acc["app_key"]
                        w2["app_secret"] = acc["app_secret"]
                        w2["paper_trading"] = False
                        w2["account_id"] = r0["id"]
                        _c2 = _wo.WebullOptions(c2)
                        _c2.connect()
                        _bp = _c2.buying_power()
                    except Exception:                   # noqa: BLE001
                        pass
                    choices.append({"id": r0["id"], "kind": r0.get("kind"),
                                    "bp": (round(float(_bp), 0)
                                           if _bp is not None else None),
                                    "current": r0["id"] == cur})
                _cch[nm] = (time.time(), choices)
                return self._json(200, {"ok": True, "choices": choices})
            except Exception as e:                      # noqa: BLE001
                return self._json(200, {"ok": False, "why": str(e)[:160]})
        if self.path.startswith("/dgkey"):
            # The Deepgram key's PERMANENT home (his ask, 8/20: "put it once,
            # saved, always active"). The browser keeps a copy, but a profile
            # wipe or extension reinstall loses that — the extension asks
            # here and restores itself. Localhost-only, like everything.
            return self._json(200, {"key": (EXEC.get("voice") or {})
                                    .get("deepgram_key", "")})
        if self.path.startswith("/positions"):
            # The real Webull account positions, so the popup mirrors the broker.
            # LIVE OVERLAY (9/2, G: "huge delay in pnl at the popup"): Webull's
            # positions endpoint is cached 8s here and its own mark lags; the
            # quote bus sweeps every option we hold once a second. So the
            # popup's "now"/P&L is repainted from the freshest bus bid (or
            # the MQTT push for stocks) on every ask; the broker row is the
            # fallback when nothing fresh is in hand.
            rows = broker_positions()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    live_px = None
                    if d.get("kind") == "option" and d.get("expiry") and d.get("strike"):
                        from webull_options import occ_symbol as _occ
                        occ = _occ(
                            d["symbol"], str(d["expiry"])[:10],
                            "CALL" if d.get("side") == "CALLS" else "PUT", d["strike"])
                        qb = getattr(BOOK, "quotes", None) if BOOK is not None else None
                        if qb is not None:
                            qb.watch(occ)
                            _a, _b, _ = qb.get(occ)
                            if _b:
                                live_px = float(_b)
                        mult = 100.0
                    elif d.get("kind") == "stock":
                        st = getattr(WB, "stream", None)
                        live_px = st.price(d["symbol"]) if st is not None else None
                        mult = 1.0
                    if live_px and d.get("fill"):
                        q = abs(int(d.get("qty") or 0)) or 1
                        d["last"] = live_px
                        d["pl"] = round((live_px - float(d["fill"])) * mult * q, 2)
                        d["pl_pct"] = round((live_px / float(d["fill"]) - 1.0) * 100, 1)
                        d["live_quote"] = True
                except Exception:                       # noqa: BLE001
                    pass
                out.append(d)
            return self._json(200, {"positions": out,
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
            w["paper_trading"] = bool(w.get("paper_trading", False))
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

    def _export_log(self):
        """The extension hands over the day's export and this writes it to
        <folder>\\DS Logs (his ask, 8/18: "logs download here"). Chrome's
        download API can't write outside Downloads and kept minting
        (1)(2)(3) duplicates; a plain file write overwrites properly, one
        file per day, always current."""
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "why": "unreadable"})
        name = str(body.get("name") or "").strip()
        text = str(body.get("text") or "")
        # filename hygiene: whatever arrives, it stays a plain .txt inside
        # DS Logs — no path parts on ANY separator style, no surprises.
        name = name.replace("\\", "/").rsplit("/", 1)[-1]
        name = name.replace("..", "").strip() or "export.txt"
        if not name.lower().endswith(".txt"):
            name += ".txt"
        if not text:
            return self._json(400, {"ok": False, "why": "empty"})
        try:
            d = os.path.join(HERE, "DS Logs")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
            return self._json(200, {"ok": True, "saved": name})
        except OSError as e:
            return self._json(200, {"ok": False, "why": str(e)[:120]})

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

    def _ai_read_image(self):
        """SCREENSHOT reading (his ask, 8/19): some rooms post the call as an
        image. Same brain, same guards as _ai_read — the model reads the picture
        and TRANSCRIBES the trade text it sees; that transcription (plus any
        caption) is what the literal-match guard validates against, so a chart
        with no order, or an invented ticker, is refused exactly like a bad
        typed read. We never trade here; we hand a clean call back to the
        extension, which runs it through the real parser + every guard."""
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:                                   # noqa: BLE001
            return self._json(400, {"ok": False, "why": "unreadable"})
        images = body.get("images") or []
        caption = str(body.get("text") or "").strip()
        if not images:
            return self._json(200, {"ok": False, "why": "no image"})
        try:
            import ai_reader
        except Exception as e:                              # noqa: BLE001
            return self._json(200, {"off": True, "why": "ai_reader missing: %s" % e})
        if not ai_reader.available(CFG):
            return self._json(200, {"off": True})
        allowed = CFG.get("allowed_symbols", []) or []
        read = ai_reader.read_image(images, caption, allowed, CFG)
        if not isinstance(read, dict):
            note("IMG READ no read")
            return self._json(200, {"ok": False, "why": "no read"})
        if read.get("_error"):
            note("IMG READ couldn't read the image (%s)" % read["_error"])
            return self._json(200, {"ok": False, "why": read["_error"]})
        # The anti-hallucination check runs against the image's OWN words (what
        # the model transcribed) plus any caption — never an empty string, or a
        # screenshot read would always fail the "must appear in the text" bar.
        seen = str(read.get("_seen_text") or "")
        check_text = (caption + "\n" + seen).strip()
        ok, why, cleaned = ai_reader.validate(read, check_text, allowed)
        if not ok:
            note("IMG READ no call — %s" % (why or "")[:80])
            return self._json(200, {"ok": False, "why": why})
        canon = ai_reader.canonical(cleaned)
        note("IMG READ  [screenshot]  ->  %s   (saw: '%s')"
             % (canon, seen[:60]))
        return self._json(200, {"ok": True, "canonical": canon,
                                "read": cleaned, "seen_text": seen,
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
                  "futures_brokers", "webull_extra_accounts", "deepgram_key", "pocket_scalps_only")
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
                # ratchet_enabled is the default exit now; take_profit_hard_close
                # is the old all-or-nothing close, still available as an
                # explicit opt-in. "enabled" keeps meaning "the bracket runs at
                # all" — off, and neither one fires.
                bracket_on = bool(st.get("enabled"))
                BOOK.ratchet_on = bracket_on and bool(
                    st.get("ratchet_enabled", True))
                BOOK.take_profit_on = bracket_on and bool(
                    st.get("take_profit_hard_close", False))
                BOOK.take_profit_pct = float(st.get("take_profit_pct", 20.0))
                # the extra accounts' books follow the same strategy switch
                for _x in WB_EXTRA:
                    try:
                        _x["book"].ratchet_on = BOOK.ratchet_on
                        _x["book"].take_profit_on = BOOK.take_profit_on
                        _x["book"].take_profit_pct = BOOK.take_profit_pct
                    except Exception:                   # noqa: BLE001
                        pass
                if bracket_on and st.get("stop_loss_pct"):
                    BOOK.stop_pct = float(st["stop_loss_pct"])
                    _sync_stop_pct(BOOK.stop_pct)
            if BOOK is not None and BOOK.ratchet_on:
                # Step is stop_loss_pct, not (tp - sl) — see the boot banner.
                note("STRATEGY ON: 1 contract, -%.0f%% stop to start, then at "
                     "+%.0f%% the stop goes to BREAKEVEN and every further "
                     "+%.0f%% locks another %.0f%%"
                     % (float(st.get("stop_loss_pct", 10)),
                        float(st.get("take_profit_pct", 20)),
                        float(st.get("stop_loss_pct", 10)),
                        float(st.get("stop_loss_pct", 10))))
            else:
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
            # Fresh Topstep credentials get logged in RIGHT NOW, so the
            # popup's green box means "TopstepX accepted them" (8/17).
            if "topstep" in incoming:
                probe_topstep_key()
            _on = ["webull"] if fb.get("webull") else []
            if (fb.get("ninjatrader") or {}).get("enabled"):
                _on.append("ninjatrader")
            if (fb.get("tradovate") or {}).get("enabled"):
                _on.append("tradovate")
            if (fb.get("topstep") or {}).get("enabled"):
                _on.append("topstep")
            note("FUTURES  trade from: %s" % (", ".join(_on) or "nothing selected"))

        # Extra Webull accounts (8/18): the popup sends the WHOLE list on
        # save (add/remove happens there). Keys are secrets — they live in
        # settings.json only, never echoed back. Connects right away so the
        # green check means "logged in", same promise as Topstep's.
        if isinstance(body.get("webull_extra_accounts"), list):
            _clean = []
            for a in body["webull_extra_accounts"]:
                if not isinstance(a, dict):
                    continue
                _e = {"name": str(a.get("name") or "").strip()[:24],
                      "app_key": str(a.get("app_key") or "").strip(),
                      "app_secret": str(a.get("app_secret") or "").strip(),
                      "enabled": bool(a.get("enabled", True)),
                      # Subscription month (his model, 8/20): "YYYY-MM".
                      # Active while it equals the current month; the popup
                      # stamps it when the toggle is flipped ON.
                      "paid_month": str(a.get("paid_month") or "").strip()[:7],
                      # Which account when the login has several (8/21).
                      "account_id": str(a.get("account_id") or "").strip()[:40]}
                # A resave with blanked secrets keeps the stored ones —
                # same only-fill-empty rule that fixed the Topstep email.
                for old in (EXEC.get("webull_extra_accounts") or []):
                    if str(old.get("name") or "").strip()[:24] == _e["name"]:
                        _e["app_key"] = _e["app_key"] or old.get("app_key", "")
                        _e["app_secret"] = (_e["app_secret"]
                                            or old.get("app_secret", ""))
                        _e["paid_month"] = (_e["paid_month"]
                                            or old.get("paid_month", ""))
                        _e["account_id"] = (_e["account_id"]
                                            or old.get("account_id", ""))
                if _e["name"]:
                    _clean.append(_e)
            data.setdefault("execution", {})["webull_extra_accounts"] = _clean
            CFG.setdefault("execution", {})["webull_extra_accounts"] = _clean
            EXEC["webull_extra_accounts"] = _clean
            note("ACCT     extra Webull accounts saved: %s"
                 % (", ".join(a["name"] for a in _clean) or "none"))
            try:
                _connect_extras()
            except Exception as _e:                     # noqa: BLE001
                note("ACCT     connect failed: %s" % str(_e)[:120])

        if "pocket_scalps_only" in body:
            data["pocket_scalps_only"] = bool(body["pocket_scalps_only"])
            CFG["pocket_scalps_only"] = bool(body["pocket_scalps_only"])
            note("POCKET   %s" % ("ON — scalps enter :43-:51 only"
                                  if CFG["pocket_scalps_only"]
                                  else "off — any minute trades"))

        # Deepgram (voice ears) key — saved on this PC so it survives any
        # browser wipe or extension reinstall (his ask, 8/20: "put it once
        # and always active"). The extension restores itself from /dgkey.
        if "deepgram_key" in body:
            _dk = str(body["deepgram_key"] or "").strip()
            _v = data.setdefault("execution", {}).setdefault("voice", {})
            _v["deepgram_key"] = _dk
            CFG.setdefault("execution", {}).setdefault(
                "voice", {})["deepgram_key"] = _dk
            EXEC.setdefault("voice", {})["deepgram_key"] = _dk
            note("VOICE    Deepgram key saved on this PC — the ears are "
                 "permanent now (survives browser reinstalls)")

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
            EXEC["ai_reader"] = dict(ar)
            # A fresh key gets tested against Anthropic RIGHT NOW, so the
            # popup's ✅ means "works", never just "pasted" (8/17).
            if "ai_api_key" in body:
                probe_ai_key()

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
        if self.path.startswith("/readimage"):
            return self._ai_read_image()
        if self.path.startswith("/read"):
            return self._ai_read()
        if self.path.startswith("/exportlog"):
            return self._export_log()

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
        # "BTO MNQ1 29115 quickie" — that room writes the CONTRACT COUNT onto
        # the root, so the symbol lands here as "MNQ1": not a futures root, not
        # a real ticker either, so it matched no gate below and the call was
        # dropped without a single line in trades.log (8/18 22:42 and 8/25
        # 21:38, both silent). Same shape as the bare-futures-exit and
        # micros-only fixes further down: a known root with a small count (or a
        # TradingView "!") stuck on the end IS that root. Only ever rewrites a
        # symbol that is NOT already a root, so ES/NQ/NG/SI are untouched.
        if sym not in FUT_MULT:
            _bare = sym.rstrip("!")
            _root = _bare.rstrip("0123456789")
            if (_root != _bare and _root in FUT_MULT
                    and len(_bare) - len(_root) <= 2):
                note("FUTURES  %s -> %s (that's the contract count stuck on "
                     "the root, not a ticker)" % (sym, _root))
                sym = _root
                order["symbol"] = sym
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

        # A bare futures exit ("close MGC") reaches here without its kind tag —
        # the reader marks entries, not one-word exits — and the option gate
        # below then demanded a strike/expiry a future never has. That block
        # stranded a NAKED NinjaTrader MGC long on 8/21 (and MES/NFLX/MGC
        # closes before it). A known futures root with no strike IS a future.
        if not order.get("kind") and order.get("strike") is None \
                and str(order.get("symbol") or "").upper() in (
                    "ES", "NQ", "MES", "MNQ", "YM", "MYM", "RTY", "M2K",
                    "CL", "MCL", "GC", "MGC"):
            order["kind"] = "future"
        # MICROS ONLY, ALWAYS (his rule, 8/23): a room's "NQ" or "ES" is
        # executed as the micro — MNQ, MES — on every leg (Webull, Topstep,
        # NinjaTrader) and for every action. Full-size NQ is $20/pt against
        # the micro's $2; one unmapped symbol would be a 10x position.
        if order.get("kind") == "future":
            _MICRO = {"NQ": "MNQ", "ES": "MES", "YM": "MYM", "RTY": "M2K",
                      "GC": "MGC", "CL": "MCL"}
            _fs = str(order.get("symbol") or "").upper()
            if _fs in _MICRO:
                order["symbol"] = _MICRO[_fs]
                note("FUTURES  %s -> %s (micros only, always)"
                     % (_fs, order["symbol"]))

        # A micro and its full-size root are ONE position. Stormzy's "ALL OUT
        # ES" (8/21 11:36) arrived on a live MES long, found no "ES" in the
        # book, and webull_futures answered "you're not in ES" without writing
        # a single line — a SILENT drop, and the position stayed open. The
        # extension rewrites this too; the same rule lives here so a stale
        # extension can never lose an exit. Deliberately narrow: exits only,
        # no strike, and only when the book holds the micro and NOT the plain
        # root — so an equity sharing a futures root (CL, SI, GC) is never
        # touched. Rewrites the SYMBOL, not just the key: webull_futures picks
        # its contract off order["symbol"], so a key-only fix would have sold
        # a full-size ES against a micro long.
        if order.get("action") in ("CLOSE", "TRIM") \
                and order.get("strike") is None and BOOK is not None:
            _sib = FUT_MICRO_OF.get(sym)
            try:
                _need = bool(_sib) and not BOOK.find_by_symbol(sym) \
                    and bool(BOOK.find_by_symbol(_sib))
            except Exception:                           # noqa: BLE001
                _need = False
            if _need:
                note("FUTURES  %s exit routed to your %s position — the micro "
                     "and its full-size root are one trade" % (sym, _sib))
                order["symbol"] = _sib
                order["kind"] = "future"
                sym = _sib

        if order.get("live") and order.get("action") != "TRIM" \
                and order.get("kind") != "future" \
                and not (order.get("strike") and order.get("expiry")):
            # 8/24: Bullwinkle's bare "OUT NVDA 4.25" landed here and got
            # BLOCKED while both accounts sat in his NVDA 207.5C — the book
            # KNEW the contract; the gate never asked it. A bare exit now
            # resolves against the book: the trader's own position in that
            # ticker first, else the only position in it. Two different
            # contracts held with no owner match still block — guessing which
            # to sell is worse than asking.
            _cands = []
            if BOOK is not None:
                try:
                    _cands = [(k, BOOK.info(k)) for k in BOOK.find_by_symbol(sym)]
                    _cands = [(k, p) for k, p in _cands if p]
                    _who = str(order.get("trader") or "").strip().lower()
                    if _who and len(_cands) > 1:
                        _own = [(k, p) for k, p in _cands
                                if _who in str(p.get("who") or k).lower()]
                        if _own:
                            _cands = _own
                except Exception:                       # noqa: BLE001
                    _cands = []
            if len(_cands) == 1:
                _k, _p = _cands[0]
                order["strike"] = _p.get("strike")
                order["expiry"] = _p.get("expiry")
                if not order.get("side"):
                    order["side"] = _p.get("side")
                note("RESOLVED %s %s — bare exit matched to your held %s %s%s "
                     "%s" % (order.get("action"), sym, sym,
                             order.get("strike"),
                             "C" if str(order.get("side") or "").upper().startswith("CALL") else "P",
                             order.get("expiry") or ""))
            else:
                note("BLOCKED  %s %s arrived with no strike/expiry%s" %
                     (order.get("action"), sym,
                      " (you hold %d different %s contracts — say which)"
                      % (len(_cands), sym) if len(_cands) > 1 else ""))
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
    _connect_extras()  # more Webull accounts, each with its own book (8/18)
    # The Webull SDK's own debug log wrote ~700MB in a week (8/23). Quiet it
    # to warnings-only, and sweep rotations older than 2 days at every boot.
    try:
        import logging
        for _nm in list(logging.root.manager.loggerDict):
            if "webull" in _nm.lower():
                logging.getLogger(_nm).setLevel(logging.WARNING)
        _cut = time.time() - 2 * 86400
        for _fn in os.listdir(HERE):
            if _fn.startswith("webull_trade_sdk.log.") \
                    and os.path.getmtime(os.path.join(HERE, _fn)) < _cut:
                os.remove(os.path.join(HERE, _fn))
    except Exception:                                   # noqa: BLE001
        pass


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
    # Test the AI key against Anthropic and the Topstep key against
    # TopstepX once per boot — every popup ✅ means "the key answered",
    # never just "a box is filled" (8/17).
    try:
        probe_ai_key()
    except Exception:                                   # noqa: BLE001
        pass
    try:
        probe_topstep_key()
    except Exception:                                   # noqa: BLE001
        pass
    # Restart the bridge BY ITSELF when its own code changes on disk (his ask,
    # 8/21: "can you restart the bridge every time?" — now nobody has to).
    # Safe by construction: waits for the edit batch to SETTLE (60s with no
    # further change), refuses to restart onto code that doesn't compile, and
    # during market hours it holds the restart until after the close so a
    # mid-session swap can't blink the reader. Positions survive restarts
    # (state.json + re-adopt + stop re-arm), same as any START HERE.
    def _code_watch_loop():
        import py_compile
        def snap():
            out = {}
            try:
                for fn in os.listdir(HERE):
                    if fn.endswith(".py"):
                        try:
                            out[fn] = os.path.getmtime(os.path.join(HERE, fn))
                        except OSError:
                            pass
            except OSError:
                pass
            return out
        base = snap()
        pending_since = None
        warned_open = False
        _RF = os.path.join(HERE, "bridge.restart")
        while True:
            time.sleep(20)
            # FORCED RESTART (9/2, G: "restart automatically"): a NON-EMPTY
            # bridge.restart file skips the safe-window wait. Still compile-
            # checks; still refuses while a bid is WORKING (money in flight).
            # Armed pullback hunts are dropped and named in the log. Empty
            # file = inert (the sandbox can write but not delete).
            forced = False
            try:
                if os.path.exists(_RF) and os.path.getsize(_RF) > 0:
                    forced = True
                    try:
                        os.remove(_RF)
                    except OSError:
                        open(_RF, "w").close()
            except Exception:                           # noqa: BLE001
                forced = False
            cur = snap()
            if cur != base:
                if pending_since is None:
                    note("CODE     change on disk — will restart once it "
                         "settles (after the close if the market's open)")
                pending_since = time.time()
                base = cur
                if not forced:
                    continue
            if forced:
                try:
                    _h, _w = BOOK.restart_exposure() if BOOK is not None else ([], [])
                except Exception:                       # noqa: BLE001
                    _h, _w = [], ["?"]
                if _w:
                    note("CODE     forced restart REFUSED — bid working on %s; "
                         "try again when it fills or cancels" % ",".join(map(str, _w)))
                    continue
                try:
                    _hunts = sorted(_PULLBACK._armed) if (_PULLBACK is not None and _PULLBACK._armed) else []
                except Exception:                       # noqa: BLE001
                    _hunts = []
                note("CODE     forced restart (bridge.restart)%s" % (
                    " — dropping armed hunt(s): %s" % ", ".join(map(str, _hunts)) if _hunts else ""))
                pending_since = time.time() - 61
            if pending_since is None:
                continue
            if time.time() - pending_since < 60:
                continue                # let the whole edit batch finish
            try:
                import eastern
                _t = eastern.now()
                _mins = _t.hour * 60 + _t.minute
                is_open = _t.weekday() < 5 and \
                    (9 * 60 + 20) <= _mins <= (16 * 60 + 15)
            except Exception:                           # noqa: BLE001
                is_open = False
            if is_open and not forced:
                # SAFE-WINDOW RESTART (8/26, his ask: "restart automatically
                # when it's safe"). Mid-market, a new build no longer waits
                # for the close if NOTHING is in flight: no resting bids, no
                # armed pullback hunts, no position mid-close — checked twice
                # 20s apart so a call landing between checks wins. Held
                # positions don't block it (their stops rest at the broker
                # and the book restores them); that's been proven daily.
                def _in_flight():
                    try:
                        _h, _w = BOOK.restart_exposure()                             if BOOK is not None else ([], [])
                        if _w:
                            return True
                        if _PULLBACK is not None and _PULLBACK._armed:
                            return True
                    except Exception:                   # noqa: BLE001
                        return True     # can't tell = not safe
                    return False
                if _in_flight():
                    if not warned_open:
                        note("CODE     new build ready — waiting for a safe "
                             "window (or the close, whichever comes first)")
                        warned_open = True
                    continue
                time.sleep(20)
                if _in_flight():
                    continue
                note("CODE     safe window — nothing in flight, restarting "
                     "onto the new build now instead of waiting for the "
                     "close")
                # fall through to the compile-check + restart below
            ok = True
            for fn in sorted(cur):
                try:
                    py_compile.compile(os.path.join(HERE, fn), doraise=True)
                except Exception as e:                  # noqa: BLE001
                    note("CODE     %s doesn't compile (%s) — NOT restarting, "
                         "staying on the running build" % (fn, str(e)[:80]))
                    ok = False
                    break
            if not ok:
                pending_since = None
                warned_open = False
                continue
            note("CODE     restarting onto the new build")
            try:
                save_day()
            except Exception:                           # noqa: BLE001
                pass
            try:
                os.execv(sys.executable,
                         [sys.executable, os.path.join(HERE, "bridge.py")])
            except Exception as e:                      # noqa: BLE001
                note("CODE     restart failed (%s) — the next START HERE "
                     "loads it" % e)
                pending_since = None
                warned_open = False
    threading.Thread(target=_code_watch_loop, daemon=True).start()

    # Keep the book in step with the REAL Webull account: adopt any open position
    # the book doesn't know about (one it never placed, or lost on a restart) so
    # a room's "all out" can actually flatten it. Runs once now and every 20s.
    _REARM_DAY = [""]

    def _reconcile_loop():
        while True:
            try:
                # Once per day just after the open: swings held overnight get
                # their broker stop back (Webull's DAY-only sell legs died at
                # yesterday's close — the 8/31 S-swing lesson).
                _lt = time.localtime()
                _td = time.strftime("%Y-%m-%d")
                if (_lt.tm_wday < 5 and _lt.tm_hour * 60 + _lt.tm_min >= 571
                        and _REARM_DAY[0] != _td and BOOK is not None):
                    _REARM_DAY[0] = _td
                    try:
                        _n = BOOK.rearm_overnight_stops()
                        if _n:
                            note("STOP-SET  %d overnight swing stop(s) "
                                 "re-armed after the open" % _n)
                    except Exception:                   # noqa: BLE001
                        pass
                if BOOK is not None and WB is not None:
                    BOOK.drop_corrupt(note)
                    BOOK.purge_expired(note)
                    BOOK.adopt(broker_positions(), note)
                    # the other direction: positions HE closed at Webull
                    if BOOK.reconcile_gone(broker_positions(), note,
                                           trust_empty_live=bool(
                                               _POS.get("ok_live"))):
                        save_day()
            except Exception:                           # noqa: BLE001
                pass
            # A configured extra account that ISN'T connected (a 429 rate
            # limit at connect time — 8/21, L's switch to the funded account)
            # gets retried every 5 minutes until it lands, instead of waiting
            # for a restart or a popup save.
            try:
                _cfgd = [str(a.get("name") or "").strip()[:24]
                         for a in (EXEC.get("webull_extra_accounts") or [])
                         if a.get("enabled", True) and a.get("app_key")]
                _livec = {x["name"] for x in WB_EXTRA}
                if any(n not in _livec for n in _cfgd):
                    global _EXTRA_RETRY_AT
                    try:
                        _last = _EXTRA_RETRY_AT
                    except NameError:
                        _last = 0
                    if time.time() - _last > 300:
                        _EXTRA_RETRY_AT = time.time()
                        note("ACCT     retrying the un-connected account(s) "
                             "— rate limits cool off")
                        _connect_extras()
            except Exception:                           # noqa: BLE001
                pass
            # Each extra account gets the same housekeeping against ITS OWN
            # broker view: adopt what it holds (so a room's "all out" can
            # flatten it, and hand trades get the same protection), and
            # notice what HE closed on that account himself.
            for _x in WB_EXTRA:
                try:
                    _rows = []
                    for _p in (_x["client"].positions() or []):
                        _d = dict(_p)
                        _d["live"] = True
                        _rows.append(_d)
                    try:
                        for _p in (_x["client"].futures_positions() or []):
                            _d = dict(_p)
                            _d["live"] = True
                            _rows.append(_d)
                    except Exception:                   # noqa: BLE001
                        pass
                    _x["book"].drop_corrupt(note)
                    _x["book"].purge_expired(note)
                    _x["book"].adopt(_rows, note)
                    if _x["book"].reconcile_gone(_rows, note):
                        save_day()
                except Exception:                       # noqa: BLE001
                    pass
            time.sleep(20)
    threading.Thread(target=_reconcile_loop, daemon=True).start()

    # ---- WHOP API READER (8/30, dark until a key exists) -----------------
    # Whop has an official API (docs.whop.com/developer/guides/chat):
    # messages.list by experience id — the SAME exp_ ids in rooms.txt. With
    # settings.json  "whop": {"api_key": "..."}  this poller reads every
    # whop room server-side and queues messages for the extension's
    # offscreen page (GET /whopfeed, 2s poll) — no tabs, no black screens,
    # no reloads. Without the key nothing here runs and the tabs carry on.
    def _whop_rooms_from_file():
        rooms = []
        try:
            _rp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "extension", "rooms.txt")
            for _ln in open(_rp, encoding="utf-8"):
                _ln = _ln.strip()
                if not _ln or _ln.startswith("#"):
                    continue
                _p = _ln.split("|")
                if len(_p) >= 4 and _p[0].startswith("whop:"):
                    _m = re.search(r"(exp_[A-Za-z0-9]+)", _p[1])
                    if _m:
                        rooms.append((_m.group(1), _p[2]))
        except Exception:                               # noqa: BLE001
            pass
        return rooms

    def _whop_feed_loop():
        key = str((CFG.get("whop") or {}).get("api_key") or "").strip()
        if not key:
            return                      # dark — no key, tabs keep the job
        import urllib.request as _ur
        import urllib.parse as _up
        rooms = _whop_rooms_from_file()
        if not rooms:
            return
        seen = {}                       # exp_id -> set of message ids
        first = {r[0]: True for r in rooms}
        # Endpoint hunt, webull-style: the SDK wraps REST; try the sane
        # paths once and remember the winner.
        paths = ["https://api.whop.com/v1/messages",
                 "https://api.whop.com/api/v1/messages",
                 "https://api.whop.com/v2/messages"]
        winner = [None]
        print("[whop-api] reader up — %d rooms, tabs now optional." % len(rooms))
        while True:
            for exp_id, label in rooms:
                try:
                    tries = [winner[0]] if winner[0] else paths
                    body = None
                    for base in tries:
                        q = _up.urlencode({"channel_id": exp_id,
                                           "direction": "desc", "first": 20})
                        req = _ur.Request(base + "?" + q, headers={
                            "Authorization": "Bearer " + key,
                            "User-Agent": "Mozilla/5.0 (DiscordSniper/1.0)"})
                        try:
                            with _ur.urlopen(req, timeout=8) as r:
                                body = json.loads(r.read().decode())
                                winner[0] = base
                                WHOP_FEED_OK[0] = time.time()
                                break
                        except Exception:               # noqa: BLE001
                            continue
                    if not isinstance(body, dict):
                        continue
                    items = body.get("data") or body.get("messages") or []
                    sset = seen.setdefault(exp_id, set())
                    fresh = []
                    for it in items:
                        mid = str(it.get("id") or "")
                        if not mid or mid in sset:
                            continue
                        sset.add(mid)
                        u = it.get("user") or {}
                        fresh.append({
                            "platform": "whop",
                            "channelId": "whop:api/" + exp_id,
                            "channelName": label,
                            "author": u.get("name") or u.get("username") or "?",
                            "text": str(it.get("content") or ""),
                            "mid": "whopapi|" + mid,
                            "postedAt": it.get("created_at") or "",
                            "history": bool(first.get(exp_id)),
                        })
                    if len(sset) > 4000:
                        sset.clear()
                    # oldest first so the extension reads in order
                    for msg in reversed(fresh):
                        WHOP_FEED_N[0] += 1
                        msg["_i"] = WHOP_FEED_N[0]
                        WHOP_FEED.append(msg)
                    first[exp_id] = False
                except Exception:                       # noqa: BLE001
                    pass
            del WHOP_FEED[:-400]        # bounded queue, newest 400 kept
            # fast only while it's actually working; walled/dead = 60s probes
            time.sleep(1.5 if time.time() - WHOP_FEED_OK[0] < 300 else 60)
    threading.Thread(target=_whop_feed_loop, daemon=True).start()

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
