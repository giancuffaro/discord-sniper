"""
replay.py — run a whole session through the bot, in order, with the brakes on.

tune.py judges lines one at a time. This runs them as a session: the position
tracker remembers what you're holding, the daily cap counts down, duplicate
calls get caught. It's the closest thing to watching the bot trade a day
without any money being involved.

    python replay.py                       (uses samples.txt)
    python replay.py --trim close          (exit on their first trim)
    python replay.py --trim at_pct --pct 50
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import signals as sigmod
from guards import Guards

G, R, Y, B, D, OFF = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                      "\033[90m", "\033[0m")


def load_cfg():
    for n in ("settings.json", "settings.example.json"):
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def main():
    cfg = load_cfg()
    args = sys.argv[1:]
    if "--trim" in args:
        cfg["trim_action"] = args[args.index("--trim") + 1]
    if "--pct" in args:
        cfg["close_at_trim_pct"] = float(args[args.index("--pct") + 1])
    # a replay is about the parser and the position logic, not the clock
    cfg.setdefault("guards", {})
    cfg["guards"] = dict(cfg["guards"])
    cfg["guards"]["regular_hours_only"] = False
    cfg["guards"]["max_message_age_seconds"] = 0
    cfg["guards"]["cooldown_seconds"] = 0
    cfg["guards"].setdefault("max_trades_per_day", 12)

    with open(os.path.join(HERE, "samples.txt"), encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f
                 if l.strip() and not l.startswith("#")]

    g = Guards(cfg, here="/tmp/__replay_no_stop__")
    fired, skipped, prepared, quiet = [], [], [], 0

    print("%sTrim setting: %s%s%s\n" % (D, cfg.get("trim_action", "ignore"),
          "" if cfg.get("trim_action") != "at_pct"
          else " at %g%%" % float(cfg.get("close_at_trim_pct", 50)), OFF))

    for i, line in enumerate(lines, 1):
        s = sigmod.parse(line, cfg=cfg)
        short = sigmod.clean_text(line)[:64]
        if s.action == "PREPARE":
            prepared.append(s)
            print("%s%3d READY   %-26s%s %s%s%s" % (Y, i, s.human()[8:], OFF, D, short, OFF))
            continue
        if not s.fire:
            if s.action:
                print("%s%3d hold    %-26s%s %s%s%s" % (D, i, (s.symbol or ""), OFF, D, s.why[:60], OFF))
            else:
                quiet += 1
            continue
        chan = (cfg.get("channel_ids") or ["1"])[0]
        ok, why = g.check(s, chan, 2, "HoneyDrip", msg_epoch=time.time())
        if not ok:
            skipped.append((s, why))
            print("%s%3d SKIP    %-26s%s %s%s%s" % (R, i, s.human(), OFF, D, why[:60], OFF))
            continue
        g.record(s)
        fired.append(s)
        col = G if s.action == "OPEN" else B
        print("%s%3d %-7s %-26s%s %s%s%s" % (col, i, s.action, s.human(), OFF, D, short, OFF))
        if s.warn:
            print("       %s! %s%s" % (Y, s.warn, OFF))

    print("\n%s%d lines: %d orders, %d get-ready notices, %d blocked by the "
          "brakes, %d ignored as chatter.%s"
          % (D, len(lines), len(fired), len(prepared), len(skipped), quiet, OFF))
    opens = [s for s in fired if s.action == "OPEN"]
    closes = [s for s in fired if s.action == "CLOSE"]
    print("%sEntries: %s%s" % (D, ", ".join(s.human()[5:] for s in opens) or "none", OFF))
    print("%sExits:   %s%s" % (D, ", ".join(s.human()[6:] for s in closes) or "none", OFF))
    if g.open_pos:
        print("%sStill open at the end: %s — the room never called an exit on "
              "these.%s" % (R, ", ".join(g.open_pos), OFF))


if __name__ == "__main__":
    main()
