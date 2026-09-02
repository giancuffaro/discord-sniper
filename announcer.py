"""FILL ANNOUNCER v3 (8/30, G) — fills, milestones, stop-outs, scoreboard.

Posts to his Discord channels via webhooks:
    ENTRY TSLA 345P 8/28 @ 4.24 x1          (options channel)
    📈 TSLA 345P 8/28 +10%  (4.24 -> 4.68)
    EXIT TSLA 345P 8/28 @ 5.10 x1  (+20%)
    ⛔ STOPPED OUT TSLA 345P 8/28 @ 3.90 x1  (-8%)
    ENTRY MNQ @ 29280 x1                     (futures channel)
    🏆 TSLA +132 today (+404 all-time) | Day | Leaders   (scoreboard)

Watches BOTH Webull accounts (margin + futures — futures wired even while
it holds $0, per G). Latency: 1-second fill polling (Webull has no push
feed). Milestones ride live quotes every ~2s, each level posted once,
upward only. Scoreboard: per-symbol realized dollars accumulate in
announcer-scoreboard.json (seeded from journals 8/19-8/28), posted after
every close; the full board posts at boot.
Read-only: never places, cancels, or modifies anything.
Single-instance via .announcer.alive heartbeat; announcer.stop = off switch.
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(HERE, "announcer-seen.json")
ALIVE_FILE = os.path.join(HERE, ".announcer.alive")
STOP_FILE = os.path.join(HERE, "announcer.stop")
MILESTONES = (10, 20, 30, 40, 50, 75, 100, 150, 200, 300, 400, 500)
SCORE_FILE = os.path.join(HERE, "announcer-scoreboard.json")
FUT_MULT = {"MNQ": 2.0, "MES": 5.0, "MYM": 0.5, "M2K": 5.0,
            "MGC": 10.0, "MCL": 100.0, "NQ": 20.0, "ES": 50.0}


def _load_score():
    try:
        with open(SCORE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                   # noqa: BLE001
        return {"date": "", "today": {}, "all": {}}


def _save_score(sc):
    try:
        with open(SCORE_FILE, "w", encoding="utf-8") as f:
            json.dump(sc, f, indent=1)
    except Exception:                                   # noqa: BLE001
        pass


def _score_add(sc, sym, dollars):
    today = time.strftime("%Y-%m-%d")
    if sc.get("date") != today:
        sc["date"] = today
        sc["today"] = {}
    sc["today"][sym] = round(sc["today"].get(sym, 0) + dollars, 2)
    sc["all"][sym] = round(sc["all"].get(sym, 0) + dollars, 2)
    _save_score(sc)


def _money(v):
    return "{:+,.0f}".format(v)


def _score_line(sc, sym):
    day_total = round(sum(sc["today"].values()), 2)
    top = sorted(sc["all"].items(), key=lambda x: -x[1])[:5]
    tops = ", ".join("%s %s" % (k, _money(v)) for k, v in top)
    return ("🏆 %s %s today (%s all-time)  |  Day: %s  |  Leaders: %s"
            % (sym, _money(sc["today"].get(sym, 0)),
               _money(sc["all"].get(sym, 0)), _money(day_total), tops))


def _score_board(sc):
    """Full scoreboard, posted at boot and on demand."""
    if not sc["all"]:
        return None
    rows = sorted(sc["all"].items(), key=lambda x: -x[1])
    body = "\n".join("%-6s %10s" % (k, _money(v)) for k, v in rows)
    grand = _money(sum(sc["all"].values()))
    return ("🏆 **SCOREBOARD** (all-time, from the journals)\n```\n%s\n%s\n%-6s %10s\n```"
            % (body, "-" * 17, "TOTAL", grand))


def _cfg():
    with open(os.path.join(HERE, "settings.json"), encoding="utf-8") as f:
        return json.load(f)


def _post(webhook, line):
    body = json.dumps({"content": line, "username": "Fill Announcer"}).encode()
    req = urllib.request.Request(webhook, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent":
                                          "Mozilla/5.0 (FillAnnouncer/1.0)"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:                              # noqa: BLE001
        print("webhook post failed:", str(e)[:120])
        return False


def _load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:                                   # noqa: BLE001
        return set()


def _save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(seen)[-500:], f)
    except Exception:                                   # noqa: BLE001
        pass


def _recent_orders(wb, account_id=None):
    """Orders for one account via the SAME proven pattern as
    webull_options.last_sell_fill — holders order_v3/order/trade/account_v2,
    verb substring "history", and the dates passed BY KEYWORD (8/28 lesson:
    positional dates land in the wrong SDK slots and 500 every time).

    The old homemade hunt here guessed verbs his SDK doesn't have and
    returned [] on every poll — the announcer sat online for three days
    without seeing a single fill (found 9/1: announcer-seen.json was []
    while the account did nine round trips)."""
    import datetime as dt
    acct = account_id or wb.account_id
    today = dt.date.today()
    start = (today - dt.timedelta(days=1)).isoformat()
    end = (today + dt.timedelta(days=1)).isoformat()
    body = None
    for args, kw in (((acct,), {"start_date": start, "end_date": end}),
                     ((acct, start, end), {}),
                     ((acct,), {})):
        try:
            body, _why = wb._try_calls(
                ["order_v3", "order", "trade", "account_v2"],
                ["history", "list_orders", "orders", "query_orders"],
                *args, **kw)
        except Exception:                               # noqa: BLE001
            body = None
        if body is not None:
            break
    if body is None:
        return []
    if isinstance(body, list):
        return body
    return (body or {}).get("orders") or (body or {}).get("data") or []


def _parse(od):
    """One raw order -> dict of the fill's facts, or None."""
    inner = od.get("orders")
    if isinstance(inner, list) and inner:
        od = inner[0]
    if str(od.get("status", "")).upper() != "FILLED":
        return None
    legs = od.get("legs") or [{}]
    lg = legs[0] if legs else {}
    exp = str(lg.get("option_expire_date") or "")
    px = od.get("filled_avg_price") or od.get("filled_price") or od.get("avg_price")
    try:
        px = float(px)
    except (TypeError, ValueError):
        px = None
    qty = od.get("filled_quantity") or od.get("total_quantity") or 1
    try:
        qty = int(float(qty))
    except (TypeError, ValueError):
        qty = 1
    return {
        "oid": str(od.get("order_id") or od.get("client_order_id") or ""),
        "sym": lg.get("symbol") or od.get("symbol") or "?",
        "strike": lg.get("strike_price"),
        "otype": (lg.get("option_type") or "")[:1].upper(),
        "exp": exp,
        "px": px, "qty": qty,
        "intent": str(od.get("position_intent") or "").upper(),
        "side": str(od.get("side") or "").upper(),
    }


