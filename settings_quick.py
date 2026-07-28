"""
settings_quick.py — change the four numbers that actually change a day,
without opening settings.json and hunting for a comma.

    python settings_quick.py

Everything here is a question with the current answer already in it. Press
Enter and nothing changes. There is no way to break the file from in here:
it's read, the answers are checked, and only then is it written back.

What this file does NOT do: it does not touch your Webull keys (that's
START HERE, number 2) and it does not switch anything to live money (that's
the button in the extension popup, and it asks twice).
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(HERE, "settings.json")
EXAMPLE = os.path.join(HERE, "settings.example.json")


def load():
    """Your settings, or a fresh copy of the example if you've never made one."""
    if not os.path.exists(SETTINGS):
        if not os.path.exists(EXAMPLE):
            print("   I can't find settings.json or settings.example.json in")
            print("   this folder. Run number 1 on START HERE first.")
            return None
        shutil.copyfile(EXAMPLE, SETTINGS)
        print("   You didn't have a settings.json yet, so I started one from")
        print("   the example. Your Webull keys aren't in it — number 2 on")
        print("   START HERE puts those in.\n")
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        # A half-edited JSON file is the one way this goes wrong, and a raw
        # parser error tells you nothing useful.
        print("   settings.json has a typo in it — usually a missing comma or")
        print("   a stray quote — so I can't read it. Easiest fix: rename it to")
        print("   settings-broken.json, run number 2 to put your keys back in,")
        print("   then run this again.")
        return None


def ask_number(label, current, low, high, note=""):
    """A number, or Enter to leave it. Anything silly is asked again rather
    than accepted and quietly clamped later."""
    while True:
        if note:
            print("   " + note)
        raw = input("   %s [now: %s]: " % (label, current)).strip()
        if not raw:
            return current
        raw = raw.replace("$", "").replace(",", "").strip()
        try:
            n = float(raw)
        except ValueError:
            print("   That wasn't a number. Try again, or press Enter to keep"
                  " %s.\n" % current)
            continue
        if n < low or n > high:
            print("   That has to be between %g and %g. Try again.\n" % (low, high))
            continue
        return int(n) if n == int(n) else n


def ask_yes_no(label, current):
    while True:
        raw = input("   %s [now: %s]: "
                    % (label, "YES" if current else "NO")).strip().lower()
        if not raw:
            return current
        if raw in ("y", "yes", "on", "true", "1"):
            return True
        if raw in ("n", "no", "off", "false", "0"):
            return False
        print("   Type Y or N, or press Enter to keep it as it is.\n")


def main():
    cfg = load()
    if cfg is None:
        return 1

    cfg.setdefault("guards", {})
    cfg.setdefault("execution", {})
    g, ex = cfg["guards"], cfg["execution"]

    print()
    print("   ============================================================")
    print("     THE NUMBERS")
    print("   ============================================================")
    print("     Press Enter on any question to leave it exactly as it is.")
    print()

    ex["dry_run_buying_power"] = ask_number(
        "Pretend buying power, dollars",
        ex.get("dry_run_buying_power", 0), 0, 1000000,
        "In test mode this is the money it pretends you have, so you can see\n"
        "   which of their calls you couldn't have afforded. One contract is\n"
        "   100 shares, so a $2.80 call costs $280. Real money ignores this and\n"
        "   asks Webull what you've actually got.")
    print()

    g["max_trades_per_day"] = ask_number(
        "Trades a day, 0 for no limit",
        g.get("max_trades_per_day", 0), 0, 100,
        "How many NEW trades it will take in one day. 0 means it follows every\n"
        "   call they make. Exits never count against this — you can always get\n"
        "   out.")
    print()

    g["max_qty"] = ask_number(
        "Contracts per trade",
        g.get("max_qty", 1), 1, 50,
        "How many contracts one entry buys. 1 is one contract, which is 100\n"
        "   shares of the option.")
    print()

    g["average_in"] = ask_yes_no(
        "Follow them when they add to a trade? Y/N",
        g.get("average_in", False))
    print("   (They post \"added to SPY, new avg 2.80\" when they buy more of\n"
          "    something. YES buys another one of what you're already holding.\n"
          "    It will never do this on a trade you're not in, and it always\n"
          "    buys the same contract you hold, not whatever's in their message.)")
    print()

    if g["average_in"]:
        g["max_adds_per_position"] = ask_number(
            "How many times to add to the same trade",
            g.get("max_adds_per_position", 2), 0, 10,
            "2 means you can end up holding three of it and no more. This is\n"
            "   the setting that stops a $280 trade turning into $1,120 while\n"
            "   you're not looking.")
        print()

    # The stop lives under execution.webull because bridge.py is what enforces
    # it — the browser never sees a fill price, so it couldn't.
    w = ex.setdefault("webull", {})
    w["stop_loss_pct"] = ask_number(
        "Stop loss, % off what you paid",
        w.get("stop_loss_pct", 20), 5, 90,
        "Measured off YOUR fill, not off the price they posted. 20 means a fill\n"
        "   at 2.80 gets a stop at 2.24. It's held two ways: a real stop order\n"
        "   sitting at Webull, and a watchdog in the bridge window. On options\n"
        "   premium 20% is tight — it's a normal wobble on a slow morning, so\n"
        "   expect it to take you out of trades that would have come back.")
    print()

    w["entry_fill_seconds"] = ask_number(
        "How long your bid may sit there, seconds",
        w.get("entry_fill_seconds", 90), 10, 900,
        "Your entry is a limit at the bid, so it waits for a seller to come to\n"
        "   you. After this many seconds it gets pulled. Long is not safer: an\n"
        "   order left resting can fill in the afternoon into a trade they\n"
        "   called at 9:40 and were out of by 10:05.")
    print()

    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    try:
        os.chmod(SETTINGS, 0o600)
    except Exception:
        pass          # Windows shrugs at this, and it doesn't matter here

    cap = g["max_trades_per_day"]
    print("   ============================================================")
    print("     SAVED")
    print("   ============================================================")
    print("     Pretend buying power  $%s" % ex["dry_run_buying_power"])
    print("     Trades a day          %s" % ("no limit" if not cap else cap))
    print("     Contracts per trade   %s" % g["max_qty"])
    print("     Averaging in          %s%s"
          % ("YES" if g["average_in"] else "NO",
             "" if not g["average_in"]
             else ", up to %s time(s) per trade" % g.get("max_adds_per_position", 2)))
    print("     Stop loss             %s%% off your fill" % w["stop_loss_pct"])
    print("     Bid waits             %s seconds, then it's pulled"
          % w["entry_fill_seconds"])
    print()
    print("     One more thing, and it matters: the extension keeps its OWN")
    print("     copy of the trade rules, because it's the extension that")
    print("     decides. Open the popup, click Settings, and set the same")
    print("     numbers there. The buying power above is the one number that")
    print("     lives here and nowhere else.")
    print()
    print("     If the bridge is already running, stop and start it (numbers 6")
    print("     then 5) so it reads the new buying power.")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n   Left everything as it was.")
        sys.exit(0)
