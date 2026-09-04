"""SETUP TRADIER (9/4/26) — paste one access token, get a read-only checklist.

Run it:  double-click "SETUP TRADIER.bat"   (or: python setup_tradier.py)

BEFORE YOU RUN THIS
  FUND THE ACCOUNT FIRST. Tradier's own API page says it plainly:

      "If your account is unfunded for more than 60 days your API access
       will be revoked. Once funded, you will need to regenerate your API
       keys to regain access."

  So a token generated while the account is empty is a token you will have
  to throw away and make again. Fund it, THEN generate, once.

WHERE THE TOKEN COMES FROM
  web.tradier.com -> (your name, top right) -> API Access
  -> "Generate Production Key"  ->  copy the token.

  Generating that key is you ACCEPTING TRADIER'S API AGREEMENT — it says so
  on the button's own panel. That is yours to accept, nobody else's, which
  is why this script cannot and will not press it for you.

  Tradier tokens do NOT expire until you regenerate them. Regenerating
  invalidates the old one, so if this ever stops working, generate a fresh
  key and run this again.

WHAT THIS DOES NOT DO
  It never places, cancels or modifies an order. It never flips the bot over
  to Tradier — `execution.broker` is deliberately left as it is, so the
  machine keeps trading Webull exactly as before until you decide otherwise.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SETTINGS = os.path.join(HERE, "settings.json")


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def main():
    print("=" * 70)
    print("  CONNECT TRADIER — read-only setup")
    print("=" * 70)
    print("  Fund the account BEFORE generating a key — Tradier revokes API")
    print("  access on accounts left unfunded, and you would have to make the")
    print("  key twice. Nothing here places an order or switches the bot.")
    print()

    try:
        cfg = json.load(open(SETTINGS, encoding="utf-8"))
    except Exception as e:                              # noqa: BLE001
        print("  Could not read settings.json (%s). Nothing changed." % e)
        return 1

    tr = cfg.setdefault("execution", {}).setdefault("tradier", {})
    have = bool(tr.get("access_token"))
    tok = ask("  ACCESS TOKEN%s: "
              % (" [keep the saved one — press Enter]" if have else ""))
    if not tok:
        tok = tr.get("access_token") or ""
    if not tok:
        print("  No token given. Nothing changed.")
        return 1

    sandbox = (ask("  Is this a SANDBOX token? [y/N]: ").lower()
               .startswith("y"))

    # --- prove it works BEFORE writing anything ---------------------------
    try:
        from tradier import TradierOptions
        cli = TradierOptions(tok, tr.get("account_id") or "", sandbox=sandbox)
        print("\n  Asking Tradier who this token belongs to ...")
        acct = cli.connect()
    except Exception as e:                              # noqa: BLE001
        print("  FAILED: %s" % str(e)[:220])
        print("\n  Nothing was written. Most likely causes:")
        print("   - the token was truncated on paste")
        print("   - it is a SANDBOX token and you answered N (or vice versa)")
        print("   - the account is unfunded and API access was revoked")
        print("     -> fund it, regenerate the key, run this again")
        return 1
    print("  OK — token works. Account: %s" % acct)

    # --- write settings ---------------------------------------------------
    tr["access_token"] = tok
    tr["account_id"] = str(acct)
    tr["sandbox"] = bool(sandbox)
    # settings.json holds EVERY key this machine owns. Never rewrite it in
    # place — a half-written file would take the Webull keys down with it.
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
        print("\n  Saved to settings.json: access token, account, sandbox flag.")
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
