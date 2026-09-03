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
RE_HDR = re.compile(r"^(?P<who>[A-Za-z0-9_.\- ]{2,24})\s*\((scribe|admin|mod)\)"
                    r"\s*[—\-]+\s*\d{1,2}:\d{2}\s*(AM|PM)\s*", re.IGNORECASE)
RE_STAG = re.compile(
    r"(?:[A-Za-z0-9_.$|&' \-]{1,40}?\s*\[[^\]]{1,16}\],?\s*)?Server Tag:\s*\S{1,16}(?:\s+\S{1,16})?"
    r"(?:\s+(?:Owner|Admin|Founder|CEO|Mod|Moderator|Analyst|Trader))?"
    r"(?:\s*[—\-]+\s*(?:\d{1,2}/\d{1,2}/\d{2,4},?\s*)?\d{1,2}:\d{2}\s*[AP]M"
    r"(?:\s+[A-Za-z]+day,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M)?)?", re.I)
RE_EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⯿️]")

# --- the pieces of a call ----------------------------------------------------
# The $ before the strike is Brett's habit: "In NVDA $210C to July 29th".
# The lookbehind is load-bearing. Without it the symbol group happily matches
# the TAIL of a longer word — "Loading 205 calls" gave a ticker of ADING, which
# then failed the allowed-list check for reasons that had nothing to do with
# what the line said.
RE_CONTRACT = re.compile(
    # The expiry between symbol and strike can be a date, a DTE, or — the
    # Whop room's habit — a month name: "Entered nvda July 20th 205c".
    # Without the month alternative, "July" got read as the SYMBOL and the
    # entry came out as TH 205C.
    r"(?<![A-Za-z])\$?(?P<symbol>[A-Za-z]{1,5})\s+"
    r"(?:(?P<expiry>\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d*dte"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\s+\d{1,2}(?:st|nd|rd|th)?)\s+)?"
    r"\$?(?P<strike>\d{1,5}(?:\.\d{1,2})?)\s*"
    r"(?P<kind>calls?|puts?|c|p)\b", re.IGNORECASE)

# The same contract written back to front: "205 calls Friday expiration on
# NVDA". Requires the word "on" before the ticker — that's what keeps it from
# reading "10% on SPY" as a contract, and it's how they actually write it.
RE_CONTRACT_REV = re.compile(
    r"(?<![A-Za-z\d.])\$?(?P<strike>\d{1,5}(?:\.\d{1,2})?)\s*"
    r"(?P<kind>calls?|puts?|c|p)\b"
    r"(?P<mid>[^.!?]{0,40}?)"
    r"\b(?:on|for)\s+\$?(?P<symbol>[A-Za-z]{1,5})\b", re.IGNORECASE)

# "Friday expiration" is not a missing date — it's the same weekly the room's
# pinned rules already default to, said out loud. Kept as the token WEEKLY so
# the log can say "this Friday" and so turning assume_weekly_expiry off doesn't
# also refuse the calls where they actually told you.
RE_FRI_EXP = re.compile(r"\bfri(?:day)?\s*exp\w*", re.IGNORECASE)

# Expiries that turn up somewhere other than in front of the strike — "to July
# 29th" trails the contract instead of leading it. Only consulted when the
# contract itself didn't carry one.
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
RE_MONTH_DAY = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
                          r"[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
RE_DTE_ANY = re.compile(r"\b(\d*dte)s?\b", re.IGNORECASE)
RE_DATE_ANY = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")

RE_PCT = re.compile(r"@\s*(-?\d{1,3}(?:\.\d+)?)\s*%")
# A percentage anywhere at all. The second room writes trims as a bare number:
# "20%", "50% @here", "40% in spy now". No verb, no ticker, just the number.
RE_PCT_ANY = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*%")
# "5-6% risk." and "risk was only 10%" are position sizing, not a gain. Same
# shape as a bare trim and the exact opposite meaning — read as a trim it sells
# you out of a trade on a sentence about how much they're willing to lose.
# Only consulted when the line has no exit verb in it, so "trimming SPY @ 45%,
# risk free now" is untouched.
RE_PCT_RISK = re.compile(
    r"\d{1,3}(?:\.\d+)?\s*%\s*(?:of\s+)?(?:risk|stop|trail)\b"
    r"|\b(?:risk|risking|risked|stop|trail|lose|losing|lost|drawdown)\b"
    r"[^.!?]{0,25}?\d{1,3}(?:\.\d+)?\s*%",
    re.IGNORECASE)
# "My avg is $3.05" — posted a minute after the entry, as its own message.
RE_AVG = re.compile(r"\bavg|\baverage\b", re.IGNORECASE)
# a price, but never a percentage: "@ 3.4" is a fill, "@ 38%" is a gain
RE_LIMIT = re.compile(r"@\s*\$?(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)")
# "(2 CONS)" and "Entered (4) SLV 55C" — the 2K challenge posts HIS size
# with every entry, in parentheses. Captured for the record and for the day
# per-room LIVE wants to mirror his sizing.
RE_QTY = re.compile(r"\b(\d{1,3})\s*(?:x|con(?:tract)?s?|lots?)\b", re.IGNORECASE)
RE_QTY_PAREN = re.compile(r"\((\d{1,3})\)\s*(?=[A-Za-z$])")
# Case-insensitive on purpose — the second room types "on spy", not "on SPY".
# Lowercase only counts when you have an allowed-symbols list to check it
# against; see _bare_symbol for why.
RE_BARE = re.compile(r"\b([A-Za-z]{1,5})\b")

# --- the five things the room says -------------------------------------------
# "loading" is the main room; "PREP AAPL 350 C 7/31" is Aristotle's word for
# the same thing, and Midas says "Loaded ... cons" — all of them mean GET
# READY, none of them buys.
RE_LOADING = re.compile(r"\b(?:load(?:ing|ed)?|prep(?:ping|ped)?)\b",
                        re.IGNORECASE)
RE_ALLOUT = re.compile(r"\ball\s+out\b", re.IGNORECASE)
RE_TRIM = re.compile(r"\btrim(?:ming|med|s)?\b|\btook\s+some\s+off\b",
                     re.IGNORECASE)
RE_BACKIN = re.compile(r"\bback\s+in\b", re.IGNORECASE)
# "swinging" is an ENTRY verb in these rooms, not chatter (his words, 8/12:
# "swinging means opening a position today and closing it tomorrow"). Aristotle
# posting "I'm swinging SPCS 165 C 9/18" is in it right now — the same shape
# that got him into SKHY on 8/11 for +$590. Only the present-progressive form
# counts: "swinging <contract>" is a position, while "swing trade idea",
# "that was a good swing" and "going to swing it" are not, and the chatter
# guard below still vetoes the conditional ones.
RE_ENTRY = re.compile(
    r"\b(?:in|entered|entering|filled|bto|bought|buying|grabbed)\b"
    r"|\b(?:took|take|taking)\s+(?:some|a|entry|entries)\b"
    r"|\bswinging\b(?!\s+(?:trade|idea|setup|watch))", re.IGNORECASE)
# "added to SPY @everyone new avg is 2.8" — they doubled up and their average
# moved. Whether that buys you a second contract is a setting, not a parser
# decision: the parser only says "this is an add", and guards.resolve_add has
# the final word, because only the guards know whether you're even in it.
RE_ADD = re.compile(r"\badd(?:ed|ing|s)?\s+(?:to|more|into)\b|\badding\b"
                    # "added $ONDS 10c 7/17" — past-tense add straight onto a
                    # contract. "adding" alone matched but "added <contract>"
                    # slipped through and read as nothing (a missed entry).
                    r"|\badd(?:ed|ing)?\s+\$?[A-Za-z]{1,5}\s+\$?\d{1,4}(?:\.\d{1,2})?\s*(?:calls?|puts?|[cp])\b"
                    r"|\baverag(?:e|ed|ing)\s+(?:in|down|up)\b"
                    r"|\b(?:new|updated)\s+(?:avg|average)\b", re.IGNORECASE)
# The premium on an add, read in priority order and NEVER off a stock level.
# "adding $LMND 65c ... off strong support @ $52" was reading $52 (the share
# support price) as the contract premium. A real premium arrives as "filled
# 10.00", "avg 8.70", or a bare "@ 1.2" — small, usually with a decimal, and
# not written as "$<whole number>".
RE_FILL_PRICE = re.compile(
    r"\b(?:filled|fill|fills|filling|bought)\s+\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)",
    re.IGNORECASE)
def _add_premium(t):
    m = RE_FILL_PRICE.search(t)
    if m:
        return float(m.group(1))
    m = RE_AVG_PRICE.search(t)
    if m:
        return float(m.group(1))
    for m in re.finditer(r"@\s*(\$?)(\d+(?:\.\d{1,4})?)(?![\d.]*\s*%)", t):
        dollar, num = m.group(1), m.group(2)
        val = float(num)
        # "@ $52" (dollar sign + whole number) is a share price, not a premium.
        if dollar and "." not in num:
            continue
        if val >= 100:                       # no option here trades at 100+
            continue
        return val
    return None
# The price out of "new avg is 2.8", "avg 3.05", "average: $2.90". Their new
# average is what you'd be paying up to, so it becomes the limit. Never a
# percentage — "avg gain 30%" is a result, not a price.
RE_AVG_PRICE = re.compile(
    r"\b(?:avg|average)\w*\s*(?:is|of|at|around|near|:|=|@)?\s*"
    r"\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)", re.IGNORECASE)
RE_EXIT = re.compile(
    r"\b(?:exited|exiting|closed|closing|stc|sold|selling|out|cutting)\b",
    re.IGNORECASE)
# "Filled 3.95 starters" — their entry arrives as TWO messages. The contract was
# named minutes earlier in a "Loading 205 calls Friday expiration on NVDA"
# notice, and this line carries nothing but the price. On its own it is not an
# order; guards.resolve_loaded pins it to that notice, or nothing is sent.
#
# Only a line that STARTS with the fill verb counts. "trimmed at 3.95" and
# "their avg was 3.95" are the same numbers meaning the opposite thing, and both
# of them lose the word "filled" at the front.
RE_BARE_FILL = re.compile(
    r"^(?:just\s+|we\s+|i\s+|i've\s+|ive\s+|we've\s+)*"
    r"(?:filled|fills|filling|fill|bought|bto|entered)\b"
    r"[^\d%]{0,14}\$?(\d{1,3}\.\d{1,2})\b(?!\s*%)",
    re.IGNORECASE)

# ---- futures ----------------------------------------------------------------
# Felony's grammar, from his real posts: "Short NQ @ 28660  Stop 29700
# Target 28550". A futures call names no strike and no expiry — the symbol,
# the direction and the price ARE the contract. The stop and target are his
# own numbers in index points, captured because the plan is to use HIS levels
# instead of the flat 20% rule when his room trades.
FUT_SYMS = {"NQ", "MNQ", "ES", "MES", "YM", "MYM", "RTY", "M2K",
            "CL", "MCL", "GC", "MGC", "SI", "SIL", "NG"}


def _fut_root(raw):
    """A futures token the rooms wrote with a trailing digit -> its ROOT.

    Same shape of bug as positions._fut_mult_for: the table is keyed by ROOT
    ("MNQ") while a room writes the contract with a number stuck on the end.
    Horizon posts "BTO MNQ1 29115"; "MNQ1" is in no set, so the entry branch
    below fell through to the no-price branch and the call died with NO log
    line at all — a silent drop, twice (8/18 22:42, 8/25 21:38).

    EXACT MATCH FIRST, so nothing that already works can change. Only if the
    token is unknown do we strip trailing digits and retry. Returns the root
    or None; the caller's price-band check still has the final say."""
    s = str(raw or "").upper()
    if s in FUT_SYMS:
        return s
    t = s
    while t and t[-1].isdigit():
        t = t[:-1]
    return t if (t and t != s and t in FUT_SYMS) else None
RE_FUT_ENTRY = re.compile(
    # The @ is optional now — his Day Trades channel writes "Short nq
    # 28240.50" with nothing between the symbol and the price. The number
    # keeps it honest: "long NQ into the close" has no price, so no entry.
    # [\$/]? on the symbol because the rooms write /NQ as often as $NQ or
    # bare NQ. \.\d{1,3} because NG quotes "3.412" and CL "66.405" — two
    # decimals used to truncate those to 3 and 66, and a wrong entry price
    # then computes a wrong stop. The trailing lookahead refuses a count
    # posing as a price: "short NQ 2 contracts here" is a size, "long ES 4
    # lots" is a size, "I've been long NQ 3 times" is a war story. A number
    # followed by a unit word is never the price.
    r"\b(short|long)\s+[\$/]?([A-Za-z0-9]{1,4})\s*(?:@|at\b)?\s*"
    r"\$?(\d[\d,]*(?:\.\d{1,3})?)\b"
    r"(?!\s*(?:times?|contracts?|cons?|lots?|handles?|cents?|ticks?|"
    r"points?|pts?|mins?|minutes?)\b)",
    re.IGNORECASE)
RE_THEIR_STOP = re.compile(
    # "SL 28302" is the same stop as "Stop 28302" — Whop shorthand. "St0p"
    # with a zero is a real typo from the High Risk channel. "SL at be"
    # (break-even) carries no number and stays unmatched.
    r"\b(?:st[o0]p(?:\s*loss)?|sl)\s*[:=@]?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)\b",
    re.IGNORECASE)
RE_THEIR_TARGET = re.compile(
    # "Target 1: 7600" numbers its targets — the first target is his level,
    # the "1" is just a label. The label only counts when a colon follows,
    # so "Target 28250" can't lose its leading digit.
    r"\b(?:target|tp|pt)\s*(?:\d\s*[:=]\s*)?\$?(\d[\d,]*(?:\.\d{1,2})?)\b",
    re.IGNORECASE)
# "Target hit $1700 a contract - 2nd trim" / "$1,100 a contract on NQ short"
# / "$800 a con". His futures trims speak in dollars per contract, and on a
# dry run that number is the only honest exit price there is.
RE_USD_CONTRACT = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:a|per|/)\s*con(?:tract)?s?\b",
    re.IGNORECASE)
# His Futures-channel entry variants: "Long NQ - AVG 24015", "Long NQ -
# 23865 AVG", "Entered NQ short 23477 average", "Short RTY AVG - 2398.4".
# Direction + symbol either way round, price arriving as an average.
RE_FUT_DIR_SYM = re.compile(
    # The wandering shape first — "Re-entered long here @ 23480 on NQ" — or
    # the alternation would stop at "long here" and never reach the symbol.
    r"\b(long|short)\b[^\n.]{0,24}?\bon\s+\$?([A-Za-z0-9]{1,4})\b"
    r"|\b(long|short)\s+\$?([A-Za-z0-9]{1,4})\b"
    r"|\b([A-Za-z0-9]{1,4})\s+(long|short)\b",
    re.IGNORECASE)
