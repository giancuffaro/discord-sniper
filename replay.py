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


NEW_DAY = "\x00NEWDAY"     # sentinel, never a real line


def author_of(line):
    """Who posted it. "Brett (Admin) — 9:42 AM In NVDA..." says so outright;
    a scribe-relayed "Unraveller is in SPY..." says it inside the sentence.
    Needed because a bare trim from Brett has to close Brett's position, not
    whatever else happens to be open."""
    m = sigmod.RE_HDR.match(line.strip())
    if m and m.groupdict().get("who"):
        return m.group("who").strip()
    m = sigmod.RE_CALLER.search(line)
    return (m.group(1).strip() if m else "")


def main():
    cfg = load_cfg()
    args = sys.argv[1:]
    if "--trim" in args:
        cfg["trim_action"] = args[args.index("--trim") + 1]
    if "--pct" in args:
        cfg["close_at_trim_pct"] = float(args[args.index("--pct") + 1])
    # What you could actually have afforded. Their 3.77 fill is $377 of your
    # money, and on a small account that decides more trades than the parser
    # does. --cash 0 turns the check off.
    cash = cfg.get("execution", {}).get("dry_run_buying_power")
    if "--cash" in args:
        cash = float(args[args.index("--cash") + 1])
    # a replay is about the parser and the position logic, not the clock
    cfg.setdefault("guards", {})
    cfg["guards"] = dict(cfg["guards"])
    cfg["guards"]["regular_hours_only"] = False
    cfg["guards"]["max_message_age_seconds"] = 0
    cfg["guards"]["cooldown_seconds"] = 0
    cfg["guards"].setdefault("max_trades_per_day", 12)

    # samples.txt holds more than one trading day. A line of dashes in a comment
    # marks the join between them, and that has to reset the day — otherwise the
    # second day's entries get refused for hitting a limit the first day used up,
    # and you'd never see how they actually parse.
    lines = []
    with open(os.path.join(HERE, "samples.txt"), encoding="utf-8") as f:
        for l in f:
            l = l.rstrip("\n")
            if l.startswith("#"):
                # A banner is usually dashes, then some prose, then dashes
                # again. That's one join, not two.
                if set(l.strip("# ")) == {"-"} and (not lines or lines[-1] is not NEW_DAY):
                    lines.append(NEW_DAY)
                continue
            if l.strip():
                lines.append(l)

    g = Guards(cfg, here="/tmp/__replay_no_stop__")
    fired, skipped, prepared, broke, quiet = [], [], [], [], 0

    print("%sTrim setting: %s%s%s\n" % (D, cfg.get("trim_action", "ignore"),
          "" if cfg.get("trim_action") != "at_pct"
          else " at %g%%" % float(cfg.get("close_at_trim_pct", 50)), OFF))

    for i, line in enumerate(lines, 1):
        if line is NEW_DAY:
            # New session: the daily counter goes back to zero and you start
            # flat, same as the real thing at 9:30 the next morning.
            g._count, g._last_fire, g._recent = 0, 0.0, {}
            g.open_pos = {}
            g.loaded = {}
            print("%s%s new trading day %s%s" % (D, "-" * 12, "-" * 40, OFF))
            continue
        s = sigmod.parse(line, cfg=cfg)
        who = author_of(line)
        # A trim that named no ticker gets one here, from what's open and who
        # opened it. Nothing else can do this — the parser never sees positions.
        if getattr(s, "needs_position", False):
            s = g.resolve_symbol(s, who)
        # "Filled 3.95 starters" — the price came in its own message and the
        # contract was in the LOADING notice before it.
        if getattr(s, "needs_loaded", False):
            s = g.resolve_loaded(s, who)
        # "added to SPY, new avg 2.8" — a second contract on something you're
        # already in, and only if you turned averaging on.
        if getattr(s, "needs_add", False):
            s = g.resolve_add(s, who)
        short = sigmod.clean_text(line)[:64]
        if s.action == "PREPARE":
            g.remember_loading(s, who)
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
        ok, why = g.check(s, chan, 2, who or "HoneyDrip", msg_epoch=time.time())
        if not ok:
            skipped.append((s, why))
            print("%s%3d SKIP    %-26s%s %s%s%s" % (R, i, s.human(), OFF, D, why[:60], OFF))
            continue
        # Last brake, and the one that stops most of these on a small account.
        # Deliberately after the guards, because that's the real order too: a
        # trade already refused for being out of hours was never a money
        # question.
        if cash and s.action in ("OPEN", "ADD") and s.limit:
            from webull_options import affordability
            _c, afford, why = affordability(s.limit, s.qty or 1, cash)
            if not afford:
                broke.append((s, why))
                print("%s%3d NO CASH %-26s%s %s%s%s"
                      % (R, i, s.human(), OFF, D, why[:58], OFF))
                continue
        g.record(s, who)
        fired.append(s)
        col = G if s.action in ("OPEN", "ADD") else B
        print("%s%3d %-7s %-26s%s %s%s%s" % (col, i, s.action, s.human(), OFF, D, short, OFF))
        if s.warn:
            print("       %s! %s%s" % (Y, s.warn, OFF))

    print("\n%s%d lines: %d orders, %d get-ready notices, %d blocked by the "
          "brakes, %d ignored as chatter.%s"
          % (D, sum(1 for l in lines if l is not NEW_DAY), len(fired),
             len(prepared), len(skipped), quiet, OFF))
    opens = [s for s in fired if s.action == "OPEN"]
    closes = [s for s in fired if s.action == "CLOSE"]
    adds = [s for s in fired if s.action == "ADD"]
    print("%sEntries: %s%s" % (D, ", ".join(s.human()[5:] for s in opens) or "none", OFF))
    print("%sExits:   %s%s" % (D, ", ".join(s.human()[6:] for s in closes) or "none", OFF))
    if adds:
        print("%sAdded:   %s%s" % (D, ", ".join(s.human()[4:] for s in adds), OFF))
    if cash:
        print("%sBuying power: $%.0f. %s%s"
              % (D, float(cash),
                 "Everything they called was affordable." if not broke
                 else "%d entr%s skipped for cost — the cheapest one you missed "
                      "was $%.0f." % (len(broke), "y was" if len(broke) == 1
                                      else "ies were",
                                      min(float(s.limit) * 100 * (s.qty or 1)
                                          for s, _ in broke)),
                 OFF))
    if g.open_pos:
        print("%sStill open at the end: %s — the room never called an exit on "
              "these.%s" % (R, ", ".join(g.open_pos), OFF))


if __name__ == "__main__":
    main()
