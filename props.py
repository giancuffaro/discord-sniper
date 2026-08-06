"""
props.py — prop-firm accounts as extra sets of hands.

The firms themselves (Apex, Topstep, Bulenox, MyFundedFutures...) don't hand
out APIs. What they hand out is an account ON a platform, and the platform is
what a program can talk to. Three kinds cover practically the whole industry:

    tradovate   Tradovate's public REST API. Apex, MyFundedFutures, Tradeify
                and others issue Tradovate accounts.
    projectx    The ProjectX Gateway API. TopstepX, Bulenox and a growing list
                of firms run on ProjectX now.
    webhook     A plain HTTP POST of the order as JSON — the universal escape
                hatch. Copy-trade services (PickMyTrade, PropSyncX) take a
                webhook and fan it into whatever firm accounts you've linked
                there. If a firm has no API, this is the road in.

Every adapter here follows the webull_futures rule: refuse LOUDLY rather than
guess, and the first live order through any prop account is a supervised
event, not a surprise. Credentials live in settings.json (chmod 600) next to
the Webull keys, never in the browser.

Config shape, written by the popup via POST /props:

    "props": [
      {"name": "Apex 50K", "platform": "tradovate", "enabled": false,
       "username": "...", "password": "...", "extra": "cid:sec or demo/live"},
      {"name": "Topstep 100K", "platform": "projectx", "enabled": false,
       "username": "...", "password": "...", "extra": "https://api.topstepx.com"},
      {"name": "PickMyTrade", "platform": "webhook", "enabled": false,
       "username": "", "password": "", "extra": "https://pmt.example/hook"}
    ]

`enabled` is the arming switch: a disabled prop is stored, checked, and never
sent a dollar of anything.
"""

import json


class PropRefused(Exception):
    """Raised with a human sentence whenever an order cannot go out safely."""


def _requests():
    import requests
    return requests


# ---- webhook: works today, everywhere ---------------------------------------
def _send_webhook(prop, order, note):
    url = str(prop.get("extra") or "").strip()
    if not url.startswith("http"):
        raise PropRefused("%s has no webhook URL saved — nothing was sent"
                          % prop.get("name"))
    body = {
        "name": prop.get("name"),
        "action": order.get("action"),
        "symbol": order.get("symbol"),
        "direction": order.get("direction"),
        "qty": int(order.get("qty") or 1),
        "limit": order.get("limit"),
        "their_stop": order.get("their_stop"),
        "their_target": order.get("their_target"),
        "kind": order.get("kind"),
        "source": "discord-sniper",
    }
    r = _requests().post(url, json=body, timeout=6)
    if not (200 <= r.status_code < 300):
        raise PropRefused("%s webhook answered HTTP %s: %s"
                          % (prop.get("name"), r.status_code, r.text[:120]))
    note("PROP     %s <- %s %s x%s (webhook accepted)"
         % (prop.get("name"), order.get("action"), order.get("symbol"),
            body["qty"]))
    return "sent to %s" % prop.get("name")


# ---- tradovate ---------------------------------------------------------------
TRADOVATE_LIVE = "https://live.tradovateapi.com/v1"
TRADOVATE_DEMO = "https://demo.tradovateapi.com/v1"


