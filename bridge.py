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

WB = None           # the Webull connection, made once at startup
WB_ERROR = ""
WB_ACCOUNT = ""


def reload_settings():
    """Pick up KEYS.bat having been run while this window was open, so you don't
    have to restart the bridge to see that your keys are in."""
    global CFG, EXEC, ALLOWED
    CFG = load_settings()
    EXEC = CFG.get("execution", {})
    ALLOWED = set(str(s).upper() for s in CFG.get("allowed_symbols", []))
    EXEC["mode"] = MODE          # the running mode wins; the file may be behind


def save_mode(new_mode):
    """Flip live/dry-run and write it down, so restarting the bridge doesn't
    quietly put you back where you were an hour ago.

    Only settings.json is touched, and only the one field. Your keys are left
    exactly as they are — this switch is about whether they get used, not about
    what they are."""
    global MODE
    path = os.path.join(HERE, "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        # No settings.json yet, or it's unreadable. Flip in memory so the button
        # still does something, but say plainly that it won't survive a restart.
        MODE = new_mode
        CFG.setdefault("execution", {})["mode"] = new_mode
        return False, ("switched to %s for now, but there's no readable "
                       "settings.json to write it to — run KEYS.bat and it "
                       "will stick next time." % new_mode.upper())

    data.setdefault("execution", {})["mode"] = new_mode
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.chmod(path, 0o600)
    except OSError as e:
        return False, "couldn't write settings.json: %s" % e

    MODE = new_mode
    CFG.setdefault("execution", {})["mode"] = new_mode
    return True, "saved"


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
    if o.get("reenter"):
        bits.append("(and straight back in)")
    return " ".join(bits)


def place(order):
    """Returns (ok, message). Never raises — a crash here would look to the
    extension exactly like a rejected order, and you'd never know which."""
    what = describe(order)

    if MODE == "dryrun":
        note("DRY RUN  %s   (nothing was sent to a broker)" % what)
        if order.get("reenter"):
            note("DRY RUN  then straight back in on the same contract%s"
                 % ("" if not order.get("reenter_limit")
                    else " around %.2f" % float(order["reenter_limit"])))
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

    if MODE == "webull":
        if WB is None:
            return False, ("not connected to Webull: %s" % (WB_ERROR or "unknown"))
        from webull_options import Refused
        qty = int(order.get("qty") or 1)
        try:
            if order.get("action") == "OPEN":
                msg = WB.buy(order["symbol"], order.get("side"),
                             order.get("strike"), order.get("expiry"), qty,
                             their_price=order.get("limit"))
                note("BOUGHT   %s" % msg)
                return True, msg

            if order.get("action") == "CLOSE":
                msg = WB.sell(order["symbol"], order.get("side"),
                              order.get("strike"), order.get("expiry"), qty)
                note("SOLD     %s" % msg)

                # "exited SPY, and back in @ 2.84" — they sold and bought the
                # same contract straight back. Both legs happen here rather
                # than as two round-trips from the browser, so the gap between
                # them is as small as it can be.
                if order.get("reenter"):
                    try:
                        back = WB.buy(order["symbol"], order.get("side"),
                                      order.get("strike"), order.get("expiry"),
                                      qty,
                                      their_price=order.get("reenter_limit"))
                        note("RE-BOUGHT %s" % back)
                        return True, msg + "  ||  back in: " + back
                    except Refused as e:
                        # The sell already went through. Say so plainly, because
                        # "failed" here would read as if you were still holding.
                        note("SOLD but could NOT get back in: %s" % e)
                        return False, ("the exit went through, but getting back "
                                       "in did not: %s  You are FLAT on %s."
                                       % (e, order["symbol"]))
                return True, msg

            return False, "nothing to do for action '%s'" % order.get("action")

        except Refused as e:
            note("REFUSED  %s  ->  %s" % (what, e))
            return False, str(e)
        except Exception as e:                          # noqa: BLE001
            note("ERROR    %s  ->  %s" % (what, e))
            return False, ("something went wrong talking to Webull: %s. The "
                           "order may not have gone out — check the Webull app."
                           % str(e)[:160])

    return False, ("execution mode '%s' isn't a thing. Use dryrun, webull or "
                   "webhook." % MODE)


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

    def _json(self, code, obj):
        self._reply(code, json.dumps(obj))

    def do_OPTIONS(self):
        self._reply(204, "")

    def _status(self):
        reload_settings()
        keys_in = bool((EXEC.get("webull") or {}).get("app_key"))
        return {"mode": MODE,
                "live": MODE == "webull",
                "connected": WB is not None,
                "account": WB_ACCOUNT,
                "error": WB_ERROR,
                "has_keys": keys_in,
                "stopped": os.path.exists(os.path.join(HERE, "STOP")) or
                           os.path.exists(os.path.join(HERE, "STOP.txt"))}

    def do_GET(self):
        if self.path.startswith("/mode"):
            return self._json(200, self._status())
        self._reply(200, "bridge is up, mode=%s" % MODE)

    def _set_mode(self):
        """The live / dry-run switch, driven from the popup so you don't have to
        find this window and restart it."""
        global WB_ERROR
        reload_settings()
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"ok": False, "message": "unreadable request"})

        want = "webull" if body.get("live") else "dryrun"
        if want == MODE:
            return self._json(200, dict(self._status(), ok=True,
                                        message="already there"))

        if want == "webull":
            if not (EXEC.get("webull") or {}).get("app_key"):
                return self._json(400, dict(self._status(), ok=False,
                    message="there are no Webull keys saved yet. Run KEYS.bat "
                            "first, then flip this."))

        ok, msg = save_mode(want)
        if want == "webull":
            connect_broker(quiet=True)
            if WB is None:
                # It's on, but it can't reach the broker. Better to say so now
                # than to let you find out on the first call of the day.
                note("LIVE MODE ON but Webull isn't connected — %s" % WB_ERROR)
                return self._json(200, dict(self._status(), ok=False,
                    message="live mode is on, but it couldn't connect: %s"
                            % WB_ERROR))
            note("LIVE MODE ON — real orders, account %s" % WB_ACCOUNT)
            return self._json(200, dict(self._status(), ok=True,
                message="LIVE. Real orders, account %s.%s"
                        % (WB_ACCOUNT, "" if ok else "  (" + msg + ")")))

        WB_ERROR = ""       # a stale connection error is noise once you're safe
        note("DRY RUN — nothing real will be sent")
        return self._json(200, dict(self._status(), ok=True,
            message="dry run. Orders are logged, nothing is sent."))

    def do_POST(self):
        if self.path.startswith("/mode"):
            return self._set_mode()

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

        # A broker needs the exact contract. The room's "all out of AMD" doesn't
        # have one, so the extension fills it in from what you're holding — if
        # it arrives here empty, something upstream lost track and the right
        # answer is to send nothing.
        if MODE != "dryrun" and not (order.get("strike") and order.get("expiry")):
            note("BLOCKED  %s %s arrived with no strike/expiry" %
                 (order.get("action"), sym))
            return self._reply(400,
                "that order didn't say which contract (no strike or expiry), so "
                "nothing was sent. Close it in the Webull app if you're in it.")

        ok, msg = place(order)
        self._reply(200 if ok else 502, msg)

    def log_message(self, *a):
        pass    # the default logger prints a line per request; note() is enough


