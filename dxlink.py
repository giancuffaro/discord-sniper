"""dxlink.py — live option GREEKS from tastytrade's dxfeed, with NO new packages.

WHY THIS FILE EXISTS AND WHY IT IS WRITTEN THIS WAY (9/4/26)
------------------------------------------------------------
G wants greeks so the machine can reason about breathing room instead of
guessing at it. tastytrade streams them over DXLink, which is JSON over a
WebSocket.

The obvious move is `pip install websockets`. We are not doing that. On 9/2 a
streaming experiment upgraded four packages past what the bridge's Webull SDK
pins allow; the running bridge survived but the NEXT restart would have failed
to import, and "FIX SDK DEPS.bat" exists solely to undo that. A dependency
that can brick the thing that places real orders is not worth a convenience.

So the WebSocket client here is ~150 lines of stdlib: socket + ssl + struct +
base64 + hashlib. RFC 6455 client framing is genuinely small once you drop the
parts we don't need (we never send binary, we decline compression). Nothing
here can move a pin or break the bridge's imports.

THE ONE SAFETY RULE
-------------------
tastytrade hands out a DEMO token on an unfunded account — the URL literally
ends in /delayed and the token says `level: demo`. Delayed greeks that look
live are worse than no greeks, so `GreeksBus` refuses to serve or tape
anything unless the token level is live, and says so once. See `live_level()`.

WHAT IT PRODUCES
  greeks_tape.csv :  ts,occ,price,iv,delta,gamma,theta,vega,rho
  .get(occ)       :  the newest greeks dict for one contract, or None

option_tape.csv is deliberately left alone — its ts,occ,bid,ask schema is read
by other tools and a widened column set would break them silently.
"""
import base64
import csv
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"     # RFC 6455

# tastytrade access tokens live 15 minutes. Re-auth at 10, in place, on the
# same socket — a third of the life left is plenty of margin for a slow
# token fetch, and it means the feed never has to be rebuilt to stay signed
# in. Before this, the socket died every 15 minutes and the greeks went dark
# for as long as the reconnect took.
REAUTH_AFTER = 600.0

# dxfeed event fields we ask for, in the order they come back.
GREEK_FIELDS = ["eventType", "eventSymbol", "price", "volatility",
                "delta", "gamma", "theta", "rho", "vega"]

# STREAMING OPTION QUOTES (9/7) — the same socket, a second event type.
#
# Webull has NO option streaming. Every option bid/ask we own comes from a
# 1-per-second poll against a 60/min door, so with N open positions each
# contract is looked at once every N seconds. That is the hard ceiling on
# how fast any premium stop can react, and the reason the ratchet rungs
# have to be spaced wider than our worst-case staleness.
#
# DXLink carries Quote events — bidPrice/askPrice — over the connection we
# are ALREADY holding open for greeks. No new socket, no new key, no cost.
#
# IT IS SHADOW ONLY. Nothing in the exit path reads it. tastytrade's quote
# is not Webull's book: both derive from the NBBO but they are different
# snapshots at different instants, and the broker filling you is the one
# whose book should price your order. This tapes both side by side so we
# can find out — from our own contracts — how far apart they actually are
# and whether a stop would have fired at a different moment. A week of that
# decides whether it ever gets promoted. Not before.
QUOTE_FIELDS = ["eventType", "eventSymbol", "bidPrice", "askPrice",
                "bidSize", "askSize"]


