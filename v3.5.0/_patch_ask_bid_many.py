    # ------------------------------------------------------------------
    # PASTE THIS INTO webull_options.py, immediately AFTER the existing
    # ask_bid() method. Same indentation — it is a method on the same class.
    # ------------------------------------------------------------------
    def ask_bid_many(self, occs):
        """Quotes for MANY contracts in ONE call. Returns {occ: (ask, bid, row)}.

        Webull's option snapshot endpoint is /market-data/options/snapshots/
        LIST — it takes a list. The single-symbol ask_bid() already probes a
        list shape ([occ]) among its candidates, so the SDK method behind it
        accepts one; this hands it the whole book at once instead.

        Six open positions used to cost six calls per poll. Now they cost one.
        That is the whole reason a 250ms sweep fits inside a 300-per-minute
        limit that a 1-second per-symbol poll would have blown straight past.

        Falls back to looping ask_bid() one at a time if the batched shape is
        refused, so this can never be the reason a stop goes unwatched. The
        working shape is remembered after the first success — the shape hunt
        does not re-run on every sweep.
        """
        occs = [str(o) for o in (occs or []) if o]
        if not occs:
            return {}
        if self.quote_client is not None and self.quote_client is not self:
            return self.quote_client.ask_bid_many(occs)

        # Webull caps a snapshot list; 50 at a time is comfortably under it.
        if len(occs) > 50:
            out = {}
            for i in range(0, len(occs), 50):
                out.update(self.ask_bid_many(occs[i:i + 50]))
            return out

        fns = self._quote_fns()
        if not fns:
            return {}

        joined = ",".join(occs)
        shapes = [((occs,), {}), ((joined,), {}),
                  ((), {"symbols": occs}), ((), {"symbols": joined}),
                  ((occs, "US_OPTION"), {}),
                  ((), {"symbols": occs, "category": "US_OPTION"})]
        # Remember the shape that worked (the 8/24 lesson: a full shape hunt
        # on every call is a dozen real failing HTTP requests a second).
        remembered = getattr(self, "_batch_shape", None)
        if remembered is not None:
            shapes = [remembered] + [s for s in shapes if s != remembered]

        for _name, fn in fns:
            for shape in shapes:
                args, kwargs = shape
                try:
                    self._pace_batch()
                    body = fn(*args, **kwargs)
                except Exception:                       # noqa: BLE001
                    continue
                parsed = self._parse_batch(body, occs)
                if parsed:
                    self._batch_shape = shape
                    return parsed

        # Batched form unavailable on this SDK — fall back one at a time, and
        # say so ONCE so the log explains why sweeps got expensive.
        if not getattr(self, "_warned_no_batch", False):
            self._warned_no_batch = True
            print("[webull] batched option quotes not available on this SDK - "
                  "falling back to one call per contract. Sweeps will be "
                  "slower and eat more of the rate limit.")
        out = {}
        for occ in occs:
            try:
                out[occ] = self.ask_bid(occ)
            except Exception:                           # noqa: BLE001
                continue
        return out

    def _pace_batch(self):
        """Budget-aware spacing.

        When a Budget is attached (the quote bus supplies one) it is the
        authority. Otherwise fall back to an HONEST 200ms — Webull documents
        300 requests per 60 seconds, which is 5 per second, NOT the 6.67 per
        second the old 150ms spacer was quietly producing. That overshoot is
        where the 8/9 wall of 429s came from.
        """
        b = getattr(self, "budget", None)
        if b is not None:
            b.take(1, priority=False, timeout=5.0)
            return
        now = time.time()
        wait = 0.20 - (now - getattr(self, "_last_call", 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _parse_batch(self, body, occs):
        """Pull {occ: (ask, bid, row)} out of whatever shape came back.

        Each snapshot row names its contract in one of several fields
        depending on endpoint version. A row we cannot match to a REQUESTED
        contract is dropped, never guessed at — a price attached to the wrong
        contract would sell the wrong position.
        """
        rows = body
        if isinstance(body, dict):
            for k in ("data", "result", "list", "snapshots", "items"):
                if isinstance(body.get(k), list):
                    rows = body[k]
                    break
        if not isinstance(rows, list):
            return {}
        want = {o.upper(): o for o in occs}
        out = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = None
            for k in ("symbol", "instrument_id", "instrumentId", "occ",
                      "option_symbol", "optionSymbol", "tickerId", "ticker"):
                v = row.get(k)
                if v is not None and str(v).upper() in want:
                    sym = want[str(v).upper()]
                    break
            if sym is None:
                continue
            ask = _find(row, "ask_price", "askPrice", "ask", "bestAsk",
                        "best_ask")
            bid = _find(row, "bid_price", "bidPrice", "bid", "bestBid",
                        "best_bid")
            try:
                ask = float(ask) if ask not in (None, "") else None
            except (TypeError, ValueError):
                ask = None
            try:
                bid = float(bid) if bid not in (None, "") else None
            except (TypeError, ValueError):
                bid = None
            if ask is None and bid is None:
                continue
            out[sym] = (ask, bid, row)
        return out
