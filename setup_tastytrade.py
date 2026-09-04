"""SETUP TASTYTRADE (9/3/26) — connect the account without your password ever
being stored, logged, or shown to anyone.

Run it:  double-click "SETUP TASTYTRADE.bat"   (or: python setup_tastytrade.py)

WHAT IT DOES, in order
  1. Asks for your tastytrade username and password AT YOUR OWN TERMINAL.
     The password echoes as asterisks only (see read_password) — it is never
     printed, never written to disk, and never leaves this machine except in
     the single login request to tastytrade itself.
  2. Logs in ONCE and asks tastytrade for a REMEMBER TOKEN.
  3. Writes ONLY the username + remember token into settings.json.
     **The password is not saved anywhere.** The remember token is what the
     bot uses from then on, and it can be revoked from your tastytrade
     account without changing your password.
  4. Lists your accounts and saves the one you pick.
  5. Runs the read-only verify() checklist — balances, a quote, positions,
     and whether the greeks stream token is reachable.

WHAT IT DOES NOT DO
  It never places, cancels or modifies an order. It never flips the bot over
  to tastytrade — `execution.broker` is deliberately left as it is, so the
  machine keeps trading Webull exactly as before until you decide otherwise.
"""
import getpass
import json
import os
import sys


def read_password(prompt):
    """Read a password with VISIBLE feedback (9/3, G: "I can type in the
    username section but not the password").

    getpass() hides the password so completely that nothing moves on screen —
    no asterisks, no cursor — so it looks frozen even though it is reading
    fine. On Windows we read a character at a time with msvcrt and echo a
    '*' per keystroke, which shows it working without showing the password.
    Backspace works. Anywhere else, or if the console won't allow it, we
    fall back to getpass and say so.
    """
    try:
        import msvcrt                                    # Windows only
    except ImportError:
        try:
            return getpass.getpass(prompt)
        except Exception:                                # noqa: BLE001
            print("  (this terminal won't hide input — it WILL be visible)")
            return input(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    buf = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):                           # Enter
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(buf)
        if ch == "\003":                                  # Ctrl-C
            raise KeyboardInterrupt
        if ch in ("\b", "\x7f"):                          # Backspace
            if buf:
                buf.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if ch in ("\000", "\xe0"):                        # arrow/function key
            msvcrt.getwch()                              # eat the second byte
            continue
        buf.append(ch)
        sys.stdout.write("*")
        sys.stdout.flush()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SETTINGS = os.path.join(HERE, "settings.json")


def main():
    print("=" * 66)
    print("  CONNECT TASTYTRADE — read-only setup")
    print("=" * 66)
    print("  Your password is typed here, used once to get a token, and then")
    print("  forgotten. It is NOT saved to settings.json and NOT logged.")
    print()

    try:
        cfg = json.load(open(SETTINGS, encoding="utf-8"))
    except Exception as e:                              # noqa: BLE001
        print("  Could not read settings.json (%s). Nothing changed." % e)
        return 1

    tt = cfg.setdefault("execution", {}).setdefault("tastytrade", {})
    user = (tt.get("username") or "").strip()
    prompt = "  tastytrade username%s: " % (" [%s]" % user if user else "")
    typed = input(prompt).strip()
    if typed:
        user = typed
    if not user:
        print("  No username given. Nothing changed.")
        return 1

    print("  (you'll see a * for each character — the password itself is")
    print("   never shown, never saved, never logged)")
    pw = read_password("  tastytrade password: ")
    if not pw:
        print("  No password given. Nothing changed.")
        return 1

    # --- log in once, purely to trade the password for a token ------------
    try:
        from tastytrade import TastytradeOptions
        cli = TastytradeOptions(username=user, password=pw)
        print("\n  Logging in ...")
        cli._session()                                  # noqa: SLF001
    except Exception as e:                              # noqa: BLE001
        print("  Login FAILED: %s" % str(e)[:200])
        print("  Nothing was written. Check the username/password, and that")
        print("  the account is open and approved for options.")
        return 1
    finally:
        pw = None                                       # drop it immediately

    remember = getattr(cli, "_remember", None)
    if remember:
        print("  Login OK — got a remember token, so the password is not needed again.")
    else:
        print("  Login OK, but tastytrade returned no remember token.")
        print("  You'll be asked for the password again next time; nothing is saved.")

    # --- which account ----------------------------------------------------
    try:
        accts = cli.accounts()
    except Exception as e:                              # noqa: BLE001
        print("  Could not list accounts: %s" % str(e)[:160])
        return 1
    nums = []
    for a in accts:
        n = a.get("account-number") or a.get("account_number")
        if n:
            nums.append(str(n))
    if not nums:
        print("  Logged in but no accounts came back. Is the account funded/open?")
        return 1
    if len(nums) == 1:
        acct = nums[0]
        print("  One account found: %s" % acct)
    else:
        print("\n  Accounts on this login:")
        for i, n in enumerate(nums, 1):
            print("    %d) %s" % (i, n))
        pick = input("  Which one should the bot use? [1]: ").strip() or "1"
        try:
            acct = nums[int(pick) - 1]
        except Exception:                               # noqa: BLE001
            print("  Not a valid choice. Nothing changed.")
            return 1
    cli.account_id = acct

    # --- write settings (username + token + account ONLY) -----------------
    tt["username"] = user
    tt["account_id"] = acct
    if remember:
        tt["remember_token"] = remember
    tt.pop("password", None)          # make sure a password never lingers
    tt.setdefault("sandbox", False)   # tastytrade's cert env needs its OWN
                                      # credentials; a live login won't work
                                      # there, so verify against live (the
                                      # checks below are all read-only).
    # settings.json holds EVERY key this machine owns. Never rewrite it in
    # place — a half-written file would take the Webull keys down with it.
    # Back it up, write a temp alongside, verify the temp parses, then swap.
    try:
        import shutil
        bak = SETTINGS + ".bak"
        shutil.copy2(SETTINGS, bak)
        tmp = SETTINGS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, encoding="utf-8") as f:           # prove it re-reads
            json.load(f)
        os.replace(tmp, SETTINGS)                        # atomic on Windows
        print("\n  Saved to settings.json: username, account, remember token.")
        print("  NOT saved: your password.")
        print("  (a backup of the previous settings is at settings.json.bak)")
    except Exception as e:                              # noqa: BLE001
        print("  Could not write settings.json: %s" % e)
        print("  Nothing was changed — the original file is intact.")
        return 1

    # --- read-only verification ------------------------------------------
    print("\n  Running the read-only checklist (places NOTHING):\n")
    try:
        for name, good, detail in cli.verify():
            mark = "  ok  " if good else ("  ??  " if good is None else " FAIL ")
            print("   %s %-22s %s" % (mark, name, detail))
    except Exception as e:                              # noqa: BLE001
        print("   verify() blew up: %s" % str(e)[:200])

    print("\n" + "=" * 66)
    print("  DONE. The bot is STILL trading Webull — nothing was switched.")
    print("  execution.broker is untouched on purpose.")
    print()
    print("  Send Claude the checklist above (it contains no secrets) and he")
    print("  will pin any response that differs from the documented shape.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
