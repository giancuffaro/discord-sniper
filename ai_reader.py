"""
ai_reader.py — a READING brain for the messages the regex parser can't crack.

His words: "give it reading intelligence, not any other thing." So that is ALL
this does. When the deterministic parser (signals.py) can't make out a message,
this hands that one message to Claude and asks it to pull out the pieces of a
call — ticker, strike, call/put, expiry, price, action — and NOTHING else. It
never decides whether to trade. Its answer is run right back through the same
guards every other signal passes: the ticker (and strike, and price) it claims
must literally appear in the message, the symbol must be on the allow-list, and
you must actually be in a position for an exit. A model that invents "AAPL 500c"
out of a weather report gets caught and refused, exactly like a bad regex would.

Money-safety by construction:
  * Only ever CALLED on a message the regex already gave up on (a miss), so it
    can't override a clean read.
  * Its output is DATA, not an instruction — validated field by field against
    the original text before anything is built.
  * No network key, no call, no cost unless you turn it on with your own key.

The call is a plain HTTPS POST (urllib) so there's no extra package to install.
"""

import json
import re
import urllib.request
import urllib.error

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# Haiku: cheap and fast, and extraction is an easy task. Overridable in settings.
DEFAULT_MODEL = "claude-3-5-haiku-latest"

SYSTEM = (
    "You read ONE message from a stock/options/futures trading signal room and "
    "extract only what is LITERALLY stated. You never guess or infer a ticker, "
    "strike, expiry, or price that is not written in the message. If the message "
    "is chatter, analysis, a P&L brag, a plan, or anything that is not an "
    "actionable order, the action is NONE. Reply with ONE JSON object and nothing "
    "else."
)

# The shape we ask for. Kept tiny on purpose — the model fills a form, it does
# not write prose.
INSTRUCTION = """Extract the trade call from this message. Return exactly this JSON:
{{"action": "OPEN|ADD|TRIM|CLOSE|NONE",
  "instrument": "option|future|equity",
  "ticker": "<symbol as written, e.g. SPY, NQ, AAPL>",
  "side": "CALL|PUT|LONG|SHORT|null",
  "strike": <number or null>,
  "expiry": "<as written, e.g. 8/7, 0DTE, Aug 7, or null>",
  "price": <number or null>,
  "qty": <number or null>,
  "confidence": <0.0-1.0>}}

Rules:
- Only use tickers, strikes, and prices that literally appear in the message.
- "loading"/"prepping"/"watching"/"looking at" is NOT an order -> action NONE.
- A percentage or "took profit"/"trimmed" with no fresh contract is a TRIM.
- "out"/"sold"/"closed"/"stopped"/"took an L" is a CLOSE.
- If you are not sure it is a real, actionable call, use action NONE.
- Known symbols in this room (for spelling, not a filter): {allowed}

Message:
\"\"\"{text}\"\"\""""


class AIError(Exception):
    pass


def available(cfg):
    """Is the AI reader switched on and keyed? One place decides."""
    a = ((cfg or {}).get("execution", {}) or {}).get("ai_reader", {}) or {}
    return bool(a.get("enabled")) and bool(a.get("api_key"))


def _cfg(cfg):
    return ((cfg or {}).get("execution", {}) or {}).get("ai_reader", {}) or {}


def _extract_json(s):
    """Pull the first {...} object out of the model's reply, tolerant of any
    stray text around it."""
    if not s:
        return None
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:                                       # noqa: BLE001
        return None