# ---------------------------------------------------------------- WebSocket
class WS:
    """A minimal RFC 6455 TEXT-frame client. Stdlib only.

    Deliberately not a general library: no compression, no binary, no
    continuation-fragment sending. It reads fragmented frames (servers do
    send those) and answers pings, which is all DXLink needs from us.
    """

    def __init__(self, url, timeout=20.0):
        if url.startswith("wss://"):
            host_path, secure, port = url[6:], True, 443
        elif url.startswith("ws://"):
            host_path, secure, port = url[5:], False, 80
        else:
            raise ValueError("not a websocket url: %s" % url)
        host, _, path = host_path.partition("/")
        if ":" in host:
            host, _, p = host.partition(":")
            port = int(p)
        self.host, self.path = host, "/" + path
        self._buf = b""
        self.closed = False

        raw = socket.create_connection((host, port), timeout=timeout)
        if secure:
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=host)
        raw.settimeout(timeout)
        self.sock = raw

        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\n"
               "Host: %s\r\n"
               "Upgrade: websocket\r\n"
               "Connection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n"
               "User-Agent: discord-sniper/1.0\r\n\r\n"
               % (self.path, host, key))
        self.sock.sendall(req.encode())

        head = self._read_until(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise IOError("websocket handshake refused: %s"
                          % head.split(b"\r\n")[0][:120])
        want = base64.b64encode(
            hashlib.sha1((key + GUID).encode()).digest()).decode().lower()
        if want.encode() not in head.lower():
            raise IOError("websocket handshake key mismatch — not a real "
                          "websocket endpoint")

    # -- byte plumbing ---------------------------------------------------
    def _read_until(self, marker):
        while marker not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError("socket closed during handshake")
            self._buf += chunk
        head, _, rest = self._buf.partition(marker)
        self._buf = rest
        return head + marker

    def _read_exactly(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise IOError("socket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    # -- frames ----------------------------------------------------------
    def _send_frame(self, opcode, payload=b""):
        if self.closed:
            raise IOError("send on a closed websocket")
        head = bytearray()
        head.append(0x80 | opcode)                       # FIN + opcode
        n = len(payload)
        if n < 126:
            head.append(0x80 | n)                        # MASK + len
        elif n < (1 << 16):
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head) + masked)

    def send(self, obj):
        self._send_frame(0x1, json.dumps(obj).encode())

    def recv(self):
        """Next TEXT message as a dict, or None on a non-data frame.

        Answers ping with pong and handles fragmentation. Raises on close.
        """
        data = b""
        opcode = None
        while True:
            b0, b1 = self._read_exactly(2)
            fin = b0 & 0x80
            op = b0 & 0x0F
            masked = b1 & 0x80
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read_exactly(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read_exactly(8))[0]
            key = self._read_exactly(4) if masked else None
            payload = self._read_exactly(ln) if ln else b""
            if key:
                payload = bytes(c ^ key[i % 4] for i, c in enumerate(payload))

            if op == 0x8:                                # close
                self.closed = True
                raise IOError("server closed the websocket")
            if op == 0x9:                                # ping -> pong
                self._send_frame(0xA, payload)
                continue
            if op == 0xA:                                # pong
                continue
            if op in (0x1, 0x2):
                opcode = op
                data = payload
            elif op == 0x0:                              # continuation
                data += payload
            if fin:
                break
        if opcode != 0x1 or not data:
            return None
        try:
            return json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            return None

    def close(self):
        try:
            if not self.closed:
                self._send_frame(0x8, b"\x03\xe8")
        except Exception:                                # noqa: BLE001
            pass
        self.closed = True
        try:
            self.sock.close()
        except Exception:                                # noqa: BLE001
            pass


# ------------------------------------------------------------ occ <-> dxfeed
def occ_to_dx(occ):
    """NVDA260904C00235000 -> .NVDA260904C235

    dxfeed wants the strike written plainly, no zero padding and no trailing
    .0 — `.SPY260918C660`, not `.SPY260918C660.0`. Half-strikes keep their
    decimal (`.IWM260904P243.5`).
    """
    s = str(occ or "").strip().replace(" ", "")          # tastytrade pads roots
    if len(s) < 15:
        return None
    tail = s[-15:]                                       # YYMMDD C/P + 8 digits
    root, ymd, cp, strike8 = s[:-15], tail[:6], tail[6], tail[7:]
    if cp not in ("C", "P") or not strike8.isdigit():
        return None
    k = int(strike8) / 1000.0
    ks = ("%.3f" % k).rstrip("0").rstrip(".")
    return ".%s%s%s%s" % (root, ymd, cp, ks)


def live_level(level, url=""):
    """Is this token good for REAL-TIME data?

    An unfunded tastytrade account gets `level: demo` on a URL ending
    /delayed. Delayed greeks that get mistaken for live would put a stop in
    the wrong place off stale gamma, so this is checked, not assumed.
    """
    lv = str(level or "").strip().lower()
    u = str(url or "").lower()
    if "delayed" in u or "demo" in u:
        return False
    return lv not in ("demo", "delayed", "")


# ---------------------------------------------------------------- the bus
class GreeksBus:
    """Streams greeks for whatever contracts it is told to watch.

    Give it a `token_fn` that returns tastytrade's /api-quote-tokens payload
    (the adapter's `quote_token()`), because the token expires and has to be
    re-fetched on reconnect.
    """

    def __init__(self, token_fn, log=None, tape=None, allow_delayed=False):
        self._token_fn = token_fn
        self._reauths = 0
        self._log = log or (lambda *a, **k: None)
        self._tape = tape
        self._allow_delayed = bool(allow_delayed)
        self._want = set()                 # dxfeed symbols
        self._greeks = {}                  # dx symbol -> (dict, ts)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._ws = None
        self.live = False                  # is the CURRENT feed real-time?
        self.level = None
        self.connected = False
        self.events = 0
        self._told_delayed = False
        # SHADOW QUOTE FEED (9/7). Streamed option bid/ask on the same
        # socket. want_quotes can be switched off from settings if the extra
        # event type ever misbehaves; the greeks feed is unaffected either
        # way, because they are separate event types on one channel.
        self._quotes = {}                  # dx symbol -> (dict, ts)
        self._qtape = None
        self.quote_events = 0
        self.want_quotes = True

    # -- what to watch ---------------------------------------------------
    def watch(self, occ):
        dx = occ_to_dx(occ)
        if not dx:
            return
        with self._lock:
            if dx in self._want:
                return
            self._want.add(dx)
        self._subscribe([dx])

    def unwatch(self, occ):
        dx = occ_to_dx(occ)
        with self._lock:
            self._want.discard(dx)
            self._greeks.pop(dx, None)
            self._quotes.pop(dx, None)

    def quote_tape_to(self, path):
        """Where to record the streamed bid/ask. Set before start()."""
        self._qtape = path

    def get(self, occ, max_age=30.0):
        """Newest greeks for a contract, or None. Never returns delayed data
        as if it were live, and never returns a stale row."""
        if not self.live:
            return None
        dx = occ_to_dx(occ)
        with self._lock:
            row = self._greeks.get(dx)
        if not row:
            return None
        g, ts = row
        if max_age and (time.time() - ts) > max_age:
            return None
        return g

    def status(self):
        with self._lock:
            n = len(self._greeks)
        return {"connected": self.connected, "live": self.live,
                "level": self.level, "watching": len(self._want),
                "with_greeks": n, "events": self.events}

    # -- lifecycle -------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:                                # noqa: BLE001
            pass

    def _subscribe(self, dxs):
        ws = self._ws
        if not ws or not dxs:
            return
        try:
            add = [{"type": "Greeks", "symbol": d} for d in dxs]
            if self.want_quotes:
                # Same contracts, same channel, second event type. Costs one
                # extra entry in a subscription message, not a second socket.
                add += [{"type": "Quote", "symbol": d} for d in dxs]
            ws.send({"type": "FEED_SUBSCRIPTION", "channel": 1, "add": add})
        except Exception:                                # noqa: BLE001
            pass          # the reconnect re-subscribes everything anyway

    def _run(self):
        backoff = 2.0
        while not self._stop.is_set():
            try:
                self._session()
                backoff = 2.0
            except Exception as e:                       # noqa: BLE001
                self.connected = False
                if not self._stop.is_set():
                    self._log("[greeks] %s — retrying in %.0fs"
                              % (str(e)[:120], backoff))
            self._stop.wait(backoff)
            backoff = min(60.0, backoff * 2)

    def _session(self):
        d = self._token_fn() or {}
        url = d.get("dxlink-url") or d.get("websocket-url")
        tok = d.get("token")
        self.level = d.get("level")
        if not url or not tok:
            raise IOError("no dxlink token available")

        self.live = live_level(self.level, url)
        if not self.live and not self._allow_delayed:
            if not self._told_delayed:
                self._told_delayed = True
                self._log("[greeks] tastytrade handed back a '%s' token on %s "
                          "— that is DELAYED data. Not connecting: delayed "
                          "greeks that look live would move a stop off stale "
                          "gamma. Fund the account and this switches itself on."
                          % (self.level, url))
            raise IOError("delayed feed — standing down")

        ws = WS(url)
        self._ws = ws
        try:
            # THE HANDSHAKE IS SEQUENTIAL, NOT A BURST (9/4). Firing SETUP,
            # AUTH, CHANNEL_REQUEST and FEED_SETUP back to back gets you
            # "AUTH step missing" from the real endpoint, forever, while the
            # socket stays happily connected — a silent no-data failure.
            # Each step waits for the server to say it is ready.
            ws.send({"type": "SETUP", "channel": 0, "version": "0.1-ds/1.0",
                     "keepaliveTimeout": 60, "acceptKeepaliveTimeout": 60})
            self._await(ws, lambda m: m.get("type") == "SETUP", "SETUP")

            ws.send({"type": "AUTH", "channel": 0, "token": tok})
            self._await(ws,
                        lambda m: (m.get("type") == "AUTH_STATE"
                                   and m.get("state") == "AUTHORIZED"),
                        "AUTH")

            ws.send({"type": "CHANNEL_REQUEST", "channel": 1,
                     "service": "FEED", "parameters": {"contract": "AUTO"}})
            self._await(ws, lambda m: m.get("type") == "CHANNEL_OPENED",
                        "CHANNEL_OPENED")

            _accept = {"Greeks": GREEK_FIELDS}
            if self.want_quotes:
                _accept["Quote"] = QUOTE_FIELDS
            ws.send({"type": "FEED_SETUP", "channel": 1,
                     "acceptEventFields": _accept})
            self._await(ws, lambda m: m.get("type") == "FEED_CONFIG",
                        "FEED_CONFIG")

            with self._lock:
                pending = sorted(self._want)
            if pending:
                self._subscribe(pending)
            self.connected = True
            self._log("[greeks] connected — %s feed, %d contract(s)"
                      % (self.level or "?", len(pending)))

            last_ka = time.time()
            authed_at = time.time()
            while not self._stop.is_set():
                if time.time() - last_ka > 25:
                    ws.send({"type": "KEEPALIVE", "channel": 0})
                    last_ka = time.time()
                # RE-AUTH BEFORE THE TOKEN DIES (9/7). tastytrade access
                # tokens last 15 minutes. We used to ride one until the
                # server said "your authentication token has expired,
                # reauthentication is required" and dropped the socket —
                # then the outer loop rebuilt the whole session. It healed
                # itself, but every 15 minutes there was a hole in the
                # greeks, and greeks feed the entry math and the stop-room
                # numbers. A hole you reconnect out of is still a hole.
                #
                # So: fetch a fresh token and re-AUTH IN PLACE on the same
                # socket, well before expiry. The subscriptions live on
                # channel 1 and are untouched, so no data is missed. If the
                # re-auth fails we raise and the outer loop reconnects —
                # exactly what happened before, so this can only be better.
                if time.time() - authed_at > REAUTH_AFTER:
                    d2 = self._token_fn() or {}
                    tok2 = d2.get("token")
                    if not tok2:
                        raise IOError("no dxlink token on re-auth")
                    ws.send({"type": "AUTH", "channel": 0, "token": tok2})
                    self._await(ws,
                                lambda m: (m.get("type") == "AUTH_STATE"
                                           and m.get("state") == "AUTHORIZED"),
                                "RE-AUTH")
                    authed_at = time.time()
                    self._reauths += 1
                    if self._reauths in (1, 10, 50):
                        self._log("[greeks] token refreshed in place (%d) — "
                                  "no reconnect, no gap in the feed"
                                  % self._reauths)
                try:
                    msg = ws.recv()
                except socket.timeout:
                    continue
                if not msg:
                    continue
                t = msg.get("type")
                if t == "KEEPALIVE":
                    ws.send({"type": "KEEPALIVE", "channel": 0})
                    last_ka = time.time()
                elif t == "ERROR":
                    self._log("[greeks] server error: %s"
                              % str(msg.get("message") or msg)[:140])
                    # If it is specifically an auth complaint, do not wait
                    # for the clock — re-auth on the next pass.
                    _m = str(msg.get("message") or "").lower()
                    if "auth" in _m or "expired" in _m:
                        authed_at = 0.0
                elif t == "AUTH_STATE" and msg.get("state") == "AUTHORIZED":
                    authed_at = time.time()     # server confirmed us again
                elif t == "FEED_DATA":
                    self._absorb(msg.get("data"))
        finally:
            self.connected = False
            self._ws = None
            ws.close()

    def _await(self, ws, test, what, seconds=15.0):
        """Read until the server says `what` happened. Data frames that
        arrive early are absorbed rather than dropped, and an ERROR is raised
        with the server's own words instead of timing out silently."""
        end = time.time() + seconds
        while time.time() < end:
            try:
                m = ws.recv()
            except socket.timeout:
                continue
            if not m:
                continue
            if m.get("type") == "KEEPALIVE":
                ws.send({"type": "KEEPALIVE", "channel": 0})
                continue
            if m.get("type") == "FEED_DATA":
                self._absorb(m.get("data"))
                continue
            if m.get("type") == "ERROR":
                raise IOError("dxlink refused %s: %s"
                              % (what, str(m.get("message") or m)[:120]))
            if test(m):
                return m
        raise IOError("dxlink never confirmed %s" % what)

    def _absorb(self, data):
        """FEED_DATA arrives either as a list of dicts (COMPACT off) or as
        ["Greeks", [flat, values, ...]] — handle both, guess at neither.

        NOW TWO EVENT TYPES SHARE THIS CHANNEL. The compact form names its
        type in data[0], and the field COUNT differs (9 for Greeks, 6 for
        Quote) — so unflattening a Quote payload with the Greeks stride
        would produce rows that look plausible and are pure garbage: a
        bidPrice read as `price`, an askPrice read as `volatility`, and a
        delta invented out of the next event's symbol. Route on the name
        FIRST, and refuse anything unrecognised rather than guessing a
        stride. In the dict form each row carries its own `eventType`, so
        the same rule applies row by row.
        """
        rows, qrows = [], []
        if isinstance(data, list) and len(data) == 2 \
                and isinstance(data[0], str) and isinstance(data[1], list):
            kind, flat = data[0], data[1]
            if kind == "Greeks":
                n = len(GREEK_FIELDS)
                for i in range(0, len(flat) - n + 1, n):
                    rows.append(dict(zip(GREEK_FIELDS, flat[i:i + n])))
            elif kind == "Quote":
                n = len(QUOTE_FIELDS)
                for i in range(0, len(flat) - n + 1, n):
                    qrows.append(dict(zip(QUOTE_FIELDS, flat[i:i + n])))
            else:
                return              # unknown type: drop it, never guess
        else:
            _all = []
            if isinstance(data, list):
                _all = [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                _all = [data]
            for r in _all:
                if str(r.get("eventType") or "") == "Quote":
                    qrows.append(r)
                else:
                    rows.append(r)

        if qrows:
            self._absorb_quotes(qrows)

        now = time.time()
        taped = []
        for r in rows:
            sym = r.get("eventSymbol")
            if not sym:
                continue
            g = {}
            for k in ("price", "volatility", "delta", "gamma", "theta",
                      "vega", "rho"):
                v = r.get(k)
                try:
                    g[k] = float(v) if v is not None else None
                except (TypeError, ValueError):
                    g[k] = None
            g["symbol"] = sym
            g["t"] = now
            with self._lock:
                self._greeks[sym] = (g, now)
                self.events += 1
            taped.append(g)
        if taped:
            self._write_tape(taped, now)

    def _absorb_quotes(self, rows):
        """Streaming option bid/ask. SHADOW ONLY — nothing in the exit path
        reads this. It lands in a dict for the comparison tool and, if a
        tape path was given, on disk next to the Webull-polled tape."""
        now = time.time()
        keep = []
        for r in rows:
            sym = r.get("eventSymbol")
            if not sym:
                continue
            try:
                bid = r.get("bidPrice")
                ask = r.get("askPrice")
                bid = float(bid) if bid is not None else None
                ask = float(ask) if ask is not None else None
            except (TypeError, ValueError):
                continue
            # A locked or crossed book (bid >= ask) is a stale or corrupt
            # snapshot, not a trading opportunity. Reg NMS forbids locking
            # protected quotes, so if we see one it is our data that is
            # wrong. Drop it rather than tape a number we would refuse to
            # price off.
            if bid is None or ask is None or bid <= 0 or ask <= 0 or bid >= ask:
                continue
            q = {"symbol": sym, "bid": bid, "ask": ask,
                 "bid_size": r.get("bidSize"), "ask_size": r.get("askSize"),
                 "t": now}
            with self._lock:
                self._quotes[sym] = (q, now)
                self.quote_events += 1
            keep.append(q)
        if keep and self._qtape:
            try:
                new = not os.path.exists(self._qtape)
                with open(self._qtape, "a", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    if new:
                        w.writerow(["ts", "symbol", "bid", "ask", "mid",
                                    "bid_size", "ask_size"])
                    for q in keep:
                        w.writerow(["%.3f" % now, q["symbol"], q["bid"],
                                    q["ask"], round((q["bid"] + q["ask"]) / 2, 4),
                                    q["bid_size"], q["ask_size"]])
            except OSError:
                pass

    def quote(self, occ, max_age=30.0):
        """(bid, ask) streamed from tastytrade, or (None, None) if stale.

        SHADOW. Provided for the comparison tool. Deliberately NOT wired
        into any stop, exit, or order-pricing path — see the note at
        QUOTE_FIELDS for why that promotion needs evidence first.
        """
        dx = occ_to_dx(occ) if occ and not str(occ).startswith(".") else occ
        with self._lock:
            v = self._quotes.get(dx)
        if not v:
            return (None, None)
        q, ts = v
        if max_age and (time.time() - ts) > max_age:
            return (None, None)
        return (q["bid"], q["ask"])

    def _write_tape(self, rows, now):
        if not self._tape:
            return
        try:
            new = not os.path.exists(self._tape)
            with open(self._tape, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["ts", "symbol", "price", "iv", "delta",
                                "gamma", "theta", "vega", "rho"])
                for g in rows:
                    w.writerow(["%.3f" % now, g["symbol"], g["price"],
                                g["volatility"], g["delta"], g["gamma"],
                                g["theta"], g["vega"], g["rho"]])
        except Exception:                                # noqa: BLE001
            pass          # a tape write must never take the stream down
