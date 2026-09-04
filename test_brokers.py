"""test_brokers.py — prove the Tradier and tastytrade adapters against a FAKE
broker before a single real credential exists (9/3/26).

Neither adapter has touched a live server, so the honest risk was: "the code
compiles, but does it actually PARSE what the broker sends?" This stands up a
local HTTP server that answers with the response shapes taken from each
broker's published docs, points the adapter at it, and checks that real
positions, quotes, fills and order states come out the other side.

What this DOES prove: the request paths, the auth headers, the JSON walking,
the OCC symbol building and parsing, the object-vs-list quirks, and that
positions() never raises.

What it CANNOT prove: that the live servers really send these shapes. That is
what TradierOptions.verify() / TastytradeOptions.verify() are for, on day one
with a real key. If a live response differs, this file is where the fix gets
pinned so it never regresses.

Run:  python test_brokers.py
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  FAIL  " + msg)


# --------------------------------------------------------------------------
# Canned responses, shaped from the published docs.
TRADIER = {
    "/v1/markets/quotes": {"quotes": {"quote": [
        {"symbol": "SPY", "last": 765.11, "bid": 765.10, "ask": 765.12},
        {"symbol": "SPY260904P00771000", "bid": 2.02, "ask": 2.06},
    ]}},
    # ONE position comes back as an object, not a list — the classic Tradier
    # trap that _one() exists to absorb.
    "/v1/accounts/ACCT/positions": {"positions": {"position":
        {"symbol": "SPY260904P00771000", "quantity": 1, "cost_basis": 202.0}}},
    "/v1/user/profile": {"profile": {"account": {"account_number": "ACCT"}}},
    "/v1/accounts/ACCT/balances": {"balances": {"option_buying_power": 514.22}},
    "/v1/accounts/ACCT/orders/9001": {"order": {
        "id": 9001, "status": "filled", "exec_quantity": 1,
        "avg_fill_price": 1.87}},
    "/v1/accounts/ACCT/orders": {"orders": {"order": [
        {"id": 9001, "status": "filled", "side": "sell_to_close",
         "option_symbol": "SPY260904P00771000", "avg_fill_price": 1.87},
        {"id": 9002, "status": "open", "side": "buy_to_open",
         "option_symbol": "SPY260904C00650000"},
    ]}},
}

TASTY = {
    "/sessions": {"data": {"session-token": "TOK123",
                           "remember-token": "REM456"}},
    "/customers/me/accounts": {"data": {"items": [
        {"account": {"account-number": "5WX00001"}}]}},
    "/accounts/5WX00001/positions": {"data": {"items": [
        {"symbol": "SPY   260904P00771000", "instrument-type": "Equity Option",
         "underlying-symbol": "SPY", "quantity": 1,
         "average-open-price": 2.02, "close-price": 1.87}]}},
    "/accounts/5WX00001/balances": {"data": {"items": [
        {"derivative-buying-power": 514.22}]}},
    "/accounts/5WX00001/orders/7001": {"data": {"items": [
        {"id": 7001, "status": "Filled", "legs": [
            {"symbol": "SPY   260904P00771000", "action": "Sell to Close",
             "fills": [{"quantity": 1, "fill-price": 1.87}]}]}]}},
    "/accounts/5WX00001/orders": {"data": {"items": [
        {"id": 7001, "status": "Filled", "legs": [
            {"symbol": "SPY   260904P00771000", "action": "Sell to Close",
             "fills": [{"quantity": 1, "fill-price": 1.87}]}]}]}},
    "/market-data/by-type": {"data": {"items": [
        {"symbol": "SPY", "last": 765.11, "bid": 765.10, "ask": 765.12}]}},
    "/api-quote-tokens": {"data": {"token": "DX", "dxlink-url": "wss://x"}},
}


class Handler(BaseHTTPRequestHandler):
    table = {}
    seen = []

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        path = self.path.split("?")[0]
        Handler.seen.append((self.command, path,
                             self.headers.get("Authorization")))
        # POST /orders -> pretend the broker accepted it
        if self.command == "POST" and path.endswith("/orders"):
            return self._send({"order": {"id": 12345},
                               "data": {"order": {"id": 12345}}})
        if self.command == "DELETE":
            return self._send({"order": {"id": 12345, "status": "ok"}})
        body = Handler.table.get(path)
        if body is None:
            return self._send({"error": "no canned response for " + path}, 404)
        self._send(body)

    def do_GET(self):
        self._route()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
        except Exception:                               # noqa: BLE001
            pass
        self._route()

    def do_DELETE(self):
        self._route()

    def log_message(self, *a):
        pass                                            # keep the run quiet


def serve(table):
    Handler.table = table
    Handler.seen = []
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


# --------------------------------------------------------------------------
def test_tradier():
    import tradier
    srv, base = serve(TRADIER)
    try:
        b = tradier.TradierOptions("TOKEN", "ACCT")
        b.base = base

        ok(b.connect() == "ACCT",
           "tradier connect() settles the account id read-only")

        px = b.stock_price("SPY")
        ok(abs(px - 765.11) < 0.001, "tradier stock_price -> 765.11, got %s" % px)

        q = b.ask_bid("SPY260904P00771000")
        ok(q[0] == 2.06 and q[1] == 2.02,
           "tradier ask_bid -> (2.06, 2.02), got %s" % (q[:2],))

        rows = b.positions()
        ok(len(rows) == 1, "tradier positions -> 1 row from an OBJECT (not a "
                           "list) — the _one() quirk, got %d" % len(rows))
        r = rows[0] if rows else {}
        ok(r.get("symbol") == "SPY" and r.get("strike") == 771.0
           and r.get("side") == "PUTS" and r.get("expiry") == "2026-09-04",
           "tradier positions parses the OCC symbol, got %s"
           % {k: r.get(k) for k in ("symbol", "strike", "side", "expiry")})
        ok(r.get("fill") == 2.02,
           "tradier turns cost_basis 202.0 x1 into a 2.02 per-share fill, "
           "got %s" % r.get("fill"))

        ok(b.buying_power() == 514.22,
           "tradier buying_power -> 514.22, got %s" % b.buying_power())

        st, fq, fp = b.order_status("9001")
        ok((st, fq, fp) == ("filled", 1, 1.87),
           "tradier order_status -> ('filled',1,1.87), got %s" % ((st, fq, fp),))

        last = b.last_sell_fill("SPY", "PUTS", 771.0, "2026-09-04")
        ok(last == 1.87,
           "tradier last_sell_fill finds the REAL 1.87 sell, got %s" % last)

        oid, stop = b.place_stop("SPY", "PUTS", 771.0, "2026-09-04", 1, 2.02,
                                 stop_price=1.82)
        ok(oid == "12345" and stop == 1.82,
           "tradier place_stop -> id + the stop it actually placed, got %s"
           % ((oid, stop),))
        posted = [s for s in Handler.seen if s[0] == "POST"]
        ok(posted and posted[0][2] == "Bearer TOKEN",
           "tradier sends 'Bearer <token>' auth, got %s"
           % (posted[0][2] if posted else None))

        try:
            b.place_conditional_entry("SPY", "CALLS", 650, "2026-09-04", 1,
                                      1.20, 761.0, "below")
            ok(False, "tradier conditional entry must REFUSE until verified")
        except Exception as e:                          # noqa: BLE001
            ok("UNVERIFIED" in str(e) or "verified" in str(e),
               "tradier conditional entry refuses loudly, got %s" % str(e)[:60])
    finally:
        srv.shutdown()


def test_tastytrade():
    import tastytrade
    srv, base = serve(TASTY)
    try:
        b = tastytrade.TastytradeOptions(username="u", password="p",
                                         account_id="5WX00001")
        b.base = base

        occ = b.tasty_occ("SPY", "2026-09-04", "PUTS", 771)
        ok(occ == "SPY   260904P00771000",
           "tastytrade pads the root to 6 chars, got %r" % occ)
        back = tastytrade._parse_tasty_occ(occ)
        ok(back and back["strike"] == 771.0 and back["side"] == "PUTS"
           and back["expiry"] == "2026-09-04",
           "tastytrade OCC round-trips, got %s" % back)

        ok(b.connect() == "5WX00001",
           "tastytrade connect() logs in and settles the account number")
        ok(abs(b.stock_price("SPY") - 765.11) < 0.001, "tastytrade stock_price")

        rows = b.positions()
        ok(len(rows) == 1, "tastytrade positions -> 1 row, got %d" % len(rows))
        r = rows[0] if rows else {}
        ok(r.get("symbol") == "SPY" and r.get("strike") == 771.0
           and r.get("side") == "PUTS",
           "tastytrade positions parses the padded OCC, got %s"
           % {k: r.get(k) for k in ("symbol", "strike", "side")})

        ok(b.buying_power() == 514.22, "tastytrade buying_power -> 514.22")

        st, fq, fp = b.order_status("7001")
        ok((st, fq, fp) == ("filled", 1, 1.87),
           "tastytrade order_status reads PER-LEG fills, got %s"
           % ((st, fq, fp),))

        last = b.last_sell_fill("SPY", "PUTS", 771.0, "2026-09-04")
        ok(last == 1.87, "tastytrade last_sell_fill -> 1.87, got %s" % last)

        auths = [s[2] for s in Handler.seen if s[2]]
        ok(auths and auths[0] == "TOK123",
           "tastytrade sends the RAW session token (no 'Bearer '), got %r"
           % (auths[0] if auths else None))
        ok(b._remember == "REM456",
           "tastytrade captures the remember-token so the password can leave "
           "settings.json, got %r" % b._remember)

        try:
            b.place_conditional_entry("SPY", "CALLS", 650, "2026-09-04", 1,
                                      1.20, 761.0, "below")
            ok(False, "tastytrade conditional entry must REFUSE until verified")
        except Exception as e:                          # noqa: BLE001
            ok("UNVERIFIED" in str(e) or "cert" in str(e),
               "tastytrade conditional entry refuses loudly, got %s"
               % str(e)[:60])
    finally:
        srv.shutdown()


def test_contract():
    """Every adapter must satisfy the same interface, and a broken server must
    never turn into 'you are flat'."""
    import broker, tradier, tastytrade
    for cls in (tradier.TradierOptions, tastytrade.TastytradeOptions):
        missing = [m for m in dir(broker.BrokerBase)
                   if not m.startswith("_")
                   and callable(getattr(broker.BrokerBase, m))
                   and not hasattr(cls, m)]
        ok(not missing, "%s implements the whole contract, missing %s"
           % (cls.__name__, missing))

    # positions() MUST NOT RAISE when the server is dead — [] means "no
    # verdict", and upstream never reads that as "flat" (the 8/31 ghost-SPY
    # lesson). Point both at a port with nothing on it.
    t = tradier.TradierOptions("TOKEN", "ACCT")
    t.base = "http://127.0.0.1:9"
    t.timeout = 0.4
    ok(t.positions() == [],
       "tradier positions() returns [] on a dead server instead of raising")

    y = tastytrade.TastytradeOptions(username="u", password="p",
                                     account_id="A")
    y.base = "http://127.0.0.1:9"
    y.timeout = 0.4
    ok(y.positions() == [],
       "tastytrade positions() returns [] on a dead server instead of raising")


def test_default_unchanged():
    """The whole point: adding brokers changed nothing about Webull."""
    import broker
    cfg = json.load(open("settings.json", encoding="utf-8"))
    c = broker.get_broker(cfg)
    ok(type(c).__name__ == "WebullOptions",
       "settings with no 'broker' key still builds Webull, got %s"
       % type(c).__name__)
    caps = broker.capabilities(c)
    ok(caps["bracket_entry"] is True
       and caps["conditional_on_underlying"] is False
       and caps["option_streaming"] is False,
       "Webull reports its real capabilities, got %s" % caps)


if __name__ == "__main__":
    print("BROKER ADAPTER TESTS (against a fake server — no credentials needed)")
    test_tradier()
    test_tastytrade()
    test_contract()
    test_default_unchanged()
    if FAILS:
        print("\n%d FAILED" % len(FAILS))
        sys.exit(1)
    print("\nAll broker-adapter checks passed. Both adapters parse the "
          "documented response shapes correctly, refuse conditional entries "
          "until verified, and never turn a dead server into 'you are flat'. "
          "What remains unproven is whether the LIVE servers match these "
          "shapes — run verify() the day a real key exists.")
