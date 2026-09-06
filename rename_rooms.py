"""rename_rooms.py — put each room's REAL Discord name into rooms.txt.

Run it:  python rename_rooms.py            (show what would change)
         python rename_rooms.py --write    (actually change it)

WHY (9/4/26)
------------
G: "I rather every single channel have its original name, not like Platinum
two, three or four. So when I go to the Discord, I know which channel we're
talking about."

rooms.txt's third column is a hand-written label. Over time those drifted
into placeholders — Platinum-1, Vero 2, Boka 3 — that match nothing a human
sees in Discord, and nothing the alert itself is tagged with. That made the
popup's new click-to-jump unable to connect a caller to their tab, and made
the logs harder to read than they needed to be.

The extension has always known the real names: it reads the channel header on
every attach. It now reports them to the bridge (POST /channames), which
saves them to chan_names.json. This script copies them into rooms.txt.

SAFE BY CONSTRUCTION
  * Only column 3 (the label) is ever touched. Channel id, URL and group are
    copied through byte-for-byte, so nothing about WHICH rooms trade changes.
  * Commented-out lines are left alone — a retired room stays retired.
  * Dry run by default. Nothing is written without --write.
  * Writes atomically via a temp file, after a .bak, so a crash mid-write
    cannot leave rooms.txt half-formed — that file decides what trades.
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOMS = os.path.join(HERE, "extension", "rooms.txt")
NAMES = os.path.join(HERE, "chan_names.json")


def clean(name):
    """Discord names carry decoration: '👑│nitro', '◽︱all-trades-mashup'.
    Strip the emoji and separator bars but KEEP the words, because the words
    are what he recognises. Leaves plain names untouched."""
    s = str(name or "")
    s = re.sub(r"[|｜│︱]+", " ", s)                 # the separator bars
    s = "".join(c for c in s if c.isascii() and (c.isalnum() or c in " -_&.'"))
    return re.sub(r"\s+", " ", s).strip()


def main():
    write = "--write" in sys.argv
    try:
        names = json.load(open(NAMES, encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        print("""No chan_names.json yet.

  The extension reports channel names to the bridge as it reads rooms, but
  only every 10 minutes and only for rooms it has attached to. So:
    1. make sure the bridge is running and the room tabs are open
    2. give it ten minutes (or reload the extension to force an attach)
    3. run this again""")
        return 1

    out, changes = [], []
    for raw in open(ROOMS, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            out.append(line)                    # comments and retired rooms
            continue
        parts = line.split("|")
        if len(parts) < 3:
            out.append(line)
            continue
        cid = parts[0].strip()
        real = clean(names.get(cid))
        old = parts[2].strip()
        if real and real.lower() != old.lower():
            changes.append((cid, old, real))
            parts[2] = real
            out.append("|".join(parts))
        else:
            out.append(line)

    if not changes:
        print("Every room already carries its real name. Nothing to do.")
        return 0

    print("%d room(s) would be renamed:\n" % len(changes))
    for cid, old, real in changes:
        print("   %-20s %-24s ->  %s" % (cid, old, real))

    if not write:
        print("\nDry run. Nothing was changed. Re-run with --write to apply.")
        return 0

    shutil.copy2(ROOMS, ROOMS + ".bak")
    tmp = ROOMS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    # prove the result still parses as a room list before swapping it in
    live = 0
    for line in open(tmp, encoding="utf-8"):
        t = line.strip()
        if t and not t.startswith("#") and len(t.split("|")) >= 3:
            live += 1
    if live < 1:
        os.remove(tmp)
        print("\nRefused to write: the result had no live rooms in it.")
        return 1
    os.replace(tmp, ROOMS)
    print("\nWritten. %d live rooms still listed. Backup at rooms.txt.bak" % live)
    print("Reload the extension so it picks up the new labels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