def connect_broker(quiet=False):
    """Done at startup, and again whenever you flip to live, so the first call
    of the day doesn't spend three seconds logging in while the move happens."""
    global WB, WB_ERROR, WB_ACCOUNT
    if MODE != "webull":
        return
    try:
        from webull_options import WebullOptions
        wb = WebullOptions(CFG)
        acct = wb.connect()
        WB, WB_ACCOUNT, WB_ERROR = wb, str(acct), ""
        if not quiet:
            print("  Webull: connected, options account %s" % acct)
        else:
            note("Webull connected, options account %s" % acct)
    except Exception as e:                              # noqa: BLE001
        WB, WB_ACCOUNT = None, ""
        WB_ERROR = str(e)
        if not quiet:
            print("  Webull: NOT CONNECTED — %s" % WB_ERROR)
            print("          nothing will fire until this is fixed.")
        else:
            note("Webull NOT connected — %s" % WB_ERROR)


def main():
    print("=" * 62)
    print("  DISCORD SNIPER BRIDGE")
    print("  listening on http://127.0.0.1:%d  (this PC only)" % PORT)
    print("  mode: %s%s" % (MODE, "   <- nothing real is being sent"
                            if MODE == "dryrun" else "   <- REAL ORDERS"))
    print("  allowed symbols: %s" % (", ".join(sorted(ALLOWED)) or "any"))
    print("  panic button: make a file called STOP in this folder")
    connect_broker()
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