def _send_tradovate(prop, order, note):
    """Auth + place, by the public API's book. The first order through a
    Tradovate prop account is supervised — run it while watching the DOM."""
    req = _requests()
    base = TRADOVATE_DEMO if "demo" in str(prop.get("extra") or "").lower() \
        else TRADOVATE_LIVE
    auth = req.post(base + "/auth/accesstokenrequest", json={
        "name": prop.get("username"), "password": prop.get("password"),
        "appId": "DiscordSniper", "appVersion": "1.0",
        "cid": 0, "sec": ""}, timeout=8)
    if auth.status_code != 200 or "accessToken" not in (auth.json() or {}):
        raise PropRefused("%s: Tradovate wouldn't log in (HTTP %s %s)"
                          % (prop.get("name"), auth.status_code,
                             auth.text[:120]))
    tok = auth.json()["accessToken"]
    hdr = {"Authorization": "Bearer " + tok}
    accts = req.get(base + "/account/list", headers=hdr, timeout=8).json()
    if not accts:
        raise PropRefused("%s: logged in but no Tradovate account came back"
                          % prop.get("name"))
    acct = accts[0]
    side = "Sell" if str(order.get("direction") or "").upper() == "SHORT" \
        else "Buy"
    if order.get("action") in ("CLOSE", "TRIM"):
        side = "Buy" if side == "Sell" else "Sell"
    body = {"accountSpec": acct.get("name"), "accountId": acct.get("id"),
            "action": side, "symbol": order.get("symbol"),
            "orderQty": int(order.get("qty") or 1),
            "orderType": "Market", "isAutomated": True}
    r = req.post(base + "/order/placeorder", headers=hdr, json=body, timeout=8)
    if r.status_code != 200:
        raise PropRefused("%s: Tradovate refused the order (HTTP %s %s)"
                          % (prop.get("name"), r.status_code, r.text[:120]))
    note("PROP     %s <- %s %s x%s (Tradovate accepted)"
         % (prop.get("name"), side, order.get("symbol"), body["orderQty"]))
    return "sent to %s" % prop.get("name")


# ---- projectx ----------------------------------------------------------------
def _send_projectx(prop, order, note):
    """ProjectX Gateway (TopstepX, Bulenox and friends). `extra` holds the
    firm's gateway base URL; username + API key log in."""
    req = _requests()
    base = str(prop.get("extra") or "").rstrip("/")
    if not base.startswith("http"):
        raise PropRefused("%s has no ProjectX gateway URL saved (Settings -> "
                          "extra field) — nothing was sent" % prop.get("name"))
    auth = req.post(base + "/api/Auth/loginKey", json={
        "userName": prop.get("username"),
        "apiKey": prop.get("password")}, timeout=8)
    j = auth.json() if auth.status_code == 200 else {}
    if not j.get("token"):
        raise PropRefused("%s: ProjectX wouldn't log in (HTTP %s %s)"
                          % (prop.get("name"), auth.status_code,
                             auth.text[:120]))
    hdr = {"Authorization": "Bearer " + j["token"]}
    accts = req.post(base + "/api/Account/search",
                     headers=hdr, json={"onlyActiveAccounts": True},
                     timeout=8).json()
    acct_list = (accts or {}).get("accounts") or []
    if not acct_list:
        raise PropRefused("%s: logged in but no ProjectX account came back"
                          % prop.get("name"))
    acct = acct_list[0]
    is_short = str(order.get("direction") or "").upper() == "SHORT"
    if order.get("action") in ("CLOSE", "TRIM"):
        is_short = not is_short
    body = {"accountId": acct.get("id"),
            "contractId": order.get("symbol"),
            "type": 2,                       # market
            "side": 1 if is_short else 0,    # 0 buy, 1 sell
            "size": int(order.get("qty") or 1)}
    r = req.post(base + "/api/Order/place", headers=hdr, json=body, timeout=8)
    j2 = r.json() if r.status_code == 200 else {}
    if not j2.get("success", False):
        raise PropRefused("%s: ProjectX refused the order (HTTP %s %s)"
                          % (prop.get("name"), r.status_code, r.text[:160]))
    note("PROP     %s <- %s %s x%s (ProjectX accepted)"
         % (prop.get("name"), "SELL" if is_short else "BUY",
            order.get("symbol"), body["size"]))
    return "sent to %s" % prop.get("name")


# ---- ninjatrader: OIF file drop (NinjaTrader 8 ATI) -------------------------
def _ninjatrader_dir(prop):
    """The folder NinjaTrader 8 watches for Order Instruction Files. `extra`
    overrides it; otherwise the standard per-user location. Works whether the
    bridge runs on Windows (the usual NinjaTrader host) or a mac test box."""
    import os
    d = str(prop.get("extra") or "").strip()
    if d:
        return os.path.expanduser(d)
    return os.path.join(os.path.expanduser("~"), "Documents",
                        "NinjaTrader 8", "incoming")


