"""BROKER ADAPTER (9/3/26, G: "build so I can plug in a Schwab").

The whole machine — parser, guards, ratchet, watchdog, journal — talks to a
broker through exactly FIFTEEN methods. This file writes that contract down
so a second broker can be added without touching anything above it.

Nothing here changes how Webull behaves. `webull_options.WebullOptions` was
already the de-facto interface; `BrokerBase` just names it, and `get_broker()`
picks an implementation from settings. Default is Webull, so a folder with no
new settings runs exactly as it did yesterday.

WHY (see v3.5.0/BROKER-TOP4-2026-09.md for the research):
  * Webull has NO conditional order that triggers off the UNDERLYING's price,
    and NO option quote streaming at any price. The ratchet therefore runs on
    a 1-per-second batched HTTP poll.
  * Tradier and Schwab both offer conditional option orders AND streaming
    option quotes. Tradier is cheaper and has no 7-day auth cliff.
  * The plan is NOT to migrate. It is to run a second broker ALONGSIDE
    Webull, route a few rooms to it, and let the journal compare real fills
    for two weeks before anything is decided.

ADDING A BROKER
  1. Subclass BrokerBase, implement the methods marked REQUIRED.
  2. Register it in _REGISTRY at the bottom.
  3. settings.json -> {"execution": {"broker": "tradier", "tradier": {...}}}
  Everything above the adapter keeps working untouched.

CONVENTIONS every implementation must honour (learned the hard way here):
  * `occ` is the OCC symbol, e.g. SPY260904P00771000.
  * `side` is the string "CALLS" or "PUTS".
  * `expiry` is "YYYY-MM-DD".
  * Prices are floats in dollars per share (1.66 means $166 a contract).
  * A method that cannot answer raises Refused(reason) — it NEVER guesses and
    NEVER returns a made-up price. Upstream treats "unknown" as "you might be
    in it", which is the only safe reading.
  * positions() must NEVER raise. On a throttle or a bad body it returns [],
    which upstream reads as "no verdict" rather than "you are flat".
"""
from webull_options import Refused                      # one shared error type


class BrokerBase(object):
    """The contract. Method names and shapes are fixed by the callers."""

    name = "base"
    # Capability flags — code above the adapter can ASK instead of assuming.
    # Webull's answers are all False except bracket_entries; that is exactly
    # why this file exists.
    supports_bracket_entry = False      # stop born WITH the entry, one group
    supports_conditional_on_underlying = False   # "buy when SPY touches 761"
    supports_option_streaming = False   # push option quotes, no polling
    supports_streaming_greeks = False   # delta/gamma/theta/vega pushed live
    option_quote_limit_per_min = None   # None = no published cap

    # ---- lifecycle ------------------------------------------------------
    def connect(self):
        """REQUIRED -> the account id, as a string.

        Reads the account list and nothing else. It must NEVER place, cancel
        or modify an order — the bridge calls this at boot, every boot.
        """
        raise NotImplementedError

    # ---- market data ----------------------------------------------------
    def ask_bid(self, occ):
        """REQUIRED -> (ask, bid, raw_row). Raises Refused if it can't."""
        raise NotImplementedError

    def ask_bid_many(self, occs):
        """REQUIRED -> {occ: (ask, bid, raw_row)}. Batch; may be partial."""
        raise NotImplementedError

    def stock_price(self, symbol):
        """REQUIRED -> float. The UNDERLYING's price (round-number hunts)."""
        raise NotImplementedError

    # ---- account --------------------------------------------------------
    def positions(self):
        """REQUIRED -> [dict]. Keys: symbol, side, strike, expiry, qty, fill,
        last, pl, pl_pct, kind. MUST NOT RAISE — return [] when unsure."""
        raise NotImplementedError

    def futures_positions(self):
        """Optional -> [dict]. Return [] when the broker has no futures."""
        return []

    def buying_power(self):
        """REQUIRED -> float or None. None means 'could not read it'."""
        raise NotImplementedError

    # ---- orders ---------------------------------------------------------
    def entry_limit(self, bid, ask):
        """REQUIRED -> float. What to bid given the book. The house rule is
        the caller's price or better, never chasing the ask."""
        raise NotImplementedError

    def order_status(self, order_id):
        """REQUIRED -> (state, filled_qty, avg_price). state is one of
        working / filled / partial / dead / unknown. 'unknown' must never be
        read as 'filled' by anything upstream."""
        raise NotImplementedError

    def open_orders(self, symbol=None):
        """Optional -> [dict]."""
        return []

    def cancel(self, order_id):
        """REQUIRED. Fire-and-forget; callers confirm separately."""
        raise NotImplementedError

    def sell(self, symbol, side, strike, expiry, qty, ref_price=None,
             urgent=False):
        """REQUIRED -> order id. urgent=True crosses the bid to get out."""
        raise NotImplementedError

    def place_stop(self, symbol, side, strike, expiry, qty, fill_price,
                   stop_price=None):
        """REQUIRED -> (order_id, stop_price_actually_placed)."""
        raise NotImplementedError

    def replace_stop(self, old_oid, symbol, side, strike, expiry, qty,
                     fill_price, stop_price=None):
        """Optional -> (order_id, placed). Modify in place so there is never
        a moment with no stop. Return (None, None) if unsupported; the caller
        falls back to cancel-then-place."""
        return None, None

    def last_sell_fill(self, symbol, side, strike, expiry, since=None):
        """REQUIRED -> float or None. What this contract ACTUALLY last sold
        for. None means 'I could not find out' — never a guessed price."""
        raise NotImplementedError

    def flatten(self, symbol):
        """Optional. Close everything in this symbol."""
        raise NotImplementedError

    # ---- capability the adapter exists FOR ------------------------------
    def place_conditional_entry(self, symbol, side, strike, expiry, qty,
                                limit_price, trigger_price, trigger_dir,
                                stop_price=None):
        """THE ONE WEBULL CANNOT DO.

        "When <symbol> the STOCK touches trigger_price (trigger_dir 'below'
        for a pullback into a call, 'above' for a bounce into a put), submit
        a limit buy on the option at limit_price, with stop_price attached."

        Returns an order id, or raises Refused("not supported") — which is
        what BrokerBase does, so pullback.py's polling hunt stays the
        fallback everywhere it isn't available. Nothing calls this yet; it is
        here so a Tradier/Schwab implementation has a defined home.
        """
        raise Refused("%s has no conditional order that triggers off the "
                      "underlying's price" % self.name)


