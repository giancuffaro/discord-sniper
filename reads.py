"""reads.py — show the READER TAPE: everything the ears heard and the eyes saw.

    python3 reads.py               last 60 lines, voice and vision together
    python3 reads.py --voice       spoken lines only
    python3 reads.py --vision      screenshot reads only
    python3 reads.py --calls       only lines the parser turned into an action
    python3 reads.py --misses      lines with a ticker in them that produced nothing
    python3 reads.py -n 200        more lines
    python3 reads.py --today       today only

Each line is:
    time  🎙/📸  room  speaker | what the parser made of it | what was heard/seen   [note]

The tape is written by bridge.py (reads.log): voice lines arrive from the
extension for every finalized transcript segment, vision reads are written by
the bridge itself — the call, the refusal, or the failure reason. It is for
review only; nothing in the trading path reads it.

G, 9/8: "i need to see them in order to help you analize." This is that.
Read the stream, point at a line, and say what it should have been.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "reads.log")

TICKERISH = re.compile(r"\b[A-Z]{2,5}\b|\b\d{2,5}\s*[cpCP]\b|\bcalls?\b|\bputs?\b", re.I)


def main(argv):
    n = 60
    want = None
    only_calls = only_misses = today = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-n" and i + 1 < len(argv):
            n = int(argv[i + 1]); i += 1
        elif a == "--voice":
            want = "🎙"
        elif a == "--vision":
            want = "📸"
        elif a == "--calls":
            only_calls = True
        elif a == "--misses":
            only_misses = True
        elif a == "--today":
            today = True
        i += 1
    if not os.path.exists(LOG):
        print("no reads.log yet — it fills up the first time the listener hears "
              "something or a room posts a screenshot.")
        return 0
    day = time.strftime("%Y-%m-%d")
    out = []
    with open(LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if want and (" %s " % want) not in line:
                continue
            if today and not line.startswith(day):
                continue
            parts = line.split(" | ", 2)
            verdict = parts[1].strip() if len(parts) > 1 else ""
            heard = parts[2] if len(parts) > 2 else ""
            if only_calls and verdict in ("", "-"):
                continue
            if only_misses and not (verdict in ("", "-") and TICKERISH.search(heard)):
                continue
            out.append(line)
    tail = out[-n:]
    print("reads.log — %d lines match, showing last %d\n" % (len(out), len(tail)))
    for line in tail:
        print(line)
    if only_misses and tail:
        print("\n(these had something ticker-shaped in them and produced nothing — "
              "the ones worth a second look)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
