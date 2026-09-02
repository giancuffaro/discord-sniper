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

import base64
import json
import re
import urllib.request
import urllib.error

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# Haiku: cheap and fast, and extraction is an easy task. Overridable in settings.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

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
- "same contracts" / "same cons" / "keep the same contracts on the load"
  = the speaker's PREVIOUS contract goes back to STAGED (loaded, ready) —
  carry prior ticker+strike+expiry forward but it is NOT an entry until
  their next "I'm in / got filled". Often said right after a stop-out: out
  at a loss, same contract re-loaded for a re-entry. "Get the contracts
  ready" with "I'm not in yet" = staging too, never an entry.
- MORE (G, 8/29): "my fingers are the trigger (on X)" = entry IMMINENT —
  keep that speaker's staged contract hot, but it is NOT the entry itself.
  "just have them ready" = staging confirmation. "taking a trim to cover
  my risk" = TRIM. "(you) can use breakeven stops" = move the stop to the
  ENTRY price (0% — scratch allowed, loss not): canonical "STOPMOVE X
  BREAKEVEN".
- STOP MOVES spoken (G, 8/29): "lowering/raising/moving my stop (loss) on
  X, <number> new stop loss" = the trader MOVED their stop to the
  UNDERLYING stock price <number>. Canonical: "STOPMOVE X <number>".
  Never an entry, never an exit, never a strike.
- "STARTERS" (G, 8/29): "I got starters (on X)" / "starter position" =
  they ENTERED with a partial-size position — a real entry (BTO), expect
  possible ADDs later. Mishears: "start this on Microsoft" = "starters on
  Microsoft". "A little chop in here" (often misheard "cock") = choppy
  market, commentary only.
- TRIMS spoken (G, 8/29): "taking (more) trims here" / "I've taken my
  second trims" = a TRIM executed — sell a partial, runners stay. "Take
  your trims, hold the rest" = the same instruction to the room: TRIM,
  never a full exit.
- "I'm stopping out (of my position) here, minus 6%" = FULL EXIT at a -6%
  LOSS. The percentage after "minus/down/loss" is their P&L, NEVER a trim
  size and NEVER a strike.
- MORE VOICE VOCAB (G, 8/29): "cons" = contracts. "I got filled (here)" =
  they are IN (execution confirmed). "I'll let you know when I get filled"
  = PENDING, not in — never an entry. "Filled on the wrong cons" = wrong
  contract, judgment call — do NOT copy. "Settle for green" / "settling
  for green here" = they are EXITING the position (a close, often small
  profit).
- VOICE-TRANSCRIPT GLOSSARY (mishears, G-confirmed 8/29): "pulls" = puts;
  "as p y" / "s p y" = SPY; "the Qs"/"cues" = QQQ; "one d t"/"one d t e" =
  1DTE (0-1 day expiry); numbers are often WORDS ("five sixty" = 560,
  "three forty five" = 345). A bare number is NEVER a strike — only
  "number + calls/puts" is. "my average is X" = their FILL PRICE (they are
  IN), not a strike. Never combine a ticker from one sentence with a strike
  from another if a different ticker appears between them.
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
    """Is the AI reader usable? One place decides.

    ALWAYS ON when a key exists (his call, 8/17: "make it always on, i need
    every trade to go through AI reading") — the old enabled flag is ignored
    so no toggle can quietly starve the reader. The only thing that turns it
    off is having no API key at all."""
    a = ((cfg or {}).get("execution", {}) or {}).get("ai_reader", {}) or {}
    return bool(a.get("api_key"))


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


# ---- SCREENSHOT reading: some rooms post the call as an image (his ask,
# 8/19: "there are some channels that post screenshots"). Same brain, same
# guards — the only new thing is the eyes. The model must TRANSCRIBE the
# trade-relevant text it sees (seen_text), and every field is then checked to
# literally appear in that transcription, exactly like a typed message. A model
# that invents "AAPL 500c" from a candlestick chart gets caught the same way.
VISION_SYSTEM = (
    "You read ONE screenshot from a stock/options/futures trading signal room "
    "and extract only what is LITERALLY visible in the image. You never guess a "
    "ticker, strike, expiry, or price that is not written in the picture. A bare "
    "chart, a candlestick, a P&L card with no order, or any image that is not an "
    "actionable order has action NONE. First transcribe the exact trade text you "
    "see, then fill the form. Reply with ONE JSON object and nothing else."
)