RE_FUT_AVG = re.compile(
    r"\b(?:avg|average)\s*[-:]?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)\b"
    r"|\b(\d[\d,]*(?:\.\d{1,2})?)\s+(?:avg|average)\b", re.IGNORECASE)
# The room says "gold"/"silver" as often as GC/SI.
FUT_NICKNAMES = {"GOLD": "GC", "SILVER": "SI", "PLATINUM": "PL"}
# A number outside these bands isn't a price, whatever the sentence says.
# Wide on purpose — they exist to catch counts ("2 contracts"), zeros and
# fat fingers, not to judge the market. An unlisted symbol gets an almost
# no-opinion band that still refuses a zero. Sell-side matters most: a
# "short NQ @ 2" limit is BELOW the market, so it fills instantly — a
# phantom price becomes a real position on the wrong side.
FUT_PRICE_BAND = {
    "NQ": (5000, 60000), "MNQ": (5000, 60000),
    "ES": (1500, 20000), "MES": (1500, 20000),
    "YM": (10000, 100000), "MYM": (10000, 100000),
    "RTY": (800, 10000), "M2K": (800, 10000),
    "CL": (10, 300), "MCL": (10, 300),
    "GC": (1000, 20000), "MGC": (1000, 20000),
    "SI": (10, 300), "SIL": (10, 300),
    "NG": (0.5, 30),
}


def _fut_price_ok(sym, px):
    lo, hi = FUT_PRICE_BAND.get(sym, (0.1, 1e6))
    return lo <= px <= hi


# "Felony posted Jul 30, 2026 Entered NVDA 205C 7/31 @ 2.05" — read on
# Aug 3. A date stamp INSIDE the body means the scraper picked up an old
# post rendered on screen (Whop draws them that way), not a live message.
# Live messages carry their date in the export header, never in the text.
# This is what let a July 30 call buy a July 31 expiry three days dead.
RE_STALE_STAMP = re.compile(
    r"\bposted\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"[a-z]*\.?\s+\d{1,2}\b"
    r"|·\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"[a-z]*\.?\s+\d{1,2}\b"
    r"|·\s*\d+\s*[dhw]\b",
    re.IGNORECASE)
# "stopped out of my personal trade, room trade still on" — HIS other
# account, not the call the room followed. Exit wording that says so is
# about a trade you were never in.
RE_NOT_ROOM_TRADE = re.compile(
    r"\bpersonal\b|\broom\s+trade\s+still\b|\bnot\s+the\s+room\b",
    re.IGNORECASE)
# "Stopped" alone at the start of a message, "Eh stopped", "Stop got hit",
# "BE stop hit", "Trailing stop hit on RTY" — their stop fired, said seven
# different ways. Start-anchored so "if we get stopped" inside an entry's
# rationale never reads as an exit. An everyday preposition after the word
# kills the start-anchored read: "Stopped by the store, back in 20" and
# "Stopping for lunch" are errands, and each of them closed a live position
# in the Aug 3 drill. Kept loose past that on purpose — the corpus has
# "Stopped\nCouldn't update was busy earlier" as a real exit, so requiring
# a trading word after "Stopped" breaks the room's actual usage.
RE_STOP_HIT = re.compile(
    r"^(?:eh\s+|welp\s+)?stopp(?:ed|ing)\b"
    r"(?!\s+(?:by|for|to|into|off|at\s+the)\b)"
    r"|\b(?:be\s+|trailing\s+)?stop\s+(?:got\s+|was\s+)?hit\b",
    re.IGNORECASE)
# "Taking paper cut" / "Locking in a 8 point loss" — an early exit by hand.
# Verb-led on purpose: "those paper cuts we took yesterday" is a war story,
# "Taking papercut" is a sale.
RE_PAPERCUT = re.compile(
    r"\btak(?:e|ing)\s+(?:a\s+|this\s+|the\s+)?paper\s*cut"
    r"|\btak(?:e|ing)\s+be\b"          # "Taking BE" — out at breakeven
    r"|\btaking\s+the\s+loss\b"
    r"|\block(?:ing)?\s+in\s+an?\s+\d+\s+point\s+loss\b"
    # "Took an L" / "take the L" / "big L on this" — slang for a loss, i.e.
    # they closed it red. Verb- or size-anchored so "cool"/"LOL"/stray "l"
    # never fire. Bullwinkle's "we took an L" on COIN went unread before this.
    r"|\b(?:took|tak(?:e|ing))\s+(?:a\s+|an\s+|the\s+|this\s+|that\s+)?l\b"
    r"|\bthat'?s\s+(?:a\s+|an\s+|the\s+)?l\b"
    r"|\b(?:big|small|tough|rough|another)\s+l\b"
    r"|\bl\s+on\s+(?:this|that|the)\b", re.IGNORECASE)


def _num(s):
    return float(str(s).replace(",", ""))


# ---- Aristotle's grammar, from his real corpus --------------------------------
# PREP names the contract, then "In @here" is the trigger — HIS fill already
# happened, the price arrives as its own message afterwards. So a bare "In"
# fires on the last PREP, at the market. "Out" / "Fully out" close the same
# way: no ticker, resolved by whose position it is. "QQQ 668 0 day puts
# @here lightly" is a whole entry in five words.
RE_BARE_IN = re.compile(
    r"^(?:i'?m\s+|i\s+|we\s+)?in\b"
    r"(?:\s+(?:here|everyone|starters?|lightly|light|small|super\s+light"
    r"|very\s+light|these|again|now))*"
    r"\s*(?:@?\s*\$?(\d{1,3}(?:\.\d{1,2})?))?\s*[.!]?$", re.IGNORECASE)
RE_BARE_OUT = re.compile(
    r"^(?:i'?m\s+)?(?:fully\s+|all\s+)?out\b(?:\s+(?:of\s+)?half)?[\s!.]{0,4}$",
    re.IGNORECASE)
RE_HALF = re.compile(r"\b(?:out\s+of|sold)\s+half\b", re.IGNORECASE)
# "Stopped out of half my position" / "Stopping out of 2nd entry" — their
# stop fired. Half or a numbered entry = partial; otherwise the trade's done.
RE_STOPPED_OUT = re.compile(
    # "Stopped out" is the main room. The Whop Day Trades room drops the
    # "out": "Stopped on nq", "Stopped at be", "Stopped be on nq",
    # "Stopped 20 point loss". All of them mean their stop fired.
    r"\bstopp?(?:ed|ing)\s+(?:out\b|on\s+\w|at\s+be\b|be\b|\d+\s+point)",
    re.IGNORECASE)
RE_PARTIAL = re.compile(
    r"\bhalf\b|\b(?:2nd|second|1st|first)\s+entry\b|\bpart\b|\bsome\b",
    re.IGNORECASE)
# Midas's "In @here my add level will be 744.30" / "In 0days at 1.97" — an
# IN at the start, not leading into prose, with a trading cue somewhere in
# the line. The blocklist is what keeps "In no rush to lose money today"
# from buying anything.
RE_LOOSE_IN = re.compile(
    r"^(?:i'?m\s+|i\s+|we\s+)?in\b(?!\s+(?:no|not|the|a|an|this|that|it"
    r"|order|fact|case|between|rush|and|but|on|to|for|honeydrip)\b)",
    re.IGNORECASE)
RE_IN_CUE = re.compile(
    r"\d+\.\d{1,2}|\bstarters?\b|\bcons?\b|\b[01]\s*d(?:ays?|tes?)\b"
    r"|\blightly\b|\bfill\b|\badd\s+level\b", re.IGNORECASE)
RE_IN_PRICE = re.compile(r"(?:\bat|@)\s*\$?(\d{1,2}\.\d{1,2})\b", re.IGNORECASE)
# Midas confirms his entry three ways after a Loaded: a bare "Filled
# @here", a bare price with the word fill/avg ("1.97 fill", "Avg 1.61"),
# or "Taking more cons". All of them mean HE IS IN — fire on his last PREP.
RE_FILL_CONF = re.compile(
    # Midas's two-step entry (missed 8/11): "Loaded $PLTR 175p 8/14" then
    # "4.10 entry @here" — the entry line carries only the price, "entry" as
    # a noun, and a trailing @here. Also "Full sized 3.80 avg" — his add to
    # full size, same shape with a prefix. Both pin to the loaded contract.
    r"^(?:filled)\b(?:\s+(?:light\s+size|lightly|starters?))*[\s.!]*$"
    r"|^(?:full\s+siz(?:e|ed)\s+)?\$?(\d{1,2}\.\d{1,2})\s+(?:is\s+my\s+)?(?:final\s+)?"
    r"(?:fill|avg|entry)\b[\s.!]*(?:@\w+[\s.!]*)?$"
    r"|^avg\s+\$?(\d{1,2}\.\d{1,2})\b[\s.!]*$"
    r"|^tak(?:e|ing)\s+(?:first|more|some)?\s*(?:size|cons?)\b",
    re.IGNORECASE)
# "All positions closed" / "Out of all trades" — everything this trader
# holds goes, whatever the tickers are.
RE_CLOSE_ALL = re.compile(
    r"\ball\s+positions?\s+(?:are\s+)?closed\b"
    r"|\bclos(?:ed|ing)\s+all\s+positions?\b"
    r"|\bout\s+of\s+all\s+trades\b|\bsold\s+everything\b", re.IGNORECASE)
RE_FILLER = re.compile(
    r"\b(?:lightly|light|super|very|small|starters?|lottos?|lotto|these|some"
    r"|size|zero|for|high|risk|deg[ea]n|accts?|account|starter)\b"
    r"|[()!,]|\.(?!\d)",
    re.IGNORECASE)
RE_DAYS_ANY = re.compile(r"\b(\d{1,2})\s*days?\b", re.IGNORECASE)
RE_CONTRACT_DTE = re.compile(
    r"(?<![A-Za-z])\$?(?P<symbol>[A-Za-z]{1,5})\s+"
    r"\$?(?P<strike>\d{1,5}(?:\.\d{1,2})?)\s+"
    r"(?P<days>\d{1,2})\s*days?\s+(?P<kind>calls?|puts?)\b", re.IGNORECASE)
RE_PCT_COUNT = re.compile(r"-?\d{1,3}(?:\.\d+)?\s*%")


# Lines that must never fire no matter what else is in them.
# Boilerplate footers rooms staple to a call — cut from the first marker to the
# end so their words (idea, p/l, disclaimer) can't veto the order in front.
RE_FOOTER = re.compile(
    r"\s*(?:how i trade\b|trade\s+idea'?s?\s+disclaimer|\bp/?l\s*[:=]|"
    r"\bdisclaimer\b|for\s+information(?:al)?\s+purposes\s+only|"
    r"not\s+financial\s+advice|educational\s+only|©).*$",
    re.IGNORECASE | re.DOTALL)

VETO_WORDS = ("do not", "don't", "dont ", "watching", "watch", "eyeing",
              # "Probably only got 10% out of that" is a P&L musing that read
              # as a 10% TRIM. "hold runners for breakeven" is coaching, not a
              # sale — both are advice/recap, never firm orders.
              "probably", "hold runners", "take trims",
              # "we have been SPOT on with direction ... getting stopped out"
              # read SPOT as the ticker and fired a CLOSE. "spot on" is the
              # idiom, not Spotify. "on watch" is a Nitro/are-alerts watchlist
              # note ("TSLA $400c on watch"), never an entry.
              "spot on", "on watch",
              "looking at", "thinking", "maybe", "might", "if it", "if you",
              "waiting", "wait for", "heads up", "scanner", "idea", "consider",
              "recap", "example", "congrats", "missed", "sorry", "pissed",
              # AlertBot posts after-the-fact summaries like "$MSFT
              # entry / exit for a 20% gain" — a recap, not a live call.
              "entry / exit", "entry/exit",
              "sets the tone", "session", "overall", "read was", "look at that",
              "still holding", "use $", "as risk", "anyone", "lmk", "great job",
              # The victory-lap paragraph. It's full of percentages and prices
              # and it is not a call — none of these words ever appear in one.
              "yesterday", "nice day", "conviction", "wish i",
              # "71.7% chance of no cut" on FOMC day — a percentage that is
              # about the Fed, not about a trade. Nearly parsed as a trim.
              "chance of", "probability", "odds of", "supposed to",
              # Midas planning out loud, day one live: "Not adding to this
              # position" would have BOUGHT five more if we'd been holding
              # his trade — the ADD pattern saw "adding" and never looked
              # left for the "Not". And "Some trim targets are 737.70 and
              # lower" is a map of where he MIGHT sell, not a sale.
              "not adding", "won't add", "wont add", "no adds", "trim target",
              # "I'm going to take 742c starters and add full size at 741.60"
              # — Midas narrating a PLAN. Day two the reader bought the verb:
              # OPEN TAKE 742C. Announced intent is not an entry; his entry
              # is the fill that follows.
              "going to", "gonna",
              # "Short NQ @ 28660 — actually cancel that, no fill" fired the
              # order and ignored the retraction. The retraction wins. Same
              # for "(paper account only, not my real one)", a P&L line
              # ("My PnL: long NQ 28660 -> 28720"), and "Last week's long ES
              # 7400" — a war story with a parseable entry inside it, same
              # family as "yesterday" above.
              "cancel", "no fill", "never filled", "paper account",
              "last week", "pnl", "p&l", "p/l",
              # Aug 3 options drill. "Was in NVDA 205c earlier" is a war
              # story and "Almost went in NVDA 205c but passed" is a pass.
              # NOT "earlier" or "if we" alone — the suite proved both live
              # inside real calls ("Stopped ... was busy earlier",
              # "Short NQ @ 29792 ... If we get stopped"). "tomorrow if"
              # is the future-intent shape: "buying NVDA tomorrow if we
              # gap up" is a plan, not an order.
              "was in", "almost", "tomorrow if",
              # 8/24: bullwinkle posted "SNDK $1500 C 41.00 I AM NOT GETTING
              # IN THIS TOO EXPINSIVE FOR ME" — a pass, not a call. The
              # reader saw the strike and tried to BUY it; only low cash
              # refused it. A trader saying no is a no. Mirrors parser.js.
              "not getting in", "not taking", "not entering", "not buying",
              "too expensive", "too expinsive", "sitting this",
              "i'll pass", "ill pass",
              # 8/25: "AAPL OUT THE GATES" — a rip cheer, not an exit.
              "out the gate")