def _send_ninjatrader(prop, order, note):
    """Fire a futures order into NinjaTrader 8 by writing its native OIF file
    into the incoming folder. No socket, no DLL — NinjaTrader picks the file up,
    places the order, and deletes it. `username` is the NinjaTrader account name
    (Sim101, or the prop account); `extra` is the incoming folder if it isn't in
    the default spot. The first order is supervised — watch it hit the DOM."""
    import os, time, uuid
    account = str(prop.get("username") or "").strip()
    if not account:
        raise PropRefused("%s has no NinjaTrader account name saved (Settings -> "
                          "the username field, e.g. Sim101) — nothing was sent"
                          % prop.get("name"))
    folder = _ninjatrader_dir(prop)
    if not os.path.isdir(folder):
        raise PropRefused("%s: NinjaTrader's incoming folder isn't there (%s). "
                          "Open NinjaTrader 8, and in Tools > Options > General "
                          "make sure the ATI 'incoming' folder exists, or set the "
                          "path in the extra field. Nothing was sent."
                          % (prop.get("name"), folder))
    # BUY opens a long / covers a short; SELL opens a short / sells a long.
    is_short = str(order.get("direction") or "").upper() == "SHORT"
    if order.get("action") in ("CLOSE", "TRIM"):
        is_short = not is_short          # exiting is the opposite side
    side = "SELL" if is_short else "BUY"
    instrument = str(order.get("symbol") or "").upper()
    qty = int(order.get("qty") or 1)
    limit = order.get("limit")
    otype = "LIMIT" if limit else "MARKET"
    lim = ("%.2f" % float(limit)) if limit else ""
    oid = "DS" + uuid.uuid4().hex[:10]
    # PLACE;ACCOUNT;INSTRUMENT;ACTION;QTY;TYPE;LIMIT;STOP;TIF;OCO;ORDERID;STRAT;STRATID
    line = "PLACE;%s;%s;%s;%d;%s;%s;;DAY;;%s;;" % (
        account, instrument, side, qty, otype, lim, oid)
    # A unique filename per order; NinjaTrader consumes and removes it.
    fname = "oif_%s.txt" % oid
    tmp = os.path.join(folder, "." + fname)         # write-then-rename, so
    dst = os.path.join(folder, fname)               # NT never reads a half file
    try:
        with open(tmp, "w", encoding="ascii") as f:
            f.write(line + "\n")
        os.replace(tmp, dst)
    except OSError as e:
        raise PropRefused("%s: couldn't write the NinjaTrader order file (%s) — "
                          "nothing was sent" % (prop.get("name"), str(e)[:100]))
    note("PROP     %s <- %s %s x%d (NinjaTrader OIF %s)"
         % (prop.get("name"), side, instrument, qty, oid))
    return "sent to %s (NinjaTrader)" % prop.get("name")


ADAPTERS = {"webhook": _send_webhook,
            "tradovate": _send_tradovate,
            "projectx": _send_projectx,
            "ninjatrader": _send_ninjatrader}


def execute_all(props, order, note):
    """Send one futures order to every ENABLED prop account. Returns
    (sent_names, refusals) — refusals are sentences, never silence."""
    sent, refused = [], []
    for prop in props or []:
        if not prop.get("enabled"):
            continue
        fn = ADAPTERS.get(str(prop.get("platform") or "").lower())
        if fn is None:
            refused.append("%s: unknown platform %r"
                           % (prop.get("name"), prop.get("platform")))
            continue
        try:
            sent.append(fn(prop, order, note))
        except PropRefused as e:
            refused.append(str(e))
        except Exception as e:                          # noqa: BLE001
            refused.append("%s: %s" % (prop.get("name"), str(e)[:140]))
    return sent, refused
