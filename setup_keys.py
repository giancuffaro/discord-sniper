"""
setup_keys.py — puts your Webull API key into settings.json for you.

Run it with KEYS.bat. It exists so you never have to open a JSON file and get
a comma wrong at 9:29 in the morning.

Nothing typed here leaves your PC. settings.json is in .gitignore, so it is
never committed and an update never overwrites it.
"""

import getpass
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "settings.json")
EXAMPLE = os.path.join(HERE, "settings.example.json")


def load():
    for p in (PATH, EXAMPLE):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


def ask(prompt, current="", secret=False):
    shown = ""
    if current:
        shown = " [keep %s]" % (("*" * 6 + str(current)[-4:]) if secret
                                else current)
    val = (getpass.getpass if secret else input)("%s%s: " % (prompt, shown))
    return val.strip() or current


def main():
    cfg = load()
    ex = cfg.setdefault("execution", {})
    wb = ex.setdefault("webull", {})

    print("=" * 60)
    print("  DISCORD SNIPER — Webull keys")
    print("=" * 60)
    print("You get these from the Webull app:")
    print("  Menu -> More -> OpenAPI -> create an App, then copy the App Key")
    print("  and App Secret. You also need the $4.99/mo options data")
    print("  subscription turned on for the API, or quotes come back empty.")
    print()
    print("Press Enter on any line to keep what's already saved.")
    print("The secret does not show on screen while you type it.")
    print()

    wb["app_key"] = ask("App Key", wb.get("app_key", ""))
    wb["app_secret"] = ask("App Secret", wb.get("app_secret", ""), secret=True)
    print()
    print("Account id: leave blank and it picks your options account on its own,")
    print("and refuses point-blank to use a futures account.")
    wb["account_id"] = ask("Account id (optional)", wb.get("account_id", "") or "")
    print()
    print("Chase limit: if their entry was 3.00 and the ask has already run to")
    print("3.60, that's 20%% worse than they got. Past this number it skips the")
    print("trade instead of buying the top.")
    chase = ask("Max chase %%", str(wb.get("max_chase_pct", 15)))
    try:
        wb["max_chase_pct"] = float(chase)
    except ValueError:
        wb["max_chase_pct"] = 15.0

    print()
    print("Live mode sends REAL orders with REAL money. There is no paper mode.")
    live = input("Turn live Webull trading on now? (yes / no) [no]: ").strip().lower()
    ex["mode"] = "webull" if live in ("y", "yes") else "dryrun"

    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(PATH, 0o600)
    except OSError:
        pass

    print()
    print("Saved to settings.json.")
    print("Mode is now: %s" % ex["mode"].upper())
    if ex["mode"] == "dryrun":
        print("Nothing real will be sent. Run this again and answer yes when "
              "you're ready.")
    else:
        print("REAL ORDERS ARE ON. The extension still has to be ARMED before "
              "anything fires.")
    print()
    print("Now restart BRIDGE.bat so it picks this up.")


if __name__ == "__main__":
    main()