NOT_TICKERS = {"THE", "A", "AN", "IT", "ALL", "IN", "OUT", "AT", "ON", "MY",
               # "I got in SOME 400 C" — "some" is a word, not a ticker (8/10).
               # "SL HIT" — the stop got hit; HIT is a verb, not a ticker (8/11).
               "SOME", "HIT",
               "IS", "AND", "OF", "TO", "BE", "OK", "DTE", "AM", "PM", "ET",
               # A5 - timezone tokens + option-strategy shorthand that read as
               # tickers on tickerless exits ("... 10:17 AM EDT" grabbed EDT).
               "EDT", "EST", "PST", "PDT", "CT", "MT", "UTC", "IV", "CSP",
               "CC", "CCS", "PCS", "STO", "BTO", "STC",
               "DO", "NOT", "BUY", "SELL", "IE", "ADMIN", "HERE", "EOD", "CPI",
               "FOMC", "PT", "SL", "TP", "AVG", "GO", "UP", "WE", "US", "NO",
               # The verbs themselves. "sold 205 calls on nvda" read SOLD as the
               # ticker, because a word directly in front of a strike looks
               # exactly like a symbol. None of these is ever a ticker he trades.
               "SOLD", "TRIM", "HOLD", "GOT", "ADD", "FULL", "TOOK", "LOAD",
               "FILL", "CALL", "CALLS", "PUT", "PUTS", "LONG", "SHORT", "SIZE",
               "RISK", "NEW", "JUST", "NOW", "OVER", "UNDER", "NEAR", "ABOVE",
               # Day two live: "going to take 742c" bought TAKE, and "Keep 305
               # puts loaded" once read KEEP as the ticker. Verbs in front of
               # a strike.
               "TAKE", "KEEP",
               # Trader shorthand that looks exactly like a ticker once
               # uppercase counts.
               "OPEX", "ORB", "HOD", "LOD", "EMA", "VWAP", "ATH", "RSI",
               "FIB", "PREP", "LOL", "SMH", "LFG", "PDT",
               # "WIN!!" in a victory lap read as ticker WIN and turned a
               # celebration into a trim on a stock nobody holds. WIN, GAIN
               # and LOSS are real tickers somewhere, but in these rooms
               # they are always the words.
               "WIN", "GAIN", "LOSS",
               # Whop role badges and prose. "Trademorewiser (MOD) posted ...
               # Full sold NQ" read the (MOD) badge as ticker MOD and MISSED the
               # NQ exit. MOD/mod is never a ticker in these rooms; nor are these
               # bits of the Whop repost boilerplate.
               "MOD", "VIP", "POSTED", "FULL", "FINAL", "CON", "CONS", "PDH",
               "PDL", "BE", "FTGH", "LH", "HH",
               # The Discord bot badge. "stockguy007 APP — 9/26 ... Stopping
               # out here" and "Nitro Trades APP — ... Closed SPY" read the
               # APP badge as ticker APP and fired CLOSE APP. Never a ticker.
               "APP", "COMMENT", "ENTRY", "PRICE", "SWING",
               # Bullwinkle's exit/management lingo fired phantom CLOSEs on the
               # word directly before/after OUT: "OUT ALL BUT 1" -> CLOSE BUT,
               # "OUT HALF" -> CLOSE HALF, "Bullwinkle EDU — ... OUT" -> CLOSE
               # EDU, "WILL STOP OUT" -> CLOSE WILL, "TRIMMED FORM THE ADD" ->
               # TRIM FORM. None of these are the ticker; the real position is
               # resolved from what's held (needs_position) instead.
               "BUT", "HALF", "MORE", "EDU", "TOO", "LAST", "WILL", "FORM",
               "LIGHT", "STARTER", "PENDING", "PICKED", "MARKETING", "LOTTO",
               "IDEA", "WATCH", "OPTION", "OPTIONS", "TRADE", "ALERT", "SETUP",
               "AFTER", "STOP", "RIDE", "TA", "WIL", "SIDELINES", "STRONG",
               # "OUT FOLKS" (Bullwinkle sign-off) -> phantom CLOSE FOLKS. Not a
               # ticker; the real position is resolved from what's held.
               "SMALL", "NEXT", "THIS", "THAT", "LETTING", "FOLKS", "GUYS",
               "EVERYONE", "EVERYBODY", "TODAY", "HERE", "NOW", "DONE", "OFF"}


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
    # "exited SPY, and back in @ 2.84" is one line but two trades: they closed
    # and immediately re-bought THE SAME contract at a new price. So this
    # closes you and puts you straight back in, on the contract you were
    # already holding — the line never names it, and it doesn't need to.
    reenter: bool = False
    reenter_limit: Optional[float] = None
    # A bare "Trimming @here" or a lone "20%" names no ticker — the room knows
    # which one, you don't. This flag says "work it out from what I'm holding",
    # and guards.resolve_symbol does exactly that. Nothing fires until it does.
    needs_position: bool = False
    # "Filled 3.95 starters" is an order with the contract missing, because the
    # contract was in the LOADING message before it. This flag says "go and find
    # the loading call that goes with this"; guards.resolve_loaded does it, and
    # nothing fires until it succeeds.
    needs_loaded: bool = False
    # A ticker named in an otherwise-bare "in" ("In meta 6.10 avg"). When set,
    # resolve_loaded REFUSES to pair it with a loading of a different ticker —
    # on Aug 4 "In meta..." bought TSLA off a stale load. Never buy the ticker
    # they didn't say.
    named_symbol: Optional[str] = None
    # "added to SPY, new avg 2.8" — a second contract on a trade you're already
    # in. Nothing about that can be decided from the line alone: it depends on
    # whether averaging is switched on, whether you're actually in it, and how
    # many times you've already added. guards.resolve_add answers all three.
    needs_add: bool = False
    # Futures and his-levels support. kind is "future" on a futures call and
    # "" otherwise; direction is LONG/SHORT; their_stop and their_target are
    # the levels HE posted; usd is "$1,100 a contract" off a trim — the only
    # honest futures exit price a dry run has.
    kind: str = ""
    direction: Optional[str] = None
    their_stop: Optional[float] = None
    their_target: Optional[float] = None
    usd: Optional[float] = None
    # "All positions closed" — close everything this trader holds.
    all: bool = False
    warn: str = ""
    raw: str = ""
    clean: str = ""
    matched: str = ""
    # The call said it's a SWING — held overnight, not a day trade. Display
    # only (his ask, 8/17: "(Swing) before the trade in a diff color"); it
    # changes no order, no bracket, no exit.
    swing: bool = False

    def key(self):
        # reenter belongs in the identity. "exited SPY, and back in" and a
        # later plain "all out of SPY" are both CLOSE SPY on the same contract,
        # but they're two different calls minutes apart — without this the real
        # exit is thrown away as a duplicate of the re-entry and you ride the
        # position into the close.
        # The caller is on the end now, too. Brett and Unraveler posting the
        # same call minutes apart are two trades, not a duplicate — without
        # the name, the second man's "all out of SPY" would die inside the
        # dedupe window of the first's. Symbol stays at index 1 because
        # guards.record's purge reads k[1].
        return (self.action, self.symbol, self.side, self.strike, self.expiry,
                self.pct, bool(self.reenter),
                str(getattr(self, "caller", "") or "").lower())

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
    t = RE_STAG.sub(" ", (raw or "").strip())      # Discord "Server Tag" junk (9/2)
    t = RE_HDR.sub("", t)
    # ANSI color codes ride along in Namrood's alerts ("[1;37;44mMETA") and
    # the trailing "m" glued onto the ticker — META became MMETA, SPY MSPY,
    # SPCX MSPCX (seen live 8/17-18). Strip them, with or without the ESC
    # byte the relay may have eaten. Mirrors parser.js.
    t = re.sub(r"\x1b?\[[0-9;]{1,16}m", " ", t)
    t = RE_PING.sub(" ", t)
    t = RE_CALLER.sub(" ", t)
    t = RE_EMOJI.sub(" ", t)
    # Numbered paste lines ("14. Loading 205 calls..."). The space after the dot
    # is required: without it "206.5 need to clear now" gets shortened to "5 need
    # to clear now", and a line like "747.5 calls on SPY" would turn into a
    # contract at a strike of 5.
    t = re.sub(r"^\s*\d{1,3}\.\s+", "", t)
    # A1 - normalize smart quotes so a quoted premium ("2.21") parses.
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("‘", "'").replace("’", "'")
    # LABELLED TEMPLATE (9/2, Platinum Blue Collar) — mirrors parser.js:
    # "LONG SETUP Ticker: SPY Contract: 764 C Entry Zone: .50 Risk: 20% ..."
    # becomes "BTO SPY 764 C @ 0.50".
    if re.search(r"\bticker\s*:", t, re.I) and re.search(r"\bcontract\s*:", t, re.I):
        t = re.sub(r"\b(?:long|short)\s+setup\b", "BTO", t, flags=re.I)
        t = re.sub(r"\bticker\s*:\s*", " ", t, flags=re.I)
        t = re.sub(r"\bcontract\s*:\s*", " ", t, flags=re.I)
        t = re.sub(r"\bentry(?:\s*zone)?\s*:\s*", " @ ", t, flags=re.I)
        t = re.sub(r"\b(?:risk|tp\d?|target\d?|stop)\s*:\s*\$?\d+(?:\.\d+)?\s*%?", " ", t, flags=re.I)
        t = re.sub(r"\b(?:risk|tp\d?)\s*:", " ", t, flags=re.I)
        if not re.search(r"\b(bto|buy|in|entry|long)\b", t, re.I):
            t = "BTO " + t
    # ".50" is a premium of 0.50 (9/2) — a leading-dot price never parsed.
    t = re.sub(r"(^|[\s@$])\.(\d{1,2})\b", r"\g<1>0.\2", t)
    # COLLECTIVE CORPUS (9/2): bot footers carry veto words — cut at the
    # first footer marker. Mirrors parser.js cleanText.
    for pat in (r"\s*(?:IG:\s*\S+\s*\|?\s*)?None of this is financial advice.*$",
                r"\s*Do not take this as financial advice.*$",
                r"\s*@\S*\s*-\s*For Educational Purposes Only.*$",
                r"\s*For (?:Educational|Informational) Purposes Only.*$",
                r"\s*©\s*20\d\d.*$", r"\s*How I Trade\b.*$",
                r"\s*@Namrood\s*-\s*Live.*$", r"\s*Solely for informational purpose.*$"):
        t = re.sub(pat, " ", t, flags=re.I | re.S)
    radar = re.match(r"^\s*(?:@\S+\s+)?([A-Z]{1,4})\s+(LONG|SHORT)\s*\(\d+m\)\s*@\s*(\d[\d,.]*)\s*\|\s*TP:\s*(\d[\d,.]*)\s*SL:\s*(\d[\d,.]*)", t, re.I)
    if radar:
        t = "%s %s @ %s Stop %s Target %s" % (radar.group(2).upper(), radar.group(1).upper(),
                                              radar.group(3), radar.group(5), radar.group(4))
    fhead = re.match(r"^\s*(?:@\S+\s+)?(long|short)\s+\$?/?([A-Za-z0-9]{1,4})\s*(?:@|at)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?)\s+(?:stop|sl)\s*(?:@|at|:)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?)(?:\s+(?:target|tp)\s*(?:\d\s*:)?\s*(?:@|at|:)?\s*\$?(\d[\d,]*(?:\.\d{1,3})?))?", t, re.I)
    if fhead and fhead.group(2).upper() in FUT_SYMS and \
            re.search(r"[a-z]{4,}\s+[a-z]{3,}\s+[a-z]{3,}", t[fhead.end():], re.I):
        t = "%s %s @ %s Stop %s%s" % (fhead.group(1), fhead.group(2).upper(), fhead.group(3),
                                      fhead.group(4), (" Target " + fhead.group(5)) if fhead.group(5) else "")
    fut = r"(NQ|MNQ|ES|MES|YM|MYM|RTY|M2K|GC|MGC|CL|MCL|SI|NG)"
    t = re.sub(r"\b" + fut + r"\s+(\d{3,6}(?:\.\d+)?)\s+(long|short)\b", r"\3 \1 @ \2", t, flags=re.I)
    t = re.sub(r"\b" + fut + r"\s+(?:quick\s+)?(long|short)\s+(?:here\s+)?@?\s*(\d{3,6}(?:\.\d+)?)\b", r"\2 \1 @ \3", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _loose_premium(text, strike):
    """A1 - scan the whole message for the premium when it isn't "@ 1.23":
    a bare "3.20", a quoted "2.21" or a range "13.25-13.40" (low end). Skips
    the strike, %-figures and anything >= 100."""
    mr = re.search(r"(\d{1,3}(?:\.\d{1,2})?)\s*[-–]\s*"
                   r"(\d{1,3}(?:\.\d{1,2})?)(?!\s*%)", text)
    if mr:
        lo = float(mr.group(1))
        if 0 < lo < 100 and lo != strike:
            return lo
    for m in re.finditer(r"\b(\d{1,3}\.\d{1,2})\b(?!\s*%)", text):
        v = float(m.group(1))
        if v == strike or v <= 0 or v >= 100:
            continue
        return v
    return None


# A1 - quantity-first entries ("2 cons QQQ 721 C 8/7 2.21") carry no verb; the
# leading count is the entry cue. Stripped as size, it never blocks the read.
RE_QTY_LEAD = re.compile(r"^\s*\d{1,3}\s*(?:cons?|contracts?|lots?)\b",
                         re.IGNORECASE)


RE_TMRW_EXP = re.compile(r"\btomorrow\s+exp\w*", re.IGNORECASE)
RE_TODAY_EXP = re.compile(r"\btoday\s+exp\w*|\bexpiring\s+today\b",
                          re.IGNORECASE)


def _expiry_anywhere(text):
    """"to July 29th" -> "7/29". Only used when the contract itself didn't
    carry an expiry, so it can't override anything they actually wrote."""
    # "tomorrow exp" is Midas's and Aristotle's way of writing 1DTE, and
    # "today exp" is 0DTE said out loud.
    if RE_TMRW_EXP.search(text):
        return "1DTE"
    if RE_TODAY_EXP.search(text):
        return "0DTE"
    m = RE_MONTH_DAY.search(text)
    if m:
        return "%d/%d" % (MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
    m = RE_DTE_ANY.search(text)
    if m:
        return m.group(1).upper()
    # Aristotle writes "0 day" where the main room writes 0DTE. Same thing.
    m = RE_DAYS_ANY.search(text)
    if m:
        return "%dDTE" % int(m.group(1))
    m = RE_DATE_ANY.search(text)
    if m:
        return "%d/%d%s" % (int(m.group(1)), int(m.group(2)),
                            "/" + m.group(3) if m.group(3) else "")
    return None


# TradeLikeGates ($STS / RWGates) posts contracts in ThinkorSwim's dotted
# form: ".HOOD260702C118" = HOOD, 2026-07-02, Call, strike 118. The leading dot
# + letters + 6-digit YYMMDD + C/P + strike is unambiguous, so it wins first.
RE_CONTRACT_OSI = re.compile(
    r"\.([A-Za-z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{1,6}(?:\.\d{1,2})?)",
    re.IGNORECASE)


def _contract(text):
    m = RE_CONTRACT_OSI.search(text)
    if m and m.group(1).upper() not in NOT_TICKERS:
        return {"symbol": m.group(1).upper(),
                "strike": float(m.group(6)),
                "side": "CALLS" if m.group(5).lower() == "c" else "PUTS",
                "expiry": "%d/%d/%s" % (int(m.group(3)), int(m.group(4)), m.group(2))}
    for m in RE_CONTRACT.finditer(text):
        sym = m.group("symbol").upper()
        if sym in NOT_TICKERS:
            continue
        k = m.group("kind").lower()
        expiry = (m.group("expiry") or "").upper() or None
        if expiry and expiry[0].isalpha() and not expiry.endswith("DTE"):
            md = RE_MONTH_DAY.search(expiry)
            if md:
                expiry = "%d/%d" % (MONTHS[md.group(1).lower()],
                                    int(md.group(2)))
        if not expiry:
            expiry = _expiry_anywhere(text[m.end():])
        return {"symbol": sym, "strike": float(m.group("strike")),
                "side": "CALLS" if k.startswith("c") else "PUTS",
                "expiry": expiry}

    # Written back to front. Tried second so a normally-written contract in the
    # same line always wins.
    for m in RE_CONTRACT_REV.finditer(text):
        sym = m.group("symbol").upper()
        if sym in NOT_TICKERS:
            continue
        mid = m.group("mid") or ""
        expiry = "WEEKLY" if RE_FRI_EXP.search(mid) else _expiry_anywhere(mid)
        return {"symbol": sym, "strike": float(m.group("strike")),
                "side": "CALLS" if m.group("kind").lower().startswith("c") else "PUTS",
                "expiry": expiry}

    # "QQQ 668 0 day puts" — the expiry sits BETWEEN strike and kind, which
    # neither shape above allows. Aristotle's habit.
    m = RE_CONTRACT_DTE.search(text)
    if m and m.group("symbol").upper() not in NOT_TICKERS:
        return {"symbol": m.group("symbol").upper(),
                "strike": float(m.group("strike")),
                "side": ("CALLS" if m.group("kind").lower().startswith("c")
                         else "PUTS"),
                "expiry": "%dDTE" % int(m.group("days"))}
    return None


def _bare_symbol(text, allowed):
    """For 'trimming AMD' and 'all out of SPY' there's no strike to anchor on,
    so only tickers you've explicitly allowed count. Without that rule 'all out
    of AAPL as well but made it up' starts looking like an order.

    Lowercase ("30% on spy") only counts when you have an allowed list. With no
    list there is nothing to check a lowercase word against, and every third
    word in a sentence would start looking like a ticker."""
    for m in RE_BARE.finditer(text):
        raw = m.group(1)
        s = raw.upper()
        if s in NOT_TICKERS:
            continue
        # A futures symbol is recognisable on its own, in ANY case — the
        # Whop room types "Stopped on nq" and "Trailed out nq" in lowercase
        # all day. These aren't English words, so lowercase is safe here in
        # a way it isn't for stock tickers.
        if s in FUT_SYMS:
            return s
        if s in FUT_NICKNAMES:
            return FUT_NICKNAMES[s]
        # Written in CAPITALS = a ticker, whoever's list it is or isn't on —
        # "Fully out of NBIS" has to resolve without NBIS being pre-listed.
        # The vocabulary list only unlocks lowercase ("40% in spy now").
        if raw == s and len(s) >= 2:
            return s
        if allowed and s in allowed:
            return s
        continue
    return None


# Cash-settled index options can't be traded on Webull, but their ETF proxy is
# the same directional bet at 1/10 the strike (SPX 7770 ≈ SPY 777). Rather than
# refuse Sir Goldman's SPX calls, retarget them to the tradeable ETF. The index
# premium doesn't carry over, so the limit is cleared and the ETF's own market
# prices the entry.
INDEX_ETF = {"SPX": ("SPY", 10.0), "SPXW": ("SPY", 10.0), "XSP": ("SPY", 1.0),
             "RUT": ("IWM", 10.0), "RUTW": ("IWM", 10.0)}

# Whether a fresh SPX/XSP/RUT-style entry is followed at all. True (default):
# retarget to the tradeable ETF proxy above. False: refuse the entry outright,
# nothing sent. Turned off 8/15 on his word - "for now", so flip this back to
# True to resume the ETF substitution. Exits/trims always still work (see
# below) so a position opened before this was flipped off can still be closed.
SPX_ENTRIES_ENABLED = False


def _index_to_etf(s):
    if s is None:
        return
    sym = str(getattr(s, "symbol", "") or "").upper()
    m = INDEX_ETF.get(sym)
    if not m:
        return
    # Retarget an actual order - an option entry OR an exit (trim/close) on the
    # index, so the exit matches the SPY position the entry became. A bare index
    # mention in chatter (no action, no strike) is left alone.
    has_action = getattr(s, "action", None) in ("OPEN", "ADD", "TRIM", "CLOSE")
    is_opt = (getattr(s, "side", None) in ("CALLS", "PUTS")
              or getattr(s, "strike", None) is not None)
    if not (has_action or is_opt):
        return
    if not SPX_ENTRIES_ENABLED and getattr(s, "action", None) in ("OPEN", "ADD"):
        # Fresh entry on a cash-index option, and following it as the ETF is
        # switched off for now - refuse it loudly rather than silently drop
        # or silently substitute. Symbol/strike/etc. are left exactly as
        # parsed so the log shows what was actually called.
        s.fire = False
        s.why = ("%s is a cash-index option - following it as an ETF is "
                 "turned off for now, so nothing was sent" % sym)
        return
    etf, ratio = m
    if getattr(s, "strike", None) is not None:
        try:
            # round-half-UP to match JS Math.round exactly (strikes are positive),
            # so signals.py and parser.js never disagree on 756.5-style cases.
            s.strike = float(int(float(s.strike) / ratio + 0.5))   # 7770 -> 777
        except (TypeError, ValueError):
            return
    s.symbol = etf
    s.limit = None                # index premium ≠ ETF premium; bid the ETF market
    try:
        s.why = ("%s isn't tradeable on Webull — following it as %s %s%s instead"
                 % (sym, etf,
                    ("%g" % s.strike) if getattr(s, "strike", None) is not None else "",
                    ("C" if getattr(s, "side", "") == "CALLS" else
                     "P" if getattr(s, "side", "") == "PUTS" else "")))
    except Exception:                                       # noqa: BLE001
        pass


def _direction_sanity(s):
    """Refuse a futures entry whose LEVELS contradict the word.

    8/12, Stormzy: "TRADE ENTRY - MNQ Shorts ... Entry: 29868.25 Sl: 29848.25
    TP 1 : 29889.25". The stop is BELOW the entry and the target is ABOVE it —
    that is the shape of a LONG. He'd typed "Shorts" by mistake and corrected
    it several messages later, but the bot would already have SOLD the exact
    trade the room was buying.

    A stop and a target are geometry, and geometry can be checked: a short is
    protected above and takes profit below, a long the other way round. When
    the words and the numbers disagree, ONE of them is a typo and there is no
    way to know which — so nothing is sent. Guessing from the levels would be
    just as likely to take the wrong side as trusting the word. It refuses out
    loud, which is a message he can act on in seconds."""
    if getattr(s, "action", None) != "OPEN" or not getattr(s, "fire", False):
        return
    if getattr(s, "kind", None) != "future":
        return
    d = str(getattr(s, "direction", "") or "").upper()
    if not d:
        return
    short = d.startswith("S")
    try:
        entry = float(getattr(s, "limit", None))
    except (TypeError, ValueError):
        return
    bad = []
    for label, lvl, want_above in (("stop", getattr(s, "their_stop", None), short),
                                   ("target", getattr(s, "their_target", None),
                                    not short)):
        if lvl is None:
            continue
        try:
            v = float(lvl)
        except (TypeError, ValueError):
            continue
        if abs(v - entry) < 1e-9:
            continue
        if (v > entry) != want_above:
            bad.append("%s %g is %s the %g entry" %
                       (label, v, "below" if v < entry else "above", entry))
    if bad:
        s.fire = False
        s.why = ("they wrote %s but the levels say the opposite (%s). One of "
                 "the two is a typo and I can't tell which, so nothing was "
                 "sent — check the room and fire it by hand if it's real."
                 % ("SHORT" if short else "LONG", "; ".join(bad)))


def parse(text, author="", channel="", cfg=None):
    """The reader, wrapped in the last set of no-matter-what checks. The
    inner function stays exactly the battle-tested paths; this wrapper only
    gets to turn a would-be OPEN into a loud refusal, never to create one.

    Aug 3 options drill, what each check paid for:
      - sell-guard: "SPX 7565 C SELL FUNDED ACCOUNT ONLY" was read as a BUY
        of the call HE is selling — direction inverted end to end.
      - bounds: "BTO @0.00", strike "0c", and "@105" on a $2 contract all
        went through untouched.
      - dot-tickers: "$BRK.B 480c" parsed as ticker B — a real company,
        the wrong one."""
    s = _parse_inner(text, author=author, channel=channel, cfg=cfg)
    _index_to_etf(s)
    _direction_sanity(s)
    if s.action != "OPEN" or s.kind == "future":
        return s
    low = (s.clean or "").lower()
    # HARD VETO (8/24, mirrors parser.js): a trader saying NO outranks every
    # entry pattern. Bullwinkle's "SNDK $1500 C ... I AM NOT GETTING IN THIS
    # TOO EXPINSIVE" parsed as a buy; only low cash refused it.
    for _hv in ("not getting in", "not taking", "not entering", "not buying",
                "too expensive", "too expinsive", "sitting this",
                "i'll pass", "ill pass"):
        if _hv in low:
            s.fire = False
            s.action = None
            s.why = ('the trader passed on it ("%s") — not a call' % _hv)
            return s
    is_option = s.side in ("CALLS", "PUTS") or s.strike is not None
    # A PROGRESS UPDATE wearing an entry's clothes (8/18): "KO 08/21 $89
    # Call @$0.62, up more than 90%!, my order filled little earlier for
    # +100%!, will look to close the remaining later" — the contract line
    # parses like a fresh call, but the rest of the sentence is a victory
    # lap about a trade ALREADY made. A real entry never brags about its
    # own gain in the same breath. Mirrors parser.js.
    if s.action == "OPEN" and re.search(
            r"\bup\s+(?:more\s+than\s+)?\+?\d{1,4}\s*%"
            r"|\bfilled\s+(?:a\s+)?(?:little\s+|bit\s+)?earlier"
            r"|\bwill\s+look\s+to\s+close"
            r"|\bclos(?:e|ed|ing)\s+the\s+remaining", low):
        s.fire = False
        s.action = None
        s.why = ("that's a progress update on an EARLIER call (it brags "
                 "about the gain / mentions closing the rest) — not a fresh "
                 "entry, so nothing was sent")
        return s
    # UNDERLYING hard stop on an options entry (his INTC alert, 8/18):
    # "stop loss under 97 hard stop" means INTC THE STOCK under $97 — not
    # the premium. The number rides in their_stop; the bridge's stock
    # watcher closes the option when the stock crosses it. Mirrors parser.js.
    if is_option and s.their_stop is None:
        _mu = re.search(r"\b(?:hard\s+)?(?:st[o0]p(?:\s*loss)?|sl)\s*:?\s+(?:is\s+)?"
                        r"(?:under|below|above|over)\s+\$?"
                        r"(\d[\d,]*(?:\.\d+)?)\b", low)
        if _mu:
            try:
                s.their_stop = float(_mu.group(1).replace(",", ""))
            except ValueError:
                pass
    if is_option and re.search(r"\b(sell|selling|sold|sto)\b", low) \
            and not re.search(r"\b(bto|buy|buying|bought)\b", low):
        s.fire = False
        s.action = None
        s.why = ("they're SELLING that option — this bot only ever buys, "
                 "so nothing was sent")
        return s
    if is_option and s.strike is not None and float(s.strike) <= 0:
        s.fire = False
        s.action = None
        s.why = "a strike of 0 isn't a contract — refused, not guessed"
        return s
    if is_option and s.limit is not None \
            and (float(s.limit) <= 0 or float(s.limit) >= 1000):
        s.fire = False
        s.action = None
        s.why = ("%g isn't a plausible option premium — refused, not "
                 "guessed" % float(s.limit))
        return s
    if re.search(r"\$[A-Za-z]{1,5}\.[A-Za-z]\b", s.raw or ""):
        s.fire = False
        s.action = None
        s.why = ("a dot-class ticker (BRK.B style) — the reader mangles "
                 "these into the wrong symbol, so nothing was sent")
        return s
    return s


def _parse_inner(text, author="", channel="", cfg=None):
    cfg = cfg or {}
    allowed = [s.upper() for s in cfg.get("allowed_symbols", [])]
    raw = (text or "").strip()
    sig = Signal(raw=raw)
    if not raw:
        sig.why = "empty message"
        return sig

    t = clean_text(raw)
    # Strip the boilerplate FOOTER some rooms staple to every call — a
    # disclaimer or a running P/L line. Market Bishop's "Trimming CRWD 220 C
    # 7/31 ... How I Trade The Market Bishop Trade Idea's Disclaimer" was
    # vetoed on the word "idea" in that footer, and Namrood's trims died on the
    # "P/L:" in theirs. The order is at the FRONT; cut the boilerplate off the
    # end so it can't veto a real call. Only cuts from a known footer marker to
    # the end, so it never touches the order itself.
    t = RE_FOOTER.sub("", t).strip() or t
    # A2 - forwarded/relayed embed: "X (MOD) posted <Channel> - <Cat> Entered
    #      ...". Unwrap to the trading verb and re-parse; drop lotto/yolo noise.
    rel = re.search(r"\bposted\b\s+.+?\s+[-–]\s+.+?\s+((?:entered|in|bto|"
                    r"open(?:ed|ing)?|taking|buying|bought|trimming|trimmed|"
                    r"closed|sold|out)\b[\s\S]*)$", t, re.IGNORECASE)
    if rel:
        t = re.sub(r"\b(?:lotto|yolo)\b", " ", rel.group(1), flags=re.IGNORECASE)
        t = re.sub(r"\s+", " ", t).strip()
    sig.clean = t
    low = t.lower()
    # Swing wording anywhere on the line tags the signal (harmless on
    # non-entries — only entries ever store or show it). Mirrors parser.js.
    sig.swing = bool(re.search(r"\bswing(?:ing|s)?\b", low))

    # A date stamp inside the body means this is an old post the scraper
    # picked up rendered on screen, not a live message. This check comes
    # before every format reader on purpose: on Aug 3 a "Felony posted
    # Jul 30" scrape bought an expired NVDA contract because the entry
    # grammar got to it first.
    if RE_STALE_STAMP.search(t):
        sig.why = ("carries its own date stamp — a rendered old post the "
                   "scraper picked up, not a live call")
        return sig

    # Credit/debit spreads and iron condors are MULTI-LEG — a buy-only bot can't
    # follow them, and he dropped credit spreads on purpose. Jen_SPX Slayer posts
    # "Put Credit Spread (PCS) ... SPX PCS 7720/7710 ... Target: 30%+", which used
    # to read as TRIM PCS — "PCS" taken for a ticker and the 30% for a trim.
    # Vetoed here, before any format reader, so no spread ever reaches the book.
    if re.search(r"\bcredit\s+spread\b|\bdebit\s+spread\b|\biron\s+condor\b"
                 r"|\bput\s+credit\b|\bcall\s+credit\b|\b(?:pcs|ccs|csp)\b", low):
        sig.why = ("a credit/debit spread or cash-secured put (a selling "
                   "strategy) — the buy-only bot doesn't trade these")
        return sig

    # Promo / recruitment spam a room drops in the feed: "50% OFF A FUNDED PORT
    # ($50K) WHEN USING CODE ZTRADEZ https://…". It carried a percent and "OFF",
    # so it read as TRIM OFF. It's an ad, not a call — veto on the ad tells.
    if re.search(r"\d{1,3}\s*%\s*off\b|\busing\s+code\b|\bfunded\s+(?:port|"
                 r"account|trader)\b|\bprop\s+firm\s+funding\b|\bsign\s*up\b", low):
        sig.why = "promotional / recruitment message, not a trade call"
        return sig

    # Who said it. Two shapes: the scribe relaying somebody ("@Brett (Admin)
    # ..."), and the admin posting straight into the room ("Brett (Admin) —
    # 10:20 AM ..."). The relay wins when both are there, because that's the
    # one naming the actual caller.
    mh = RE_HDR.match(raw)
    if mh:
        sig.caller = mh.group("who").strip()
    mc = RE_CALLER.search(raw)
    if mc:
        sig.caller = mc.group(1)

    # ---- Market Guru™ Alerts labeled futures format. The entry is one message
    #      with newlined labels (collapsed to spaces by clean_text):
    #        Ticker: `MNQ SHORT SMALL RISKY TRADE`  Entry: 28590  Stoploss: 28620
    #      The symbol is a micro future, the extra words (SMALL RISKY TRADE) are
    #      noise, the entry/stop are index points. Management arrives later as
    #      bare point counts: "14 points trim", "45 points trim 2", "102 points
    #      exit target hit". The point number is THEIR running P&L, never a
    #      price — the trim/exit word is what acts, and a lone "309 points omg"
    #      is a brag that does nothing.
    mg = re.search(r"ticker:\s*`?\s*([A-Za-z]{2,4})\b([^`\n]*)", t, re.IGNORECASE)
    if (mg and mg.group(1).upper() in FUT_SYMS
            and re.search(r"\bentry:\s*[\d]", t, re.IGNORECASE)):
        sig.symbol = mg.group(1).upper()
        sig.kind = "future"
        sig.direction = "SHORT" if "short" in mg.group(2).lower() else "LONG"
        me = re.search(r"\bentry:\s*([\d][\d.,]*)", t, re.IGNORECASE)
        if me:
            sig.limit = _num(me.group(1))
        ms = re.search(r"\bstop\s*loss:?\s*([\d][\d.,]*)", t, re.IGNORECASE)
        if ms:
            sig.their_stop = _num(ms.group(1))
        sig.action, sig.matched = "OPEN", "market-guru futures entry"
        sig.fire = True
        if sig.limit is None:
            sig.warn = "no entry price posted — it pays the market."
        sig.why = "entry: %s %s @ %s" % (
            sig.direction, sig.symbol, ("%g" % sig.limit) if sig.limit else "mkt")
        return sig

    # Market Guru management by running point count. "exit"/"target hit" closes,
    # a trim word trims; both need the position worked out from what you hold. A
    # bare "N points" (no verb) falls through and ends as a non-order.
    mg_pts = re.match(r"^\s*[-+]?\d+(?:\.\d+)?\s*points?\b(.*)$", low, re.DOTALL)
    if mg_pts and "$" not in low and not re.search(r"\ba con(?:tract)?\b", low):
        # bare point call only — a "$800 a con" line is Felony's dollar exit and
        # belongs to the Whop/Felony handler downstream, not here.
        rest = mg_pts.group(1)
        if re.search(r"\bexit\b|target\s*hit", rest):
            sig.action, sig.matched = "CLOSE", "market-guru points exit"
            sig.needs_position = True
            sig.why = "their exit on the points call — close what it belongs to"
            return sig
        if RE_TRIM.search(rest):
            sig.action, sig.matched = "TRIM", "market-guru points trim"
            sig.needs_position = True
            sig.why = "their trim on the points call — sell some of it"
            return sig

    # ---- "Open / Update / Closed" alert-bot format (JPM Options and the like):
    #      a keyword then the contract on the next line (newlines are already
    #      spaces here): "Open  SPY 08/03 753C @.92". "Open" is the only thing
    #      that buys. "Update" is a running P&L post — "SPY 753C @1.29 (+40%)" —
    #      and must NEVER read as a trim; they're just tracking the runner.
    #      "Closed"/"Close" is the exit. Gated on a readable contract so a stray
    #      "close the door" can't do anything.
    # A short lead-in before the label is allowed: are-alerts writes
    # "For my small fries : OPEN $HPE $30 call 5/15 @ 0.50 (swing)". The prefix
    # must be a single short clause ending in a colon so a whole sentence can't
    # sneak a label out of the middle of prose.
    jm = re.match(r"^(?:[^:\n]{1,40}:\s+)?(open|update|closed|close)\b\s*(.*)$",
                  t, re.IGNORECASE | re.DOTALL)
    if jm and _contract(jm.group(2).strip()):
        label = jm.group(1).lower()
        rest = jm.group(2).strip()
        if label == "update":
            sig.why = "an Update — a running P&L post, not an order"
            return sig
        c = _contract(rest)
        sig.symbol, sig.strike = c["symbol"], c["strike"]
        sig.side, sig.expiry = c["side"], c["expiry"]
        # Their price can be written "@.92" with no leading zero, which the
        # normal limit regex skips — read it here so the entry has a number.
        mp = re.search(r"@\s*\$?([0-9]*\.?[0-9]+)", rest)
        sig.limit = float(mp.group(1)) if mp else None
        if label == "open":
            sig.action, sig.matched = "OPEN", "open-label entry"
            sig.fire = True
            if sig.limit is None:
                sig.warn = "no price on the entry — it pays the market."
            sig.why = "entry: %s" % sig.human()
        else:
            sig.action, sig.matched = "CLOSE", "close-label exit"
            sig.why = "full exit on %s" % sig.symbol
        return sig

    # ---- Bullwinkle (ZTRADEZ top-flow / scalps / futures) format:
    #        "AMD | $550 C 12.72"   "QQQ $707 P 8.75 NEXT WEEK"
    #        "DELL | $445 C NEXT W 19.48"   "SPY | $742 C 4.49 7/31"
    #        "/MES | LONG HERE"     "MES | SHORT HERE"
    #      Options: TICKER, a pipe or a $-strike, then C/P and the premium — the
    #      first plain decimal after the side, NOT a "$266.50 break-of" level.
    #      CC (covered call) and CSP (cash-secured put) are SELLING strategies,
    #      never a buy, so the single-letter [CP] word boundary is deliberate:
    #      it refuses to read CC/CSP as C/P.
    bwf = re.match(r"^/?([A-Za-z]{2,4})\s*\|\s*(long|short)\s+here\b",
                   t, re.IGNORECASE)
    if bwf and bwf.group(1).upper() in FUT_SYMS:
        sig.symbol = bwf.group(1).upper()
        sig.kind = "future"
        sig.direction = bwf.group(2).upper()
        sig.action, sig.matched = "OPEN", "bullwinkle futures entry"
        sig.fire = True
        sig.warn = "no price on the entry — it pays the market."
        sig.why = "entry: %s %s" % (sig.direction, sig.symbol)
        return sig
    bw_pre = re.match(r"^(?:(?:swing(?:ing)?|lotto|scalp|day\s*trade)\s*:?\s+)?"
                      r"(?:(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d*dte)\s+)?", t, re.I)
    bw_t = t[bw_pre.end():] if bw_pre and bw_pre.group(0) else t
    bw_lead = bw_pre.group(1) if bw_pre else None
    bw = re.match(r"^([A-Za-z]{1,5})\s*(\|)?\s*(\$)?"
                  r"(\d{1,5}(?:\.\d+)?)\s*([CcPp])\b(.*)$", bw_t)
    if bw and (bw.group(2) or bw.group(3)
               or re.search(r"(?<![\d$.])\d+\.\d{1,2}(?!\s*%)",
                            bw.group(6) or "")) and \
            bw.group(1).upper() not in NOT_TICKERS:
        rest = bw.group(6)
        sig.symbol = bw.group(1).upper()
        sig.strike = float(bw.group(4))
        sig.side = "CALLS" if bw.group(5).upper() == "C" else "PUTS"
        md = re.search(r"\b(\d{1,2}/\d{1,2})\b", rest)
        if md:
            sig.expiry = md.group(1)
        elif bw_lead:
            sig.expiry = bw_lead.upper() if "dte" in bw_lead.lower() else bw_lead
        # premium: the first plain decimal that isn't a $-prefixed stock level.
        mp = re.search(r"(?<![\d$])(\d+\.\d{1,2})\b", rest)
        sig.limit = float(mp.group(1)) if mp else None
        sig.action, sig.matched = "OPEN", "bullwinkle entry"
        sig.fire = True
        if sig.limit is None:
            sig.warn = "no premium I could read — it pays the market."
        sig.why = "entry: %s" % sig.human()
        return sig

    # ---- The Market Bishop / "The Pawn": "I'm Entering Option: NOW 97 C 7/24
    #      Entry: 0.82". The label makes the ticker unambiguous, so the contract
    #      is read directly (NOW = ServiceNow, which the generic reader rejects
    #      as the word "now" — here the label overrides that). Trims already read
    #      via "Trimming ARM 535 P ...".
    pw = re.match(r"^(?:@\w+\s+)?i'?m\s+entering\s+option:?\s*(.*)$",
                  t, re.IGNORECASE | re.DOTALL)
    if pw:
        mc = re.match(r"\s*([A-Za-z]{1,5})\s+\$?(\d{1,5}(?:\.\d+)?)\s*"
                      r"([CcPp])\b(.*)$", pw.group(1))
        if mc:
            sig.symbol = mc.group(1).upper()
            sig.strike = float(mc.group(2))
            sig.side = "CALLS" if mc.group(3).upper() == "C" else "PUTS"
            md = re.search(r"\b(\d{1,2}/\d{1,2})\b", mc.group(4))
            if md:
                sig.expiry = md.group(1)
            me = re.search(r"entry:?\s*\$?([0-9]*\.?[0-9]+)",
                           pw.group(1), re.IGNORECASE)
            sig.limit = float(me.group(1)) if me else None
            sig.action, sig.matched = "OPEN", "market-bishop entry"
            sig.fire = True
            if sig.limit is None:
                sig.warn = "no entry price posted — it pays the market."
            sig.why = "entry: %s" % sig.human()
            return sig

    # ---- Nitro Trades: "Entry Contract: TSLA $390p Price: $1.75 Comments:none".
    #      A fully labeled entry — the "Entry Contract:" tag and "Price:" make it
    #      unambiguous. Anything led by "Comment" is a watch/recap/exit, handled
    #      by the normal reader (and "on watch" is vetoed above).
    # ---- TLM (9/2): full contract + "at <price>", no verb, short line.
    bare = _contract(t)
    atp = re.search(r"\b(?:at|@)\s*\$?(\d{1,3}(?:\.\d{1,2})?)\b(?!\s*%)", t, re.I)
    if bare and atp and len(t) <= 110 and bare.get("symbol") not in NOT_TICKERS and \
            not re.search(r"\b(sold|sell|selling|out|close|closed|closing|trim|trimm|stop|stops|update|watch|watching|target hit|hedge|spread|avg|average|now)\b", t, re.I):
        px = float(atp.group(1))
        if px > 0 and px != bare.get("strike"):
            sig.symbol, sig.strike, sig.side = bare["symbol"], bare["strike"], bare["side"]
            sig.expiry, sig.limit = bare.get("expiry"), px
            sig.action, sig.matched = "OPEN", "bare priced entry"
            sig.fire = True
            sig.why = "entry: %s" % sig.human()
            return sig

    ntr = re.search(
        r"\b(?:entry\s+)?contract:?\s*\$?([A-Za-z]{1,5})\s+\$?"
        r"(\d{1,5}(?:\.\d{1,2})?)\s*([CcPp])\b"
        r"(?:.*?\bprice:?\s*\$?(\d+(?:\.\d{1,2})?))?", t, re.IGNORECASE)
    if ntr and ntr.group(1).upper() not in NOT_TICKERS:
        sig.symbol = ntr.group(1).upper()
        sig.strike = float(ntr.group(2))
        sig.side = "CALLS" if ntr.group(3).upper() == "C" else "PUTS"
        if ntr.group(4):
            sig.limit = float(ntr.group(4))
        sig.action, sig.matched = "OPEN", "nitro entry"
        sig.fire = True
        if sig.limit is None:
            sig.warn = "no entry price posted — it pays the market."
        sig.why = "entry: %s" % sig.human()
        return sig

    # ---- stockguy007: "USO Calls Jul 18th exp 74" / "SPY Puts Aug 6th exp 630s"
    #      / "ROKU Calls May 15th 120s". Ticker, side spelled out, a month+day
    #      expiry, then the strike (often with a trailing "s"). No premium — it
    #      pays the market. The spelled-out Calls/Puts + month name + day + strike
    #      is the fingerprint; chatter almost never lines those up in that order.
    sgm = re.search(
        r"(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+(calls?|puts?)\s+"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th|dn)?\s+(?:exp\.?\s+)?\$?(\d{1,4})s?\b",
        t, re.IGNORECASE)
    if sgm and sgm.group(1).upper() not in NOT_TICKERS:
        _mo = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
               "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11,
               "dec": 12}[sgm.group(3).lower()]
        sig.symbol = sgm.group(1).upper()
        sig.side = "CALLS" if sgm.group(2).lower().startswith("call") else "PUTS"
        sig.expiry = "%d/%d" % (_mo, int(sgm.group(4)))
        sig.strike = float(sgm.group(5))
        sig.action, sig.matched = "OPEN", "stockguy entry"
        sig.fire = True
        sig.warn = "no premium posted — it pays the market."
        sig.why = "entry: %s" % sig.human()
        return sig

    # ---- Namrood-Trades (ZTRADEZ): "Buy To Open MSFT 400C 1DTE $2.6" /
    #      "Buy To Open GOOGL 345C 08/21/2026 $4.6" / "Lotto Trade — RISKY TSLA
    #      402.5C 7/17/2026 $3.35". The label is the buy; "Close or Trim & Set
    #      SL to BE ..." and "Idea ..." are exits/watches, read elsewhere.
    if re.search(r"\bbuy\s+to\s+open\b|\blotto\s+trade\b", low):
        c = _contract(t)
        if c and c["symbol"] not in NOT_TICKERS:
            sig.symbol, sig.strike = c["symbol"], c["strike"]
            sig.side, sig.expiry = c["side"], c["expiry"]
            mps = re.findall(r"\$\s*(\d+(?:\.\d{1,2})?)\b(?!\s*%)", t)
            # premium is the LAST $-number (a $-strike like "$900.0 CALL" comes
            # first); ignore it if it's the strike itself.
            if mps and float(mps[-1]) != sig.strike:
                sig.limit = float(mps[-1])
            sig.action, sig.matched = "OPEN", "namrood entry"
            sig.fire = True
            if sig.limit is None:
                sig.warn = "no entry price I could read — it pays the market."
            sig.why = "entry: %s" % sig.human()
            return sig

    # ---- Adex Swing: "Entering $MA 535C 6/18 @4.5" / "Entering: $LOW 230C 8/21
    #      @3.30". A "TRIM $WMT CALLS 23%" and the big "Options Analysis ·" table
    #      are not entries (the table is vetoed; TRIM reads as a trim).
    if re.search(r"\bentering\b", low) and not re.search(r"\boptions?\s+analysis\b", low):
        c = _contract(t)
        if c and c["symbol"] not in NOT_TICKERS:
            sig.symbol, sig.strike = c["symbol"], c["strike"]
            sig.side, sig.expiry = c["side"], c["expiry"]
            mp = re.search(r"@\s*\$?(\d+(?:\.\d{1,2})?)\b(?!\s*%)", t)
            if mp:
                sig.limit = float(mp.group(1))
            sig.action, sig.matched = "OPEN", "adex entry"
            sig.fire = True
            if sig.limit is None:
                sig.warn = "no entry price posted — it pays the market."
            sig.why = "entry: %s" % sig.human()
            return sig

    # ---- King Maker Bot: "TWLO 11/21 $140 Calls @$1.49 SL: TWLO < $128.50" /
    #      "AMPX 02/20/26 $11 Call @$0.90". Ticker, MM/DD expiry, $strike, side,
    #      @premium. A line with a % gain or "trimming/booking/took" is an
    #      update, not an entry, so those are left to the trim reader.
    km = re.match(
        r"^(?:@everyone\s+)?([A-Za-z]{1,5})\s+(\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?)\s+"
        r"\$(\d{1,5}(?:\.\d{1,2})?)\s+(calls?|puts?)\s+@\s*\$?(\d+(?:\.\d{1,2})?)",
        t, re.IGNORECASE)
    if km and km.group(1).upper() not in NOT_TICKERS \
            and not RE_PCT_ANY.search(t) \
            and not re.search(r"\b(trimming|booking|took|book\b|profits?)\b", low):
        p = re.findall(r"\d+", km.group(2))
        sig.symbol = km.group(1).upper()
        sig.expiry = "%d/%d" % (int(p[0]), int(p[1]))
        sig.strike = float(km.group(3))
        sig.side = "CALLS" if km.group(4).lower().startswith("call") else "PUTS"
        sig.limit = float(km.group(5))
        sig.action, sig.matched = "OPEN", "kingmaker entry"
        sig.fire = True
        sig.why = "entry: %s" % sig.human()
        return sig

    # ---- KuMo Bot: "Weekly CAVA 07/17/26 $100 Call @$1.50-$1.60 PT1:..." /
    #      "Monthly TJX 05/15/26 $165 Call @$1.55 SL:...". Single-leg only —
    #      a "Debit Spread"/"Credit Spread" is two legs the buy-only bot skips.
    kumo = re.search(
        r"\b(?:weekly|monthly)\s+([A-Za-z]{1,5})\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+"
        r"\$(\d{1,5}(?:\.\d{1,2})?)\s+(calls?|puts?)\s+@\s*\$?(\d+(?:\.\d{1,2})?)",
        t, re.IGNORECASE)
    if kumo and kumo.group(1).upper() not in NOT_TICKERS \
            and not re.search(r"\bspread\b", low) and not RE_PCT_ANY.search(t):
        p = re.findall(r"\d+", kumo.group(2))
        sig.symbol = kumo.group(1).upper()
        sig.expiry = "%d/%d" % (int(p[0]), int(p[1]))
        sig.strike = float(kumo.group(3))
        sig.side = "CALLS" if kumo.group(4).lower().startswith("call") else "PUTS"
        sig.limit = float(kumo.group(5))
        sig.action, sig.matched = "OPEN", "kumo entry"
        sig.fire = True
        sig.why = "entry: %s" % sig.human()
        return sig

    # ---- Stormzy (futures): "TRADE ENTRY - MNQ Shorts - 1/4 Size Position
    #      Entry: 28163.75 Sl: 28194.50". Symbol, direction, entry price; the
    #      "Trade Alert TP 1 : ..." and "SETUP ON WATCH" lines are not entries.
    sz = re.search(
        r"\btrade\s+entry\b[^\n]{0,40}?\b(MNQ|NQ|MES|ES|MYM|YM|M2K|RTY|MCL|CL|MGC|GC)\b"
        r"[^\n]{0,20}?\b(short|long)s?\b[^\n]{0,40}?\bentry:?\s*\$?(\d[\d,]*(?:\.\d{1,2})?)",
        t, re.IGNORECASE)
    if sz:
        _px = _num(sz.group(3))
        if _fut_price_ok(sz.group(1).upper(), _px):
            sig.symbol = sz.group(1).upper()
            sig.kind = "future"
            sig.direction = sz.group(2).upper()
            sig.limit = _px
            ms = RE_THEIR_STOP.search(t)
            if ms:
                sig.their_stop = _num(ms.group(1))
            sig.action, sig.matched = "OPEN", "stormzy futures entry"
            sig.fire = True
            sig.why = "entry: %s %s" % (sig.direction, sig.symbol)
            return sig

    # ---- Vero: "QQQ 708C 7/21 1.03 2 CONTRACTS" / "SPY 757P 8/3 1.13 4 CONS".
    #      Symbol, strike+side, date, premium, size — the "N CONTRACTS/CONS" tail
    #      is the fingerprint that makes this safe to read as an entry.
    vr = re.match(r"^([A-Za-z]{1,5})\s+(\d{1,5})\s*([CcPp])\s+"
                  r"(\d{1,2}/\d{1,2})\s+(\d+\.\d{1,2})\s+\d+\s*"
                  r"(?:contracts?|cons?)\b", t, re.IGNORECASE)
    if vr and vr.group(1).upper() not in NOT_TICKERS:
        sig.symbol = vr.group(1).upper()
        sig.strike = float(vr.group(2))
        sig.side = "CALLS" if vr.group(3).upper() == "C" else "PUTS"
        sig.expiry = vr.group(4)
        sig.limit = float(vr.group(5))
        sig.action, sig.matched = "OPEN", "vero entry"
        sig.fire = True
        sig.why = "entry: %s" % sig.human()
        return sig

    # ---- MR.TOPHAT lotto: "lotto yolo SPX 7460C 0dte @0.25". Anchored on the
    #      lotto/yolo lead + an @-price + a real contract, and refused if it
    #      carries a percentage (that's a recap, not a fresh call).
    if re.match(r"^(?:@\w+\s+)?(?:lotto|yolo)\b", low) and "@" in t \
            and not RE_PCT_ANY.search(t):
        c = _contract(t)
        if c:
            sig.symbol, sig.strike = c["symbol"], c["strike"]
            sig.side, sig.expiry = c["side"], c["expiry"]
            mp = re.search(r"@\s*\$?([0-9]*\.?[0-9]+)", t)
            sig.limit = float(mp.group(1)) if mp else None
            sig.action, sig.matched = "OPEN", "lotto entry"
            sig.fire = True
            sig.why = "entry: %s" % sig.human()
            return sig

    # ---- labeled alert-bot format (Sir Goldman [BOKA] and any bot that
    #      posts ENTRY / TRIM / EXIT / COMMENT as a keyword). The label is
    #      the truth; COMMENT is chatter no matter how many tickers it holds.
    ml = re.match(r"^(?:@\w+\s+)?(ENTRY|TRIM|EXIT|COMMENT)\b\s*(.*)$",
                  t, re.IGNORECASE | re.DOTALL)
    if ml:
        label = ml.group(1).upper()
        rest = ml.group(2).strip()
        rlow = rest.lower()
        if label == "COMMENT":
            sig.why = "a COMMENT from the alert bot — never an order"
            return sig
        if label == "ENTRY":
            # futures first ("Longs MNQ 450s"), then an options contract.
            md = re.search(r"\b(long|short)s?\b[^\n.]{0,20}?"
                           r"\b([A-Za-z]{2,4})\b", rest, re.IGNORECASE)
            if md and md.group(2).upper() in FUT_SYMS:
                sig.symbol = md.group(2).upper()
                sig.kind = "future"
                sig.direction = md.group(1).upper()
                mp = RE_LIMIT.search(rest)
                sig.limit = float(mp.group(1)) if mp else None
                sig.action, sig.matched = "OPEN", "alert-bot futures entry"
                sig.fire = True
                if sig.limit is None:
                    sig.warn = "no price on the entry — it pays the market."
                sig.why = "entry: %s %s" % (sig.direction, sig.symbol)
                return sig
            c_l = _contract(rest)
            if c_l:
                sig.symbol, sig.strike = c_l["symbol"], c_l["strike"]
                sig.side, sig.expiry = c_l["side"], c_l["expiry"]
                mp = RE_LIMIT.search(rest)
                sig.limit = float(mp.group(1)) if mp else None
                sig.action, sig.matched = "OPEN", "alert-bot entry"
                sig.fire = True
                sig.why = "entry: %s" % sig.human()
                return sig
            sig.why = "an ENTRY label with no contract I could read"
            return sig
        # TRIM or EXIT — sell at the posted premium if there is one.
        sig.symbol = _bare_symbol(rest, allowed)
        sig.action = "TRIM" if label == "TRIM" else "CLOSE"
        sig.matched = "alert-bot %s" % label.lower()
        mp = re.search(r"\b(\d{1,3}(?:\.\d{1,2})?)\s*[!]", rest)
        if mp:
            sig.limit = float(mp.group(1))
        mpc = RE_PCT_ANY.search(rest)
        if mpc:
            sig.pct = float(mpc.group(1))
        if not sig.symbol:
            sig.needs_position = True
            sig.why = ("their %s with no ticker — working out which position "
                       "they meant" % label.lower())
            return sig
        sig.fire = sig.action == "CLOSE"
        sig.why = ("%s on %s" % (
            "full exit" if sig.action == "CLOSE" else "trim", sig.symbol))
        return sig

    if "?" in t:
        sig.why = "it's a question, not a call"
        return sig

    # An explicit buy-to-open with a real contract is an ORDER, not chatter. A
    # stray soft word in a risk note — "BTO $MSFT 400c @0.43 cheapie, watch
    # sizing" — must not be vetoed by "watch". The hard "don't/do not" vetoes
    # still fire, and the sell-guard downstream still catches a genuine SELL.
    _explicit_buy = bool(re.search(r"\b(?:bto|bought)\b", low)) and bool(_contract(t))
    for w in tuple(VETO_WORDS) + tuple(cfg.get("extra_veto_words", ())):
        if w.lower() in low and not RE_PAPERCUT.search(low):
            if _explicit_buy and w.lower() not in ("do not", "don't", "dont "):
                continue
            sig.why = 'chatter, not an order (it contains "%s")' % w.strip()
            return sig

    # 0. The recap line. "Way to close the day: AAPL 25% / SPY 63% / JNJ -33%"
    #    — three or more percentages in one message is a scoreboard, not a
    #    call, and reading it as a trim would sell on a summary.
    if len(RE_PCT_COUNT.findall(t)) >= 3:
        sig.why = ("three or more percentages in one line — that's a recap, "
                   "not a call")
        return sig

    # "Or from 15% profit" — Midas describing the level he'd trim FROM. The
    # "from" in front of the percentage is the tell: it's a condition for
    # later, not something he just did. Read as a trim it would have sold.
    if re.search(r"\bfrom\s+\d{1,3}(?:\.\d+)?\s*%", low):
        sig.why = ('a percentage with "from" in front of it is a level '
                   "they're planning around, not a sale")
        return sig

    # "I'm about 80% sure market falls" — a percentage about his CONFIDENCE,
    # not his position. Day two it fired TRIM (+80%).
    if re.search(r"\d{1,3}(?:\.\d+)?\s*%\s*sure\b", low):
        sig.why = "that percentage is how sure they are, not a sale"
        return sig

    # The Whop room narrates its RESTING orders: "Sell order at 29630",
    # "Buy order sitting at 28934", "First trim order at 28550", "First
    # trim at 29563". Those are orders they PLACED, not fills — acting on
    # one sells at a level the market hasn't reached. ("First trim 37%"
    # has no "at <level>", so a real first trim still reads as a trim.)
    if re.search(r"\b(?:buy|sell|trim)\s+order\b|\border\s+(?:at|sitting|set)\b"
                 r"|\bfirst\s+(?:trim|sell)\s+(?:order\s+)?(?:set\s+)?at\s+\$?\d+(?!\s*%)",
                 low):
        sig.why = "that's a resting order they've placed, not a fill — nothing has happened yet"
        return sig

    # ---- z trades' posted format (their own server-map rules) --------------
    #   GREEN circle  = BOUGHT      RED circle = SOLD      WHITE = update
    #   "ON THE BREAK OF $451.50"   = conditional: he enters when the stock
    #   breaks that level — a LOADING, and his "in @ 1.06" reply is the fill.
    #   Scissors = a trim. Circles live in the RAW text (the cleaner strips
    #   emoji), so they're read before anything else.
    zg = "\U0001F7E2" in raw                       # green circle
    zr = "\U0001F534" in raw                       # red circle
    zw = "\u26AA" in raw                           # white circle
    zs = "\u2702" in raw                           # scissors
    if zw and not zg and not zr:
        sig.why = "their price update (white circle) — not an order"
        return sig
    if zg or zr or (zs and not RE_TRIM.search(low)):
        # Bullwinkle writes "GOOGL - $172.5 C" — the dash between symbol and
        # strike hides the contract from the normal reader. Drop it here.
        t_z = re.sub(r"\s-\s", " ", t)
        c_z = _contract(t_z)
        # the premium: first decimal in the line that isn't the strike
        px_z = None
        for mm in re.finditer(r"\b(\d{1,4}\.\d{1,4})\b", t_z):
            v = float(mm.group(1))
            if c_z and abs(v - float(c_z["strike"])) < 0.001:
                continue
            px_z = v
            break
        if zg:
            brk = re.search(r"on\s+the\s+break\s+of\s+\$?(\d[\d.,]*)", low)
            if c_z and brk:
                sig.symbol = c_z["symbol"]
                sig.strike, sig.side = c_z["strike"], c_z["side"]
                sig.expiry = c_z["expiry"]
                sig.action, sig.matched = "PREPARE", "z-format conditional"
                sig.why = ("they'll buy when %s breaks %s — waiting for their "
                           "fill, exactly like a LOADING"
                           % (sig.symbol, brk.group(1)))
                return sig
            if c_z:
                sig.symbol = c_z["symbol"]
                sig.strike, sig.side = c_z["strike"], c_z["side"]
                sig.expiry = c_z["expiry"]
                sig.action, sig.matched = "OPEN", "z-format entry"
                m_l = RE_LIMIT.search(t)
                sig.limit = float(m_l.group(1)) if m_l else px_z
                if sig.limit is None:
                    sig.warn = ("no price on the green circle — it pays the "
                                "market.")
                sig.fire = True
                sig.why = "entry: %s" % sig.human()
                return sig
            if px_z is not None:
                # "GOOGL - in @ 1.06" — the fill on his break-of conditional
                sig.action, sig.matched = "OPEN", "z-format fill"
                sig.needs_loaded = True
                sig.limit = px_z
                sig.symbol = _bare_symbol(t, allowed)
                sig.why = ("their fill on the break-of call — looking for the "
                           "conditional it belongs to")
                return sig
            sig.why = "a green circle with no contract and no price — nothing to follow"
            return sig
        # red circle or scissors: they sold something
        sig.symbol = _bare_symbol(t, allowed)
        partial = bool(zs or re.search(
            r"\bout\s+half\b|\bout\s+\d/\d\b|\ball\s+but\b"
            r"|\bone\s+left\b|\btrim", low))
        sig.action = "TRIM" if partial else "CLOSE"
        sig.matched = "z-format exit"
        if px_z is not None:
            sig.limit = px_z            # the price they sold at
        if not sig.symbol:
            sig.needs_position = True
            sig.why = ("they sold (%s circle) with no ticker — working out "
                       "which position they meant" % ("red" if zr else "scissors"))
            return sig
        sig.fire = sig.action == "CLOSE"
        sig.why = (("full exit on %s" if sig.action == "CLOSE"
                    else "their trim on %s") % sig.symbol) +             ("" if px_z is None else " at %g" % px_z)
        return sig

    # 1. LOADING — get contracts ready. The room says outright: DO NOT BUY IN.
    # A4 - exit/trim/all-out wins over LOADING. "all out of AMD ... keep same
    #      cons loaded" must close, not read as a no-op PREPARE on "loaded".
    if (RE_LOADING.search(low) and not RE_ALLOUT.search(low)
            and not RE_CLOSE_ALL.search(low) and not RE_TRIM.search(low)
            and not RE_STOPPED_OUT.search(low) and not RE_EXIT.search(low)):
        c = _contract(t)
        sig.action = "PREPARE"
        sig.matched = "loading"
        if c:
            sig.symbol, sig.strike = c["symbol"], c["strike"]
            sig.side, sig.expiry = c["side"], c["expiry"]
        sig.why = ("they're getting ready on %s — LOADING never buys, that's the "
                   "room's own rule" % (sig.symbol or "something"))
        return sig

    # 1b. "All positions closed" / "Out of all trades" — everything this
    #     trader holds goes. No ticker to resolve: the worker walks their
    #     whole book and closes each one.
    if RE_CLOSE_ALL.search(low):
        sig.action, sig.all = "CLOSE", True
        sig.matched = "close everything"
        sig.why = ("they closed everything — selling every trade of theirs "
                   "still open")
        return sig

    # 2. ALL OUT — full exit. Checked before trim, because "all out" wins.
    if RE_ALLOUT.search(low):
        c = _contract(t)
        sig.symbol = c["symbol"] if c else _bare_symbol(t, allowed)
        if c:
            sig.strike, sig.side, sig.expiry = c["strike"], c["side"], c["expiry"]
        sig.action, sig.matched = "CLOSE", "all out"
        if sig.symbol and sig.symbol in FUT_SYMS:
            sig.kind = "future"
        mu0 = RE_USD_CONTRACT.search(t)
        if mu0:
            sig.usd = _num(mu0.group(1))
        m = RE_PCT.search(t)
        if m:
            sig.pct = float(m.group(1))
        if not sig.symbol:
            sig.why = "they called an exit but I couldn't tell which ticker"
            return sig
        sig.fire = True
        sig.why = "full exit on %s" % sig.symbol
        return sig

    # 2b. "Out" / "Fully out" — Aristotle's exit is two words with no ticker.
    #     Resolved by whose position it is, exactly like a bare trim. The
    #     anchored regex is what keeps "Damn it actually worked out" from
    #     reading as an exit — a bare out IS the whole message, or it's chatter.
    if (RE_STOPPED_OUT.search(low) or RE_STOP_HIT.search(t)
            or RE_PAPERCUT.search(low)):
        if RE_NOT_ROOM_TRADE.search(low):
            # "stopped out of my personal trade, room trade still on" —
            # his OTHER account. The room's position is explicitly alive;
            # closing it here is the exact wrong read.
            sig.why = ("their stop fired on a personal trade, not the room's "
                       "— the room trade is still on")
            return sig
        sig.symbol = _bare_symbol(t, allowed)
        sig.action = "TRIM" if RE_PARTIAL.search(low) else "CLOSE"
        sig.matched = "stopped out"
        if not sig.symbol:
            sig.needs_position = True
            sig.why = ("their stop fired — working out which position they "
                       "meant")
            return sig
        sig.fire = sig.action == "CLOSE"
        sig.why = (("stopped out of %s" if sig.action == "CLOSE"
                    else "partial stop on %s") % sig.symbol)
        return sig

    if RE_BARE_OUT.match(t):
        sig.action = "TRIM" if RE_HALF.search(t) else "CLOSE"
        sig.needs_position = True
        sig.matched = "bare exit"
        sig.why = ("an exit with no ticker in it — working out which position "
                   "they meant")
        return sig

    # 3. EXITED ... AND BACK IN — one line, two trades.
    #    They sold and immediately re-bought the SAME contract at a new price.
    #    The line doesn't name the contract because everyone in the room already
    #    knows which one, so the re-entry is filled in from what you're holding.
    if RE_BACKIN.search(low) and RE_EXIT.search(low):
        c = _contract(t)
        sig.symbol = c["symbol"] if c else _bare_symbol(t, allowed)
        if c:
            sig.strike, sig.side, sig.expiry = c["strike"], c["side"], c["expiry"]
        sig.action, sig.matched = "CLOSE", "exit and re-entry"
        m = RE_LIMIT.search(t)
        if m:
            sig.limit = float(m.group(1))
        if not sig.symbol:
            sig.why = "they exited and re-entered but I couldn't tell which ticker"
            return sig
        sig.fire = True
        sig.reenter = True
        sig.reenter_limit = sig.limit
        sig.warn = ("two orders off one line: it sells, then buys the same "
                    "contract straight back.")
        sig.why = ("out and back into %s%s — same contract, sold and re-bought"
                   % (sig.symbol,
                      "" if sig.limit is None else " @ %.2f" % sig.limit))
        return sig

    # 2c. Midas's fill confirmations — "Filled @here", "1.97 fill",
    #     "Avg 1.61", "Taking more cons at 748.50". He is IN (or adding);
    #     fires on his last Loaded, and a second one on the same PREP goes
    #     down the averaging path like any other add.
    # A3 - "SAME ONES" / "same cons": re-enter the caller's last posted
    #      contract. If the contract is on the line ("AMD | SAME ONES 500 C
    #      13.25-13.40") parse it and mark a re-entry - the spelled-out
    #      strike/side stops "ONES" being read as the ticker. Full state (prior
    #      expiry / anti-double-up) is the guards' call; never a silent drop.
    if re.search(r"\bsame\s+(?:ones?|cons?|contracts?)\b", low):
        t_s = re.sub(r"\bsame\s+(?:ones?|cons?|contracts?)\b", " ", t,
                     flags=re.IGNORECASE)
        t_s = re.sub(r"\|", " ", t_s)
        t_s = re.sub(r"\s+", " ", t_s).strip()
        lp_s = _loose_premium(t_s, None)
        # Strip price decimals/ranges before reading the contract so a range
        # like "13.25-13.40" can't be misread as an expiry (25/13).
        t_c = re.sub(r"\d{1,3}\.\d{1,2}\s*[-–]\s*\d{1,3}\.\d{1,2}", " ", t_s)
        t_c = re.sub(r"\b\d{1,3}\.\d{1,2}\b", " ", t_c)
        t_c = re.sub(r"\s+", " ", t_c).strip()
        c_s = _contract(t_c)
        sig.reenter = True
        sig.matched = "same-ones re-entry"
        sig.needs_position = True
        if c_s:
            sig.symbol, sig.strike = c_s["symbol"], c_s["strike"]
            sig.side, sig.expiry = c_s["side"], c_s["expiry"]
            sig.action = "OPEN"
            if lp_s is not None:
                sig.limit = lp_s
                sig.reenter_limit = lp_s
            sig.why = ("re-entry of %s - same contract they just called; "
                       "holding to confirm against your open position before "
                       "it fires" % sig.human())
        else:
            sig.why = ('a "same ones" re-entry with no contract on the line - '
                       "resolving it from their last call")
        return sig

    mfc = RE_FILL_CONF.match(t)
    if mfc:
        sig.action = "OPEN"
        sig.matched = "fill confirmation on a loaded contract"
        sig.needs_loaded = True
        p0 = mfc.group(1) or mfc.group(2)
        if p0:
            sig.limit = float(p0)
        else:
            mp0 = RE_IN_PRICE.search(t)
            if mp0:
                sig.limit = float(mp0.group(1))
        sig.why = "their fill confirmation — looking for the PREP it belongs to"
        return sig

    # 3a-equity. "Entered BULL equity @ 7.24" / "Grabbed NFLX equity @ 74.8"
    #    / "Snagging starters on PYPL equity @ 41.03 AVG" — plain shares,
    #    Swing Trades and Long Term style. The word "equity" next to the
    #    ticker IS the instrument; price from @ or their average.
    meq = re.search(r"(?<![A-Za-z])\$?([A-Za-z]{1,5})\s+(?:equity|shares|stock)\b",
                    t, re.IGNORECASE)
    if meq and meq.group(1).upper() not in NOT_TICKERS:
        if re.search(r"\b(?:entered|entering|grabbed|grabbing|snagg?(?:ed|ing)"
                     r"|bought|buying|added|adding|in)\b", low):
            sig.symbol = meq.group(1).upper()
            sig.kind = "equity"
            sig.action, sig.matched = "OPEN", "equity entry"
            m_l = RE_LIMIT.search(t)
            ma_e = RE_FUT_AVG.search(t)
            if m_l:
                sig.limit = float(m_l.group(1))
            elif ma_e:
                sig.limit = _num(ma_e.group(1) or ma_e.group(2))
            ms_e = RE_THEIR_STOP.search(t)
            if ms_e:
                sig.their_stop = _num(ms_e.group(1))
            mt_e = RE_THEIR_TARGET.search(t)
            if mt_e:
                sig.their_target = _num(mt_e.group(1))
            if sig.limit is None:
                sig.why = ("an equity entry with no price anywhere — nothing "
                           "to follow")
                return sig
            sig.fire = True
            sig.why = ("equity entry: %s shares of %s @ %g"
                       % ("some", sig.symbol, sig.limit))
            return sig

    # 3a2. "1.26 new avg" on its own — that's their bookkeeping after an add
    #      that was already signalled, not a second add. Reading it as one
    #      would buy five more contracts per arithmetic update.
    if re.match(r"^\$?\d+(?:\.\d+)?\s*(?:is\s+)?(?:my\s+)?new\s+avg\.?$", t,
                re.IGNORECASE):
        sig.matched = "their new average"
        sig.why = ("their running average after an add they already called — "
                   "nothing to do")
        return sig

    # 3b. ADDED TO — they doubled up and posted their new average.
    #     This is a second buy on a trade you're already in. The parser stops
    #     short of firing it, because the three things that decide it are all
    #     state: is averaging switched on, are you actually in that position,
    #     and how many times have you added already. guards.resolve_add.
    if RE_ADD.search(low):
        c = _contract(t)
        sig.symbol = c["symbol"] if c else _bare_symbol(t, allowed)
        if c:
            sig.strike, sig.side, sig.expiry = c["strike"], c["side"], c["expiry"]
        p = _add_premium(t)
        if p is not None:
            sig.limit = p
        mq = RE_QTY.search(t)
        if mq:
            sig.qty = int(mq.group(1))
        # JonnyOptions [BOKA] says "adding $WULF 17c 4/17" to OPEN, not to
        # average up — his word, his room. A per-channel flag turns "adding"
        # + a full contract into a fresh entry; a bare "adding more" (no
        # contract) still averages, because you can't open what has no strike.
        if cfg.get("adding_is_entry") and c:
            sig.action, sig.matched = "OPEN", "entry (their \"adding\" = enter)"
            sig.fire = True
            sig.why = "entry: %s" % sig.human()
            return sig
        sig.action, sig.matched = "ADD", "added to their position"
        sig.needs_add = True
        sig.why = ("they added to their %s and their average moved — checking "
                   "whether you can follow them in"
                   % (sig.symbol or "position"))
        return sig

    # 3c. FUTURES — "Short NQ @ 28660  Stop 29700  Target 28550".
    #     No strike, no expiry: the symbol, the direction and the price are
    #     the whole contract. His stop and target ride along as THEIR levels —
    #     the plan of record is to run his numbers, not the flat 20%, when
    #     this grammar goes live. Which side of the switch that happens on is
    #     not the parser's decision; it reads, the guards and bridge decide.
    mfut = RE_FUT_ENTRY.search(t)
    fut_dir = fut_sym = fut_px = None
    fut_end = 0
    _mroot = _fut_root(mfut.group(2)) if mfut else None
    if _mroot:
        _px = _num(mfut.group(3))
        if not _fut_price_ok(_mroot, _px):
            # "Long NQ @ 0", "Long NQ @ 286600000", or a count the unit-word
            # lookahead didn't know. Refused loudly, never guessed — a short
            # at a nonsense-low price is a marketable order.
            sig.why = ("looks like a futures entry but %g isn't a plausible "
                       "%s price — refused, not guessed"
                       % (_px, _mroot))
            return sig
        fut_dir, fut_sym = mfut.group(1).upper(), _mroot
        fut_px, fut_end = _px, mfut.end()
    else:
        # "Long NQ - AVG 24015" / "Entered NQ short 23477 average" — no
        # inline price, direction and symbol either way round, the price
        # arriving as an average. Requires the average or his stop/target so
        # "comfortable being long NQ" chatter (no numbers) stays chatter.
        # TWO safety guards, from the High Risk channel's own lines. His trim
        # updates read "...$1,000 a contract on NQ short - Trimmed / Stop now
        # 28130 ... post in gains" — that has a direction, a symbol, a stop
        # with digits and even the word "in". Without these guards it would
        # have BOUGHT. 1) any trim word kills the entry read; 2) an entry
        # leads with its call, so the direction+symbol must sit in the first
        # 40 characters, where "on NQ short" buried mid-update doesn't.
        md = None
        if not RE_TRIM.search(low):
            for cand in RE_FUT_DIR_SYM.finditer(t):
                if cand.start() > 40:
                    break
                c_s = (cand.group(2) or cand.group(4) or cand.group(5)
                       or "").upper()
                if c_s in FUT_SYMS:
                    md = cand
                    break
        if md:
            d0 = (md.group(1) or md.group(3) or md.group(6) or "").upper()
            s0 = (md.group(2) or md.group(4) or md.group(5) or "").upper()
            if d0 and s0 in FUT_SYMS:
                ma_f = RE_FUT_AVG.search(t)
                ml_f = RE_LIMIT.search(t)
                if ma_f or ml_f:
                    _px2 = _num(ma_f.group(1) or ma_f.group(2)) if ma_f \
                        else float(ml_f.group(1))
                    if not _fut_price_ok(s0, _px2):
                        sig.why = ("looks like a futures entry but %g isn't "
                                   "a plausible %s price — refused, not "
                                   "guessed" % (_px2, s0))
                        return sig
                    fut_dir, fut_sym = d0, s0
                    fut_px, fut_end = _px2, md.end()
                elif RE_THEIR_STOP.search(t) and RE_ENTRY.search(low):
                    # "Short NQ - Light / Stop 23400 / Target 23300" — a
                    # real call with no price anywhere. Recorded as a
                    # market entry; the dry run will say so out loud.
                    fut_dir, fut_sym, fut_end = d0, s0, md.end()
    if fut_sym:
        sig.symbol = fut_sym
        sig.kind = "future"
        sig.direction = fut_dir
        sig.limit = fut_px
        sig.action, sig.matched = "OPEN", "futures entry"
        rest = t[fut_end:]
        ms = RE_THEIR_STOP.search(rest)
        if ms:
            sig.their_stop = _num(ms.group(1))
        mt = RE_THEIR_TARGET.search(rest)
        if mt:
            sig.their_target = _num(mt.group(1))
        sig.fire = True
        if sig.limit is None:
            sig.warn = ("they posted no price on this one — it pays the "
                        "market.")
        sig.why = ("futures entry: %s %s @ %s%s%s"
                   % (sig.direction, sig.symbol,
                      "market" if sig.limit is None else "%g" % sig.limit,
                      "" if sig.their_stop is None
                      else ", their stop %g" % sig.their_stop,
                      "" if sig.their_target is None
                      else ", their target %g" % sig.their_target))
        return sig

    # 4. TRIMMING — a partial.
    #
    #    Two grammars. One room writes the word: "trimming SPY @ 38%". The
    #    other just posts the number: "20%", "50% @here", "40% in spy now".
    #    A bare percentage with no contract in the line is a trim — nobody
    #    opens a position by posting "34%". The no-contract test is what keeps
    #    a real entry from being swallowed here.
    pct_m = RE_PCT.search(t) or RE_PCT_ANY.search(t)
    _has_contract = bool(RE_CONTRACT.search(t) or RE_CONTRACT_OSI.search(t))
    if pct_m and not RE_TRIM.search(low) and RE_PCT_RISK.search(t) and not _has_contract:
        sig.why = ("that percentage is their risk, not a gain — nothing to act "
                   "on")
        return sig
    # "Full sold nvda close to 25%" — the word FULL turns a percentage line
    # into a complete exit. Without this, the trim rule below would swallow it
    # and sell 3 of 5 on a call that means "I'm out".
    # "Full sold $3400 a contract" / "Full sold nq 500 points" / "Full sold
    # 200 points" — the Whop room's full exits often carry dollars or points
    # instead of a percentage. FULL + an exit verb is the call; the numbers
    # just say how it went.
    if re.search(r"\bfull(?:y)?\b", low) and RE_EXIT.search(low) and \
            not _contract(t):
        sig.symbol = _bare_symbol(t, allowed)
        sig.action, sig.matched = "CLOSE", "full exit"
        if pct_m:
            sig.pct = float(pct_m.group(1))
        mu_f = RE_USD_CONTRACT.search(t)
        if mu_f:
            sig.usd = _num(mu_f.group(1))
        if not sig.symbol:
            sig.needs_position = True
            sig.why = ("a full exit with no ticker in it — working out which "
                       "position they meant")
            return sig
        sig.fire = True
        sig.why = "full exit on %s" % sig.symbol
        return sig
    bare_pct_ok = cfg.get("bare_pct_trims", True) if cfg else True
    # A BARE percentage with no "trim" verb and no ticker is only a trim when
    # the line is terse — "37%", "50% here". A recap like "3 10-12% trades
    # today lol, green is green" carries a percentage but is an end-of-day
    # summary, and acting on it would trim a live position on a reflection. A
    # percentage RANGE ("10-12%") or a long sentence is the tell. A percentage
    # WITH a ticker ("110% NVDA taking profits") is still a real trim, so this
    # only guards the symbol-less case.
    bare_pct = bool(pct_m) and not _contract(t) and bare_pct_ok
    if bare_pct and not RE_TRIM.search(low) and not _bare_symbol(t, allowed):
        _is_range = re.search(r"\d{1,3}\s*[-–]\s*\d{1,3}\s*%", t)
        if _is_range or len(t.split()) > 6:
            bare_pct = False
    if RE_TRIM.search(low) or bare_pct:
        sig.symbol = _bare_symbol(t, allowed)
        sig.action, sig.matched = "TRIM", "trim"
        if pct_m:
            sig.pct = float(pct_m.group(1))
        # Futures trims speak in dollars, not percent: "$1,100 a contract on
        # NQ short - Trimmed". The dollars are the exit price a dry run
        # settles at.
        if sig.symbol and sig.symbol in FUT_SYMS:
            sig.kind = "future"
        mu = RE_USD_CONTRACT.search(t)
        if mu:
            sig.usd = _num(mu.group(1))

        # There used to be a trim_action setting here (ignore / close / close
        # above a %). Deleted on his word — "no filters wanted. id like to
        # follow everything to the tee as they do." A trim is a trim: the
        # follow-them logic downstream sells its share and keeps the rest.
        if not sig.symbol:
            # Held back rather than dropped. guards.resolve_symbol works out
            # which position they meant from what you're holding and who said
            # it; if it can't, nothing is sent.
            sig.needs_position = True
            sig.why = ("a trim with no ticker in it — working out which "
                       "position they meant")
            return sig
        # "Out of JNJ -33%" — OUT OF a named ticker is a full exit that
        # happens to carry a percentage, not a partial. "out of half" stays
        # a trim.
        if re.match(r"^(?:i'?m\s+)?(?:fully\s+)?out\s+of\b", t,
                    re.IGNORECASE) and not RE_HALF.search(t):
            sig.action, sig.fire = "CLOSE", True
            sig.why = ("full exit on %s%s"
                       % (sig.symbol,
                          "" if sig.pct is None else " at %g%%" % sig.pct))
            return sig
        sig.why = ("trim on %s%s — following their trim"
                   % (sig.symbol,
                      "" if sig.pct is None else " at %g%%" % sig.pct))
        return sig

    # 5. IN — the entry. Needs a full contract; a bare "in" is not an order.
    # But a strong exit word (out/closed/sold) alongside only a weak bare "in"
    # is an EXIT with commentary, not a buy: "QQQ OUT 2.10 In one runner on MNQ
    # futures" is Vero closing QQQ, where the stray "In" used to hijack it into
    # the entry path and drop the exit. Let section 6 handle those.
    _strong_entry = re.search(
        r"\b(?:entered|entering|filled|bto|bought|buying|grabbed)\b", low)
    _exit_with_weak_in = bool(RE_EXIT.search(low)) and not _strong_entry
    # A1 - "taking" is an entry verb ("Also taking $AAPL 315c ... 3.20") but not
    #      "taking profits/off" (a trim, handled above); a quantity-first line
    #      has no verb at all - the leading count is the cue.
    _taking_entry = (bool(re.search(r"\btaking\b", low))
                     and not re.search(
                         r"\btaking\s+(?:profits?|gains?|some|off|half|the\s+l)\b",
                         low)
                     and bool(_contract(t)))
    if ((RE_ENTRY.search(low) or _taking_entry or RE_QTY_LEAD.search(t))
            and not _exit_with_weak_in):
        c = _contract(t)
        if not c:
            # The two-message entry: "Loading 205 calls Friday expiration on
            # NVDA", then a minute later "Filled 3.95 starters". This second line
            # really is the order — it's just that the contract is in the message
            # before it. Held back rather than dropped, the same way a bare trim
            # is: guards.resolve_loaded finds the loading call, and if it can't,
            # nothing is sent.
            mf = RE_BARE_FILL.match(t)
            if mf and not _bare_symbol(t, allowed):
                sig.action, sig.matched = "OPEN", "fill on a loaded contract"
                sig.needs_loaded = True
                sig.limit = float(mf.group(1))
                mq = RE_QTY.search(t)
                if mq:
                    sig.qty = int(mq.group(1))
                sig.why = ("a fill price with no contract in it — looking for the "
                           "LOADING call it belongs to")
                return sig
            # Aristotle's trigger: "In @here starters" — the whole message.
            # His fill already happened; the contract was in his PREP a minute
            # ago, and the price (if any) trails on the end ("I'm in @1.31").
            # Fires on the last thing this admin loaded, at the market when no
            # price came.
            mi = RE_BARE_IN.match(t)
            if mi:
                sig.action, sig.matched = "OPEN", "bare in on a loaded contract"
                sig.needs_loaded = True
                sig.limit = float(mi.group(1)) if mi.group(1) else None
                sig.why = 'a bare "in" — looking for the PREP it belongs to'
                return sig
            # Midas's shape: "In @here my add level will be 744.30" / "In
            # 0days at 1.97". Starts with IN, not prose, and carries a
            # trading cue. The price is only believed when it's premium-sized
            # — 744.30 is a level on the chart, not a thing you pay for a
            # contract.
            if RE_LOOSE_IN.match(t) and RE_IN_CUE.search(t):
                sig.action = "OPEN"
                sig.matched = "loose in on a loaded contract"
                sig.needs_loaded = True
                # If they named a ticker ("In meta 6.10 avg"), pin it so
                # resolve_loaded won't pair it with a different ticker's load.
                sig.named_symbol = _bare_symbol(t, allowed)
                mp = RE_IN_PRICE.search(t)
                lim = float(mp.group(1)) if mp else None
                if lim is None:
                    md0 = re.search(r"\b(\d{1,2}\.\d{1,2})\b", t)
                    if md0 and float(md0.group(1)) < 100:
                        lim = float(md0.group(1))
                sig.limit = lim
                sig.why = ('an "in" with detail around it — looking for the '
                           'PREP it belongs to')
                return sig
            sig.why = "sounds like an entry but there's no full contract in it"
            return sig
        sig.symbol, sig.strike = c["symbol"], c["strike"]
        sig.side, sig.expiry = c["side"], c["expiry"]
        sig.action, sig.matched = "OPEN", "entry"
        m = RE_LIMIT.search(t)
        if m:
            sig.limit = float(m.group(1))
        else:
            # The Whop room posts the fill on the next line of the SAME
            # message: "Entered nvda July 20th 205c / Avg 2.25". Their
            # average is the price they paid — that's the limit.
            ma = RE_AVG_PRICE.search(t)
            if ma:
                sig.limit = float(ma.group(1))
        # A1 - price written anywhere, not just after "@".
        if sig.limit is None:
            lp = _loose_premium(t, sig.strike)
            if lp is not None:
                sig.limit = lp
        mq = RE_QTY.search(t) or RE_QTY_PAREN.search(t)
        if mq:
            sig.qty = int(mq.group(1))
        # "Entered AMD 520C 7/20 @ 1.75  Target 524  Stop 505" — HIS levels,
        # on the underlying. Written down for the day his numbers replace the
        # flat 20% rule; nothing acts on them yet.
        ms_o = RE_THEIR_STOP.search(t)
        if ms_o and float(ms_o.group(1).replace(",", "")) != (sig.strike or -1):
            sig.their_stop = _num(ms_o.group(1))
        mt_o = RE_THEIR_TARGET.search(t)
        if mt_o and float(mt_o.group(1).replace(",", "")) != (sig.strike or -1):
            sig.their_target = _num(mt_o.group(1))
        # (The allowed-symbols refusal that used to sit here is gone — every
        # ticker trades. "no filters wanted.")
        if sig.limit is None:
            # No price in the message. Worth saying out loud rather than
            # discovering on the fill.
            sig.warn = ("they didn't post a fill price on this one — nothing "
                        "to compare your fill against.")
        sig.fire = True
        sig.why = "entry: %s" % sig.human()
        return sig

    # 5b. "QQQ 668 0 day puts @here lightly" — a whole entry in five words,
    #     no verb, no price. Only counts when stripping the contract and the
    #     sizing filler leaves NOTHING — "NVDA 205C looks juicy" leaves
    #     "looks juicy" and stays chatter.
    c5 = _contract(t)
    if c5:
        leftover = re.sub(
            r"(?<![A-Za-z])\$?[A-Za-z]{1,5}\s+\$?\d{1,5}(?:\.\d{1,2})?"
            r"\s*(?:\d{1,2}\s*days?\s*)?(?:calls?|puts?|c|p)\b",
            " ", t, count=1, flags=re.IGNORECASE)
        leftover = re.sub(
            r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b\d*dte\b"
            r"|\b\d{1,2}\s*days?\b", " ", leftover, flags=re.IGNORECASE)
        leftover = RE_FILLER.sub(" ", leftover)
        leftover = re.sub(r"\s+", " ", leftover).strip()
        lone = re.match(r"^\$?(\d{1,2}(?:\.\d{1,2})?)$", leftover)
        if not leftover or (lone and float(lone.group(1)) < 100):
            sig.symbol, sig.strike = c5["symbol"], c5["strike"]
            sig.side, sig.expiry = c5["side"], c5["expiry"]
            sig.action, sig.matched = "OPEN", "bare contract entry"
            sig.fire = True
            if lone:
                sig.limit = float(lone.group(1))
            else:
                sig.warn = "no price posted — it pays the market."
            sig.why = ("entry: %s — the contract IS the whole message"
                       % sig.human())
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

    # 7. "My avg is $3.05" — the fill price, posted a minute after the entry as
    #    its own message. Nothing to do with it: the order is long gone by then
    #    by then. Named here only so
    #    the log says something useful instead of "nothing in it".
    if RE_AVG.search(low):
        sig.matched = "their fill price"
        sig.why = ("that's their average fill on a trade they already called — "
                   "nothing to do with it")
        return sig

    sig.why = "nothing in it that means buy or sell"
    return sig
