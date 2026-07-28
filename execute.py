"""
execute.py — where the order actually goes.

Deliberately the smallest file here, and deliberately swappable. The listener
doesn't know or care what a broker is; it hands a Signal to fire() and gets a
one-line result back.

Backends:
  dryrun   — writes the order to the screen and the log, sends nothing. Default,
             because the first day of a new signal bot should cost you nothing.
  webhook  — POSTs the order as JSON to a URL you control.
  webull   — placeholder that fails loudly until it's wired to a real account.

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

    def describe(self):
        if self.mode == "dryrun":
            return ("DRY RUN — orders are printed, nothing is sent to a broker. "
                    "Nothing here can lose money.")
        if self.mode == "webhook":
            return "LIVE — orders are POSTed to %s" % self.url
        return "Backend '%s' is not wired up yet." % self.mode

    def fire(self, sig, qty):
        """Returns (ok, message). Must never raise — the listener stays alive."""
        order = {"action": sig.action, "symbol": sig.symbol, "side": sig.side,
                 "qty": qty, "strike": sig.strike, "expiry": sig.expiry,
                 "limit": sig.limit, "source": "discord", "raw": sig.raw,
                 "ts": time.time()}

        if self.mode == "dryrun":
            return True, "DRY RUN order: " + json.dumps(order, separators=(",", ":"))

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
