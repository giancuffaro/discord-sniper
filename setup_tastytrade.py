"""SETUP TASTYTRADE (rewritten 9/4/26) — OAuth. Your password is never asked
for, never typed, never stored.

Run it:  double-click "SETUP TASTYTRADE.bat"   (or: python setup_tastytrade.py)

BEFORE YOU RUN THIS, do these once in your browser, signed into tastytrade:

  1. Go to  my.tastytrade.com  ->  Manage  ->  API Access
     ->  OAuth Applications  ->  create a new application.
     Tick the scopes you want (read, trade, openid), and put
        http://localhost:8000
     as the callback URL.
     ** COPY THE CLIENT SECRET. It is shown ONCE and never again. **

  2. On that same application:  Manage  ->  Create Grant.
     ** COPY THE REFRESH TOKEN. **

Then run this and paste those two strings. That is the whole setup — refresh
tokens never expire, so you do it once and never again.

WHY THIS IS BETTER THAN THE OLD PASSWORD FLOW
  Your account password stays yours. Nothing here can log into your account
  as you; a refresh token only does what its scopes allow and can be revoked
  from your tastytrade account at any time without changing your password.

WHAT THIS DOES NOT DO
  It never places, cancels or modifies an order. It never flips the bot over
  to tastytrade — `execution.broker` is deliberately left as it is, so the
  machine keeps trading Webull exactly as before until you decide otherwise.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SETTINGS = os.path.join(HERE, "settings.json")


def ask(prompt):
    """Read a value. These are pasted, not typed, so they are shown — you
    need to SEE that a long paste landed intact. Nothing is echoed to any log
    and nothing but settings.json (gitignored) ever holds them."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def main():
    print("=" * 70)
    print("  CONNECT TASTYTRADE — OAuth, read-only checks")
    print("=" * 70)
    print("  No password is asked for here. If you have not made the OAuth")
    print("  application yet, close this and follow the steps at the top of")
    print("  setup_tastytrade.py (or just ask Claude to walk you through it).")
    print()

    try:
        cfg = json.load(open(SETTINGS, encoding="utf-8"))
    except Exception as e:                              # noqa: BLE001
        print("  Could not read settings.json (%s). Nothing changed." % e)
        return 1

    tt = cfg.setdefault("execution", {}).setdefault("tastytrade", {})

    have_secret = bool(tt.get("client_secret"))
    have_refresh = bool(tt.get("refresh_token"))
    secret = ask("  CLIENT SECRET%s: "
                 % (" [keep the saved one — press Enter]" if have_secret else ""))
    if not secret:
        secret = tt.get("client_secret") or ""
    refresh = ask("  REFRESH TOKEN%s: "
                  % (" [keep the saved one — press Enter]" if have_refresh else ""))
    if not refresh:
        refresh = tt.get("refresh_token") or ""

    if not secret or not refresh:
        print("\n  Need both the client secret and the refresh token.")
        print("  Nothing was changed.")
        return 1

    # --- log in with them BEFORE writing anything -------------------------
    try:
        from tastytrade import TastytradeOptions
        cli = TastytradeOptions(client_secret=secret, refresh_token=refresh,
                                sandbox=bool(tt.get("sandbox", False)))
        print("\n  Exchanging the refresh token for an access token ...")
        cli._session()                                  # noqa: SLF001
    except Exception as e:                              # noqa: BLE001
        print("  FAILED: %s" % str(e)[:220])
        print("\n  Nothing was written. Most likely causes:")
        print("   - the client secret or refresh token was truncated on paste")
        print("   - the grant was made on a DIFFERENT OAuth application")
        print("   - the account is not yet approved for options")
        return 1
    print("  OK — got an access token. (They last 15 minutes and refresh")
    print("      themselves; the refresh token never expires.)")

    # --- which account ----------------------------------------------------
    try:
        accts = cli.accounts()
    except Exception as e:                              # noqa: BLE001
        print("  Could not list accounts: %s" % str(e)[:160])
        print("  Check that the OAuth application has a READ scope ticked.")
        return 1
    nums = []
    for a in accts:
        n = a.get("account-number") or a.get("account_number")
        if n:
            nums.append(str(n))
    if not nums:
        print("  Authenticated, but no accounts came back. Is it funded/open?")
        return 1
    if len(nums) == 1:
        acct = nums[0]
        print("  One account found: %s" % acct)
    else:
        print("\n  Accounts on this login:")
        for i, n in enumerate(nums, 1):
            print("    %d) %s" % (i, n))
        pick = ask("  Which one should the bot use? [1]: ") or "1"
        try:
            acct = nums[int(pick) - 1]
        except Exception:                               # noqa: BLE001
            print("  Not a valid choice. Nothing changed.")
            return 1
    cli.account_id = acct

    # --- write settings ---------------------------------------------------
    tt["client_secret"] = secret
    tt["refresh_token"] = refresh
    tt["account_id"] = acct
    tt.setdefault("sandbox", False)
    for dead in ("password", "remember_token"):
        tt.pop(dead, None)      # the password flow is retired — leave nothing
    # settings.json holds EVERY key this machine owns. Never rewrite it in
    # place — a half-written file would take the Webull keys down with it.
    # Back it up, write a temp alongside, verify the temp parses, then swap.
    try:
        import shutil
        shutil.copy2(SETTINGS, SETTINGS + ".bak")
        tmp = SETTINGS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, encoding="utf-8") as f:           # prove it re-reads
            json.load(f)
        os.replace(tmp, SETTINGS)                        # atomic on Windows
        print("\n  Saved to settings.json: client secret, refresh token, account.")
        print("  NOT saved (never asked for): your password.")
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

    print("\n" + "=" * 70)
    print("  DONE. The bot is STILL trading Webull — nothing was switched.")
    print("  execution.broker is untouched on purpose.")
    print()
    print("  Send Claude the checklist above. It contains NO secrets — just")
    print("  your account number, buying power, and which checks passed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
