"""
tune.py — teach the bot to read YOUR room, without risking a dollar.

Paste real messages from the signal room into samples.txt (one per line),
then run:   python tune.py

It prints how the bot reads each line: what it would fire, and for the ones it
ignores, exactly why. This is the step to get right before the bot ever sees a
live account — if a line you expect to trade comes back "ignored", the parser
needs a tweak, and that tweak costs nothing at this stage.

You can also just run it with no samples.txt and type lines by hand.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import signals as sigmod

GREEN, RED, DIM, OFF = "\033[92m", "\033[91m", "\033[90m", "\033[0m"


def cfg():
    for name in ("settings.json", "settings.example.json"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def show(line, c):
    s = sigmod.parse(line, cfg=c)
    if s.fire:
        print("%sFIRE %s%s   <- %s" % (GREEN, s.human(), OFF, line.strip()[:70]))
    else:
        print("%signored%s  %s%s%s   <- %s"
              % (RED, OFF, DIM, s.why, OFF, line.strip()[:70]))
    return s


def main():
    c = cfg()
    path = os.path.join(HERE, "samples.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip() and not l.startswith("#")]
        fired = sum(1 for l in lines if show(l, c).fire)
        print("\n%d of %d lines would have fired." % (fired, len(lines)))
        print("If that split is wrong, the fix is in signals.py — the word lists "
              "at the top and the allowed_symbols list in settings.")
        return

    print("No samples.txt found. Type message lines to test one at a time "
          "(blank line to quit).\n")
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not line.strip():
            break
        show(line, c)


if __name__ == "__main__":
    main()
