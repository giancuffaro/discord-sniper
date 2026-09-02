"""STREAM BUS (9/2, G: "stream all data from the best source we can").

Webull pushes STOCK/ETF/futures prices over MQTT (developer.webull.com
market-data-api/getting-started: DataStreamingClient). Options are NOT
carried (see v3.5.0/OPTIONS-BROKER-REFERENCE.md) — those stay on the
batched 1/s quote bus. This module streams the UNDERLYINGS: every symbol
the round-number pullback is hunting, every swing's stock level, every
"underlying at fill" — so a $762 touch is caught the tick it prints
instead of on the next HTTP poll.

Design: one MQTT connection (limit is 5 per app key), one daemon thread,
a dict of the freshest price per symbol. webull_options.stock_price()
asks here first; a price older than STALE_S is ignored and the old HTTP
path answers as before. Nothing here can block trading: every call is
try/except and the fallback is exactly yesterday's behaviour.
"""
import threading
import time

STALE_S = 3.0                      # a pushed price older than this is ignored
ETFS = {"SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "XLF", "XLE", "XLK",
        "XLV", "XLI", "XLP", "XLY", "XLU", "XLB", "XLC", "XLRE", "SMH", "SOXX",
        "SOXL", "SOXS", "TQQQ", "SQQQ", "SPXL", "SPXS", "UVXY", "VXX", "ARKK",
        "XBI", "IBIT", "KWEB", "FXI", "EEM", "EFA", "HYG", "LQD", "IEF", "VOO",
        "IVV", "RSP", "MDY", "XOP", "XRT", "XHB", "KRE", "KBE", "UNG", "USO"}


class StockStream:
    def __init__(self, app_key, app_secret, region="us", log=print):
        self.app_key, self.app_secret, self.region = app_key, app_secret, region
        self.log = log or (lambda *a, **k: None)
        self._px = {}              # SYM -> (price, ts)
        self._want = set()         # symbols we want subscribed
        self._have = set()         # symbols the live connection has
        self._lock = threading.Lock()
        self._client = None
        self._connected = False
        self._thread = None
        self.msgs = 0
        self.session = "sniper-%d" % int(time.time())

    # ---- public --------------------------------------------------------
    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def watch(self, symbol):
        s = str(symbol or "").upper().strip()
        if not s:
            return
        with self._lock:
            if s in self._want:
                return
            self._want.add(s)
        self._subscribe([s])

    def price(self, symbol, max_age=STALE_S):
        """Freshest pushed price, or None if we have nothing fresh."""
        s = str(symbol or "").upper().strip()
        with self._lock:
            v = self._px.get(s)
        if not v:
            self.watch(s)          # first ask = start streaming it
            return None
        px, ts = v
        return px if (time.time() - ts) <= max_age else None

    def status(self):
        with self._lock:
            return {"connected": self._connected, "symbols": sorted(self._have),
                    "msgs": self.msgs, "fresh": {k: v[0] for k, v in self._px.items()
                                                 if time.time() - v[1] <= STALE_S}}

    # ---- internals -----------------------------------------------------
    def _subscribe(self, syms):
        cli = self._client
        if cli is None or not self._connected:
            return                 # on_connect will subscribe everything wanted
        try:
            etfs = [s for s in syms if s in ETFS]
            stks = [s for s in syms if s not in ETFS]
            if etfs:
                cli.subscribe(etfs, "US_ETF", ["SNAPSHOT", "TICK"])
            if stks:
                cli.subscribe(stks, "US_STOCK", ["SNAPSHOT", "TICK"])
            with self._lock:
                self._have.update(syms)
        except Exception as e:                          # noqa: BLE001
            self.log("[stream] subscribe failed for %s: %s" % (syms, str(e)[:80]))

    def _on_connect(self, client, api_client, session_id):
        self._client = client
        self._connected = True
        with self._lock:
            want = sorted(self._want)
            self._have.clear()
        self.log("[stream] connected (%s) — %d symbols wanted" % (session_id, len(want)))
        if want:
            self._subscribe(want)

    def _on_message(self, client, topic, quotes):
        try:
            self.msgs += 1
            # SDK hands parsed protobuf; Snapshot has .price, Tick has .price,
            # both carry .basic.symbol. Tolerate dict shapes too.
            sym = None
            px = None
            b = getattr(quotes, "basic", None)
            if b is not None:
                sym = getattr(b, "symbol", None)
            if sym is None and isinstance(quotes, dict):
                sym = (quotes.get("basic") or {}).get("symbol") or quotes.get("symbol")
            p = getattr(quotes, "price", None)
            if p is None and isinstance(quotes, dict):
                p = quotes.get("price")
            if p in (None, ""):
                # QUOTE topic: derive a mid from the book
                asks = getattr(quotes, "asks", None) or (quotes.get("asks") if isinstance(quotes, dict) else None)
                bids = getattr(quotes, "bids", None) or (quotes.get("bids") if isinstance(quotes, dict) else None)
                try:
                    a = float(getattr(asks[0], "price", None) or asks[0]["price"])
                    bb = float(getattr(bids[0], "price", None) or bids[0]["price"])
                    p = (a + bb) / 2.0
                except Exception:                       # noqa: BLE001
                    p = None
            if sym and p not in (None, ""):
                px = float(p)
                with self._lock:
                    self._px[str(sym).upper()] = (px, time.time())
        except Exception:                               # noqa: BLE001
            pass

    def _run(self):
        try:
            from webull.data.data_streaming_client import DataStreamingClient
        except Exception as e:                          # noqa: BLE001
            self.log("[stream] SDK has no DataStreamingClient (%s) — HTTP prices only"
                     % str(e)[:60])
            return
        while True:
            try:
                # Production hosts spelled out (docs: api.webull.com /
                # data-api.webull.com) so nothing can drift to sandbox.
                try:
                    cli = DataStreamingClient(self.app_key, self.app_secret,
                                              self.region, self.session,
                                              http_host="api.webull.com",
                                              mqtt_host="data-api.webull.com")
                except TypeError:
                    cli = DataStreamingClient(self.app_key, self.app_secret,
                                              self.region, self.session)
                cli.on_connect_success = self._on_connect
                cli.on_quotes_message = self._on_message
                cli.on_subscribe_success = lambda c, a, s: None
                self._client = cli
                cli.connect_and_loop_forever()          # blocks
            except Exception as e:                      # noqa: BLE001
                self.log("[stream] dropped (%s) — reconnecting in 15s" % str(e)[:80])
            self._connected = False
            time.sleep(15)
            self.session = "sniper-%d" % int(time.time())   # never reuse an id
