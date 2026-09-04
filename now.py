"""now.py — WHAT IS TRUE RIGHT NOW. Broker first, book second, log never.

Run it:  double-click "WHAT DO I HOLD.bat"   (or: python now.py)

WHY THIS EXISTS (9/4/26)
------------------------
Claude told G he was holding a 5-lot SPY position. He wasn't — it had been
closed an hour earlier. The claim came from a log line:

    11:44:59  ADOPT  left SPY x5 alone — bigger than anything the bot trades

That line was TRUE when it was written and FALSE by the time it was read. A
log is a narrative in the past tense; it is not a statement of state. Reading
one as "what I hold" is the same class of error as the bot saying "you closed
it yourself" when its own stop had fired.

Then, compounding it, Claude looked at "ADOPTED x2" plus "ADOPTED x3", saw
2+3=5, and accused the adopt code of inventing the position. The order history
said otherwise: a real 5-lot SPY 769P bought 11:44:30 at 0.46 and sold
11:48:49 at 0.54. The code was right. A tidy-looking theory beat a 10-second
check, which is exactly the habit this file is meant to end.

THE RULE THIS ENFORCES
    positions  -> ask the ACCOUNT
    prices     -> ask the ORDER HISTORY
    reasoning  -> read the logs
    ...and never substitute one for another.

Everything here is READ-ONLY. It places nothing, cancels nothing, changes
nothing. Safe to run any time, including mid-trade.
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _hdr(t):
    print("\n" + t)
    print("-" * len(t))


def main():
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                                   # noqa: BLE001
        now = dt.datetime.now()
    print("=" * 68)
    print("  WHAT IS TRUE RIGHT NOW — %s New York" % now.strftime("%a %d %b %H:%M:%S"))
    print("=" * 68)

    cfg = json.load(open(os.path.join(HERE, "settings.json"), encoding="utf-8"))

    # ---- 1. THE ACCOUNT. This is the only answer to "what do I hold".
    _hdr("1. POSITIONS — straight from Webull, not from any book or log")
    wb = None
    try:
        from webull_options import WebullOptions
        wb = WebullOptions(cfg)
        rows = wb.positions()
        if not rows:
            print("   FLAT. Webull reports no open positions.")
        for r in rows:
            print("   %-6s %-5s %-9s x%-3s  fill %-8s  %s"
                  % (r.get("symbol"), r.get("side"), r.get("strike"),
                     r.get("qty"), r.get("fill"), r.get("expiry") or ""))
    except Exception as e:                              # noqa: BLE001
        print("   COULD NOT ASK THE ACCOUNT: %s" % str(e)[:150])
        print("   ^ that is NOT 'you are flat'. It is 'no verdict'.")

    # ---- 2. Resting orders: anything that could still fire on its own.
    _hdr("2. RESTING ORDERS — what can still execute without you")
    try:
        opens = wb.open_orders() if hasattr(wb, "open_orders") else None
        if opens is None:
            print("   (adapter has no open_orders(); check Webull directly)")
        elif not opens:
            print("   none resting.")
        else:
            for o in opens:
                print("   %s" % str(o)[:150])
    except Exception as e:                              # noqa: BLE001
        print("   could not read: %s" % str(e)[:120])

    # ---- 3. What the BOOK thinks, and whether it agrees with the account.
    _hdr("3. THE BOT'S BOOK — and whether it MATCHES the account above")
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8787/positions",
                                    timeout=4) as r:
            book = json.loads(r.read().decode() or "{}")
        rows = book.get("rows") or book.get("table") or []
        if not rows:
            print("   book holds nothing.")
        for b in rows:
            print("   %-6s %-5s %-9s x%-3s  %s"
                  % (b.get("symbol"), b.get("side"), b.get("strike"),
                     b.get("qty"), b.get("state") or ""))
        print("\n   If this disagrees with section 1, THE ACCOUNT WINS.")
    except Exception as e:                              # noqa: BLE001
        print("   bridge not reachable (%s) — run 'START HERE' if it should be up."
              % str(e)[:80])

    # ---- 4. Today's fills, from the broker's own record.
    _hdr("4. TODAY'S FILLS — the broker's record, not ours")
    try:
        hist = wb.order_history(days=1) if hasattr(wb, "order_history") else None
        if hist is None:
            print("   (no order_history() on the adapter — use the journal,")
            print("    or ask Claude to pull it from the Webull connector)")
        else:
            for h in hist:
                print("   %s" % str(h)[:150])
    except Exception as e:                              # noqa: BLE001
        print("   could not read: %s" % str(e)[:120])

    # ---- 5. Feeds. A stale feed is a silent lie, so it gets a line.
    _hdr("5. FEEDS")
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8787/mode",
                                    timeout=4) as r:
            mode = json.loads(r.read().decode() or "{}")
        g = mode.get("greeks") or {}
        print("   greeks : %s  (level %s, %d contract(s), %d events)"
              % ("LIVE" if g.get("live") else "NOT LIVE",
                 g.get("level"), g.get("with_greeks", 0), g.get("events", 0)))
        print("   swings : %s" % ("PAUSED" if mode.get("swings_paused")
                                  else "trading"))
        print("   announcer: %s" % ("on" if mode.get("announcer_alive")
                                    else "off/paused"))
    except Exception as e:                              # noqa: BLE001
        print("   bridge not reachable (%s)" % str(e)[:80])

    print("\n" + "=" * 68)
    print("  Sections 1 and 4 are the BROKER. Everything else is opinion.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
