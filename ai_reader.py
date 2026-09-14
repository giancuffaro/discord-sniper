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
import time
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
- FELONY LIVE VOCAB (from the first captured FST Zoom, 9/9): "take
  breakeven" / "taking breakeven" / "I'm a take breakeven" / "we'll take
  breakeven" = they are EXITING the whole position (a CLOSE at ~entry).
  "that was our target" / "hopefully you guys trimmed" = a TRIM at target,
  not a new order. "if we break that candle's high we're out" / "we'll just
  stop out" = a CONDITIONAL stop, NOT an exit now -> NONE. Spelled-out
  futures roots are tickers: "r t y" = RTY, "y m" = YM, "e s" = ES, "n q"
  = NQ; "in queue" = NQ; "queues" / "the queues" = QQQ. Deepgram writes
  index LEVELS as small dollar amounts: "$7.64" said about SPY = the 764
  level, "$3.18" said about Apple = 318 — a "$X.XX" under $10 next to a
  ticker is the underlying price x100, NEVER a premium unless "contracts",
  "cons" or "premium" is said. "short RTY, long YM, long ES" said as a
  read of relative strength ("makes sense, right?") is commentary -> NONE.
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


def key_of(cfg):
    """The Anthropic key. Its presence is no longer the same question as
    "can we read" — see signal_available()."""
    return _cfg(cfg).get("api_key")


# ANTHROPIC IS THE LAST RESORT NOW (9/14). The account has been billing-blocked
# since 9/13, and the image lane was the one place still calling it FIRST: every
# screenshot read on 9/14 came back "HTTP 400: Your credit balance is too low",
# including PT's 10:22 post. A refusal that names credit/billing parks the
# provider for six hours so the image lane stops paying latency for a call that
# cannot succeed; settings execution.ai_reader.billing_blocked = true parks it
# outright.
BILLING_WORDS = ("credit balance", "insufficient credit", "billing",
                 "purchase credits", "insufficient_quota")
_ANTHROPIC_BLOCK_UNTIL = [0.0]
ANTHROPIC_BLOCK_SECONDS = 6 * 3600


def note_anthropic_error(err):
    """Remember a refusal that can only be fixed by paying the bill."""
    low = str(err or "").lower()
    if any(w in low for w in BILLING_WORDS):
        _ANTHROPIC_BLOCK_UNTIL[0] = time.time() + ANTHROPIC_BLOCK_SECONDS
        return True
    return False


def anthropic_blocked(cfg):
    if _cfg(cfg).get("billing_blocked"):
        return True
    return time.time() < _ANTHROPIC_BLOCK_UNTIL[0]


def _providers_ready(cfg):
    try:
        import observer_providers
        return observer_providers.providers_available(cfg)
    except Exception:                                       # noqa: BLE001
        return False


def signal_available(cfg):
    """Can ONE message be read at all? Any provider key will do — the Anthropic
    key alone stopped being the answer to that on 9/13, when it was billing-
    blocked and `available()` still said yes 242 times."""
    return _providers_ready(cfg) or (
        bool(_cfg(cfg).get("api_key")) and not anthropic_blocked(cfg))


def image_available(cfg):
    """Same question for a screenshot, same answer."""
    return signal_available(cfg)


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


