"""
signals.py — turn one line of your signal room into a trade, or into nothing.

This is written against the actual grammar of YOUR room, not a generic one:

    loading AMD 7/31 480P          -> GET READY. Explicitly "DO NOT BUY IN".
    in AMD 7/31 480P @ 3.4         -> the entry. This is the only thing that buys.
    trimming AMD @ 38%             -> they took a piece off.
    all out of AMD                 -> full exit.
    exited SPY, and back in @ 2.84 -> out and straight back in.

Everything else in that channel is chatter, and the room posts a LOT of it.

The rule the parser follows: say NO unless the line is unmistakably one of the
five things above. Firing on chatter is the only way this can really hurt you.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional

# --- cleaning up the relay format --------------------------------------------
# The scribe reposts each admin's call, so a raw line looks like:
#   "@Unraveller (Admin)🔮 in AMD 7/31 480P @everyone"
RE_CALLER = re.compile(r"@\s*([A-Za-z0-9_.\-]{2,24})\s*\((admin|mod|analyst|scribe)\)",
                       re.IGNORECASE)
RE_PING = re.compile(r"@(everyone|here)\b", re.IGNORECASE)
RE_HDR = re.compile(r"^[A-Za-z0-9_.\- ]{2,24}\s*\((scribe|admin|mod)\)\s*[—\-]+\s*"
                    r"\d{1,2}:\d{2}\s*(AM|PM)\s*", re.IGNORECASE)
RE_EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⯿️]")

# --- the pieces of a call ----------------------------------------------------
RE_CONTRACT = re.compile(
    r"\$?(?P<symbol>[A-Za-z]{1,5})\s+"
    r"(?:(?P<expiry>\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d*dte)\s+)?"
    r"(?P<strike>\d{1,5}(?:\.\d{1,2})?)\s*"
    r"(?P<kind>calls?|puts?|c|p)\b", re.IGNORECASE)

RE_PCT = re.compile(r"@\s*(\d{1,3}(?:\.\d+)?)\s*%")
# a price, but never a percentage: "@ 3.4" is a fill, "@ 38%" is a gain
RE_LIMIT = re.compile(r"@\s*\$?(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)")
RE_QTY = re.compile(r"\b(\d{1,3})\s*(?:x|contracts?|lots?)\b", re.IGNORECASE)
RE_BARE = re.compile(r"\b([A-Z]{1,5})\b")

# --- the five things the room says -------------------------------------------
RE_LOADING = re.compile(r"\bloading\b", re.IGNORECASE)
RE_ALLOUT = re.compile(r"\ball\s+out\b", re.IGNORECASE)
RE_TRIM = re.compile(r"\btrim(?:ming|med|s)?\b", re.IGNORECASE)
RE_BACKIN = re.compile(r"\bback\s+in\b", re.IGNORECASE)
RE_ENTRY = re.compile(r"\b(?:in|entered|entering|filled|bto|bought|buying)\b",
                      re.IGNORECASE)
RE_EXIT = re.compile(r"\b(?:exited|exiting|closed|closing|stc|sold|selling|out)\b",
                     re.IGNORECASE)

# Lines that must never fire no matter what else is in them.
VETO_WORDS = ("do not", "don't", "dont ", "watching", "watch", "eyeing",
              "looking at", "thinking", "maybe", "might", "if it", "if you",
              "waiting", "wait for", "heads up", "scanner", "idea", "consider",
              "recap", "example", "congrats", "missed", "sorry", "pissed",
              "sets the tone", "session", "overall", "read was", "look at that",
              "still holding", "use $", "as risk", "anyone", "lmk", "great job")

NOT_TICKERS = {"THE", "A", "AN", "IT", "ALL", "IN", "OUT", "AT", "ON", "MY",
               "IS", "AND", "OF", "TO", "BE", "OK", "DTE", "AM", "PM", "ET",
               "DO", "NOT", "BUY", "SELL", "IE", "ADMIN", "HERE", "EOD", "CPI",
               "FOMC", "PT", "SL", "TP", "AVG", "GO", "UP", "WE", "US", "NO"}


@dataclass
class Signal:
    """What the bot thinks the line means. `fire` is the only field that
    decides whether money moves."""
    fire: bool = False
    why: str = ""                    # plain English, always filled in
    action: Optional[str] = None     # OPEN | CLOSE | TRIM | PREPARE
    symbol: Optional[str] = None
    side: Optional[str] = None       # CALLS | PUTS
    strike: Optional[float] = None
    expiry: Optional[str] = None
    limit: Optional[float] = None
    pct: Optional[float] = None      # the gain they reported on a trim
    qty: Optional[int] = None
    caller: str = ""                 # which admin the scribe was relaying
    warn: str = ""
    raw: str = ""
    clean: str = ""
    matched: str = ""

    def key(self):
        return (self.action, self.symbol, self.side, self.strike, self.expiry,
                self.pct)

    def human(self):
        if not self.action:
            return "no trade"
        bits = [self.action, self.symbol or "?"]
        if self.strike:
            bits.append(("%g" % self.strike) + ("C" if self.side == "CALLS" else "P"))
        if self.expiry:
            bits.append(self.expiry)
        if self.limit:
            bits.append("@ %.2f" % self.limit)
        if self.pct is not None:
            bits.append("(+%g%%)" % self.pct)
        return " ".join(bits)

    def dict(self):
        return asdict(self)


def clean_text(raw):
    """Strip the relay wrapper so the parser sees the call, not the plumbing."""
    t = RE_HDR.sub("", (raw or "").strip())
    t = RE_PING.sub(" ", t)
    t = RE_CALLER.sub(" ", t)
    t = RE_EMOJI.sub(" ", t)
    t = re.sub(r"^\s*\d{1,3}\.\s*", "", t)      # numbered paste lines
    return re.sub(r"\s+", " ", t).strip()


def _contract(text):
    for m in RE_CONTRACT.finditer(text):
        sym = m.group("symbol").upper()
        if sym in NOT_TICKERS:
            continue
        k = m.group("kind").lower()
        return {"symbol": sym, "strike": float(m.group("strike")),
                "side": "CALLS" if k.startswith("c") else "PUTS",
                "expiry": (m.group("expiry") or "").upper() or None}
    return None


def _bare_symbol(text, allowed):
    """For 'trimming AMD' and 'all out of SPY' there's no strike to anchor on,
    so only tickers you've explicitly allowed count. Without that rule 'all out
    of AAPL as well but made it up' starts looking like an order."""
    for m in RE_BARE.finditer(text):
        s = m.group(1).upper()
        if s in NOT_TICKERS:
            continue
        if allowed and s not in allowed:
            continue
        if not allowed and len(s) < 2:
            continue
        return s
    return None


