"""
drill.py — practice the reader on a whole chat export, no money anywhere.

The extension's "Export chat" button downloads signal-room-chat.txt — every
message the extension has seen, tagged by room. This runs each line through
the exact same reader that trades and writes drill-report.txt saying what
would have happened: which lines fire, which are ignored, and exactly why.

    python drill.py signal-room-chat.txt            the whole file
    python drill.py signal-room-chat.txt midas      one room only

This is how a room's wording gets learned. Scroll far back in the channel
(the extension captures history as you scroll — history is never traded),
hit Export chat, and drill the file. Any line that reads wrong is a line for
samples.txt, and once it's there the parity tests hold it forever.

Two honest limits: the drill has no positions, so trims and all-outs show as
"would sell if holding"; and the timing guards (message age, the four-hour
loading window) don't apply to a replay — this is wording practice, not a
backtest. replay.py is the backtest.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import signals as sigmod

# "7/30/2026, 11:56:03 AM  [midas]  Midas (Admin): Filled at 1.46"
RE_LINE = re.compile(r"^(?P<when>.+?)\s\s+\[(?P<room>[^\]]*)\]\s\s+(?P<rest>.*\S)\s*$")


def contract_of(s):
    strike = getattr(s, "strike", None)
    side = getattr(s, "side", None) or ""
    bits = [getattr(s, "symbol", None),
            (("%g" % strike) + (side[:1] if side else "")) if strike is not None else None,
            getattr(s, "expiry", None)]
    return " ".join(str(b) for b in bits if b)


def verdict(s, loaded, author="?"):
    """One line: what the bot would have done with this message."""
    action = getattr(s, "action", None)
    fire = getattr(s, "fire", None)
    limit = getattr(s, "limit", None)
    pct = getattr(s, "pct", None)
    why = getattr(s, "why", "") or ""
    if action == "PREPARE":
        return "noted: " + why
    # Live, the guards finish these two shapes — a bare fill price attaches
    # to the caller's last Loaded, and a bare trim resolves to their newest
    # open position. The drill says what WOULD happen rather than "ignored".
    if getattr(s, "needs_loaded", False):
        pin = loaded.get((getattr(s, "caller", None) or author).lower())
        if pin:
            return ("WOULD FIRE: OPEN %s @ %g — their fill on the Loaded call "
                    "above" % (pin, limit)) if limit is not None else \
                   ("WOULD FIRE: OPEN " + pin + " — their fill on the Loaded "
                    "call above")
        return ("reads as their fill confirmation — live it buys whatever "
                "their last Loaded call named (none in this file yet)")
    if getattr(s, "needs_position", False) and action in ("TRIM", "CLOSE"):
        what = action + ((" (%+g%%)" % pct) if pct is not None else "")
        return ("WOULD SELL (if holding their trade): %s — live it resolves "
                "to their newest open position" % what)
    if action and fire is not False:
        what = (action + " " + contract_of(s)).strip()
        if limit is not None:
            what += " @ %g" % limit
        elif pct is not None:
            what += " (%+g%%)" % pct
        if "fill confirmation" in (getattr(s, "matched", "") or ""):
            pin = loaded.get((getattr(s, "caller", None) or author).lower())
            what += (" — pairs with their Loaded " + pin) if pin else \
                    " — live, this pairs with their last Loaded call"
        if action in ("TRIM", "CLOSE"):
            return "WOULD SELL (if holding their trade): " + what
        return "WOULD FIRE: " + what
    return "ignored: " + why


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    room_pick = None
    if args and not os.path.exists(args[-1]) and len(args) > 1:
        room_pick = args.pop().lower()
    elif len(args) == 2:
        room_pick = args.pop().lower()
    path = args[0] if args else None
    if not path:
        for cand in (os.path.join(HERE, "signal-room-chat.txt"),
                     os.path.join(os.path.expanduser("~"), "Downloads",
                                  "signal-room-chat.txt")):
            if os.path.exists(cand):
                path = cand
                break
    if not path or not os.path.exists(path):
        print("Can't find the export. Hit \"Export chat\" in the extension "
              "popup, then: python drill.py <path to signal-room-chat.txt>")
        return 1

    cfg = {"allowed_symbols": []}
    out, counts, rooms_seen = [], {}, set()
    loaded = {}       # room -> {author.lower(): "contract @ price"} for verdicts
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if not raw.strip():
                continue
            m = RE_LINE.match(raw)
            when, room, rest = (m.group("when"), m.group("room").lower(),
                                m.group("rest")) if m else ("", "?", raw.strip())
            rooms_seen.add(room)
            if room_pick and room != room_pick:
                continue
            # The export writes "Author: text" but live the reader gets the
            # text alone, author separate. Split the same way, or shapes
            # like a bare "Filled at 1.46" stop being recognisable.
            author, _, text = rest.partition(": ")
            if not text:
                author, text = "?", rest
            s = sigmod.parse(text, cfg=cfg)
            lmem = loaded.setdefault(room, {})
            if getattr(s, "action", None) == "PREPARE" and getattr(s, "symbol", None):
                lmem[(getattr(s, "caller", None) or author).lower()] = contract_of(s)
            v = verdict(s, lmem, author)
            counts[v.split(":", 1)[0]] = counts.get(v.split(":", 1)[0], 0) + 1
            out.append("[%s] %s  %s" % (room, when, rest))
            out.append("     -> " + v)
    if not out:
        want = room_pick or "anything"
        print("No lines for %r in that file. Rooms present: %s"
              % (want, ", ".join(sorted(rooms_seen)) or "none"))
        return 1

    head = ["THE DRILL — every line below went through the same reader that "
            "trades.",
            "File: %s%s" % (path, ("   room: " + room_pick) if room_pick else ""),
            "Verdicts: " + ", ".join("%s %d" % (k, v)
                                     for k, v in sorted(counts.items())),
            "A line that reads wrong is exactly what I need — send this "
            "report back.", ""]
    report = os.path.join(HERE, "drill-report.txt")
    with io.open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(head + out) + "\n")
    print("Read %d lines. %s" % (len(out) // 2,
          "  ".join("%s: %d" % (k, v) for k, v in sorted(counts.items()))))
    print("The whole report: " + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