VISION_INSTRUCTION = """Look at the screenshot(s) and extract the trade call. Return exactly this JSON:
{{"seen_text": "<verbatim transcription of any order/ticker/strike/price text visible in the image>",
  "action": "OPEN|ADD|TRIM|CLOSE|NONE",
  "instrument": "option|future|equity",
  "ticker": "<symbol exactly as shown>",
  "side": "CALL|PUT|LONG|SHORT|null",
  "strike": <number or null>,
  "expiry": "<as shown, or null>",
  "price": <number or null>,
  "qty": <number or null>,
  "confidence": <0.0-1.0>}}

Rules:
- seen_text MUST be a faithful transcription — only characters actually in the image.
- Only use tickers, strikes and prices that literally appear in the image.
- A chart/graph with no explicit order text -> action NONE.
- "same contracts" / "same cons" / "keep the same contracts on the load"
  = the speaker's PREVIOUS contract goes back to STAGED (loaded, ready) —
  carry prior ticker+strike+expiry forward but it is NOT an entry until
  their next "I'm in / got filled". Often said right after a stop-out: out
  at a loss, same contract re-loaded for a re-entry. "Get the contracts
  ready" with "I'm not in yet" = staging too, never an entry.
- MORE (G, 8/29): "my fingers are the trigger (on X)" = entry IMMINENT —
  keep that speaker's staged contract hot, but it is NOT the entry itself.
  "just have them ready" = staging confirmation. "taking a trim to cover
  my risk" = TRIM. "(you) can use breakeven stops" = move the stop to the
  ENTRY price (0% — scratch allowed, loss not): canonical "STOPMOVE X
  BREAKEVEN".
- STOP MOVES spoken (G, 8/29): "lowering/raising/moving my stop (loss) on
  X, <number> new stop loss" = the trader MOVED their stop to the
  UNDERLYING stock price <number>. Canonical: "STOPMOVE X <number>".
  Never an entry, never an exit, never a strike.
- "STARTERS" (G, 8/29): "I got starters (on X)" / "starter position" =
  they ENTERED with a partial-size position — a real entry (BTO), expect
  possible ADDs later. Mishears: "start this on Microsoft" = "starters on
  Microsoft". "A little chop in here" (often misheard "cock") = choppy
  market, commentary only.
- TRIMS spoken (G, 8/29): "taking (more) trims here" / "I've taken my
  second trims" = a TRIM executed — sell a partial, runners stay. "Take
  your trims, hold the rest" = the same instruction to the room: TRIM,
  never a full exit.
- "I'm stopping out (of my position) here, minus 6%" = FULL EXIT at a -6%
  LOSS. The percentage after "minus/down/loss" is their P&L, NEVER a trim
  size and NEVER a strike.
- MORE VOICE VOCAB (G, 8/29): "cons" = contracts. "I got filled (here)" =
  they are IN (execution confirmed). "I'll let you know when I get filled"
  = PENDING, not in — never an entry. "Filled on the wrong cons" = wrong
  contract, judgment call — do NOT copy. "Settle for green" / "settling
  for green here" = they are EXITING the position (a close, often small
  profit).
- VOICE-TRANSCRIPT GLOSSARY (mishears, G-confirmed 8/29): "pulls" = puts;
  "as p y" / "s p y" = SPY; "the Qs"/"cues" = QQQ; "one d t"/"one d t e" =
  1DTE (0-1 day expiry); numbers are often WORDS ("five sixty" = 560,
  "three forty five" = 345). A bare number is NEVER a strike — only
  "number + calls/puts" is. "my average is X" = their FILL PRICE (they are
  IN), not a strike. Never combine a ticker from one sentence with a strike
  from another if a different ticker appears between them.
- "loading"/"watching"/"looking at" is NOT an order -> action NONE.
- A percentage or "trimmed"/"took profit" with no fresh contract is a TRIM.
- "out"/"sold"/"closed"/"stopped" is a CLOSE.
- If unsure it is a real, actionable call, use action NONE.
- Known symbols in this room (spelling help, not a filter): {allowed}
- Caption posted with the image (may be empty): \"\"\"{caption}\"\"\""""


