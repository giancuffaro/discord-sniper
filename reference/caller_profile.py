#!/usr/bin/env python3
"""caller_profile.py - how do the callers actually trade?

G, 9/14: "what is the callers' average trade hold time, because we need to
match that to get similar results - I'm even happy getting to the first trim.
What's their normal stop also?"

This answers that from the recovered room record only.  It is MEASUREMENT:
it reads CSVs, writes two files into reference/, and touches nothing live.

SOURCES (read-only)
  recovered_alerts_chat.csv    entries + management posts; `links_to` ties a
                               trim/exit/add back to its entry.  high+medium
                               confidence only, 2026-08-03 .. 2026-09-10.
  daily-reports/CALLER-OUTCOMES-2026-09-11.csv
  daily-reports/CALLER-OUTCOMES-2026-09-14.csv
                               already-paired claim events for two days.
  master_ledger.csv            what WE did, for the side-by-side.
  databento_tape_clean.csv / option_tape.csv / missed_tape.csv / alert_tape.csv
                               real bids, used only to price a caller exit that
                               carries no stated percent.

RULES OF EVIDENCE (AGENTS.md)
  - a later high is NOT a caller exit;
  - a missing exit stays `unavailable`, it is never estimated;
  - a caller-stated percent is labelled `stated`; a bid from the tape at the
    caller's exit second is labelled `measured`; a percent computed from two
    prices the caller himself posted is labelled `caller-price`;
  - a price-only post with no contract is not an exit;
  - every number carries its sample size.

ONE DELIBERATE RECOVERY RULE
  Some rooms write the premium inline and the original recovery left
  `their_price` blank - e.g. VeroTrade's "QQQ 718P 8/18 1.22 2 CONTRACTS".
  `entry_price()` recovers that one shape (ticker, strike, C/P, expiry, then
  the premium) and nothing else.  Every recovered price is counted separately
  in the report so it can be discounted.
"""
from __future__ import annotations

import csv
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DATE = "2026-09-14"
WIN_LO, WIN_HI = "2026-08-03", "2026-09-10"
MIN_N = 5                      # min linked entries for a per-caller row
RUNNER_EDGE = 25.0             # pct-points beyond the first trim = "adds"

MD_PATH = os.path.join(ROOT, "reference", "CALLER-PROFILE-%s.md" % OUT_DATE)
CSV_PATH = os.path.join(ROOT, "reference", "CALLER-PROFILE-%s.csv" % OUT_DATE)