# --------------------------------------------------------------------------
def _webull_factory(cfg, **kw):
    # WebullOptions reads the WHOLE settings dict (it also needs paper keys,
    # the account picker and the quote-client wiring), so it is handed cfg
    # as-is rather than unpacked — deliberately, so nothing drifts.
    from webull_options import WebullOptions
    return WebullOptions(cfg, **kw)


def _tradier_factory(cfg, **kw):
    from tradier import TradierOptions
    t = (cfg.get("execution") or {}).get("tradier") or {}
    return TradierOptions(t.get("access_token"), t.get("account_id"),
                          sandbox=bool(t.get("sandbox")), **kw)


def _tastytrade_factory(cfg, **kw):
    from tastytrade import TastytradeOptions
    t = (cfg.get("execution") or {}).get("tastytrade") or {}
    return TastytradeOptions(username=t.get("username"),
                             password=t.get("password"),
                             remember_token=t.get("remember_token"),
                             account_id=t.get("account_id"),
                             sandbox=bool(t.get("sandbox")), **kw)


_REGISTRY = {
    "webull": _webull_factory,
    "tradier": _tradier_factory,
    "tastytrade": _tastytrade_factory,
}


def get_broker(cfg, which=None, **kw):
    """Build the configured broker. Defaults to Webull, so an untouched
    settings.json behaves exactly as it always has."""
    name = str(which or (cfg.get("execution") or {}).get("broker")
               or "webull").lower().strip()
    make = _REGISTRY.get(name)
    if make is None:
        raise Refused("unknown broker %r — known: %s"
                      % (name, ", ".join(sorted(_REGISTRY))))
    return make(cfg, **kw)


def capabilities(client):
    """What can this broker actually do? For the popup and the log."""
    return {
        "name": getattr(client, "name", type(client).__name__),
        "bracket_entry": bool(getattr(client, "supports_bracket_entry", False)),
        "conditional_on_underlying":
            bool(getattr(client, "supports_conditional_on_underlying", False)),
        "option_streaming":
            bool(getattr(client, "supports_option_streaming", False)),
        "option_quote_limit_per_min":
            getattr(client, "option_quote_limit_per_min", None),
        # 9/3: only tastytrade streams greeks. This is the flag the ratchet
        # would branch on if it ever learns to reason about delta/theta
        # instead of inferring everything from price.
        "streaming_greeks":
            bool(getattr(client, "supports_streaming_greeks", False)),
    }