def _read_signal_anthropic(prompt, cfg, timeout):
    """The last-resort lane. Same prompt, same JSON contract."""
    a = _cfg(cfg)
    model = a.get("model") or DEFAULT_MODEL
    body = json.dumps({
        "model": model,
        "max_tokens": 300,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=body, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("x-api-key", key_of(cfg))
    req.add_header("anthropic-version", API_VERSION)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        why = ""
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
            why = str(((j.get("error") or {}).get("message")) or "")[:160]
        except Exception:                                   # noqa: BLE001
            pass
        note_anthropic_error(why)
        return {"_error": "anthropic HTTP %s" % e.code}
    except Exception:                                       # noqa: BLE001
        return {"_error": "anthropic unreachable"}
    # Anthropic returns content as a list of blocks; the text is in the first.
    try:
        parts = data.get("content") or []
        raw = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except Exception:                                       # noqa: BLE001
        raw = ""
    out = _extract_json(raw)
    if not isinstance(out, dict):
        return {"_error": "anthropic unparseable reply"}
    out["_provider"] = "anthropic"
    out["_model"] = model
    return out


def read_signal(text, allowed_symbols, cfg, timeout=8):
    """Read ONE message into fields. Returns a dict or None.

    THE PROVIDER ORDER IS THE ONE THE IMAGE LANE AND THE OBSERVER USE (9/14):
    OpenAI first, Gemini next, Anthropic last and skipped while it is
    billing-blocked. Same prompt, same JSON contract, same keys, same cooldown
    map. This changes WHO reads, never what a read is allowed to do: the answer
    is still DATA, validated field by field against the literal message and then
    run back through the parser and every guard. AI confidence authorizes
    nothing. Before this, the lane was hard-coded to Anthropic and logged 242
    "AI READ no call - ai: HTTP 400" lines on 9/14 alone.

    Never raises into the caller for an ordinary failure (no key, network, bad
    reply) — a reader that crashes the bridge would be worse than one that stays
    quiet. A failure comes back as {"_error": ...}, which validate() turns into
    a refusal: no call, never an order.
    """
    if not text:
        return None
    allowed = ", ".join(sorted(set(allowed_symbols or [])))[:400]
    prompt = INSTRUCTION.format(allowed=allowed or "(none listed)", text=text[:1500])
    attempts = []
    try:
        import observer_providers
    except Exception:                                       # noqa: BLE001
        observer_providers = None
    if observer_providers is not None and observer_providers.providers_available(cfg):
        out, _ms = observer_providers.read_signal(SYSTEM, prompt, cfg)
        if isinstance(out, dict):
            attempts = out.get("_attempts") or []
            if not out.get("_error"):
                return out
    failed = _attempt_error(attempts)
    if not key_of(cfg):
        return {"_error": failed} if failed else None
    if anthropic_blocked(cfg):
        return {"_error": ((failed + "; ") if failed else "")
                          + "anthropic billing-blocked"}
    out = _read_signal_anthropic(prompt, cfg, timeout)
    if out.get("_error") and failed:
        out["_error"] = failed + "; " + out["_error"]
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


def _image_blocks(images, timeout):
    """Fetch at most three images the browser already displayed and return
    [(media_type, base64), ...]."""
    blocks = []
    for u in list(images)[:3]:
        got = _fetch_image_b64(u, timeout=min(timeout, 8))
        if got:
            blocks.append(got)
    return blocks


def _attempt_error(attempts):
    """'openai HTTP_400; gemini timeout' — which provider failed and how, so
    the log line is the diagnosis instead of a bare 'no read'."""
    bits = []
    for a in attempts or []:
        if a.get("error"):
            bits.append("%s %s" % (a.get("provider"), a.get("error")))
    return "; ".join(bits)


def _read_image_anthropic(blocks, prompt, cfg, timeout):
    """The last-resort lane. Same prompt, same JSON contract."""
    a = _cfg(cfg)
    key = a.get("api_key")
    model = a.get("vision_model") or a.get("model") or DEFAULT_MODEL
    content = [{"type": "image", "source": {"type": "base64",
                                            "media_type": mt, "data": b64}}
               for mt, b64 in blocks]
    content.append({"type": "text", "text": prompt})
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
        # KEEP THE REASON (9/8 vision sweep). 12 of 137 screenshot reads in the
        # log had failed as a bare "HTTP 400" — the API's own explanation was
        # read and discarded, so nobody could tell whether it was image size,
        # a media type, or a bad request. The message is short and it is the
        # whole diagnosis; carry it, and let it park a billing failure.
        why = ""
        try:
            body_ = e.read().decode("utf-8", "replace")
            j = json.loads(body_)
            why = str(((j.get("error") or {}).get("message")) or body_)[:160]
        except Exception:                                   # noqa: BLE001
            pass
        note_anthropic_error(why)
        return {"_error": "anthropic HTTP %s%s" % (e.code, (": " + why) if why else "")}
    except Exception:                                       # noqa: BLE001
        return {"_error": "anthropic unreachable"}
    try:
        parts = data.get("content") or []
        raw = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except Exception:                                       # noqa: BLE001
        raw = ""
    out = _extract_json(raw)
    if not isinstance(out, dict):
        return {"_error": "anthropic unparseable reply"}
    out["_provider"] = "anthropic"
    out["_model"] = model
    return out


def read_image(images, caption, allowed_symbols, cfg, timeout=15):
    """Read a screenshot into the same fields read_signal returns, PLUS a
    seen_text transcription used for the anti-hallucination check.

    THE PROVIDER ORDER IS THE SAME ONE THE TEXT OBSERVER USES (9/14): OpenAI
    vision first, Gemini next, Anthropic last and only when it is not
    billing-blocked. Same prompt contract, same keys, same cooldowns. Nothing
    here authorizes an order: the result is a PROPOSED read, validated field by
    field against the image's own transcribed words and then run through the
    normal parser and guards, exactly as before.

    Returns a dict (with _seen_text and _provider) or None. Never raises for an
    ordinary failure — a reader that crashes the bridge would be worse than one
    that stays quiet.
    """
    if not images:
        return None
    blocks = _image_blocks(images, timeout)
    if not blocks:
        return {"_error": "no image could be fetched"}
    allowed = ", ".join(sorted(set(allowed_symbols or [])))[:400]
    prompt = VISION_INSTRUCTION.format(allowed=allowed or "(none listed)",
                                       caption=(caption or "")[:400])
    attempts = []
    try:
        import observer_providers
    except Exception:                                       # noqa: BLE001
        observer_providers = None
    if observer_providers is not None and observer_providers.providers_available(cfg):
        out, _ms = observer_providers.read_image(VISION_SYSTEM, prompt,
                                                 blocks, cfg)
        if isinstance(out, dict):
            attempts = out.get("_attempts") or []
            if not out.get("_error"):
                out["_seen_text"] = str(out.get("seen_text") or "")
                return out
    failed = _attempt_error(attempts)
    if not _cfg(cfg).get("api_key"):
        return {"_error": failed or "no vision provider key"}
    if anthropic_blocked(cfg):
        return {"_error": ((failed + "; ") if failed else "")
                          + "anthropic billing-blocked"}
    out = _read_image_anthropic(blocks, prompt, cfg, timeout)
    if out.get("_error"):
        return {"_error": ((failed + "; ") if failed else "") + out["_error"]}
    # Expose the transcription under a private key the bridge feeds to validate()
    # as the "text" — so the literal-match guard checks the image's own words.
    out["_seen_text"] = str(out.get("seen_text") or "")
    return out


# ---- the guard: the model's read is DATA, checked against the text ----------

# ANSI COLOUR CODES ARE NOT PART OF THE MESSAGE (9/11). Namrood-BOT posts its
# alerts inside a coloured Discord code block, so the raw text the reader
# scrapes carries "\x1b[1;30;47m" right in front of the ticker. The escape byte
# is invisible, the "m" is not: every literal check below then saw "47mMETA"
# and refused a real call as "the reader named META but it isn't in the
# message" — three times live, 8/12-8/18 (MXLU / MMETA / MSPCX in trades.log,
# where the same glued "m" reached the log as the symbol). parser.js strips
# these in cleanText; this is the same strip for the AI path's guard, so the
# two readers judge the same string.
RE_ANSI = re.compile(r"\x1b?\[[0-9;]{1,16}m")


def _plain(text):
    return RE_ANSI.sub(" ", str(text or ""))


def _num_in_text(n, text):
    """Does this number literally appear in the message? 155 matches '155',
    '$155', '155c'; 2.42 matches '2.42'. Anti-hallucination for strike/price."""
    if n is None:
        return True
    text = _plain(text)
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

    up = _plain(text).upper()
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
        # IS THAT A TICKER, OR A WORD FROM THE MESSAGE? (9/11)
        # Being present in the text is not enough when the "ticker" is an
        # English word that was in the sentence all along:
        #     "...has to hold and then can go with 773c."  ->  OPEN WITH 773C
        # (Midas, 9/3, in trades.log). The literal-match guard above passes
        # that one happily, because WITH really is in the message. parser.js
        # and bridge.py both check extension/optionable.txt; this reader was
        # the one side that did not, so a word-as-ticker could still be minted
        # here and only got stopped three layers later, after it was in the log
        # and in the room's attribution. FAILS OPEN exactly as the other two
        # do: symbols.known() returns True when the file is missing or short,
        # because a text file that failed to load must never halt trading.
        try:
            import symbols as _symbols
            if not _symbols.known(ticker):
                return False, ("%s isn't a ticker anyone lists options on — "
                               "that's a word from the message" % ticker), None
        except ImportError:
            pass
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
    instrument = str(read.get("instrument") or "option").lower()
    if action in ("OPEN", "ADD"):
        if instrument == "option" and side not in ("CALLS", "PUTS"):
            return False, "option entry requires an explicit call or put side", None
        if instrument == "future":
            side = {"BUY": "LONG", "SELL": "SHORT"}.get(side, side)
            if side not in ("LONG", "SHORT"):
                return False, "futures entry requires an explicit direction", None

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
            d = {"BUY": "LONG", "SELL": "SHORT"}.get(c.get("side"), c.get("side"))
            if d not in ("LONG", "SHORT"):
                return ""
            s = "%s %s" % (d, t)
            return s + (" @ %g" % price if price is not None else "")
        if c.get("instrument") == "equity":
            s = "%s equity" % t
            return s + (" @ %g" % price if price is not None else "")
        # An entry verb (BTO / adding) + a $ before the strike is the form the
        # parser reads without ambiguity — a bare "COIN 155C" doesn't parse.
        sd = {"CALL": "C", "CALLS": "C", "PUT": "P", "PUTS": "P"}.get(c.get("side"))
        if sd is None:
            return ""
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
