# CLEANUP PROPOSAL — for G to approve, 9/4/26 overnight

He asked for hygiene: *"keys that I never use... eliminating code that's
stair-stepping... the sandbox key that is saved but not connected."*

**Nothing in this file has been done.** Removing a feature is not the same as
fixing a bug, and his "fix everything without asking" rule covers bugs. If I
am wrong about what is wired to what, he finds out mid-session with real
money on the line. So: evidence here, one-minute decision from him, then I
execute.

Everything below is measured from `trades.log` (8,210 lines, back to 8/01)
and a reference count across the codebase.

---

## ALREADY DONE TONIGHT (safe, reversible, no feature removed)

**1. Browser lag — the big one.** `content.js` ran `handle()` over every
visible message row in every Discord tab every 1.5s. The dedupe check sat
*after* `textOf()` and `imagesOf()`, so each of roughly **80,000 calls a
minute** did two `querySelectorAll` walks and a regex before deciding it had
nothing new. Now a single native `li.textContent.length` read decides first.
Measured on a 100-row simulation: DOM queries over three sweeps fell from 600
to 200, and the saving grows with every sweep — in practice ~40 sweeps a
minute per tab, so it approaches a 97% cut in repeat work. The late-embed
hydration path is proven unchanged by test (blank shell → hydrates → fires
exactly once).

**2. The permanent record was 21% boot banner.** `trades.log` is what every
audit tool reads, what the journal trues up from, and the one file that
survives a git reset. **1,735 of its 8,210 lines** were the same startup
sentences repeated across ~200 restarts — 244 "test account: unlimited", 239
"Webull LIVE connected", 226 "paper quotes now come from the LIVE feed", 199
"TOPSTEP key VERIFIED". They still print to the console, where seeing boot
state is useful; they no longer go in the record. Nothing that actually
*happened* is affected.

---

## PROPOSED REMOVALS — his call

### A. TRADOVATE — remove. Confidence: high.
```
mentions in trades.log, all time : 1
   2026-08-17  "FUTURES  trade from: webull, tradovate, topstep"
that line is a config echo, not a trade
code references                  : 39
orders ever sent through it      : 0
```
One appearance in six weeks, and it was a settings line listing which futures
brokers were enabled. It has never carried an order. This is the "trade of
eight" he meant. **Safe to delete.**

### B. VOICE / DEEPGRAM — remove or shelve. Confidence: high.
```
VOICE lines in trades.log        : 4  (all "Deepgram key saved", 2 duplicated)
transcripts ever produced        : 0
voice reads that became a trade  : 0
code                             : offscreen.js 215 lines + offscreen.html
                                   + 51 refs in background.js, 12 in popup.js,
                                   10 in bridge.py
```
The ears have never heard anything. ~300 lines and an offscreen document that
has never returned a word. He asked me to "see if we could make sense of
them" — there is nothing to make sense of.
**Question for him:** delete, or was this meant for a room that streams voice
he has not switched on yet? If it is a someday-feature, say so and it stays.

### C. WEBULL SANDBOX / PAPER — needs his decision. Confidence: medium.
```
"sandbox" lines in trades.log    : 226  (all the same boot sentence)
simulated order ids (SIM-) ever  : 0
paper_trading refs in code       : 24
```
The paper account has never filled anything. **But** this is the whole TEST
path: rooms that are not flipped LIVE are supposed to fill here. Removing it
means every room is either real money or nothing at all. That is a strategy
decision, not hygiene. He said *"I don't think we're even using it"* — the
data agrees it has never filled, but I would not rip out the safety net that
lets a new room be watched without money on it.
**Recommendation:** keep the code, delete the unused sandbox KEY from
settings so the popup stops showing "saved but not connected".

### D. TOPSTEP — do NOT remove. Confidence: high.
```
mentions in trades.log           : 242
   199  "key VERIFIED" boot noise (now console-only)
    14  "FUTURES trade from: webull, topstep"
    19  PROP-NO refusals — MGC switched off, account paused/locked,
        ProjectX refused the order
```
Unlike Tradovate, Topstep is **wired and has attempted real orders**. They
were refused by Topstep's own risk rules, not by our code. It looks unused
because it keeps getting turned away. Removing it would delete a working
integration. Leave it.

### E. NINJATRADER — leave, but it is warning at you.
```
27  "PROP  NinjaTrader WARN — no ATM template set"
 1  a real order:  "NinjaTrader <- SELL MNQ x3 (OIF ...)"
```
It has traded once and warns 27 times that it is misconfigured. Either set the
ATM template or switch it off — right now it is half-connected, which is the
worst of both.

---

## STILL TO DO (not started)
* **Popup slimming** — panels he never opens.
* **Dead settings** — keys in settings.json nothing reads.
* The `signals.py` mirror still misses 4 no-ticker exits
  ("Out of 80% of my position"). Flagged repeatedly, still unfixed.
* `restore_state` drops `hi_pct`/`lo_pct` on restart, so a position held
  across a restart loses its run-up/drawdown history.
* Tradier **OTOCO is unverified** — the conditional entry, and the main
  reason to want Tradier at all. Prove it in their sandbox first.
