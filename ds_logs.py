"""DS Logs — the extension's room-chat exports, one file per WEEK per lane.

ONE FILE PER WEEK PER LANE (9/15, G: "make them weekly"). The exports used to
be one file per ET day per lane, and every one of them re-wrote the whole
retained backlog: 9/13 discord was 8.6 MB and 9/14 was 10 MB of overwhelmingly
the same messages. Now a week is one file --

    signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt

-- and each capture day appends its OWN NEW LINES under a day header:

    ===== Mon Sep 14 2026 =====

A day's block holds only what the earlier days of that same file do not
already hold; re-exporting the same day REPLACES that day's block instead of
stacking a second header. Week runs Monday..Sunday, day boundary Eastern.

The pre-9/10 untagged dailies (`signal-room-chat Aug-18-2026.txt` ..
`Sep-10-2026.txt`) predate the lane split and are NOT merged; every reader
here still finds them.
"""
import glob
import os
import re
from datetime import date, datetime, timedelta

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

LANES = ("discord", "whop")

# "===== Mon Sep 14 2026 ====="
DAY_HEADER_RE = re.compile(
    r"^=====\s+(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(\d{1,2})\s+(\d{4})\s+=====\s*$")

# "signal-room-chat week-of-Sep-14-to-Sep-20-2026 (discord).txt" and the
# year-boundary spelling "week-of-Dec-29-2025-to-Jan-4-2026".
WEEKLY_NAME_RE = re.compile(
    r"^signal-room-chat week-of-"
    r"([A-Z][a-z]{2})-(\d{1,2})(?:-(\d{4}))?-to-"
    r"([A-Z][a-z]{2})-(\d{1,2})-(\d{4})"
    r"(?: \(([a-z]+)\))?\.txt$")

# The legacy one-file-per-day name, with or without the lane tag.
DAILY_NAME_RE = re.compile(
    r"^signal-room-chat ([A-Z][a-z]{2}-\d{1,2}-\d{4})"
    r"(?: \(([a-z]+)\))?\.txt$")

# A message line's stable source id, when the capture had one.
MESSAGE_ID_RE = re.compile(r" message_id=([^\]\s]+)\]")


# ---- naming ---------------------------------------------------------------

def week_bounds(day):
    """The Monday and Sunday of ``day``'s week."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def week_tag(day):
    """``week-of-Sep-14-to-Sep-20-2026``.

    A week that straddles New Year carries both years so the name can never
    be read two ways: ``week-of-Dec-29-2025-to-Jan-4-2026``.
    """
    mon, sun = week_bounds(day)
    start = "%s-%d" % (MONTHS[mon.month - 1], mon.day)
    if mon.year != sun.year:
        start += "-%d" % mon.year
    return "week-of-%s-to-%s-%d-%d" % (
        start, MONTHS[sun.month - 1], sun.day, sun.year)


def weekly_name(day, lane):
    """The file ``day``'s capture belongs in, for ``lane``."""
    return "signal-room-chat %s (%s).txt" % (week_tag(day), lane)


def day_header(day):
    return "===== %s %s %d %d =====" % (
        WEEKDAYS[day.weekday()], MONTHS[day.month - 1], day.day, day.year)


def parse_day_header(line):
    m = DAY_HEADER_RE.match(line)
    if not m:
        return None
    return date(int(m.group(4)), MONTHS.index(m.group(2)) + 1, int(m.group(3)))


def week_of_name(name):
    """(monday, sunday, lane) for a weekly file name, else None."""
    m = WEEKLY_NAME_RE.match(os.path.basename(name))
    if not m:
        return None
    smon, sday, syear, emon, eday, eyear, lane = m.groups()
    end = date(int(eyear), MONTHS.index(emon) + 1, int(eday))
    start = date(int(syear or eyear), MONTHS.index(smon) + 1, int(sday))
    return start, end, (lane or "")


def day_of_name(name):
    """The ISO day a legacy per-day export covers, else None."""
    m = DAILY_NAME_RE.match(os.path.basename(name))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%b-%d-%Y").date().isoformat()
    except ValueError:
        return None


# ---- the file as day blocks ------------------------------------------------

def _section_kind(head):
    h = head.upper()
    for prefix, kind in (("CURRENT STATE", "state"),
                         ("RAW MESSAGES", "raw"),
                         ("LIVE PARSER INPUTS", "parser"),
                         ("WHAT THE BOT DID", "did")):
        if h.startswith(prefix):
            return kind
    return "other:" + h


def line_key(kind, line):
    """What makes two exported lines the same record.

    Message id when the capture carried one (DATA-MAP's identity rule), with
    the body alongside so an edited message is never silently dropped;
    otherwise the whole line, which already spells out timestamp, room and
    text. Keys never cross section kinds: LIVE PARSER INPUTS is a second view
    of a RAW message, not a duplicate of it.
    """
    m = MESSAGE_ID_RE.search(line)
    if m and m.group(1) != "legacy-unknown":
        body = line.split("]  ", 1)[1] if "]  " in line else line
        return (kind, "id", m.group(1), body)
    return (kind, "line", line)