def _con(f):
    exp_s = (f["exp"][5:7].lstrip("0") + "/" + f["exp"][8:10].lstrip("0")) \
        if len(f["exp"]) == 10 else f["exp"]
    if f["strike"] and f["otype"]:
        return "%s %g%s %s" % (f["sym"], float(f["strike"]), f["otype"], exp_s)
    return f["sym"]


def main():
    # single instance: a heartbeat younger than 90s means another copy
    # is already narrating — this one stands down quietly.
    try:
        if time.time() - os.path.getmtime(ALIVE_FILE) < 90:
            print("another announcer is alive — standing down.")
            return
    except OSError:
        pass
    import atexit
    atexit.register(lambda: os.path.exists(ALIVE_FILE) and os.remove(ALIVE_FILE))
    cfg = _cfg()
    ann = cfg.get("announcer") or {}
    webhook = ann.get("webhook_url") or ""
    if not webhook.startswith("https://discord.com/api/webhooks/"):
        print("No webhook_url in settings.json under \"announcer\".")
        return
    poll = float(ann.get("poll_seconds", 1))
    score_hook = ann.get("scoreboard_webhook_url") or webhook
    fut_hook = ann.get("futures_webhook_url") or webhook
    sc = _load_score()

    import webull_options
    wb = webull_options.WebullOptions(cfg)
    wb.paper = False
    wb.connect()
    print("Fill Announcer v3 up — fills at %.0fs, milestones on live quotes." % poll)
    _post(webhook, "📡 Fill Announcer v3 online — options fills, "
                   "milestones, stop-outs, and the scoreboard.")
    if fut_hook != webhook:
        _post(fut_hook, "📡 Fill Announcer v3 online — futures entries and "
                        "exits post here.")
    board = _score_board(sc)
    if board:
        _post(score_hook, board)

    seen = _load_seen()
    open_pos = {}          # con -> {entry, qty, hit:set(), occ}
    first_pass = True
    last_quote = 0.0
    last_beat = 0.0
    while True:
        if os.path.exists(STOP_FILE) and os.path.getsize(STOP_FILE) > 0:
            # empty stop file = inert (9/1: the sandbox mount can write but
            # not delete, so a cleared stop is truncated, not removed)
            print("stop file found — announcer signing off.")
            _save_seen(seen)
            return
        if time.time() - last_beat >= 15:
            last_beat = time.time()
            try:
                with open(ALIVE_FILE, "w") as _f:
                    _f.write(str(int(last_beat)))
            except OSError:
                pass
        try:
            # ---- fills: margin AND futures accounts -----------------------
            _rows = [(od, False) for od in _recent_orders(wb)]
            _fut = getattr(wb, "futures_account_id", None)
            if _fut:
                try:
                    _rows += [(od, True) for od in _recent_orders(wb, _fut)]
                except Exception:                       # noqa: BLE001
                    pass
            for od, is_fut in _rows:
                f = _parse(od)
                if not f or not f["oid"] or f["oid"] in seen:
                    continue
                seen.add(f["oid"])
                con = _con(f)
                if first_pass:
                    continue           # history isn't news
                if "OPEN" in f["intent"] or (f["intent"] == "" and f["side"] == "BUY"):
                    p = open_pos.get(con)
                    if p and f["px"]:
                        tot = p["qty"] + f["qty"]
                        p["entry"] = (p["entry"] * p["qty"] + f["px"] * f["qty"]) / tot
                        p["qty"] = tot
                    elif f["px"]:
                        occ = None
                        try:
                            if f["strike"] and f["otype"] and len(f["exp"]) == 10:
                                occ = webull_options.occ_symbol(
                                    f["sym"], f["exp"],
                                    "CALL" if f["otype"] == "C" else "PUT",
                                    float(f["strike"]))
                        except Exception:               # noqa: BLE001
                            occ = None
                        open_pos[con] = {"entry": f["px"], "qty": f["qty"],
                                         "hit": set(), "occ": occ}
                    # underlying at fill (9/1, G's ask) — best effort
                    _u = ""
                    if f["strike"]:
                        try:
                            _up = wb.stock_price(f["sym"])
                            if _up:
                                _u = "  (%s @ %.2f)" % (f["sym"], float(_up))
                        except Exception:               # noqa: BLE001
                            _u = ""
                    line = "ENTRY %s @ %s x%s%s" % (con, f["px"], f["qty"], _u)
                else:
                    p = open_pos.pop(con, None)
                    pct = None
                    if p and f["px"] and p["entry"]:
                        pct = (f["px"] - p["entry"]) / p["entry"] * 100
                    if pct is not None and pct < 0:
                        line = "⛔ STOPPED OUT %s @ %s x%s  (%.0f%%)" % (
                            con, f["px"], f["qty"], pct)
                    elif pct is not None:
                        line = "EXIT %s @ %s x%s  (+%.0f%%)" % (
                            con, f["px"], f["qty"], pct)
                    else:
                        line = "EXIT %s @ %s x%s" % (con, f["px"], f["qty"])
                    # SCOREBOARD: realized dollars on this close
                    if p and f["px"] and p.get("entry"):
                        mult = 100.0 if f["strike"] else \
                            FUT_MULT.get(str(f["sym"])[:3].rstrip("0123456789"), 1.0)
                        dollars = (f["px"] - p["entry"]) * mult * f["qty"]
                        _score_add(sc, f["sym"], dollars)
                        _post(score_hook, _score_line(sc, f["sym"]))
                print(time.strftime("%H:%M:%S"), line)
                _post(fut_hook if is_fut else webhook, line)
            if first_pass:
                first_pass = False
                _save_seen(seen)

            # ---- milestones off live quotes (every ~2s) -------------------
            now = time.time()
            if open_pos and now - last_quote >= 2.0:
                last_quote = now
                for con, p in list(open_pos.items()):
                    if not p.get("occ"):
                        continue
                    try:
                        ask, bid, _ = wb.ask_bid(p["occ"])
                    except Exception:                   # noqa: BLE001
                        continue
                    if not bid:
                        continue
                    pct = (float(bid) - p["entry"]) / p["entry"] * 100
                    for m in MILESTONES:
                        if pct >= m and m not in p["hit"]:
                            p["hit"].add(m)
                            line = "📈 %s +%d%%  (%.2f -> %.2f)" % (
                                con, m, p["entry"], float(bid))
                            print(time.strftime("%H:%M:%S"), line)
                            _post(webhook, line)
            if len(seen) % 5 == 0:
                _save_seen(seen)
        except Exception as e:                          # noqa: BLE001
            print("poll error:", str(e)[:120])
            time.sleep(10)
        time.sleep(poll)


if __name__ == "__main__":
    main()
