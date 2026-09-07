"""thetadata_probe.py — see ThetaData's real data before paying for it.

Run it:  python thetadata_probe.py

WHAT THIS ANSWERS
-----------------
Tradier gives us 1-minute option bars, but only while the contract is ALIVE:
of 111 trades since 8/05, 87 had no intraday history left and 84 of those
were on expired contracts. Nearly all of them 0DTE. That history is gone.

ThetaData sells the archive. Two things it has that Tradier does not:

  1. EXPIRED contracts, back years.
  2. Historical QUOTES — the actual bid and ask. Tradier serves TRADE prints.
     The ratchet fires on the BID, so every replay done against trade prints
     is an approximation. Quotes make it exact.

This probe deliberately picks a contract from G's OWN trade history that
Tradier could NOT serve, and asks ThetaData for it. If data comes back, that
is the proof — the exact thing that is missing, recovered.

THE FREE TIER
  1 year of free END-OF-DAY data for US stocks and options, 20 req/min.
  Free does NOT include 1-minute bars or quotes, so this probe will likely
  show EOD working and the minute/quote endpoints refused. That is still the
  answer: it proves the contract EXISTS in their archive, which is what
  Tradier could not do at any price.

  Options Value  $40/mo — 1-minute bars + QUOTES, back to 2020
  Options Standard $80/mo — tick level back to 2016, plus historical
                   IMPLIED VOLATILITY and 1st-order GREEKS on expired
                   contracts. That is the tier that would give G greeks for
                   trades he has already taken, instead of waiting weeks.

BEFORE RUNNING
  ThetaData is not a plain cloud API. You run their "Theta Terminal" (a small
  Java app) on this PC, and it serves data at 127.0.0.1:25510. Sign up at
  thetadata.net, download the terminal, log in, leave it running, then run
  this. Nothing here sends money or subscribes to anything.

NOT YET TESTED AGAINST A LIVE TERMINAL. Written from their published API
docs; the terminal only runs on G's machine, not where this was written. If
a response shape differs from what is handled here, that is the first thing
to fix — and it is exactly what verify-style probes are for.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:25510"
BARS = os.path.join(HERE, "bars")

ORDER_IN = re.compile(
    r'ORDER IN BUY\s+(\d+)\s+([A-Z]{1,6})\s+([\d.]+)([CP])\s+(\d{4}-\d\d-\d\d)')


def terminal_up():
    try:
        urllib.request.urlopen(BASE + "/v2/system/mdds/status", timeout=4).read()
        return True
    except urllib.error.HTTPError:
        return True                      # answered, just not that route
    except Exception:                    # noqa: BLE001
        return False


def get(path, **params):
    q = "&".join("%s=%s" % (k, v) for k, v in params.items())
    url = "%s%s?%s" % (BASE, path, q)
    with urllib.request.urlopen(url, timeout=30) as fh:
        return json.loads(fh.read().decode("utf-8", "replace"))


def a_contract_tradier_lost():
    """One of his real trades whose bars Tradier could NOT give us."""
    seen = []
    try:
        for line in open(os.path.join(HERE, "trades.log"),
                         encoding="utf-8", errors="replace"):
            m = ORDER_IN.search(line)
            if not m:
                continue
            day = line[:10]
            sym, strike, cp, exp = m.group(2), m.group(3), m.group(4), m.group(5)
            from occ import build as _occ_build
            occ = _occ_build(sym, exp, cp, strike)
            have = os.path.exists(os.path.join(BARS, "%s_%s.json" % (occ, day)))
            if not have:
                seen.append((sym, exp, strike, cp, day))
    except OSError:
        pass
    return seen[len(seen) // 2] if seen else None


def main():
    print("=" * 68)
    print("  THETADATA PROBE — can it give us what Tradier lost?")
    print("=" * 68)

    if not terminal_up():
        print("""
  The Theta Terminal is NOT running on this PC.

  It is not a plain cloud API — a small Java app runs locally and serves
  data at 127.0.0.1:25510. To try it:

    1. Sign up (free tier is fine) at thetadata.net
    2. Download and start the Theta Terminal, log in
    3. Leave it running, then run this file again

  Nothing here spends money or subscribes to anything.""")
        return 1
    print("  Theta Terminal is running.\n")

    pick = a_contract_tradier_lost()
    if not pick:
        print("  Every traded contract already has Tradier bars — nothing to")
        print("  prove. Run this again after a day whose 0DTEs expired.")
        return 0
    sym, exp, strike, cp, day = pick
    k = int(round(float(strike) * 1000))          # 1/10th cent, same as OCC
    print("  Asking for a contract from YOUR history that Tradier could not serve:")
    print("     %s %s%s expiring %s, traded %s\n" % (sym, strike, cp, exp, day))

    ymd = lambda d: d.replace("-", "")            # noqa: E731
    common = dict(root=sym, exp=ymd(exp), strike=k, right=cp,
                  start_date=ymd(day), end_date=ymd(day))

    for label, path, extra in (
            ("END-OF-DAY  (free tier)", "/v2/hist/option/eod", {}),
            ("1-MINUTE BARS  ($40 Value)", "/v2/hist/option/ohlc", {"ivl": 60000}),
            ("QUOTES bid/ask ($40 Value)", "/v2/hist/option/quote", {"ivl": 60000}),
            ("IV + GREEKS  ($80 Standard)", "/v2/hist/option/implied_volatility",
             {"ivl": 60000}),
    ):
        try:
            d = get(path, **dict(common, **extra))
            rows = (d or {}).get("response") or []
            fmt = ((d or {}).get("header") or {}).get("format")
            if rows:
                print("   ok   %-28s %d row(s)" % (label, len(rows)))
                if fmt:
                    print("        columns: %s" % ", ".join(map(str, fmt)))
                print("        first:   %s" % (rows[0],))
                print("        last:    %s" % (rows[-1],))
            else:
                print("   --   %-28s no rows (not on your tier, or no data)"
                      % label)
        except urllib.error.HTTPError as e:
            print("   --   %-28s HTTP %s — usually 'not on your tier'"
                  % (label, e.code))
        except Exception as e:                    # noqa: BLE001
            print("  FAIL  %-28s %s" % (label, str(e)[:70]))

    print("""
  HOW TO READ THIS
    Any rows at all on the EOD line means the contract IS in their archive —
    which is the whole question, because Tradier has nothing for it at any
    price.
    Rows on the QUOTES line would make every ratchet replay exact instead of
    approximate, because a stop fires on the bid.
    Rows on the IV + GREEKS line would give greeks for trades already taken,
    instead of waiting weeks to collect them.""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
