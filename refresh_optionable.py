"""refresh_optionable.py — rebuild extension/optionable.txt from the broker.

THE ONE LIST of symbols this bot may trade. A symbol earns its place by having
an option chain at tastytrade (the API publishes option-tick-sizes for it).
That is the only question worth asking: we trade options, so a real company
with no chain is exactly as untradeable as a word somebody typed in chat.

Why an allowlist and not a blocklist: the reader used to take any capitalised
word in front of a strike as a ticker, which produced "OPEN WITH 773C" from the
sentence "...then can go with 773c", and "CLOSE EXIT" from "| EXIT ALERT
Ticker: NBIS" (the real ticker being NBIS). Blocking words one at a time is
whack-a-mole — blocking VERY simply moved the misread on to GREEN.

Run it whenever you want it fresh; nothing depends on it being run often, since
new option listings are rare and a missing symbol fails LOUD, not silent.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "extension", "optionable.txt")
BASE = "https://api.tastyworks.com"
# Not equities, so they never appear in the equities feed — kept by hand.
FUT = ["6B","6E","6J","CL","ES","GC","HG","M2K","MBT","MCL","MES","MGC","MNQ",
       "MYM","NG","NQ","PL","RTY","SI","YM","ZB","ZC","ZN","ZS","ZW"]
IDX = ["DJX","NDX","RUT","SPX","SPXW","VIX","VIXW","XSP"]


def _token(cfg):
    tt = cfg["execution"]["tastytrade"]
    body = urllib.parse.urlencode({"grant_type": "refresh_token",
                                   "refresh_token": tt["refresh_token"],
                                   "client_secret": tt["client_secret"]}).encode()
    req = urllib.request.Request(BASE + "/oauth/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["access_token"]


def _page(tok, per, off):
    h = {"Authorization": "Bearer " + tok, "Accept": "application/json"}
    url = BASE + "/instruments/equities/active?per-page=%d&page-offset=%d" % (per, off)
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(2 + i * 2); continue
            raise
        except Exception:
            time.sleep(1 + i)
    return None


def main():
    cfg = json.load(open(os.path.join(HERE, "settings.json"), encoding="utf-8"))
    tok = _token(cfg)
    per, off, total, opt = 1000, 0, None, set()
    while True:
        b = _page(tok, per, off // per)
        if not b:
            break
        items = (b.get("data") or {}).get("items") or []
        total = (b.get("pagination") or {}).get("total-items", total)
        if not items:
            break
        for it in items:
            s = (it.get("symbol") or "").strip().upper()
            # option-tick-sizes present == the broker lists an option chain
            if s and "/" not in s and it.get("option-tick-sizes"):
                opt.add(s)
        off += per
        if off >= (total or 0):
            break
    if len(opt) < 3000:
        print("REFUSING to write: only %d optionable symbols came back (expected "
              "~6000). The feed is short or the token is wrong — the old file is "
              "better than a truncated one." % len(opt))
        return 1
    hdr = [
        "# optionable.txt — THE one list of symbols this bot is allowed to trade.",
        "#",
        "# Generated %s by refresh_optionable.py from tastytrade" % datetime.date.today().isoformat(),
        "# /instruments/equities/active (%s active equities). A symbol is here if" % total,
        "# the broker publishes OPTION TICK SIZES for it — an option chain exists.",
        "# We trade options, so a real company with no chain is as untradeable as",
        "# a word somebody typed in chat.",
        "#",
        "# Read by BOTH background.js and bridge.py. One file, two readers, no",
        "# drift — the same rule as rooms.txt. A symbol missing from here fails",
        "# LOUD at the bridge, it is never silently skipped.",
        "#",
        "# %d equity/ETF option roots, %d futures, %d cash indexes." % (len(opt), len(FUT), len(IDX)),
        "#",
        "# --- FUTURES ---",
    ]
    lines = hdr + FUT + ["# --- CASH INDEXES ---"] + IDX + ["# --- EQUITY / ETF ---"] + sorted(opt)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, OUT)
    print("wrote %s — %d equity roots + %d futures + %d indexes"
          % (OUT, len(opt), len(FUT), len(IDX)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
