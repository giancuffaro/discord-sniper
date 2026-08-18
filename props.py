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


# ---- projectx (TopstepX, Bulenox, and other ProjectX firms) -----------------
# Docs: https://gateway.docs.projectx.com  |  TopstepX base = https://api.topstepx.com
# Auth:  POST /api/Auth/loginKey {userName, apiKey} -> {token}  (Bearer, ~24h)
# Order needs a ProjectX contractId like "CON.F.US.ENQ.U25", NOT a plain
# symbol, so we look the symbol up first. Entries carry a server-side
# stop+target bracket, so protection lives on the firm's servers, not the PC.

_PX_TOKENS = {}     # (base, user)  -> (token, expires_epoch)
_PX_CONTRACTS = {}  # (base, symbol)-> {"id":..., "tick":...}

# His index-futures bracket, mirroring the Webull rule: stop 10 pts, take
# profit 25 pts. Applied only to the e-mini / micro index set; anything else
# enters with no auto-bracket rather than guess a tick size wrong.
PX_BRACKET_PTS = {"stop": 10.0, "target": 25.0}
PX_INDEX = {"ES", "MES", "NQ", "MNQ", "YM", "MYM", "RTY", "M2K"}
PX_TICK = {"ES": 0.25, "MES": 0.25, "NQ": 0.25, "MNQ": 0.25,
           "YM": 1.0, "MYM": 1.0, "RTY": 0.10, "M2K": 0.10}

# ---- Topstep account-safety rules (his call, 8/17) --------------------------
# "need all topstep rules to be followed, so if anything is going to trigger
# that will burn the account, dont execute." Everything this side can check
# is checked BEFORE an order leaves; what Topstep's own engine enforces (the
# Daily Loss Limit flatten-and-pause, the trailing Max Loss) is respected by
# refusing to enter whenever the account reports it can't trade. EXITS ARE
# NEVER BLOCKED — getting out is always allowed, rules or no rules.
PX_RULES = {
    # Scaling-plan floor: 1 contract is legal at every balance level of
    # every Topstep account size. Raise on purpose only.
    "max_contracts": 1,
    # The flat-by-4:10-PM-ET rule: no NEW entry from 3:50 PM ET until the
    # 6:00 PM ET reopen — 20 minutes of margin ahead of the forced flatten.
    "entry_cutoff_et": (15, 50),
    "reopen_et": (18, 0),
    # Topstep's consistency rule: the best DAY may be at most this share of
    # total profit (50% standard; set 0.40 on the stricter payout path).
    "consistency_pct": 0.50,
}

# Day-start balances survive a bridge restart in this tiny file — without
# it, a mid-day restart would re-baseline "today's profit" to zero and the
# consistency lock would quietly under-count the day.
def _px_state_path():
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "px_day.json")