def split_sections(text):
    """[(header_line, [body lines])] — text before the first ``=== `` header
    is returned under the header ``None``."""
    out = [(None, [])]
    for ln in text.replace("\r\n", "\n").split("\n"):
        if ln.startswith("=== ") and ln.rstrip().endswith(" ==="):
            out.append((ln.rstrip(), []))
        else:
            out[-1][1].append(ln)
    return out


def split_day_blocks(text):
    """[(date, [lines])] for a weekly file, in file order. Lines before the
    first day header (the preamble) are dropped."""
    blocks = []
    cur = None
    for ln in (text or "").replace("\r\n", "\n").split("\n"):
        day = parse_day_header(ln)
        if day is not None:
            cur = (day, [])
            blocks.append(cur)
        elif cur is not None:
            cur[1].append(ln)
    return blocks


def _dedupe_block(lines, seen):
    """Strip every line already in ``seen``; add what survives. Returns
    (kept lines, {kind: dropped count})."""
    dropped = {}
    out = []
    for head, body in split_sections("\n".join(lines)):
        kind = _section_kind(head[4:-4].strip()) if head else None
        if head is None:
            out.extend(body)
            continue
        if kind == "state" or str(kind).startswith("other:"):
            out.append(head)
            out.extend(body)
            continue
        kept = []
        for ln in body:
            if not ln.strip():
                continue
            key = line_key(kind, ln)
            if key in seen:
                dropped[kind] = dropped.get(kind, 0) + 1
                continue
            seen.add(key)
            kept.append(ln)
        # The count in the header is the count of what is in THIS block.
        out.append(re.sub(r" \(\d+\) ===$", " (%d) ===" % len(kept), head))
        out.extend(kept)
        out.append("")
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out, dropped


def preamble(monday, sunday, lane):
    return [
        "Discord Sniper — weekly room-chat export, %s %s %d %d to %s %s %d %d"
        " (%s lane)" % (
            WEEKDAYS[monday.weekday()], MONTHS[monday.month - 1], monday.day,
            monday.year, WEEKDAYS[sunday.weekday()], MONTHS[sunday.month - 1],
            sunday.day, sunday.year, lane or "?"),
        "Every day below holds only that day's NEW lines; nothing earlier in"
        " this file is repeated.",
        "",
    ]


def merge_day(existing_text, day, export_text, lane=""):
    """Put ``export_text`` (one day's export) into the weekly file body.

    The day's own block is REPLACED, never stacked. Every block is then
    re-deduped against the blocks before it, so the result is the same
    whether the day was exported once or twenty times, and the earliest
    day that held a line is the day that keeps it.

    Returns (new_text, {day_iso: {section: dropped_count}}).
    """
    blocks = [(d, ls) for d, ls in split_day_blocks(existing_text) if d != day]
    blocks.append((day, (export_text or "").replace("\r\n", "\n").split("\n")))
    blocks.sort(key=lambda b: b[0])

    mon, sun = week_bounds(day)
    seen = set()
    stats = {}
    out = preamble(mon, sun, lane)
    for d, lines in blocks:
        kept, dropped = _dedupe_block(lines, seen)
        stats[d.isoformat()] = dropped
        out.append(day_header(d))
        out.append("")
        out.extend(kept)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n", stats


# ---- what the readers ask for ---------------------------------------------

def logs_dir(root):
    return os.path.join(root, "DS Logs")


def export_files(root):
    """Every room-chat export: the weekly files and the legacy dailies."""
    return sorted(glob.glob(os.path.join(logs_dir(root),
                                         "signal-room-chat*.txt")))


def days_covered(path):
    """Every ISO day a room-chat export holds, from its day headers, falling
    back to the day in a legacy per-day file name."""
    days = set()
    week = week_of_name(path)
    if week or os.path.basename(path).startswith("signal-room-chat week-of-"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    d = parse_day_header(ln.rstrip("\n"))
                    if d is not None:
                        days.add(d.isoformat())
        except OSError:
            pass
        return days
    one = day_of_name(path)
    if one:
        days.add(one)
    return days


def files_for_day(root, day):
    """Every export holding ``day`` (ISO string): the weekly file of each
    lane, or the legacy per-day files when that is all we have.

    Lane-split files are the authoritative independent snapshots, so when a
    legacy unsuffixed daily sits beside them it is not counted twice.
    """
    weekly, legacy = [], []
    for f in export_files(root):
        if day in days_covered(f):
            (weekly if week_of_name(f) else legacy).append(f)
    if weekly:
        return weekly
    if legacy:
        split = [f for f in legacy
                 if re.search(r" \((discord|whop)\)\.txt$", f)]
        return split or legacy
    found = []
    for f in export_files(root):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                if any(ln.startswith(day + " ") for ln in fh):
                    found.append(f)
        except OSError:
            continue
    return found


def all_days(root):
    """Every ISO day any export covers, sorted."""
    days = set()
    for f in export_files(root):
        days |= days_covered(f)
    return sorted(days)