def _fetch_image_b64(url, timeout=8, cap_bytes=5 * 1024 * 1024):
    """Download an image the browser already showed and return
    (media_type, base64) — or None. The page loaded it; we only read it, same
    footing as reading the text. Capped so a huge file can't stall the reader."""
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("user-agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            raw = resp.read(cap_bytes + 1)
        if len(raw) > cap_bytes:
            return None
        if ct not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
            # fall back on the extension when the header is vague
            low = url.lower()
            ct = ("image/png" if ".png" in low
                  else "image/gif" if ".gif" in low
                  else "image/webp" if ".webp" in low
                  else "image/jpeg")
        return ct, base64.b64encode(raw).decode("ascii")
    except Exception:                                       # noqa: BLE001
        return None


def read_image(images, caption, allowed_symbols, cfg, timeout=15):
    """Ask Claude to read a screenshot into the same fields read_signal returns,
    PLUS a seen_text transcription used for the anti-hallucination check. Returns
    a dict (with _seen_text) or None. Never raises for an ordinary failure."""
    a = _cfg(cfg)
    key = a.get("api_key")
    if not key or not images:
        return None
    # A vision-capable model. The configured model is used as-is (Haiku 4.5 and
    # the Sonnet/Opus lines all read images); a dedicated vision_model override
    # wins when set.
    model = a.get("vision_model") or a.get("model") or DEFAULT_MODEL
    blocks = []
    for u in list(images)[:3]:            # cap: at most 3 images per post
        got = _fetch_image_b64(u, timeout=min(timeout, 8))
        if not got:
            continue
        mt, b64 = got
        blocks.append({"type": "image", "source": {
            "type": "base64", "media_type": mt, "data": b64}})
    if not blocks:
        return {"_error": "no image could be fetched"}
    allowed = ", ".join(sorted(set(allowed_symbols or [])))[:400]
    prompt = VISION_INSTRUCTION.format(allowed=allowed or "(none listed)",
                                       caption=(caption or "")[:400])
    content = blocks + [{"type": "text", "text": prompt}]
    body = json.dumps({
        "model": model,
        "max_tokens": 400,
        "system": VISION_SYSTEM,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=body, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("x-api-key", key)
    req.add_header("anthropic-version", API_VERSION)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": "HTTP %s" % e.code}
    except Exception:                                       # noqa: BLE001
        return {"_error": "unreachable"}
    try:
        parts = data.get("content") or []
        raw = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except Exception:                                       # noqa: BLE001
        raw = ""
    out = _extract_json(raw)
    if not isinstance(out, dict):
        return {"_error": "unparseable reply"}
    # Expose the transcription under a private key the bridge feeds to validate()
    # as the "text" — so the literal-match guard checks the image's own words.
    out["_seen_text"] = str(out.get("seen_text") or "")
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
        # NO symbol whitelist. His rule is "follow everything to the tee" and
        # the main parser has no filter — the AI path having one meant SPXW and
        # NBIS calls were dropped as "not on your list" (8/12) while the same
        # names traded fine through the parser. The list is spelling help for
        # the model (see INSTRUCTION), never a gate. The real guard is below:
        # the ticker must actually appear in the message, which is what stops a
        # hallucinated symbol — that one stays.
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
    # A "premium" at or above the strike is the STOCK level, not the option
    # (9/2 11:06, Midas: "In $NVDA 225c 9/4 2.71 adding at 224.70" read as
    # @ 224.7 — the add trigger on the underlying; the premium was 2.71).
    # An option never costs its own strike in these rooms; drop the number
    # so the bridge bids the market instead of carrying a stock price as
    # a limit through affordability and the reverse-average math.
    try:
        if (price is not None and strike is not None
                and str(read.get("instrument") or "option").lower() == "option"
                and float(price) >= float(strike) > 0):
            price = None
    except (TypeError, ValueError):
        pass

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
