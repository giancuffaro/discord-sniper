"""
execute.py — where the order actually goes.

Deliberately the smallest file here, and deliberately swappable. The listener
doesn't know or care what a broker is; it hands a Signal to fire() and gets a
one-line result back.

Backends:
  dryrun   — writes the order to the screen and the log, sends nothing. Default,
             because the first day of a new signal bot should cost you nothing.
  webhook  — POSTs the order as JSON to a URL you control.
  webull   — real options orders in your Webull account. Options only; a
             futures account is refused outright. No paper mode exists for
             options, so this is real money every time.

Speed note: the HTTP session is built once and kept alive, and warm() opens the
TLS connection before the market does anything. A cold handshake is 150-400ms —
that is the difference between the signal price and a chase.
"""

import json
import time

try:
    import requests
except Exception:
    requests = None


class Executor:
    def __init__(self, cfg, log=print):
        e = cfg.get("execution", {})
        self.mode = (e.get("mode") or "dryrun").lower()
        self.url = e.get("webhook_url") or ""
        self.headers = e.get("headers") or {}
        self.timeout = float(e.get("timeout_seconds", 4))
        self.log = log
        self.cfg = cfg
        self.wb = None              # the Webull connection, made once by warm()
        self.wb_error = ""
        self.sess = None
        if requests is not None:
            self.sess = requests.Session()
            self.sess.headers.update({"Content-Type": "application/json",
                                      **self.headers})
            a = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4,
                                              max_retries=0)
            self.sess.mount("https://", a)
            self.sess.mount("http://", a)

    def warm(self):
        """Open the connection now so the first real order doesn't pay for it."""
        if self.mode == "webhook" and self.sess and self.url:
            try:
                self.sess.head(self.url, timeout=self.timeout)
                self.log("Connection to your order endpoint is open and warm.")
            except Exception:
                self.log("Couldn't pre-warm the order endpoint — first order may "
                         "be a touch slower. Not fatal.")
        if self.mode == "webull":
            # Logging in takes a couple of seconds. Pay for that now, at 9:25,
            # not in the middle of the first call of the day.
            try:
                from webull_options import WebullOptions
                wb = WebullOptions(self.cfg)
                acct = wb.connect()
                self.wb = wb
                self.log("Webull: connected, options account %s" % acct)
            except Exception as e:                      # noqa: BLE001
                self.wb_error = str(e)
                self.log("Webull: NOT CONNECTED — %s" % self.wb_error)
                self.log("Nothing will fire until that's fixed.")

    def describe(self):
        if self.mode == "dryrun":
            return ("DRY RUN — orders are printed, nothing is sent to a broker. "
                    "Nothing here can lose money.")
        if self.mode == "webhook":
            return "LIVE — orders are POSTed to %s" % self.url
        if self.mode == "webull":
            return ("LIVE — real options orders in your Webull account. There "
                    "is no paper mode for options; every fill is real money.")
        return "Backend '%s' is not wired up yet." % self.mode

    def _webull(self, order):
        """Real orders. Returns (ok, message) and never raises."""
        if self.wb is None:
            return False, ("not connected to Webull: %s"
                           % (self.wb_error or "warm() hasn't run yet"))
        from webull_options import Refused

        sym = order["symbol"]
        qty = int(order.get("qty") or 1)
        # A broker needs the exact contract. If the guards couldn't fill one in
        # from your open position, sending anything would be a guess.
        if not (order.get("strike") and order.get("expiry")):
            return False, ("that order didn't say which contract (no strike or "
                           "expiry), so nothing was sent. Close it in the "
                           "Webull app if you're in it.")
        try:
            if order["action"] == "OPEN":
                return True, self.wb.buy(sym, order.get("side"),
                                         order.get("strike"),
                                         order.get("expiry"), qty,
                                         their_price=order.get("limit"))

            if order["action"] == "CLOSE":
                msg = self.wb.sell(sym, order.get("side"), order.get("strike"),
                                   order.get("expiry"), qty)
                # "exited SPY, and back in @ 2.84" is one line and two trades:
                # sell it, then buy the same contract straight back. Both legs
                # run here, back to back, so the gap between them is minimal.
                if order.get("reenter"):
                    try:
                        back = self.wb.buy(
                            sym, order.get("side"), order.get("strike"),
                            order.get("expiry"), qty,
                            their_price=order.get("reenter_limit"))
                        return True, msg + "  ||  back in: " + back
                    except Refused as e:
                        # The sell filled. Saying "failed" here would read as
                        # if you were still holding, which you are not.
                        return False, ("the exit went through, but getting back "
                                       "in did not: %s  You are FLAT on %s."
                                       % (e, sym))
                return True, msg

            return False, "nothing to do for action '%s'" % order["action"]

        except Refused as e:
            return False, str(e)
        except Exception as e:                          # noqa: BLE001
            return False, ("something went wrong talking to Webull: %s. The "
                           "order may not have gone out — check the Webull app."
                           % str(e)[:160])

    def fire(self, sig, qty):
        """Returns (ok, message). Must never raise — the listener stays alive."""
        order = {"action": sig.action, "symbol": sig.symbol, "side": sig.side,
                 "qty": qty, "strike": sig.strike, "expiry": sig.expiry,
                 "limit": sig.limit, "source": "discord", "raw": sig.raw,
                 "reenter": bool(getattr(sig, "reenter", False)),
                 "reenter_limit": getattr(sig, "reenter_limit", None),
                 "ts": time.time()}

        if self.mode == "dryrun":
            return True, "DRY RUN order: " + json.dumps(order, separators=(",", ":"))

        if self.mode == "webull":
            return self._webull(order)

        if self.mode == "webhook":
            if not self.sess:
                return False, ("the 'requests' library isn't installed, so the "
                               "order couldn't be sent. Run SETUP again.")
            if not self.url:
                return False, ("no webhook_url is set in settings.json, so there "
                               "is nowhere to send the order.")
            t0 = time.time()
            try:
                r = self.sess.post(self.url, json=order, timeout=self.timeout)
            except Exception as ex:
                return False, ("couldn't reach your order endpoint (%s). The "
                               "trade did NOT go out." % type(ex).__name__)
            ms = (time.time() - t0) * 1000
            if r.status_code >= 300:
                return False, ("your order endpoint refused it: HTTP %d %s"
                               % (r.status_code, r.text[:160]))
            return True, "sent in %.0f ms — %s" % (ms, r.text[:160] or "accepted")

        return False, ("execution mode '%s' isn't built yet, so nothing was sent. "
                       "Set mode to 'dryrun' or 'webhook' in settings.json."
                       % self.mode)
