"""prove_tradier_bracket.py — THE ONE THING BETWEEN HERE AND SPX GOING LIVE.

G picked Tradier for SPX and said prove the bracket first. This is that proof.

WHY IT IS NEEDED
`TradierOptions.place_conditional_entry` does not work. It is written, and it
RAISES rather than sending anything, with the reason in its own docstring:
the OTOCO leg encoding for options was never confirmed against a live account.
That is the right way round — a stub that refuses is safe, a stub that guesses
is not — but it means an SPX entry currently has no way to carry a stop born
alongside it, and "no naked entries" is doctrine.

Webull does this with a combo (MASTER limit + STOP_LOSS leg). Tradier's
equivalent is order class `otoco`: a first leg that opens, and a linked pair
that closes. Until one real order comes back with an id and the right legs,
nobody knows whether our encoding is right.

WHAT THIS DOES
Builds exactly the order the machine would send for one SPX call, one
contract, with a stop underneath it — and by default PRINTS IT AND STOPS.
Nothing is sent without --place.

    python3 prove_tradier_bracket.py                  show the order, send nothing
    python3 prove_tradier_bracket.py --strike 6800    pick the strike
    python3 prove_tradier_bracket.py --place          SEND IT (G only)

G PLACES IT, NOT ME. Real-money actions are his alone — that is the house
rule and this script does not bend it. Run the dry version first, read the
payload, then run --place yourself while watching the Tradier screen.

WHAT TO LOOK FOR WHEN YOU RUN --place
  1. an order id comes back at all
  2. the account shows ONE long call and ONE resting stop, not two orders
     that both filled
  3. the stop is GTC, not DAY. Tradier allows GTC on option sells where
     Webull does not, and that is the whole reason the 9:31 re-arm dance
     goes away for SPX.
  4. cancel it by hand afterwards if it has not filled.

SIZE: one contract, and the strike is chosen FAR out of the money by default
so the premium is a few dollars. This is a plumbing test, not a trade.
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import occ                                                    # noqa: E402


def _cfg():
    with open(os.path.join(HERE, "settings.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def next_friday():
    t = dt.date.today()
    return (t + dt.timedelta(days=(4 - t.weekday()) % 7 or 7)).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strike", type=float, default=None,
                    help="default: ~8%% out of the money, so it is cheap")
    ap.add_argument("--expiry", default=None, help="YYYY-MM-DD (default: next Friday)")
    ap.add_argument("--place", action="store_true",
                    help="actually send it. G runs this, nobody else.")
    a = ap.parse_args()

    s = _cfg()
    t = ((s.get("execution") or {}).get("tradier") or {})
    from tradier import TradierOptions
    c = TradierOptions(t.get("access_token"), t.get("account_id"),
                       bool(t.get("sandbox")))
    c.connect()

    spx = c.stock_price("SPX") or c.stock_price("$SPX.X")
    if not spx:
        print("could not price SPX — check the token's market-data scope.")
        return 2
    strike = a.strike if a.strike else round((spx * 1.08) / 25.0) * 25.0
    expiry = a.expiry or next_friday()
    sym = occ.build("SPXW", expiry, "CALLS", strike)

    try:
        ask, bid, _raw = c.ask_bid(sym)
    except Exception as e:                                    # noqa: BLE001
        print("no quote for %s (%s) — pick another strike/expiry." % (sym, str(e)[:80]))
        return 2
    if not ask:
        print("no ask for %s — that contract is not quoting. Pick another." % sym)
        return 2

    limit = round(float(ask), 2)
    stop = max(0.05, round(limit * 0.75, 2))          # a real stop, well under
    print("=" * 70)
    print("TRADIER SPX BRACKET — PROOF ORDER")
    print("=" * 70)
    print("  SPX now      : %.2f" % spx)
    print("  contract     : %s" % sym)
    print("                 SPXW %s %g CALL" % (expiry, strike))
    print("  quote        : bid %s / ask %s" % (bid, ask))
    print("  BUY          : 1 contract, limit %.2f   (= %.0f dollars)"
          % (limit, limit * 100))
    print("  STOP         : %.2f, GTC, sell_to_close" % stop)
    print("  worst case   : about %.0f dollars if it gaps through the stop"
          % ((limit - stop) * 100))
    print()
    if not a.place:
        print("  DRY RUN — nothing was sent.")
        print("  Read the numbers above. If they look right, YOU run:")
        print("      python3 prove_tradier_bracket.py --place")
        print("  and watch the Tradier screen while it goes in.")
        return 0

    # --- the real thing -----------------------------------------------------
    print("  SENDING...")
    try:
        oid = c.buy(symbol="SPXW", side="CALLS", strike=strike, expiry=expiry,
                    qty=1, limit_price=limit)
    except AttributeError:
        print("  ! TradierOptions has no buy() — the ENTRY side is not built.")
        print("    That is the gap this proof exists to expose. The sell,")
        print("    stop and flatten paths exist; the open does not.")
        return 3
    except Exception as e:                                    # noqa: BLE001
        print("  ! entry refused: %s" % str(e)[:200])
        return 3
    print("  entry order id: %s" % oid)
    try:
        sid, used = c.place_stop("SPXW", "CALLS", strike, expiry, 1, limit, stop)
        print("  stop  order id: %s at %.2f" % (sid, used))
    except Exception as e:                                    # noqa: BLE001
        print("  ! STOP REFUSED: %s" % str(e)[:200])
        print("    THE POSITION IS NAKED. Put a stop on it by hand, now.")
        return 4
    print()
    print("  Now check on Tradier: one long call, one RESTING GTC stop.")
    print("  Cancel both by hand when you are done looking.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
