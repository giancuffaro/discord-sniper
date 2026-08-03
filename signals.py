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
    r"(?P<kind>calls?|puts?)\b"
    r"(?P<mid>[^.!?]{0,40}?)"
    r"\bon\s+\$?(?P<symbol>[A-Za-z]{1,5})\b", re.IGNORECASE)

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
RE_ENTRY = re.compile(
    r"\b(?:in|entered|entering|filled|bto|bought|buying|grabbed)\b"
    r"|\b(?:took|take|taking)\s+(?:some|a)\b", re.IGNORECASE)
# "added to SPY @everyone new avg is 2.8" — they doubled up and their average
# moved. Whether that buys you a second contract is a setting, not a parser
# decision: the parser only says "this is an add", and guards.resolve_add has
# the final word, because only the guards know whether you're even in it.
RE_ADD = re.compile(r"\badd(?:ed|ing|s)?\s+(?:to|more|into)\b|\badding\b"
                    r"|\baverag(?:e|ed|ing)\s+(?:in|down|up)\b"
                    r"|\b(?:new|updated)\s+(?:avg|average)\b", re.IGNORECASE)
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
RE_FUT_ENTRY = re.compile(
    # The @ is optional now — his Day Trades channel writes "Short nq
    # 28240.50" with nothing between the symbol and the price. The number
    # keeps it honest: "long NQ into the close" has no price, so no entry.
    r"\b(short|long)\s+\$?([A-Za-z0-9]{1,4})\s*(?:@|at\b)?\s*"
    r"\$?(\d[\d,]*(?:\.\d{1,2})?)\b",
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
# "Stopped" alone at the start of a message, "Eh stopped", "Stop got hit",
# "BE stop hit", "Trailing stop hit on RTY" — their stop fired, said seven
# different ways. Start-anchored so "if we get stopped" inside an entry's
# rationale never reads as an exit.
RE_STOP_HIT = re.compile(
    r"^(?:eh\s+|welp\s+)?stopp(?:ed|ing)\b"
    r"|\b(?:be\s+|trailing\s+)?stop\s+(?:got\s+|was\s+)?hit\b",
    re.IGNORECASE)
# "Taking paper cut" / "Locking in a 8 point loss" — an early exit by hand.
# Verb-led on purpose: "those paper cuts we took yesterday" is a war story,
# "Taking papercut" is a sale.
RE_PAPERCUT = re.compile(
    r"\btak(?:e|ing)\s+(?:a\s+|this\s+|the\s+)?paper\s*cut"
    r"|\btak(?:e|ing)\s+be\b"          # "Taking BE" — out at breakeven
    r"|\btaking\s+the\s+loss\b"
    r"|\block(?:ing)?\s+in\s+an?\s+\d+\s+point\s+loss\b", re.IGNORECASE)


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
    r"^(?:filled)\b(?:\s+(?:light\s+size|lightly|starters?))*[\s.!]*$"
    r"|^\$?(\d{1,2}\.\d{1,2})\s+(?:is\s+my\s+)?(?:final\s+)?"
    r"(?:fill|avg)\b[\s.!]*$"
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
VETO_WORDS = ("do not", "don't", "dont ", "watching", "watch", "eyeing",
              "looking at", "thinking", "maybe", "might", "if it", "if you",
              "waiting", "wait for", "heads up", "scanner", "idea", "consider",
              "recap", "example", "congrats", "missed", "sorry", "pissed",
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
              "going to", "gonna")

NOT_TICKERS = {"THE", "A", "AN", "IT", "ALL", "IN", "OUT", "AT", "ON", "MY",
               "IS", "AND", "OF", "TO", "BE", "OK", "DTE", "AM", "PM", "ET",
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
               "FIB", "PREP", "LOL", "SMH", "LFG", "PDT"}


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
    t = RE_HDR.sub("", (raw or "").strip())
    t = RE_PING.sub(" ", t)
    t = RE_CALLER.sub(" ", t)
    t = RE_EMOJI.sub(" ", t)
    # Numbered paste lines ("14. Loading 205 calls..."). The space after the dot
    # is required: without it "206.5 need to clear now" gets shortened to "5 need
    # to clear now", and a line like "747.5 calls on SPY" would turn into a
    # contract at a strike of 5.
    t = re.sub(r"^\s*\d{1,3}\.\s+", "", t)
    return re.sub(r"\s+", " ", t).strip()


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


def _contract(text):
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

    for w in tuple(VETO_WORDS) + tuple(cfg.get("extra_veto_words", ())):
        if w.lower() in low and not RE_PAPERCUT.search(low):
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
    if RE_STOPPED_OUT.search(low) or RE_STOP_HIT.search(t) \
            or RE_PAPERCUT.search(low):
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
        sig.action, sig.matched = "ADD", "added to their position"
        sig.needs_add = True
        m = RE_LIMIT.search(t) or RE_AVG_PRICE.search(t)
        if m:
            sig.limit = float(m.group(1))
        mq = RE_QTY.search(t)
        if mq:
            sig.qty = int(mq.group(1))
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
    if mfut and mfut.group(2).upper() in FUT_SYMS:
        fut_dir, fut_sym = mfut.group(1).upper(), mfut.group(2).upper()
        fut_px, fut_end = _num(mfut.group(3)), mfut.end()
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
                    fut_dir, fut_sym = d0, s0
                    fut_px = _num(ma_f.group(1) or ma_f.group(2)) if ma_f \
                        else float(ml_f.group(1))
                    fut_end = md.end()
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
    if pct_m and not RE_TRIM.search(low) and RE_PCT_RISK.search(t):
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
    if RE_TRIM.search(low) or (pct_m and not _contract(t) and bare_pct_ok):
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
    if RE_ENTRY.search(low):
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
