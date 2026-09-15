"""alert_revision.py — AN EDITED ALERT IS A REPLACEMENT, NOT A SECOND TRADE.

9/14, live, real money. "PT | ei trades" posted in Platinum nitro

    Entry — Contract: TSLA $357.5c — Price: $1.42

at 10:21 and then EDITED that same message to 357.5p; Discord keeps ONE
message id and paints "(edited)". The reader re-read the fuller row and the
bridge armed a SECOND round-number pullback with nothing standing the first
one down:

    10:21:21  PULLBACK TSLA CALL: waiting for a dip to $358
    10:22:17  PULLBACK TSLA PUT:  waiting for a bounce to $359

The stale CALL arm fired at 10:24:04 and bought TSLA 357.5C for $740 — the
wrong side of a call the room had already corrected. The PUT arm never fired.

This module owns ONE decision and has NO side effects: given an incoming OPEN,
which earlier OPEN(s) does it REPLACE? The bridge does the cancelling, which is
what keeps this testable with no broker, no book and no network.

IDENTITY, in order:
  1. the Discord MESSAGE ID (order["message_id"], the row id content.js
     already reads). Same message, different contract = an edit. This is the
     only certain signal, and it wins whenever both sides carry one.
  2. NO message id on either side (a legacy extension build, voice, vision):
     the same trader, the same ticker, a different contract, within five
     minutes, AND the text reads as a correction of the pending one. That
     means either an explicit correction word ("edit", "edited",
     "correction", "meant", "typo", a leading "*", "not calls/puts") or a
     near-duplicate: with the contract tokens (ticker, strike, side, expiry,
     price) stripped, the two texts are >= 0.9 similar (difflib ratio; bare
     contract lines with no prose to speak of are compared whole). A same-trader,
     same-ticker alert that reads differently is a SIBLING trade (TSLA calls
     at 10:00, TSLA puts as a new idea at 10:03) and the earlier arm stays.
     No text on either side is no evidence, so it is never an edit.

Two message ids that DIFFER are two different messages and never an edit. The
house rule is that separately posted contracts are separate trades (HANDOFF:
"TWO CONTRACTS IN ONE MESSAGE = TWO ORDERS"), so cancelling a live arm because
the caller posted a second contract would be its own bug — a worse one, since
it would silently delete trades he meant to take.

An IDENTICAL contract is never a revision: that is a repost, and the existing
dedupe ladder (extension in-flight lock -> bridge echo-lock -> per-trader
claim) already owns it.
"""

import difflib
import re
import threading
import time

# How far back the no-message-id fallback will look.
WINDOW_SECONDS = 300.0
# How alike two no-message-id alerts must read, contract tokens removed,
# before the second is an edit of the first.
SIMILARITY = 0.9
# How long any pending entry is remembered at all. Longer than the 10-minute
# pullback window so an edit that lands late still finds its original.
TTL_SECONDS = 900.0


def _text(v):
    return str(v or "").strip()


def _side_letter(side):
    s = _text(side).upper()
    if s.startswith("C"):
        return "C"
    if s.startswith("P"):
        return "P"
    return s[:1]


def _strike(v):
    try:
        return "%g" % float(v)
    except (TypeError, ValueError):
        return _text(v)


def contract_of(order):
    """(SYMBOL, C/P, strike, expiry) — the four fields that make one contract
    a different trade from another."""
    return (_text(order.get("symbol")).upper(),
            _side_letter(order.get("side")),
            _strike(order.get("strike")),
            _text(order.get("expiry")))


def label(order, other=None):
    """'357.5C' — the way G reads a contract. The expiry is appended only when
    `other` names a DIFFERENT one, so an edit that moved the DATE still reads
    as a change instead of '357.5C -> 357.5C'."""
    sym, side, strike, expiry = contract_of(order)
    txt = "%s%s" % (strike or "?", side or "?")
    if other is not None and expiry and contract_of(other)[3] != expiry:
        txt += " " + expiry
    return txt


def message_id(order):
    return _text(order.get("message_id"))


def raw_text(order):
    return _text(order.get("raw"))


_CORRECTION = re.compile(
    r"(?i)(?:^\s*\*)|\b(?:edit(?:ed)?|correction|corrected|meant|typo)\b"
    r"|\bnot\s+(?:the\s+)?(?:calls?|puts?|\$?\d)")
_CONTRACT_TOKENS = re.compile(
    r"(?i)\$?\d+(?:[.,/]\d+)*[cp]?\b|\b(?:calls?|puts?|[cp])\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b"
    r"|[@$\u2014\-:|,.]+")


def is_correction(text):
    """Does the alert SAY it is a fix? ("*puts", "meant 360", "typo")."""
    return bool(_CORRECTION.search(_text(text)))


def _prose(text, symbol):
    t = _text(text).lower()
    sym = _text(symbol).lower()
    if sym:
        t = re.sub(r"\b%s\b" % re.escape(sym), " ", t)
    t = _CONTRACT_TOKENS.sub(" ", t)
    return " ".join(t.split())