def _px_day_load():
    try:
        with open(_px_state_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:                                   # noqa: BLE001
        return {}


def _px_day_save(d):
    try:
        with open(_px_state_path(), "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:                                   # noqa: BLE001
        pass                     # a full disk never blocks the refusal path


def _px_entry_guard(prop, order, acct, qty):
    """Every Topstep rule this side can check, checked before the entry
    leaves. Raises PropRefused with the reason, or returns the (possibly
    capped) size. CLOSE/TRIM never come through here."""
    name = prop.get("name")
    # Topstep's own lock is the law: after a Daily Loss Limit pause or a
    # breach, the account answers canTrade=false — nothing goes out.
    if acct.get("canTrade") is False:
        raise PropRefused("%s: Topstep has this account paused or locked "
                          "(daily-loss pause, or a breach) — nothing sent"
                          % name)
    # Flat-by-4:10-PM-ET: entering minutes before the forced flatten is how
    # an account picks up a violation. No new entries 3:50 PM - 6:00 PM ET.
    mins = None
    try:
        import eastern
        t = eastern.now()
        mins = t.hour * 60 + t.minute
    except Exception:                                   # noqa: BLE001
        pass                    # no clock -> skip this check, never crash
    if mins is not None:
        cut = PX_RULES["entry_cutoff_et"][0] * 60 + PX_RULES["entry_cutoff_et"][1]
        reopen = PX_RULES["reopen_et"][0] * 60 + PX_RULES["reopen_et"][1]
        if cut <= mins < reopen:
            raise PropRefused("%s: inside the flat-by-4:10-PM-ET window (no "
                              "new entries 3:50-6:00 PM ET) — nothing sent. "
                              "Exits still go." % name)
    # Bracket-or-nothing: only contracts with the server-side stop+target
    # may enter. Anything else would sit on a funded account with no stop.
    sym = str(order.get("symbol") or "").upper()
    if sym not in PX_INDEX:
        raise PropRefused("%s: only the auto-bracketed index contracts (%s) "
                          "enter on Topstep — %s would have no server-side "
                          "stop, so nothing was sent"
                          % (name, " ".join(sorted(PX_INDEX)), sym))
    # Scaling plan: never send more than the configured cap.
    cap = int(PX_RULES.get("max_contracts") or 1)
    if qty > cap:
        qty = cap
    # The balance-based rules need the account's balance in the API answer.
    # When it's there: a personal daily-loss stop, and the CONSISTENCY LOCK.
    bal = acct.get("balance")
    if isinstance(bal, (int, float)):
        try:
            import eastern
            day = eastern.now().strftime("%Y-%m-%d")
        except Exception:                               # noqa: BLE001
            import time as _t
            day = _t.strftime("%Y-%m-%d")
        k = "%s|%s|%s" % (str(prop.get("extra") or ""), acct.get("id"), day)
        st = _px_day_load()
        if k not in st:
            st[k] = float(bal)
            _px_day_save(st)
        day_start = float(st[k])
        today = float(bal) - day_start
        # Personal daily-loss stop, tighter than Topstep's own DLL: set
        # "daily_loss_stop" (dollars) and entries stop once the account is
        # down that much on the day.
        stop_d = float(prop.get("daily_loss_stop") or 0)
        if stop_d > 0 and -today >= stop_d:
            raise PropRefused("%s: down $%.0f today — your daily-loss stop "
                              "($%.0f) says no more entries"
                              % (name, -today, stop_d))
        # CONSISTENCY LOCK (his ask, 8/17): Topstep's rule is best day <= 50%
        # of total profit. Keeping today under 50% of the NEW total means:
        # today may earn at most what the whole account had earned before
        # today (cap = pct/(1-pct) * prior profit; at 50% that's exactly the
        # prior profit). When today's profit reaches the cap, entries LOCK
        # until tomorrow — Topstep answers a payout question with "trade
        # more days", this answers it by never concentrating the profit in
        # the first place. Needs "start_balance" (the account's size, e.g.
        # 50000) on the prop entry to know total profit; only applies while
        # the account is actually ahead (prior profit > 0) — early green
        # days BUILD the base, locking those would freeze a new account.
        start_bal = float(prop.get("start_balance") or 0)
        if start_bal > 0:
            # The STAGE picks the percentage by itself (his ask, 8/17: "check
            # yourself if its passed — it says in the name"). Topstep bakes
            # the stage into the account name: an Express Funded Account
            # carries XFA — that's PASSED, the strict 40% payout path
            # applies. Anything else (the Combine) gets Topstep's own 50%.
            # The settings value is only a fallback when the name says
            # nothing recognisable.
            nm = str(acct.get("name") or "").upper()
            if "XFA" in nm or "EXPRESS" in nm:
                pct = 0.40
            else:
                pct = float(prop.get("consistency_pct")
                            or PX_RULES["consistency_pct"])
            pct = min(max(pct, 0.05), 0.95)
            prior = day_start - start_bal
            if prior > 0 and today > 0:
                # round to cents — 0.4/0.6*600 is 400.000000000006 in floats,
                # and "up exactly $400" must NOT slip under a cap of $400.
                cap = round((pct / (1.0 - pct)) * prior, 2)
                if today >= cap:
                    raise PropRefused(
                        "%s: CONSISTENCY LOCK — up $%.0f today, and the "
                        "%.0f%% best-day rule caps today at $%.0f. No more "
                        "entries until tomorrow; exits still go."
                        % (name, today, pct * 100, cap))
    return qty


def _px_token(req, base, user, key):
    import time
    ck, now = (base, user), time.time()
    cached = _PX_TOKENS.get(ck)
    if cached and cached[1] > now + 60:
        return cached[0]
    auth = req.post(base + "/api/Auth/loginKey",
                    json={"userName": user, "apiKey": key}, timeout=8)
    j = auth.json() if auth.status_code == 200 else {}
    if not j.get("token"):
        raise PropRefused("ProjectX wouldn't log in (HTTP %s %s) — check the "
                          "username and API key" % (auth.status_code, auth.text[:120]))
    _PX_TOKENS[ck] = (j["token"], now + 23 * 3600)
    return j["token"]


def _px_contract(req, base, hdr, symbol):
    """Plain symbol (MNQ, MES) -> ProjectX contractId + tick size, front month."""
    sym = str(symbol or "").upper().strip()
    ck = (base, sym)
    if ck in _PX_CONTRACTS:
        return _PX_CONTRACTS[ck]
    r = req.post(base + "/api/Contract/search", headers=hdr,
                 json={"searchText": sym, "live": False}, timeout=8)
    lst = ((r.json() or {}).get("contracts") or []) if r.status_code == 200 else []
    def _score(c):
        name = str(c.get("name") or c.get("symbolId") or "").upper()
        return (bool(c.get("activeContract")), name.startswith(sym))
    lst = sorted(lst, key=_score, reverse=True)
    if not lst:
        raise PropRefused("ProjectX has no contract matching %r" % sym)
    c = lst[0]
    info = {"id": c.get("id"),
            "tick": float(c.get("tickSize") or PX_TICK.get(sym) or 0) or None}
    _PX_CONTRACTS[ck] = info
    return info


def _send_projectx(prop, order, note):
    # MGC is switched OFF here (his call, 8/17): gold has no auto-bracket on
    # ProjectX (only the index set does), so an MGC call would sit on a
    # funded account with no stop. Refused loudly until he turns it on
    # on purpose. Webull's own MGC handling is untouched.
    if str(order.get("symbol") or "").upper() == "MGC":
        raise PropRefused("%s: MGC is switched off for Topstep — his call. "
                          "Nothing was sent." % prop.get("name"))
    req = _requests()
    base = str(prop.get("extra") or "").rstrip("/")
    # `extra` may be "URL" or "URL|AccountName" to pick a specific account.
    acct_want = ""
    if "|" in base:
        base, acct_want = base.split("|", 1)
        base, acct_want = base.rstrip("/"), acct_want.strip().upper()
    if not base.startswith("http"):
        raise PropRefused("%s has no ProjectX gateway URL saved (put "
                          "https://api.topstepx.com in the extra field) — "
                          "nothing was sent" % prop.get("name"))
    tok = _px_token(req, base, prop.get("username"), prop.get("password"))
    hdr = {"Authorization": "Bearer " + tok}

    accts = ((req.post(base + "/api/Account/search", headers=hdr,
                       json={"onlyActiveAccounts": True}, timeout=8).json())
             or {}).get("accounts") or []
    if not accts:
        raise PropRefused("%s: logged in but no active ProjectX account came back"
                          % prop.get("name"))
    acct = accts[0]
    if acct_want:
        acct = next((a for a in accts
                     if str(a.get("name") or "").upper() == acct_want), acct)
    acct_id = acct.get("id")

    con = _px_contract(req, base, hdr, order.get("symbol"))
    contract_id, tick = con["id"], con.get("tick")
    qty = int(order.get("qty") or 1)
    is_short = str(order.get("direction") or "").upper() == "SHORT"

    # CLOSE / TRIM use ProjectX's own close endpoints, so we can never flip
    # into a fresh position by sending an opposing order that's too big.
    if order.get("action") == "CLOSE":
        r = req.post(base + "/api/Position/closeContract", headers=hdr,
                     json={"accountId": acct_id, "contractId": contract_id}, timeout=8)
        ok = (r.json() or {}).get("success", False) if r.status_code == 200 else False
        if not ok:
            raise PropRefused("%s: ProjectX wouldn't close %s (HTTP %s %s)"
                              % (prop.get("name"), order.get("symbol"), r.status_code, r.text[:140]))
        note("PROP     %s <- CLOSE %s (ProjectX)" % (prop.get("name"), order.get("symbol")))
        return "closed on %s" % prop.get("name")
    if order.get("action") == "TRIM":
        r = req.post(base + "/api/Position/partialCloseContract", headers=hdr,
                     json={"accountId": acct_id, "contractId": contract_id, "size": qty}, timeout=8)
        ok = (r.json() or {}).get("success", False) if r.status_code == 200 else False
        if not ok:
            raise PropRefused("%s: ProjectX wouldn't trim %s (HTTP %s %s)"
                              % (prop.get("name"), order.get("symbol"), r.status_code, r.text[:140]))
        note("PROP     %s <- TRIM %s x%s (ProjectX)" % (prop.get("name"), order.get("symbol"), qty))
        return "trimmed on %s" % prop.get("name")

    # Entry. Every Topstep rule checked FIRST — burn nothing (8/17).
    qty = _px_entry_guard(prop, order, acct, qty)
    # Limit if a price came with the call, otherwise market.
    limit = order.get("limit")
    body = {"accountId": acct_id, "contractId": contract_id,
            "side": 1 if is_short else 0,      # 0 = buy, 1 = sell
            "size": qty}
    if limit not in (None, "", 0):
        body["type"], body["limitPrice"] = 1, float(limit)   # 1 = limit
    else:
        body["type"] = 2                                     # 2 = market

    # Server-side bracket (ticks) = protection that survives the PC going dark.
    sym = str(order.get("symbol") or "").upper()
    if tick and sym in PX_INDEX:
        body["stopLossBracket"] = {"ticks": int(round(PX_BRACKET_PTS["stop"] / tick)), "type": 1}
        body["takeProfitBracket"] = {"ticks": int(round(PX_BRACKET_PTS["target"] / tick)), "type": 1}

    r = req.post(base + "/api/Order/place", headers=hdr, json=body, timeout=8)
    j2 = r.json() if r.status_code == 200 else {}
    if not j2.get("success", False):
        raise PropRefused("%s: ProjectX refused the order (HTTP %s %s)"
                          % (prop.get("name"), r.status_code, r.text[:160]))
    br = " +bracket" if "stopLossBracket" in body else ""
    note("PROP     %s <- %s %s x%s (ProjectX accepted%s)"
         % (prop.get("name"), "SELL" if is_short else "BUY",
            order.get("symbol"), qty, br))
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