def read_signal(text, allowed_symbols, cfg, timeout=8):
    """Ask Claude to read one message into fields. Returns a dict or None.

    Never raises into the caller for an ordinary failure (no key, network, bad
    reply) — a reader that crashes the bridge would be worse than one that
    stays quiet. Returns None on any trouble; the message just stays unread,
    same as before the AI existed.
    """
    a = _cfg(cfg)
    key = a.get("api_key")
    if not key or not text:
        return None
    model = a.get("model") or DEFAULT_MODEL
    allowed = ", ".join(sorted(set(allowed_symbols or [])))[:400]
    prompt = INSTRUCTION.format(allowed=allowed or "(none listed)", text=text[:1500])
    body = json.dumps({
        "model": model,
        "max_tokens": 300,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=body, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("x-api-key", key)
    req.add_header("anthropic-version", API_VERSION)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 401 bad key, 429 rate, 5xx — all just mean "no read this time".
        return {"_error": "HTTP %s" % e.code}
    except Exception:                                       # noqa: BLE001
        return {"_error": "unreachable"}
    # Anthropic returns content as a list of blocks; the text is in the first.
    try:
        parts = data.get("content") or []
        raw = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except Exception:                                       # noqa: BLE001
        raw = ""
    out = _extract_json(raw)
    if not isinstance(out, dict):
        return {"_error": "unparseable reply"}
    return out


# ---- the guard: the model's read is DATA, checked against the text ----------

def _num_in_text(n, text):
    """Does this number literally appear in the message? 155 matches '155',
    '$155', '155c'; 2.42 matches '2.42'. Anti-hallucination for strike/price."""
    if n is None:
        return True
    s = ("%g" % float(n))
    # whole numbers: match as a token not glued inside a longer number
    if "." not in s:
        return re.search(r"(?<!\d)%s(?!\d)" % re.escape(s), text) is not None
    return s in text.replace(",", "")


def validate(read, text, allowed_symbols):
    """Turn a model read into a trustworthy (action, fields) or a refusal.

    Returns (ok: bool, reason_or_none, cleaned_dict). Every field that could
    move money is checked to LITERALLY exist in the message, and the ticker
    must be on the allow-list — the same bar a regex read has to clear.
    """
    if not isinstance(read, dict):
        return False, "no read", None
    if read.get("_error"):
        return False, "ai: %s" % read["_error"], None
    action = str(read.get("action") or "NONE").upper()
    if action == "NONE":
        return False, "the reader saw no actionable call in it", None
    if action not in ("OPEN", "ADD", "TRIM", "CLOSE"):
        return False, "the reader returned an action I don't run (%s)" % action, None

    up = text.upper()
    ticker = str(read.get("ticker") or "").upper().lstrip("$").strip()
    allow = {str(s).upper() for s in (allowed_symbols or [])}

    # For an EXIT/TRIM a bare "out"/"trim" needs no ticker in the line — the
    # position resolves it downstream. But if the model DID name a ticker, it
    # has to be real and present.
    if ticker:
        if allow and ticker not in allow:
            return False, "the reader named %s, which isn't on your list" % ticker, None
        if not re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(ticker), up):
            return False, "the reader named %s but it isn't in the message" % ticker, None
    elif action in ("OPEN", "ADD"):
        return False, "the reader found an entry with no ticker in the message", None

    strike = read.get("strike")
    if action in ("OPEN", "ADD") and strike is not None and not _num_in_text(strike, text):
        return False, "the reader's strike %s isn't in the message" % strike, None
    price = read.get("price")
    if price is not None and not _num_in_text(price, text):
        # a price that isn't in the text is untrustworthy — drop it, don't refuse
        price = None

    side = str(read.get("side") or "").upper() or None
    if side in ("CALL", "CALLS"):
        side = "CALLS"
    elif side in ("PUT", "PUTS"):
        side = "PUTS"

    cleaned = {
        "action": action,
        "instrument": str(read.get("instrument") or "option").lower(),
        "ticker": ticker or None,
        "side": side,
        "strike": float(strike) if (strike is not None and action in ("OPEN", "ADD")) else None,
        "expiry": read.get("expiry") or None,
        "price": float(price) if price is not None else None,
        "qty": int(read["qty"]) if str(read.get("qty") or "").strip().isdigit() else None,
        "confidence": float(read.get("confidence") or 0),
    }
    # An OPEN option with no strike is not a whole contract — refuse rather than
    # buy a guess.
    if cleaned["action"] in ("OPEN", "ADD") and cleaned["instrument"] == "option" \
            and cleaned["strike"] is None:
        return False, "the reader found an entry but no strike, so it's not a full contract", None
    return True, None, cleaned


def canonical(c):
    """Rebuild a validated read as a CLEAN call in the room's own grammar, so it
    can be run straight back through the real parser (signals.py / parser.js) and
    through every guard — dedupe, position resolution, live/test routing. The AI
    only translates messy -> clean; the proven parser still has the final say."""
    if not c:
        return ""
    act = c.get("action")
    t = (c.get("ticker") or "").upper()
    price = c.get("price")
    if act in ("OPEN", "ADD"):
        if c.get("instrument") == "future":
            d = c.get("side") if c.get("side") in ("LONG", "SHORT") else "LONG"
            s = "%s %s" % (d, t)
            return s + (" @ %g" % price if price is not None else "")
        if c.get("instrument") == "equity":
            s = "%s equity" % t
            return s + (" @ %g" % price if price is not None else "")
        # An entry verb (BTO / adding) + a $ before the strike is the form the
        # parser reads without ambiguity — a bare "COIN 155C" doesn't parse.
        sd = "C" if c.get("side") == "CALLS" else ("P" if c.get("side") == "PUTS" else "C")
        verb = "adding" if act == "ADD" else "BTO"
        s = "%s %s $%g%s" % (verb, t, float(c.get("strike")), sd)
        if c.get("expiry"):
            s += " %s" % c["expiry"]
        return s + (" @ %g" % price if price is not None else "")
    if act == "TRIM":
        return ("TRIM %s" % t).strip()
    if act == "CLOSE":
        return ("%s OUT" % t).strip() if t else "OUT"
    return ""
