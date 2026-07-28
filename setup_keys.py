"""
setup_keys.py — puts your Webull key, secret and account into settings.json.

Menu number 2 runs it. It exists so you never have to open a JSON file and get
a comma wrong at 9:29 in the morning.

It does one thing beyond typing: it logs in and shows you every account you
have — margin, cash, futures, IRA — and makes you pick. Auto-picking an
account is how a bot ends up firing options orders at a futures account.

Nothing typed here leaves your PC. settings.json is in .gitignore, so it is
never committed and an update never overwrites it.

There is no live / dry-run question in here on purpose. That switch belongs to
the extension popup, where you can see it and flip it in one click.
"""

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


def mask(v):
    v = str(v or "")
    return ("*" * 6 + v[-4:]) if len(v) > 4 else ("*" * len(v))


def ask(prompt, current="", secret=False):
    """Everything is typed in plain sight now.

    The secret used to be read with getpass, which hides what you type — and
    on Windows that also blocks Ctrl+V, so a 60-character secret had to be
    typed by hand. Not worth it. You're at your own PC; close the window when
    you're done and it's gone."""
    shown = " [keep %s]" % (mask(current) if secret else current) if current else ""
    val = input("%s%s: " % (prompt, shown))
    return val.strip() or current


# --- picking the account -----------------------------------------------------

def choose_account(app_key, app_secret, current=""):
    """Log in, show every account, make him pick one. Returns an account id,
    or whatever was already saved if we couldn't get the list."""
    print()
    print("Looking up your Webull accounts...")
    try:
        import webull_options
        accounts = webull_options.list_accounts(app_key, app_secret)
    except Exception as e:                                  # noqa: BLE001
        # A Refused already reads like English. Anything else gets trimmed so
        # you get a sentence instead of a stack trace.
        why = getattr(e, "args", [""])[0] if e.args else str(e)
        print()
        print("  Couldn't get the list: %s" % str(why)[:200])
        print()
        print("  That's usually one of three things: the key and secret got")
        print("  swapped, the app isn't approved on Webull's side yet, or")
        print("  you're not online.")
        typed = ask("  Type an account id by hand, or press Enter to skip",
                    current)
        return typed

    print()
    print("  Your Webull accounts:")
    print()
    for i, a in enumerate(accounts, 1):
        star = "  <- saved now" if current and a["id"] == str(current) else ""
        note = ""
        if a["kind"] == "FUTURES":
            note = "   (futures — this bot will refuse to use it)"
        print("    %d.  %s%s%s" % (i, a["label"], note, star))
    print()
    print("  Pick the one you want the bot to trade options in.")
    print("  If you're not sure, it's the MARGIN one.")
    print()

    default_i = 1
    for i, a in enumerate(accounts, 1):
        if current and a["id"] == str(current):
            default_i = i
            break
    else:
        for i, a in enumerate(accounts, 1):
            if a["kind"] == "MARGIN":
                default_i = i
                break

    while True:
        pick = input("  Number [%d]: " % default_i).strip() or str(default_i)
        if pick.isdigit() and 1 <= int(pick) <= len(accounts):
            chosen = accounts[int(pick) - 1]
            if chosen["kind"] == "FUTURES":
                print("  That's your futures account. Options orders can't go")
                print("  there, so the bridge would refuse it every morning.")
                print("  Pick a different number.")
                continue
            print("  Using %s." % chosen["label"].strip())
            return chosen["id"]
        print("  Type one of the numbers above.")


# --- the screen --------------------------------------------------------------

def main():
    cfg = load()
    ex = cfg.setdefault("execution", {})
    wb = ex.setdefault("webull", {})
    ex.setdefault("mode", "dryrun")      # never changed from here — see the popup

    print("=" * 62)
    print("  DISCORD SNIPER — Webull keys")
    print("=" * 62)
    print("You get these from the Webull app:")
    print("  Menu -> More -> OpenAPI -> create an App, then copy the App Key")
    print("  and App Secret. You also need the $4.99/mo options data")
    print("  subscription turned on for the API, or quotes come back empty.")
    print()
    print("Right-click in this window pastes. Both lines show what you paste,")
    print("so nothing silently goes in half-typed.")
    print("Press Enter on any line to keep what's already saved.")
    print()

    wb["app_key"] = ask("App Key", wb.get("app_key", ""))
    wb["app_secret"] = ask("App Secret", wb.get("app_secret", ""), secret=True)

    if wb["app_key"] and wb["app_secret"]:
        wb["account_id"] = choose_account(wb["app_key"], wb["app_secret"],
                                          wb.get("account_id", "") or "")
    else:
        print()
        print("No key or secret yet, so there's nothing to log in with — the")
        print("account list is skipped. Run this again once you have them.")

    print()
    print("Chase limit: if their entry was 3.00 and the ask has already run to")
    print("3.60, that's 20% worse than they got. Past this number it skips the")
    print("trade instead of buying the top — it does NOT buy it late.")
    chase = ask("Max chase %", str(wb.get("max_chase_pct", 15)))
    try:
        wb["max_chase_pct"] = float(str(chase).strip().rstrip("%"))
    except ValueError:
        wb["max_chase_pct"] = 15.0

    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(PATH, 0o600)
    except OSError:
        pass

    print()
    print("Saved to settings.json.")
    print("  key      %s" % mask(wb.get("app_key", "")))
    print("  secret   %s" % mask(wb.get("app_secret", "")))
    print("  account  %s" % (wb.get("account_id") or "(not set — it will pick "
                             "your options account on its own)"))
    print("  chase    %g%%" % wb.get("max_chase_pct", 15))
    print()
    print("Real orders are OFF until you switch the extension to LIVE. That")
    print("switch is in the extension popup, not in here.")
    print()
    print("Now restart the bridge so it picks this up: START HERE, 6 then 5.")
    print("Your secret is on this screen — close the window when you're done.")


if __name__ == "__main__":
    main()
