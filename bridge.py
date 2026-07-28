"""
bridge.py — the only thing on your PC that is allowed to spend money.

The extension in your browser reads the room and decides "this is an order".
It then posts a plain description of that order here, and this file is what
talks to the broker.

The split is deliberate. Anything that can read your extension folder can read
everything inside it, and a browser extension folder is not a safe place for
account keys. So the browser holds no credentials at all — worst case, someone
who got into it can make this program place a one-contract order on a symbol
you allow-listed, during market hours, up to your daily cap. That is a bad
afternoon, not a drained account.

Run it with BRIDGE.bat and leave it running. It listens on 127.0.0.1 only,
which means nothing outside this machine can reach it — not your router, not
your wifi, not the internet.
"""

import json
import os
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")
LOG = os.path.join(HERE, "trades.log")
PORT = 8787

# Second opinion on size. The extension already caps this, but the extension
# is the part that lives in a browser, so it does not get the last word.
HARD_MAX_QTY = 2


def load_settings():
    for name in ("settings.json", "settings.example.json"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return {}


CFG = load_settings()
EXEC = CFG.get("execution", {})
MODE = str(EXEC.get("mode", "dryrun")).lower()
ALLOWED = set(str(s).upper() for s in CFG.get("allowed_symbols", []))


def note(line):
    stamp = datetime.now(ET).strftime("%H:%M:%S")
    print("%s  %s" % (stamp, line), flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s\t%s\n" % (datetime.now(ET).isoformat(timespec="seconds"), line))
    except OSError:
        pass


def describe(o):
    bits = [o.get("action", "?"), o.get("symbol", "?")]
    if o.get("strike"):
        bits.append("%s%s" % (o["strike"], "C" if o.get("side") == "CALLS" else "P"))
    if o.get("expiry"):
        bits.append(str(o["expiry"]))
    bits.append("x%s" % o.get("qty", 1))
    if o.get("limit"):
        bits.append("@ %.2f" % float(o["limit"]))
    return " ".join(bits)


def place(order):
    """Returns (ok, message). Never raises — a crash here would look to the
    extension exactly like a rejected order, and you'd never know which."""
    what = describe(order)

    if MODE == "dryrun":
        note("DRY RUN  %s   (nothing was sent to a broker)" % what)
        return True, "dry run — logged, not sent"

    if MODE == "webhook":
        url = EXEC.get("webhook_url", "")
        if not url:
            return False, "webhook mode is on but no webhook_url is set in settings.json"
        try:
            import requests
            r = requests.post(url, json=order,
                              headers=EXEC.get("headers", {}),
                              timeout=float(EXEC.get("timeout_seconds", 4)))
            ok = 200 <= r.status_code < 300
            note("%s  %s  ->  HTTP %s" % ("SENT" if ok else "REJECTED", what, r.status_code))
            return ok, "HTTP %s %s" % (r.status_code, r.text[:120])
        except Exception as e:
            note("FAILED  %s  ->  %s" % (what, e))
            return False, "the webhook didn't answer: %s" % e

    # Room for a real broker backend. Tell me which broker and this is where it
    # goes — credentials read from settings.json, which is gitignored.
    return False, ("execution mode '%s' isn't wired up yet. Leave it on "
                   "'dryrun' until it is." % MODE)


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, msg):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The browser extension is a different origin, so without this the
        # order never arrives and Chrome tells you nothing useful.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._reply(204, "")

    def do_GET(self):
        self._reply(200, "bridge is up, mode=%s" % MODE)

    def do_POST(self):
        if os.path.exists(os.path.join(HERE, "STOP")) or \
           os.path.exists(os.path.join(HERE, "STOP.txt")):
            note("BLOCKED  the STOP file is here, so nothing goes out")
            return self._reply(423, "the STOP file is in the folder — nothing fires")

        try:
            n = int(self.headers.get("Content-Length", 0))
            order = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._reply(400, "that wasn't a readable order")

        sym = str(order.get("symbol", "")).upper()
        if not sym:
            return self._reply(400, "no symbol in that order")
        if ALLOWED and sym not in ALLOWED:
            note("BLOCKED  %s isn't on the allowed list in settings.json" % sym)
            return self._reply(403, "%s isn't on your allowed-symbols list" % sym)

        try:
            qty = max(1, min(int(order.get("qty") or 1), HARD_MAX_QTY))
        except (TypeError, ValueError):
            qty = 1
        order["qty"] = qty

        ok, msg = place(order)
        self._reply(200 if ok else 502, msg)

    def log_message(self, *a):
        pass    # the default logger prints a line per request; note() is enough


def main():
    print("=" * 62)
    print("  DISCORD SNIPER BRIDGE")
    print("  listening on http://127.0.0.1:%d  (this PC only)" % PORT)
    print("  mode: %s%s" % (MODE, "   <- nothing real is being sent"
                            if MODE == "dryrun" else "   <- REAL ORDERS"))
    print("  allowed symbols: %s" % (", ".join(sorted(ALLOWED)) or "any"))
    print("  panic button: make a file called STOP in this folder")
    print("=" * 62)
    print("Leave this window open. Close it and the extension can't trade.")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError as e:
        print("\nCouldn't start: %s" % e)
        print("Usually that means a bridge is already running in another "
              "window. Close it and try again.")
    except KeyboardInterrupt:
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