# ----------------------------------------------------------------- helpers
def rd(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def num(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def dt(ts):
    try:
        return datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def mins(a, b):
    return (b - a).total_seconds() / 60.0


def q(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return (0, None, None, None)
    if len(v) == 1:
        return (1, v[0], v[0], v[0])
    return (len(v), statistics.median(v),
            v[int(round(0.25 * (len(v) - 1)))],
            v[int(round(0.75 * (len(v) - 1)))])


def fmt(x, nd=1, suf=""):
    return "unavailable" if x is None else ("%.*f%s" % (nd, x, suf))


def qs(tup, nd=1, suf=""):
    n, m, a, b = tup
    if not n:
        return "unavailable (n=0)"
    return "%s  (p25 %s / p75 %s, n=%d)" % (fmt(m, nd, suf), fmt(a, nd, suf),
                                            fmt(b, nd, suf), n)


# ------------------------------------------------------- message classifier
FRAC = re.compile(r"\b(1/2|1/3|1/4|2/3|3/4|1/5)\b|\bhalf\b|\bquarter\b|\bthird\b", re.I)
PARTIAL = re.compile(
    r"\btrim\w*\b|\bpartial\b|\bscal(?:e|ing)\s*out\b|\btook\s+(?:some|a\s+few|profit)"
    r"|\b(?:few|some)\s+(?:more\s+)?off\b|\bbook(?:ing|ed)\s+(?:some\s+)?profit"
    r"|\bleft\s+a?\s*runner|\bleaving\s+(?:a\s+)?(?:few\s+)?runner|\brunners?\s+left\b"
    r"|\bholding\s+(?:the\s+)?rest\b|\bsold\s+\d+\s*,?\s*holding\b", re.I)
FULL = re.compile(
    r"\ball\s*-?\s*out\b|\ball\s+out\s+of\b|\bclos(?:ed|ing)\b|\bstopped\b|\bstop\s+hit\b"
    r"|\bfully\s+(?:out|sold)\b|\bfull\s+(?:exit|sold|out)\b|\bout\s+of\b|\bflat\b"
    r"|\blast\s+of\b|\bsold\s+the\s+rest\b|\bremainder\b|\bout\s+runner", re.I)
# "be" is an ordinary English word - only a stop-flavoured breakeven counts.
BE = re.compile(r"\bb\s*/\s*e\b|\bbreak\s*-?\s*even\b|\bslbe\b"
                r"|\b(?:sl|stop|stops)\b[^.\n]{0,12}\bb\.?e\.?\b", re.I)
LOSS_WORD = re.compile(r"\bstopped\b|\bstop\s+hit\b|\bfor\s+a\s+loss\b|\bloss\b|\bred\b", re.I)
ALLOUT = re.compile(r"\ball\s*-?\s*out\b|\ball\s+out\s+of\b", re.I)


def classify(row):
    """partial | full | add | exit-unqualified | commentary"""
    t = (row["source_message_verbatim"] or "").replace("\n", " ")
    mt = row["msg_type"]
    if mt == "add":
        return "add"
    if mt == "commentary":
        return "commentary"
    if (FRAC.search(t) or PARTIAL.search(t)) and not ALLOUT.search(t):
        return "partial"
    if mt == "trim":
        return "partial"
    if FULL.search(t):
        return "full"
    return "exit-unqualified"


# ----------------------------------------------------------- percent parsing
SIGNED = re.compile(r"([+\-]\s?\d{1,4}(?:\.\d+)?)\s?%")
AT_PCT = re.compile(r"(?:@|\bat\b|\bfor\b|\bup\b|\bhit\b)\s*\*?\+?(\d{1,4}(?:\.\d+)?)\s?%", re.I)
ON_PCT = re.compile(r"(\d{1,4}(?:\.\d+)?)\s?%\s*(?:\+)?\s*(?:on\b|gain|winner|runner)", re.I)
TICK_PCT = re.compile(r"\btrim\w*\s+(?:more\s+)?\$?[A-Za-z]{1,6}\s+(\d{1,4}(?:\.\d+)?)\s?%", re.I)
ANY_PCT = re.compile(r"(\d{1,4}(?:\.\d+)?)\s?%")
SIZE_PCT = re.compile(r"(\d{1,3})\s?%\s*(?:of\s+(?:the\s+)?(?:position|gap)|position)"
                      r"|\btrimmed\s+(\d{1,3})\s?%", re.I)


def stated_pct(text):
    """The caller's own stated gain/loss percent, or None. Never a trim size."""
    t = (text or "").replace("\n", " ")
    m = SIGNED.search(t)
    if m:
        return num(m.group(1).replace(" ", ""))
    sizes = {g for pair in SIZE_PCT.findall(t) for g in pair if g}
    for rx in (AT_PCT, ON_PCT, TICK_PCT):
        m = rx.search(t)
        if m and m.group(1) not in sizes:
            v = num(m.group(1))
            if v is not None and v <= 3000:
                return -v if LOSS_WORD.search(t) else v
    toks = [x for x in ANY_PCT.findall(t) if x not in sizes]
    if len(toks) == 1 or (toks and t.lstrip().startswith(toks[0])):
        v = num(toks[0])
        if v is not None and v <= 3000:
            return -v if LOSS_WORD.search(t) else v
    return None


PRICE = re.compile(r"(?:@|\bat\b|\bValue:\s*@?)\s*\$?(\d{1,5}(?:\.\d+)?)(?![\w/%])", re.I)
# "QQQ 718P 8/18 1.22 2 CONTRACTS" - strike+side, expiry, then the premium.
INLINE_ENTRY = re.compile(r"\d{1,5}(?:\.\d+)?\s?[CP]\b[^\d]{0,4}\d{1,2}/\d{1,2}(?:/\d{2,4})?"
                          r"\s+\$?(\d{1,3}\.\d{1,2})\b", re.I)


def posted_price(text):
    t = (text or "").replace("\n", " ")
    m = PRICE.search(t)
    return num(m.group(1)) if m else None


def entry_price(e):
    """(price, 'posted'|'recovered'|None) - premium the caller entered at."""
    p = num(e["their_price"])
    if p:
        return p, "posted"
    if e["kind"] != "option":
        return None, None
    m = INLINE_ENTRY.search((e["source_message_verbatim"] or "").replace("\n", " "))
    if m:
        v = num(m.group(1))
        st = num(e["strike"])
        if v and 0.05 <= v <= 100 and (st is None or abs(v - st) > 1e-6):
            return v, "recovered"
    return None, None


SIZE_WORDS = [(re.compile(r"\b1/2\b|\bhalf\b", re.I), "1/2"),
              (re.compile(r"\b1/3\b|\bthird\b", re.I), "1/3"),
              (re.compile(r"\b1/4\b|\bquarter\b", re.I), "1/4"),
              (re.compile(r"\b2/3\b", re.I), "2/3"),
              (re.compile(r"\b3/4\b", re.I), "3/4"),
              (re.compile(r"\btrimmed\s+(\d{1,3})\s?%", re.I), None)]


def trim_size(text):
    t = (text or "").replace("\n", " ")
    for rx, lab in SIZE_WORDS:
        m = rx.search(t)
        if m:
            return lab or (m.group(1) + "%")
    return ""


# ------------------------------------------------- entry-message stop talk
STOP_MENTION = re.compile(r"\bSL\b|\bstop\s*loss\b|\bstop\b|\bstopped\b", re.I)
NO_STOP = re.compile(r"\bno\s+stop\s*loss\b|\bSL\s*:?\s*none\b|\bno\s+sl\b", re.I)
UNDERLYING_STOP = re.compile(r"\bS\.?L\.?\s*:?\s*(?:under|below|above|over)\b"
                             r"|\b(?:under|below|above|over)\s+\$?\d+(?:\.\d+)?\s*(?:daily|weekly)?\b"
                             r"|\busing\s+\$?\d+(?:\.\d+)?\s+as\b", re.I)
PREMIUM_STOP = re.compile(r"\bS\.?L\.?\s*:?\s*@?\s*\$?(\d{1,3}\.\d{1,2})\b", re.I)


# --------------------------------------------------------------- load chat
raw = rd("recovered_alerts_chat.csv")
seen, chat = set(), []
for r in raw:
    k = (r["ts"], r["room"], r["caller"], r["msg_type"],
         (r["source_message_verbatim"] or "")[:200])
    if k in seen:
        continue
    seen.add(k)
    chat.append(r)
DUPES = len(raw) - len(chat)

win = [r for r in chat if WIN_LO <= r["date"] <= WIN_HI
       and r["confidence"] in ("high", "medium")]
for r in win:
    r["_dt"] = dt(r["ts"])

entries = [r for r in win if r["msg_type"] == "entry" and r["_dt"]]
by_ts = defaultdict(list)
for e in entries:
    by_ts[e["ts"]].append(e)

mgmt = [r for r in win if r["msg_type"] in ("trim", "exit", "add")
        and r["links_to"].strip() and r["_dt"]]

linked = defaultdict(list)
drop_noentry = drop_ambig = drop_backwards = 0
for m in mgmt:
    cands = by_ts.get(m["links_to"].strip(), [])
    if not cands:
        drop_noentry += 1
        continue
    if len(cands) > 1:
        same = [c for c in cands if c["room"] == m["room"]] or \
               [c for c in cands if c["caller"] == m["caller"]]
        if len(same) != 1:
            drop_ambig += 1
            continue
        cands = same
    e = cands[0]
    d = mins(e["_dt"], m["_dt"])
    if d < 0:
        drop_backwards += 1
        continue
    m["_dtm"] = d
    m["_same_day"] = (m["date"] == e["date"])
    m["_cls"] = classify(m)
    linked[id(e)].append(m)

ALL_MGMT = [r for r in chat if r["msg_type"] in ("trim", "exit", "add")]
UNLINKABLE = sum(1 for r in ALL_MGMT if not r["links_to"].strip())


# ------------------------------------------------------------ tape (bids)
def load_tape(want):
    out = defaultdict(list)
    if not want:
        return out
    for f in ("databento_tape_clean.csv", "option_tape.csv",
              "missed_tape.csv", "alert_tape.csv"):
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            continue
        with open(p, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                o = row.get("occ")
                if o not in want:
                    continue
                t, b = num(row.get("ts")), num(row.get("bid"))
                if t and b is not None:
                    out[o].append((t, b))
    for o in out:
        out[o].sort()
    return out


def bid_at(tape, occ, when, tol=120):
    arr = tape.get(occ)
    if not arr:
        return None
    target = when.timestamp() + 4 * 3600      # naive ET -> epoch, fixed -04:00
    lo, hi, best, bd = 0, len(arr) - 1, None, None
    while lo <= hi:
        mid = (lo + hi) // 2
        d = abs(arr[mid][0] - target)
        if bd is None or d < bd:
            bd, best = d, arr[mid][1]
        if arr[mid][0] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return best if (bd is not None and bd <= tol) else None


TAPE = load_tape({e["occ"].strip() for e in entries
                  if e["occ"].strip() and linked.get(id(e))})


# -------------------------------------------------------- per-entry record
def pct_for(m, e, ep):
    txt = m["source_message_verbatim"]
    p = stated_pct(txt)
    if p is not None:
        return p, "stated"
    xp = posted_price(txt)
    if ep and xp and ep > 0:
        if e["kind"] == "future":
            pts = xp - ep
            if "SHORT" in (e["source_message_verbatim"] or "").upper():
                pts = -pts
            if abs(pts) < 0.5 * abs(ep):
                return pts, "caller-price-points"
        elif 0.01 <= xp <= 500 and 0.01 <= ep <= 500:
            v = (xp - ep) / ep * 100.0
            if -100 <= v <= 3000:
                return v, "caller-price"
    occ = e["occ"].strip()
    if occ and m.get("_dt") and ep and e["kind"] == "option":
        b = bid_at(TAPE, occ, m["_dt"])
        if b is not None and ep > 0:
            return (b - ep) / ep * 100.0, "measured"
    return None, "unavailable"


recs = []
for e in entries:
    ms = sorted(linked.get(id(e), []), key=lambda r: r["_dtm"])
    ep, ep_src = entry_price(e)
    trims = [m for m in ms if m["_cls"] == "partial"]
    fulls = [m for m in ms if m["_cls"] == "full"]
    unq = [m for m in ms if m["_cls"] == "exit-unqualified"]
    ft = trims[0] if trims else None
    fe = fulls[0] if fulls else (unq[-1] if unq else None)
    ftp, ftb = pct_for(ft, e, ep) if ft else (None, "")
    fep, feb = pct_for(fe, e, ep) if fe else (None, "")
    later = [pct_for(m, e, ep)[0] for m in ms if ft and m["_dtm"] > ft["_dtm"]]
    later = [x for x in later if x is not None]
    be = [m for m in ms if BE.search(m["source_message_verbatim"] or "")]
    etxt = (e["source_message_verbatim"] or "").replace("\n", " ")
    recs.append({
        "caller": e["caller"].strip() or "(unnamed)",
        "room": e["room"].strip(), "kind": e["kind"],
        "date": e["date"], "ts": e["ts"], "symbol": e["symbol"],
        "side": e["side"], "strike": e["strike"], "occ": e["occ"],
        "entry_px": ep, "entry_px_src": ep_src,
        "their_stop": num(e["their_stop"]),
        "n_mgmt": len(ms),
        "t_first_trim": ft["_dtm"] if ft else None,
        "ft_same_day": ft["_same_day"] if ft else None,
        "first_trim_pct": ftp, "first_trim_basis": ftb,
        "first_trim_size": trim_size(ft["source_message_verbatim"]) if ft else "",
        "first_trim_dt": ft["_dt"] if ft else None,
        "t_full_exit": fe["_dtm"] if fe else None,
        "ex_same_day": fe["_same_day"] if fe else None,
        "exit_pct": fep, "exit_basis": feb,
        "exit_qualified": bool(fulls),
        "exit_dt": fe["_dt"] if fe else None,
        "exit_is_loss": bool(fe and (LOSS_WORD.search(fe["source_message_verbatim"] or "")
                                     or (fep is not None and fep < 0))),
        "better_later": bool(ftp is not None and later and max(later) > ftp),
        "any_later_pct": bool(later),
        "silent": not ms,
        "no_exit": fe is None,
        "be_min": be[0]["_dtm"] if be else None,
        "be_same_day": be[0]["_same_day"] if be else None,
        "stop_mention": bool(STOP_MENTION.search(etxt)),
        "stop_none": bool(NO_STOP.search(etxt)),
        "stop_underlying": bool(UNDERLYING_STOP.search(etxt)),
        "stop_premium": (num(PREMIUM_STOP.search(etxt).group(1))
                         if (PREMIUM_STOP.search(etxt) and not NO_STOP.search(etxt)
                             and not UNDERLYING_STOP.search(etxt)) else None),
        "e": e,
    })

OPT = [r for r in recs if r["kind"] == "option"]
FUT = [r for r in recs if r["kind"] == "future"]
EQ = [r for r in recs if r["kind"] == "equity"]


# ------------------------------------------------------------ 5. the match
led = [r for r in rd("master_ledger.csv") if WIN_LO <= r.get("date", "") <= WIN_HI]
for r in led:
    r["_o"] = dt("%s %s" % (r["date"], r["opened"])) if r["opened"].strip() else None
    r["_c"] = dt("%s %s" % (r["date"], r["closed"])) if r["closed"].strip() else None
    if r["_o"] and r["_c"] and r["_c"] < r["_o"]:
        r["_c"] = None                      # closed-before-opened: unusable row


def side_eq(a, b):
    a, b = (a or "").upper(), (b or "").upper()
    return bool(a) and bool(b) and a[0] == b[0] and a[0] in "CP"


matches = []
for r in OPT:
    st = num(r["strike"])
    if st is None:
        continue
    for L in led:
        if L["kind"] != "option" or not L["_o"]:
            continue
        if L["symbol"].strip().upper() != r["symbol"].strip().upper():
            continue
        if not side_eq(L["side"], r["side"]):
            continue
        ls = num(L["strike"])
        if ls is None or abs(ls - st) > 1e-6:
            continue
        gap = abs(mins(r["e"]["_dt"], L["_o"]))
        if gap > 5:
            continue
        hold = mins(L["_o"], L["_c"]) if L["_c"] else None
        still = out_first = None
        if r["first_trim_dt"] and L["_c"]:
            still = L["_c"] >= r["first_trim_dt"]
            out_first = not still
        matches.append({
            "date": r["date"], "symbol": r["symbol"], "side": r["side"],
            "strike": r["strike"], "caller": r["caller"], "room": r["room"],
            "entry_ts": r["ts"], "gap_min": gap,
            "caller_first_trim_min": r["t_first_trim"],
            "caller_first_trim_pct": r["first_trim_pct"],
            "caller_first_trim_basis": r["first_trim_basis"],
            "bot_hold_min": hold, "bot_pl_pct": num(L["pl_pct"]),
            "bot_source": L["source"],
            "bot_still_in_at_first_trim": still,
            "bot_out_before_first_trim": out_first,
        })
seen_m, uniq = set(), []
for m in matches:
    k = (m["entry_ts"], m["symbol"], m["strike"], m["side"],
         round(m["gap_min"], 3), m["bot_hold_min"], m["bot_pl_pct"])
    if k in seen_m:
        continue
    seen_m.add(k)
    uniq.append(m)
matches = uniq
BOOK = [m for m in matches if m["bot_source"] != "webull-export-only"]
st_in = [m for m in matches if m["bot_still_in_at_first_trim"] is True]
st_out = [m for m in matches if m["bot_out_before_first_trim"] is True]
both = st_in + st_out
ANSW_ENTRIES = len({m["entry_ts"] for m in both})


# ------------------------------------------------ CALLER-OUTCOMES two days
out_rows = []
for d in ("2026-09-11", "2026-09-14"):
    for r in rd(os.path.join("daily-reports", "CALLER-OUTCOMES-%s.csv" % d)):
        a = dt("%s %s" % (d, r.get("entry_time", "").strip()))
        b = dt("%s %s" % (d, r.get("event_time", "").strip()))
        if not a or not b:
            continue
        r["_day"] = d
        r["_min"] = mins(a, b)
        r["_pct"] = num(r.get("reported_pct")) or num(r.get("calculated_pct"))
        out_rows.append(r)
oc_first = {}
for r in sorted(out_rows, key=lambda x: x["_min"]):
    if "trim" not in (r.get("event") or "").lower():
        continue
    oc_first.setdefault((r["_day"], r.get("room"), r.get("contract")), r)
oc_full = [r for r in out_rows if "full exit" in (r.get("event") or "").lower()]


# --------------------------------------------------------------- 3. stops
posted_fut = [(abs(r["their_stop"] - (num(r["e"]["their_price"]) or 0)), r)
              for r in recs if r["kind"] == "future" and r["their_stop"]
              and num(r["e"]["their_price"])]
opt_stop_posted = [r for r in OPT if r["their_stop"] is not None]
opt_mention = [r for r in OPT if r["stop_mention"]]
opt_prem = [r for r in opt_mention if r["stop_premium"] is not None]
opt_under = [r for r in opt_mention if r["stop_underlying"]]
opt_none = [r for r in opt_mention if r["stop_none"]]
opt_prem_pct = [abs(r["stop_premium"] - r["entry_px"]) / r["entry_px"] * 100.0
                for r in opt_prem if r["entry_px"] and r["entry_px"] > 0
                and 0.2 <= r["stop_premium"] / r["entry_px"] <= 1.0]

revealed = [r for r in recs if r["exit_is_loss"] and r["exit_pct"] is not None
            and r["exit_pct"] < 0 and r["kind"] == "option"]
be_rows = [r for r in recs if r["be_min"] is not None]
be_same = [r for r in be_rows if r["be_same_day"]]


# ---------------------------------------------------------- 4. runner/trim
two = [r for r in recs if r["n_mgmt"] >= 2 and r["t_first_trim"] is not None]
pair = [r for r in two if r["first_trim_pct"] is not None and r["exit_pct"] is not None]
adds = [r for r in pair if r["exit_pct"] - r["first_trim_pct"] > RUNNER_EDGE]
gives = [r for r in pair if r["exit_pct"] < r["first_trim_pct"]]
ft_all = [r for r in recs if r["t_first_trim"] is not None]
only_pos = [r for r in ft_all if not r["better_later"]]
no_later = [r for r in ft_all if not r["any_later_pct"]]


# ------------------------------------------------------------ per-caller
prof = []
bycaller = defaultdict(list)
for r in recs:
    bycaller[r["caller"]].append(r)
for name, rs in bycaller.items():
    lk = [r for r in rs if r["n_mgmt"] > 0]
    if len(lk) < MIN_N:
        continue
    same = [r for r in rs if r["ft_same_day"]]
    ftm = q([r["t_first_trim"] for r in same])
    ftp = q([r["first_trim_pct"] for r in rs])
    exm = q([r["t_full_exit"] for r in rs if r["ex_same_day"]])
    exp = q([r["exit_pct"] for r in rs])
    kind = Counter(r["kind"] for r in rs).most_common(1)[0][0]
    if kind == "future":
        stopv = q([abs(r["their_stop"] - (num(r["e"]["their_price"]) or 0))
                   for r in rs if r["their_stop"] and num(r["e"]["their_price"])])
        stop_unit = "pts"
    else:
        stopv = q([abs(r["stop_premium"] - r["entry_px"]) / r["entry_px"] * 100.0
                   for r in rs if r["stop_premium"] and r["entry_px"]
                   and 0.2 <= r["stop_premium"] / r["entry_px"] <= 1.0])
        stop_unit = "%"
    posted_n = sum(1 for r in rs if r["their_stop"] is not None
                   or r["stop_premium"] is not None or r["stop_underlying"])
    prof.append({
        "caller": name,
        "room": Counter(r["room"] for r in rs).most_common(1)[0][0],
        "kind": kind, "entries_all": len(rs), "entries_linked": len(lk),
        "median_min_to_first_trim_sameday": ftm[1],
        "p25_min_first_trim": ftm[2], "p75_min_first_trim": ftm[3],
        "n_first_trim_sameday": ftm[0],
        "n_first_trim_any": sum(1 for r in rs if r["t_first_trim"] is not None),
        "median_first_trim_pct": ftp[1], "n_first_trim_pct": ftp[0],
        "median_min_to_exit_sameday": exm[1], "n_exit_sameday": exm[0],
        "median_exit_pct": exp[1], "n_exit_pct": exp[0],
        "posts_a_stop_pct": 100.0 * posted_n / len(rs),
        "median_stop": stopv[1], "stop_unit": stop_unit, "n_stop": stopv[0],
        "silent_rate_pct": 100.0 * sum(1 for r in rs if r["silent"]) / len(rs),
        "no_posted_exit_pct": 100.0 * sum(1 for r in rs if r["no_exit"]) / len(rs),
    })


def score(p):
    """matchable = a first trim that exists, same day, at a reachable percent."""
    if not p["n_first_trim_sameday"] or p["median_first_trim_pct"] is None:
        return -1.0
    s = min(p["n_first_trim_sameday"], 40) * 1.0
    m = p["median_min_to_first_trim_sameday"]
    if m is not None and m >= 1.0:
        s += 20
    if 8 <= (p["median_first_trim_pct"] or 0) <= 80:
        s += 25
    s -= p["silent_rate_pct"] * 0.25
    return s


for p in prof:
    p["matchable_score"] = round(score(p), 1)
prof.sort(key=lambda p: -p["matchable_score"])


# ----------------------------------------------------------------- output
def hold_block(lab, rs):
    n = len(rs)
    ftd = q([r["t_first_trim"] for r in rs if r["ft_same_day"]])
    fts = q([r["t_first_trim"] / 60.0 for r in rs if r["ft_same_day"] is False])
    exd = q([r["t_full_exit"] for r in rs if r["ex_same_day"]])
    exs = q([r["t_full_exit"] / 60.0 for r in rs if r["ex_same_day"] is False])
    sil = sum(1 for r in rs if r["silent"])
    nox = sum(1 for r in rs if r["no_exit"])
    return ["**%s** - %d entries" % (lab, n), "",
            "| measure | value |", "|---|---|",
            "| entry -> first trim, SAME DAY (min) | %s |" % qs(ftd),
            "| entry -> first trim, next day or later (hours) | %s |" % qs(fts),
            "| entry -> full exit, SAME DAY (min) | %s |" % qs(exd),
            "| entry -> full exit, next day or later (hours) | %s |" % qs(exs),
            "| entries with NO management post at all (silent) | %d of %d = %s |"
            % (sil, n, fmt(100.0 * sil / n if n else None, 1, "%")),
            "| entries with no posted exit of any kind | %d of %d = %s |"
            % (nox, n, fmt(100.0 * nox / n if n else None, 1, "%")), ""]


L = []
A = L.append
A("# Caller profile - how the callers actually trade (%s)" % OUT_DATE)
A("")
A("G's question: *\"what is the callers' average trade hold time, because we need "
  "to kind of match that to get similar results - I'm even happy getting to the "
  "first trim. What's their normal stop also?\"*")
A("")
A("Built by `reference/caller_profile.py`. Measurement only - reads CSVs, writes "
  "this file and its `.csv` twin, changes nothing live. Re-runnable.")
A("")
A("## The three numbers")
A("")
_ftd = q([r["t_first_trim"] for r in OPT if r["ft_same_day"]])
_ftp = q([r["first_trim_pct"] for r in OPT])
_rev = q([r["exit_pct"] for r in revealed])
A("| | |")
A("|---|---|")
A("| **options: entry -> first trim** | **%s** |" % qs(_ftd))
A("| **options: the percent that trim is posted at** | **%s** |" % qs(_ftp, 1, "%"))
A("| **options: their stop, revealed by posted losing exits** | **%s** |" % qs(_rev, 1, "%"))
A("")
A("They almost never post a premium stop on an option: %d of %d option entries in "
  "scope mention a stop at all, and only %d of those quote a stop as a premium."
  % (len(opt_mention), len(OPT), len(opt_prem)))
A("")
A("---")
A("")
A("## What this is measured on")
A("")
A("| | |")
A("|---|---|")
A("| source | `recovered_alerts_chat.csv` |")
A("| rows after de-duplicating the overlapping exports | %d (dropped %d duplicates) |"
  % (len(chat), DUPES))
A("| window + confidence filter | %s .. %s, high+medium only |" % (WIN_LO, WIN_HI))
A("| entries in scope | **%d** (%d option, %d futures, %d equity) |"
  % (len(recs), len(OPT), len(FUT), len(EQ)))
A("| management posts linked to one of those entries | **%d** |"
  % sum(len(v) for v in linked.values()))
A("| entries with at least one linked management post | **%d** |"
  % sum(1 for r in recs if r["n_mgmt"]))
A("| entry premium known | %d posted by the caller + %d recovered from the message text |"
  % (sum(1 for r in recs if r["entry_px_src"] == "posted"),
     sum(1 for r in recs if r["entry_px_src"] == "recovered")))
A("")
A("**The linking caveat, up front.** %d management messages in the whole file carry "
  "no `links_to` at all - they name a ticker and a percent and nothing else, so they "
  "can never be tied to an entry. A further %d point at an entry outside this window "
  "or below medium confidence, %d are ambiguous (two entries share a timestamp), %d "
  "timestamp before their entry. All excluded. **Every hold-time number below is "
  "measured on callers who write a linkable management post - the tidy ones. It is "
  "not a sample of all calls.**"
  % (UNLINKABLE, drop_noentry, drop_ambig, drop_backwards))
A("")
A("---")
A("")
A("## 1. Hold time")
A("")
L += hold_block("Options", OPT)
L += hold_block("Futures", FUT)
A("Same-day and multi-day are split on purpose: one swing trim four days later "
  "would otherwise drag the median into the thousands of minutes.")
A("")
A("Read the silent line carefully: an entry with no posted exit is not a loss and "
  "not a win. It is **unavailable**. A later high is not a caller exit.")
A("")
A("---")
A("")
A("## 2. The first trim")
A("")
bas = Counter(r["first_trim_basis"] for r in ft_all)
A("| measure | value |")
A("|---|---|")
A("| entries that got a first trim | %d of %d |" % (len(ft_all), len(recs)))
A("| of those, same day | %d |" % sum(1 for r in ft_all if r["ft_same_day"]))
A("| minutes to it, same-day only | %s |"
  % qs(q([r["t_first_trim"] for r in ft_all if r["ft_same_day"]])))
A("| percent it is posted at | %s |" % qs(q([r["first_trim_pct"] for r in ft_all]), 1, "%"))
A("| where that percent came from | %s |"
  % ", ".join("%s %d" % (k or "none", v) for k, v in bas.most_common()))
A("| first trim is the only positive event (nothing better posted later) | %d of %d |"
  % (len(only_pos), len(ft_all)))
A("| ... of which no later percent was posted at all (unavailable, not zero) | %d |"
  % len(no_later))
A("")
sz = Counter(r["first_trim_size"] for r in recs if r["first_trim_size"])
if sz:
    A("Stated trim size where the caller gives one: " +
      ", ".join("%s x%d" % (k, v) for k, v in sz.most_common(6)) +
      ". Most trims state no size at all.")
    A("")
dist = Counter()
for r in ft_all:
    p = r["first_trim_pct"]
    if p is None:
        continue
    dist["<10%" if p < 10 else "10-19%" if p < 20 else "20-34%" if p < 35
         else "35-59%" if p < 60 else "60%+"] += 1
if dist:
    A("Where the first trim lands: " +
      ", ".join("%s %d" % (k, dist[k]) for k in
                ("<10%", "10-19%", "20-34%", "35-59%", "60%+") if dist[k]) +
      " (n=%d)." % sum(dist.values()))
    A("")
A("---")
A("")
A("## 3. Their stop")
A("")
A("### (a) Posted stops")
A("")
A("| measure | value |")
A("|---|---|")
A("| FUTURES entries carrying a posted stop | %d of %d |"
  % (sum(1 for r in FUT if r["their_stop"] is not None), len(FUT)))
A("| futures stop distance, points from entry | %s |" % qs(q([x for x, _ in posted_fut]), 1))
A("| OPTION entries with a stop in the recovered `their_stop` field | **%d of %d** |"
  % (len(opt_stop_posted), len(OPT)))
A("| OPTION entries whose message mentions a stop at all | %d of %d = %s |"
  % (len(opt_mention), len(OPT),
     fmt(100.0 * len(opt_mention) / len(OPT) if OPT else None, 1, "%")))
A("| ... stated as an UNDERLYING level (\"SL: under 55\") | %d |" % len(opt_under))
A("| ... stated as \"no stop loss\" / \"SL: None\" | %d |" % len(opt_none))
A("| ... stated as a PREMIUM stop | %d |" % len(opt_prem))
A("| premium-stop distance below entry | %s |" % qs(q(opt_prem_pct), 1, "%"))
A("")
futbot = sum(1 for _, r in posted_fut
             if "NEW POTENTIAL SIGNAL" in (r["e"]["source_message_verbatim"] or ""))
if futbot:
    A("**Read the futures stop with care:** %d of those %d come from one automated "
      "signal poster that prints a fixed `TP:/SL:` on every message. That is a "
      "machine's parameter, not a human's risk decision."
      % (futbot, len(posted_fut)))
    A("")
A("### (b) Revealed stops - where a losing exit was actually posted")
A("")
A("| measure | value |")
A("|---|---|")
A("| option entries with a posted losing exit and a readable percent | %d |" % len(revealed))
A("| the loss at that exit | %s |" % qs(_rev, 1, "%"))
worst = q([r["exit_pct"] for r in revealed])
A("| the deepest quartile (p25) | %s |" % fmt(worst[2], 1, "%"))
A("")
A("This is the only honest read on \"their normal stop\" for options: not a resting "
  "order, a habit. When a caller gives up on an option he is typically already down "
  "%s." % fmt(_rev[1], 0, "%"))
A("")
A("### (c) \"SL to b/e\"")
A("")
A("| measure | value |")
A("|---|---|")
A("| entries where a management post moves the stop to breakeven | %d of %d |"
  % (len(be_rows), len(recs)))
A("| minutes after entry, same-day cases | %s |"
  % qs(q([r["be_min"] for r in be_same])))
A("| cases that happened on a later day | %d |" % (len(be_rows) - len(be_same)))
A("")
A("---")
A("")
A("## 4. Runner vs trim")
A("")
A("| measure | value |")
A("|---|---|")
A("| entries with 2+ management posts and a first trim | %d |" % len(two))
A("| of those, both first-trim %% and final-exit %% readable | %d |" % len(pair))
A("| median first-trim %% | %s |" % fmt(q([r["first_trim_pct"] for r in pair])[1], 1, "%"))
A("| median final-exit %% | %s |" % fmt(q([r["exit_pct"] for r in pair])[1], 1, "%"))
A("| runner adds more than +%d pts beyond the first trim | %d of %d |"
  % (RUNNER_EDGE, len(adds), len(pair)))
A("| runner ends BELOW the first trim (gives back) | %d of %d |" % (len(gives), len(pair)))
A("")
A("n=%d is a small sample and it is the *only* set where both ends are readable. "
  "Treat the split as a direction, not a result." % len(pair))
A("")
A("---")
A("")
A("## 5. The match question - was the bot still in when the caller trimmed?")
A("")
A("Join: same date, same symbol, same strike, same side, our entry within 5 minutes "
  "of theirs, against `master_ledger.csv`. A ledger row whose close timestamps "
  "before its open is dropped as unusable.")
A("")
A("| measure | value |")
A("|---|---|")
A("| caller entries the ledger also shows a position in | **%d** |" % len(matches))
A("| of those, rows with book provenance (not Webull-export-only) | %d |" % len(BOOK))
A("| pairs where the caller ALSO posted a first trim (the answerable set) | **%d** "
  "(%d distinct caller entries) |" % (len(both), ANSW_ENTRIES))
A("| **bot still in when the caller trimmed** | **%d of %d** |" % (len(st_in), len(both)))
A("| **bot already out before the caller's first trim** | **%d of %d** |"
  % (len(st_out), len(both)))
A("")
A("| measure | value |")
A("|---|---|")
A("| our hold time on matched trades (min) | %s |"
  % qs(q([m["bot_hold_min"] for m in matches])))
A("| our exit %% on matched trades | %s |"
  % qs(q([m["bot_pl_pct"] for m in matches]), 1, "%"))
A("| the caller's first-trim clock on the same trades (min) | %s |"
  % qs(q([m["caller_first_trim_min"] for m in matches])))
A("| the caller's first-trim %% on the same trades | %s |"
  % qs(q([m["caller_first_trim_pct"] for m in matches]), 1, "%"))
A("")
if both:
    A("Every answerable pair. Where one caller entry matched several of our "
      "positions in the same contract, each of our positions is its own row.")
    A("")
    A("| date | contract | caller | their 1st trim | their % | our hold | our % | still in? |")
    A("|---|---|---|---:|---:|---:|---:|---|")
    for m in sorted(both, key=lambda x: (x["date"], x["symbol"])):
        A("| %s | %s %s%s | %s | %s min | %s | %s min | %s | %s |" % (
            m["date"], m["symbol"], m["strike"], (m["side"] or "")[:1],
            m["caller"][:18], fmt(m["caller_first_trim_min"]),
            fmt(m["caller_first_trim_pct"], 1, "%"),
            fmt(m["bot_hold_min"]), fmt(m["bot_pl_pct"], 1, "%"),
            "yes" if m["bot_still_in_at_first_trim"] else "NO - out first"))
    A("")
A("---")
A("")
A("## 6. The two fully-paired days (9/11 and 9/14)")
A("")
A("`daily-reports/CALLER-OUTCOMES-*.csv` pairs claim events by hand for two days. "
  "Small, but every row carries both timestamps - so it is the cleanest check on "
  "the big sample above.")
A("")
A("| measure | value |")
A("|---|---|")
A("| claim events paired across the two days | %d |" % len(out_rows))
A("| distinct positions whose FIRST trim is timed | %d |" % len(oc_first))
A("| entry -> first trim (min) | %s |" % qs(q([r["_min"] for r in oc_first.values()])))
A("| first-trim %% | %s |" % qs(q([r["_pct"] for r in oc_first.values()]), 1, "%"))
A("| full exits recorded | %d |" % len(oc_full))
A("| entry -> full exit (min) | %s |" % qs(q([r["_min"] for r in oc_full])))
A("")
A("Basis on those rows: %d caller-stated, %d market-bid-at-caller-exit (measured), "
  "%d unavailable."
  % (sum(1 for r in out_rows if (r.get("basis") or "") == "caller-stated"),
     sum(1 for r in out_rows if "market bid" in (r.get("basis") or "")),
     sum(1 for r in out_rows if r["_pct"] is None)))
A("")
A("---")
A("")
A("## 7. Per-caller profile (min %d linked entries), ranked by matchable" % MIN_N)
A("")
A("`matchable` rewards a first trim that exists, lands the same day at least a "
  "minute after entry, sits between +8%% and +80%%, and is not buried under a high "
  "silent rate. It is a ranking, not a score with units.")
A("")
A("| caller | n entries / linked | median min to 1st trim (same day) | typical "
  "1st-trim % | posts a stop | typical stop | silent | median exit % | matchable |")
A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for p in prof:
    A("| %s | %d / %d | %s | %s | %s | %s | %s | %s | %s |" % (
        p["caller"][:24], p["entries_all"], p["entries_linked"],
        fmt(p["median_min_to_first_trim_sameday"]) + (" (n=%d)" % p["n_first_trim_sameday"]),
        fmt(p["median_first_trim_pct"], 1, "%") + (" (n=%d)" % p["n_first_trim_pct"]),
        fmt(p["posts_a_stop_pct"], 0, "%"),
        (fmt(p["median_stop"], 1, p["stop_unit"]) + (" (n=%d)" % p["n_stop"])),
        fmt(p["silent_rate_pct"], 0, "%"),
        fmt(p["median_exit_pct"], 1, "%") + (" (n=%d)" % p["n_exit_pct"]),
        p["matchable_score"]))
A("")
A("## 8. Per-room")
A("")
byroom = defaultdict(list)
for r in recs:
    byroom[r["room"]].append(r)
A("| room | entries | linked | median min to 1st trim (same day) | median 1st-trim % "
  "| median min to exit (same day) | silent |")
A("|---|---:|---:|---:|---:|---:|---:|")
for room, rs in sorted(byroom.items(), key=lambda kv: -len(kv[1])):
    lk = [r for r in rs if r["n_mgmt"]]
    if len(lk) < MIN_N:
        continue
    A("| %s | %d | %d | %s | %s | %s | %s |" % (
        room[:46], len(rs), len(lk),
        fmt(q([r["t_first_trim"] for r in rs if r["ft_same_day"]])[1]),
        fmt(q([r["first_trim_pct"] for r in rs])[1], 1, "%"),
        fmt(q([r["t_full_exit"] for r in rs if r["ex_same_day"]])[1]),
        fmt(100.0 * sum(1 for r in rs if r["silent"]) / len(rs), 0, "%")))
A("")
A("## 9. What this cannot say")
A("")
A("- **No caller win rate, no caller net result.** Most entries never get a posted "
  "exit, and an unposted exit is unavailable, not a number. Nothing here is a "
  "scoreboard.")
A("- The hold times describe **callers who post linkable management messages**. "
  "Rooms that post an entry and go quiet sit in the silent column, not in the medians.")
A("- `their_target` is not recorded anywhere in this repo, so no target study exists.")
A("- Percentages labelled `stated` are the caller's own claim on their own fill. They "
  "are not broker truth and they are not the bid we could have hit.")
A("- The match section joins on contract and clock only - `master_ledger.csv` carries "
  "a room on a minority of rows, so a match is evidence we held the same contract at "
  "the same minute, not proof the room caused our order.")
A("")

with open(MD_PATH, "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

cols = ["caller", "room", "kind", "entries_all", "entries_linked",
        "median_min_to_first_trim_sameday", "p25_min_first_trim", "p75_min_first_trim",
        "n_first_trim_sameday", "n_first_trim_any", "median_first_trim_pct",
        "n_first_trim_pct", "median_min_to_exit_sameday", "n_exit_sameday",
        "median_exit_pct", "n_exit_pct", "posts_a_stop_pct", "median_stop",
        "stop_unit", "n_stop", "silent_rate_pct", "no_posted_exit_pct",
        "matchable_score"]
with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for p in prof:
        w.writerow({k: p.get(k, "") for k in cols})

print("wrote", MD_PATH)
print("wrote", CSV_PATH)
print(json.dumps({
    "entries": len(recs), "options": len(OPT), "futures": len(FUT),
    "linked_mgmt": sum(len(v) for v in linked.values()),
    "first_trims": len(ft_all), "matches": len(matches),
    "answerable_pairs": len(both), "bot_still_in": len(st_in),
    "bot_out_first": len(st_out),
}, indent=1))
