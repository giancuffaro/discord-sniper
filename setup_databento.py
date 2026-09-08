"""
setup_databento.py — puts your Databento API key into settings.json.

One job only: paste the key from databento.com/dashboard into
execution.databento.api_key. This is a HISTORICAL backfill key — it never
places an order, never watches anything live, and nothing about live trading
changes because of it. It only fills in real OPRA option prices so the
ratchet/anti-clip study can run on real fills instead of modelled ones.

Nothing typed here leaves your PC. settings.json is in .gitignore, so it is
never committed and an update never overwrites it.
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


def main():
    cfg = load()
    ex = cfg.setdefault("execution", {})
    db = ex.setdefault("databento", {})

    print("=" * 62)
    print("  DISCORD SNIPER — Databento key")
    print("=" * 62)
    print("Get this from databento.com -> your dashboard -> API keys.")
    print("Right-click in this window pastes.")
    print("Press Enter with nothing typed to keep what's already saved.")
    print()

    current = db.get("api_key", "")
    shown = " [keep %s]" % mask(current) if current else ""
    typed = input("API Key%s: " % shown).strip()
    db["api_key"] = typed or current

    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(PATH, 0o600)
    except OSError:
        pass

    print()
    print("Saved to settings.json.")
    print("  key   %s" % (mask(db.get("api_key", "")) or "(none saved)"))
    print()
    print("Your key is on this screen — close the window when you're done.")


if __name__ == "__main__":
    main()
