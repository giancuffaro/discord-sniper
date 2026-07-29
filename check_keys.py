"""check_keys.py — is this thing actually going to work on Monday?

Run it whenever you want reassurance. It checks, in order, the things that
would stop a trade going out, and it stops at the first real problem rather
than burying it in a wall of green ticks.

It places no orders and it cannot place orders. The worst it does is ask
Webull for a price.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OK = "  [ OK ]  "
NO = "  [ NO ]  "
HM = "  [ ?? ]  "


def line(mark, text):
    print(mark + text)


def blank():
    print("")


def main():
    print("")
    print("  ============================================================")
    print("    Checking your setup")
    print("  ============================================================")
    blank()

    # --- 1. the clock --------------------------------------------------------
    try:
        import eastern
        now = eastern.now()
        line(OK, "Market clock: it's %s in New York."
              % now.strftime("%a %d %b, %H:%M"))
        if "built-in" in eastern.source():
            line(HM, "Using the built-in timezone rule — the tzdata package "
                     "isn't installed.")
            line("         ", "Not a problem, but double-clicking START HERE would tidy it up.")
    except Exception as e:                              # noqa: BLE001
        line(NO, "Couldn't work out the time in New York: %s" % e)
        return 1

    # --- 2. settings.json ----------------------------------------------------
    path = os.path.join(HERE, "settings.json")
    if not os.path.exists(path):
        line(NO, "There's no settings.json in this folder.")
        blank()
        line("         ", "Put your Webull keys in through the extension popup's "
                          "key and secret in. That creates it.")
        return 1
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except ValueError as e:
        line(NO, "settings.json is there but it isn't readable: %s" % e)
        blank()
        line("         ", "Something edited it by hand and broke it. Menu "
                          "saving your keys in the popup writes a fresh one.")
        return 1
    line(OK, "settings.json found and readable.")

    ex = cfg.get("execution", {}) or {}
    wb = ex.get("webull", {}) or {}
    key, secret = wb.get("app_key", ""), wb.get("app_secret", "")

    # --- 3. are the keys even there ------------------------------------------
    if not key or not secret:
        line(NO, "No Webull API key saved.")
        blank()
        line("         ", "Paste your keys into the extension popup's Settings. Nothing can trade "
                          "until that's done.")
        return 1
    # Never print the key. Enough to recognise it, not enough to use it.
    line(OK, "Webull key saved (ends %s), secret saved (%d characters)."
          % (key[-4:], len(secret)))

    mode = ex.get("mode", "dryrun")
    if mode == "webull":
        line(HM, "Mode is LIVE. Real orders. Real money.")
    else:
        line(OK, "Mode is DRY RUN — it will describe trades and send nothing.")

    # --- 4. the SDK ----------------------------------------------------------
    try:
        import webull_options as W
    except Exception as e:                              # noqa: BLE001
        line(NO, "Couldn't load the Webull code: %s" % e)
        return 1
    if not W.SDK_OK:
        line(NO, "The Webull SDK isn't installed.")
        blank()
        line("         ", "Double-click START HERE, let it finish, then "
                          "press 3 again.")
        line("         ", "(%s)" % W.SDK_WHY[:110])
        return 1
    line(OK, "Webull SDK installed.")

    # --- 5. do the keys actually work -----------------------------------------
    blank()
    print("  Asking Webull whether it recognises your key...")
    blank()
    try:
        client = W.WebullOptions(cfg)
        account = client.connect()
    except W.Refused as e:
        line(NO, str(e))
        return 1
    except Exception as e:                              # noqa: BLE001
        line(NO, "Couldn't reach Webull: %s" % str(e)[:160])
        blank()
        line("         ", "Usually that's no internet, or Webull being down. "
                          "Try again in a minute.")
        return 1

    line(OK, "Connected. Trading account: %s" % account)

    sus = [s for s in client.futures_suffixes if account.upper().endswith(s)]
    if sus:
        line(NO, "That account looks like your FUTURES account. It should "
                 "never have got this far — tell me straight away.")
        return 1
    line(OK, "Confirmed it is not your futures account.")

    # --- 6. options data ------------------------------------------------------
    # The bit people get caught by: the key works, the account is right, and
    # then every options quote comes back 403 because the OPRA subscription
    # isn't on. Better to find that out now than at 9:31.
    print("")
    print("  Asking for a real options price (this is the one that catches")
    print("  people out - it needs your options data subscription)...")
    blank()
    try:
        import datetime as dt
        friday = dt.date.today()
        friday += dt.timedelta(days=(4 - friday.weekday()) % 7 or 7)
        occ = W.occ_symbol("SPY", friday.isoformat(), "CALL", 700)
        ask, bid, _row = client.ask_bid(occ)
        if ask:
            line(OK, "Got a live price back (%s: ask %.2f). Options data is "
                     "working." % (occ, ask))
        else:
            line(HM, "Connected, but no price came back for %s." % occ)
            line("         ", "That strike may just not be listed. Not "
                              "necessarily a problem.")
    except W.Refused as e:
        msg = str(e)
        line(NO, msg)
        if "403" in msg or "subscri" in msg.lower() or "permission" in msg.lower():
            blank()
            line("         ", "That's the options data subscription. It's "
                              "$4.99/mo inside the Webull app.")
            line("         ", "Without it every options quote comes back "
                              "refused and nothing can trade.")
        return 1
    except Exception as e:                              # noqa: BLE001
        line(HM, "Couldn't get a test price: %s" % str(e)[:150])
        line("         ", "Worth a second run before you trust it.")

    # --- 7. the brakes --------------------------------------------------------
    blank()
    g = cfg.get("guards", {}) or {}
    print("  Your limits, as they're currently set:")
    print("    - at most %s contract(s) per trade" % g.get("max_qty", 1))
    print("    - at most %s trades a day" % g.get("max_trades_per_day", 6))
    print("    - new trades only between %s and %s New York time"
          % (g.get("open_time", "09:30"), g.get("close_time", "12:00")))
    print("    - exits allowed at any time")
    print("    - only these symbols: %s"
          % ", ".join(cfg.get("allowed_symbols", [])) or "(none set!)")
    if not cfg.get("allowed_symbols"):
        line(NO, "No allowed symbols — everything would be refused.")

    blank()
    print("  ============================================================")
    if mode == "webull":
        print("    Everything checks out. You are on LIVE.")
    else:
        print("    Everything checks out. You are on DRY RUN - safe.")
    print("  ============================================================")
    blank()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Stopped.")
        sys.exit(1)