def parse(text, author="", channel="", cfg=None):
    cfg = cfg or {}
    allowed = [s.upper() for s in cfg.get("allowed_symbols", [])]
    raw = (text or "").strip()
    sig = Signal(raw=raw)
    if not raw:
        sig.why = "empty message"
        return sig

    t = clean_text(raw)
    sig.clean = t
    low = t.lower()

    mc = RE_CALLER.search(raw)
    if mc:
        sig.caller = mc.group(1)

    if "?" in t:
        sig.why = "it's a question, not a call"
        return sig

    for w in tuple(VETO_WORDS) + tuple(cfg.get("extra_veto_words", ())):
        if w.lower() in low:
            sig.why = 'chatter, not an order (it contains "%s")' % w.strip()
            return sig

    # 1. LOADING — get contracts ready. The room says outright: DO NOT BUY IN.
    if RE_LOADING.search(low):
        c = _contract(t)
        sig.action = "PREPARE"
        sig.matched = "loading"
        if c:
            sig.symbol, sig.strike = c["symbol"], c["strike"]
            sig.side, sig.expiry = c["side"], c["expiry"]
        sig.why = ("they're getting ready on %s — LOADING never buys, that's the "
                   "room's own rule" % (sig.symbol or "something"))
        return sig

    # 2. ALL OUT — full exit. Checked before trim, because "all out" wins.
    if RE_ALLOUT.search(low):
        c = _contract(t)
        sig.symbol = c["symbol"] if c else _bare_symbol(t, allowed)
        if c:
            sig.strike, sig.side, sig.expiry = c["strike"], c["side"], c["expiry"]
        sig.action, sig.matched = "CLOSE", "all out"
        m = RE_PCT.search(t)
        if m:
            sig.pct = float(m.group(1))
        if not sig.symbol:
            sig.why = "they called an exit but I couldn't tell which ticker"
            return sig
        sig.fire = True
        sig.why = "full exit on %s" % sig.symbol
        return sig

    # 3. EXITED ... AND BACK IN — one line, two trades.
    if RE_BACKIN.search(low) and RE_EXIT.search(low):
        sig.symbol = _bare_symbol(t, allowed)
        sig.action, sig.matched = "CLOSE", "exit and re-entry"
        m = RE_LIMIT.search(t)
        if m:
            sig.limit = float(m.group(1))
        if not sig.symbol:
            sig.why = "they exited and re-entered but I couldn't tell which ticker"
            return sig
        sig.fire = True
        sig.warn = ("they got out and straight back in. This closes you and "
                    "leaves you flat — re-enter by hand if you want to follow.")
        sig.why = "exit on %s (they re-entered; you will be flat)" % sig.symbol
        return sig

    # 4. TRIMMING — a partial. You hold one contract, so you can't trim; what
    #    you can do is decide at which of their trims you take your money.
    if RE_TRIM.search(low):
        sig.symbol = _bare_symbol(t, allowed)
        sig.action, sig.matched = "TRIM", "trim"
        m = RE_PCT.search(t)
        if m:
            sig.pct = float(m.group(1))
        if not sig.symbol:
            sig.why = "a trim, but I couldn't tell which ticker"
            return sig
        mode = (cfg.get("trim_action") or "ignore").lower()
        if mode == "close":
            sig.action, sig.fire = "CLOSE", True
            sig.why = "closing %s on their first trim" % sig.symbol
        elif mode == "at_pct":
            target = float(cfg.get("close_at_trim_pct", 50))
            if sig.pct is not None and sig.pct >= target:
                sig.action, sig.fire = "CLOSE", True
                sig.why = ("closing %s — they're trimming at %g%%, your target is "
                           "%g%%" % (sig.symbol, sig.pct, target))
            else:
                sig.why = ("trim on %s at %s%% — under your %g%% target, holding"
                           % (sig.symbol,
                              "?" if sig.pct is None else ("%g" % sig.pct), target))
        else:
            sig.why = ("trim on %s%s — you're set to ignore trims and exit on "
                       "\"all out\"" % (sig.symbol,
                                        "" if sig.pct is None else " at %g%%" % sig.pct))
        return sig

    # 5. IN — the entry. Needs a full contract; a bare "in" is not an order.
    if RE_ENTRY.search(low):
        c = _contract(t)
        if not c:
            sig.why = "sounds like an entry but there's no full contract in it"
            return sig
        sig.symbol, sig.strike = c["symbol"], c["strike"]
        sig.side, sig.expiry = c["side"], c["expiry"]
        sig.action, sig.matched = "OPEN", "entry"
        m = RE_LIMIT.search(t)
        if m:
            sig.limit = float(m.group(1))
        mq = RE_QTY.search(t)
        if mq:
            sig.qty = int(mq.group(1))
        if allowed and sig.symbol not in allowed:
            sig.why = "%s isn't on your allowed-symbols list" % sig.symbol
            return sig
        sig.fire = True
        sig.why = "entry: %s" % sig.human()
        return sig

    # 6. A plain exit word with a real contract behind it.
    if RE_EXIT.search(low):
        c = _contract(t)
        sig.symbol = c["symbol"] if c else _bare_symbol(t, allowed)
        if c:
            sig.strike, sig.side, sig.expiry = c["strike"], c["side"], c["expiry"]
        if not sig.symbol:
            sig.why = "sounds like an exit but I couldn't tell which ticker"
            return sig
        sig.action, sig.matched = "CLOSE", "exit"
        sig.fire = True
        sig.why = "exit on %s" % sig.symbol
        return sig

    sig.why = "nothing in it that means buy or sell"
    return sig