def similarity(a, b, symbol=""):
    """How alike two alerts read once the contract itself is removed. A bare
    contract line ("TSLA 357.5c 1.42", or one with a one-word tag like
    "lotto") leaves too little prose to judge by, so those are compared
    whole: a one-letter side flip still scores ~0.94, a different strike and
    price ~0.73."""
    pa, pb = _prose(a, symbol), _prose(b, symbol)
    if len(pa.split()) >= 3 and len(pb.split()) >= 3:
        return difflib.SequenceMatcher(None, pa, pb).ratio()
    ta, tb = " ".join(_text(a).lower().split()), " ".join(_text(b).lower().split())
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb).ratio()


def reads_as_edit(new_text, old_text, symbol=""):
    """The no-message-id test: a correction word, or a near-duplicate."""
    if is_correction(new_text):
        return True
    return similarity(new_text, old_text, symbol) >= SIMILARITY


def trader_of(order):
    return _text(order.get("trader")).lower()


def as_order(entry):
    """The pending entry back in order shape, for the existing cancel paths
    (Pullback.cancel_order / the book's key)."""
    return {"trader": entry.get("trader_name"), "symbol": entry.get("symbol"),
            "side": entry.get("side"), "strike": entry.get("strike"),
            "expiry": entry.get("expiry")}


class Revisions:
    """Every OPEN the bridge accepted, newest last, for as long as an edit of
    it could still arrive. Thread-safe: orders arrive on HTTP handler threads
    and pullback hunts run on their own."""

    def __init__(self, window_seconds=WINDOW_SECONDS, ttl_seconds=TTL_SECONDS):
        self.window = float(window_seconds)
        self.ttl = float(ttl_seconds)
        self._lock = threading.Lock()
        self._pending = []

    # -- state ---------------------------------------------------------------
    def clear(self):
        with self._lock:
            self._pending = []

    def pending(self):
        with self._lock:
            return [dict(e) for e in self._pending]

    def _sweep(self, now):
        cut = now - self.ttl
        self._pending = [e for e in self._pending if e["ts"] >= cut]

    def record(self, order, key=None, now=None):
        """Remember an OPEN the bridge accepted. A repost of the SAME contract
        by the same trader refreshes the one entry rather than stacking a
        second copy of it."""
        now = time.time() if now is None else float(now)
        sym, side, strike, expiry = contract_of(order)
        entry = {"ts": now,
                 "message_id": message_id(order),
                 "trader": trader_of(order),
                 "trader_name": _text(order.get("trader")) or "the caller",
                 "contract": (sym, side, strike, expiry),
                 "symbol": _text(order.get("symbol")).upper(),
                 "side": order.get("side"),
                 "strike": order.get("strike"),
                 "expiry": order.get("expiry"),
                 "entry_mode": _text(order.get("entry_mode")),
                 "raw": raw_text(order),
                 "key": key}
        with self._lock:
            self._sweep(now)
            self._pending = [e for e in self._pending
                             if not (e["contract"] == entry["contract"]
                                     and e["trader"] == entry["trader"])]
            self._pending.append(entry)
        return dict(entry)

    def drop(self, entry):
        """Forget one pending entry (it was cancelled, or it already filled and
        the ratchet owns it now)."""
        with self._lock:
            self._pending = [e for e in self._pending
                             if not (e["ts"] == entry.get("ts")
                                     and e["contract"] == entry.get("contract")
                                     and e["trader"] == entry.get("trader"))]

    # -- the one decision ----------------------------------------------------
    def superseded_by(self, order, now=None):
        """Which pending OPENs does this incoming OPEN replace? Oldest first."""
        if str(order.get("action") or "").upper() != "OPEN":
            return []
        # The second contract of a two-strike call shares its message id with
        # the first on purpose. It is a sibling, never a correction.
        if order.get("sibling"):
            return []
        now = time.time() if now is None else float(now)
        mine = contract_of(order)
        mid = message_id(order)
        who = trader_of(order)
        text = raw_text(order)
        out = []
        with self._lock:
            self._sweep(now)
            for e in self._pending:
                if e["contract"] == mine:
                    continue                    # identical repost, not an edit
                if mid and e["message_id"]:
                    if e["message_id"] != mid:
                        continue                # a different message entirely
                else:
                    if not who or e["trader"] != who:
                        continue
                    if e["contract"][0] != mine[0]:
                        continue
                    if now - e["ts"] > self.window:
                        continue
                    if not reads_as_edit(text, e.get("raw"), mine[0]):
                        continue                # a sibling trade, not a fix
                out.append(dict(e))
        return out


if __name__ == "__main__":
    r = Revisions()
    base = {"action": "OPEN", "trader": "PT | ei trades", "symbol": "TSLA",
            "side": "CALLS", "strike": 357.5, "expiry": "2026-09-16",
            "message_id": "chat-messages-1-2"}
    r.record(base, key="pt | ei trades|TSLA|357.5|CALLS|2026-09-16")
    edit = dict(base, side="PUTS")
    hit = r.superseded_by(edit)
    assert len(hit) == 1 and hit[0]["contract"][1] == "C", hit
    assert label(as_order(hit[0]), edit) == "357.5C"
    assert r.superseded_by(dict(base)) == []
    print("PASS  alert_revision self-check")
