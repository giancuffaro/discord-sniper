"""futures_protection_proof.py — the one real trade that opens the futures door.

WHY THIS EXISTS
G funded futures and his alerts will not trade, because every Webull futures
OPEN is refused before any broker call. That refusal is deliberate: Webull has
no OCO/OTOCO for futures, so the protective stop is a SEPARATE GTC STOP_LOSS
placed AFTER the fill — and if that second leg silently fails he is long a
micro overnight with no stop on a ~$600 account. The stop machinery in
webull_futures.py is built and unit-tested against a fake broker. What was
never done is the only thing that matters: running the loop against the REAL
broker once and looking at what it answered.

This is that run. It executes the real sequence ONCE on ONE MES contract
(the smallest instrument, $5 a point) and verifies at the broker after every
single step:

    buy 1 MES at market  ->  fill confirmed by a broker READ (never assumed)
    ->  GTC STOP_LOSS placed under the fill  ->  re-read and matched EXACTLY
    ->  stop cancelled  ->  cancel confirmed by re-read
    ->  position flattened  ->  flat confirmed by a positions read

On a clean full pass it writes futures_protection_proof.json: the timestamp,
the contract, every broker order id, every verification, and the sha256 of
webull_futures.py as it was when proven. webull_futures.protective_entries_ready()
reads that file. Any later edit to webull_futures.py changes the hash, the
proof stops applying, and the door closes again until it is re-proven.

FAILURE IS THE IMPORTANT PATH. Anything uncertain STOPS the run, says exactly
what is unverified, and names the client order id to look up at Webull. It
never retries, and it never leaves a position with an unverified stop without
saying so in the loudest words it has.

HOW G RUNS IT
    PROVE FUTURES STOPS.bat              the dry run: preflight + the plan
    python futures_protection_proof.py   the same dry run from a terminal
    python futures_protection_proof.py --live     sends, after he types YES

Dry run is the DEFAULT. Sending needs BOTH --live and the typed YES. Nothing
here is ever run by the bridge, the autopilot or a scheduled task: it places a
real order, and real-money actions are G's alone.

EXIT CODES
    0 clean pass (proof written)   5 stop placement/verification unsafe
    2 preflight refused            6 cancel not confirmed
    3 entry not sent               7 the stop FILLED instead of cancelling
    4 fill not confirmed           8 flatten / flat not confirmed
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import eastern                                                # noqa: E402
import market_hours                                           # noqa: E402
import webull_futures as futures                              # noqa: E402

# --- the shape of the test, all in one place -------------------------------
ROOT = "MES"                  # smallest equity-index future: $5 a point
STOP_POINTS = 10.0            # $50 of intended risk on a one-lot MES
TICK = 0.25                   # MES trades on quarter points
POINT_VALUE = 5.0             # dollars per point, one MES contract
SPREAD_TICKS = 1              # a normal MES market is one tick wide
COMMISSION_PER_SIDE = 1.25    # Webull micro futures, per contract per side
MIN_FUTURES_BP = 500.0        # refuse below this: day margin plus room to be wrong
FILL_WAIT_S = 60.0            # how long a market order gets to come back FILLED
FLAT_WAIT_S = 60.0
POLL_S = 2.5                  # Order Detail is 2 per 2s — stay under it
CONTRACT_RE = re.compile(r"^%s[FGHJKMNQUVXZ]\d{1,2}$" % ROOT)
WORKING = ("WORK", "PEND", "OPEN", "SUBMIT", "PART", "QUEUE", "ACCEPT")
DEAD = ("CANCEL", "REJECT", "FAIL", "EXPIR")

BAR = "=" * 72


def say(text=""):
    print(text)
    sys.stdout.flush()


def loud(title, lines):
    """The block he must not be able to scroll past."""
    say("")
    say("!" * 72)
    say("!!  " + title)
    say("!" * 72)
    for ln in lines:
        say("!!  " + ln)
    say("!" * 72)
    say("")


def _now():
    return eastern.now()


def _stamp():
    return _now().strftime("%Y-%m-%d %H:%M:%S ET")


def _cid(prefix):
    """A durable client order id, reserved BEFORE the send. It is the only
    handle on an order whose response was ambiguous."""
    return "%s%s%s" % (prefix, _now().strftime("%y%m%d%H%M%S"),
                       os.urandom(2).hex())


def _cfg():
    with open(os.path.join(HERE, "settings.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _num(row, *names):
    for n in names:
        v = row.get(n)
        if v not in (None, "", "0", 0):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _mask(acct):
    a = str(acct or "")
    return ("..." + a[-4:]) if len(a) > 4 else "set"


# --- broker reads ----------------------------------------------------------
def read_positions(wb, account):
    """(rows for this root, read_ok). An unreadable read is NOT a flat account —
    that confusion is exactly what F02 cost in September."""
    body, _why = wb._try_calls(["position_v2", "position", "account_v2",
                                "trade"], ["position"], account)  # noqa: SLF001
    if body is None:
        return [], False
    items = body if isinstance(body, list) else \
        ((body or {}).get("positions") or (body or {}).get("data") or [])
    rows = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").upper()
        if not sym.startswith(ROOT):
            continue
        try:
            qty = int(float(it.get("quantity") or it.get("position") or 0))
        except (TypeError, ValueError):
            qty = 0
        if qty:
            rows.append({"symbol": sym, "qty": qty, "raw": it})
    return rows, True


def read_working_orders(wb, account):
    """(working orders on this root, read_ok)."""
    body, _why = wb._try_calls(["order_v3", "order"],                # noqa: SLF001
                               ["list_open_orders", "open_orders",
                                "list_orders"], account)
    if body is None:
        return [], False
    items = body if isinstance(body, list) else \
        ((body or {}).get("orders") or (body or {}).get("data") or [])
    rows = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").upper()
        if not sym.startswith(ROOT):
            continue
        st = str(it.get("status") or it.get("order_status") or "").upper()
        if st and not any(k in st for k in WORKING):
            continue
        rows.append({"symbol": sym, "status": st,
                     "order_id": it.get("order_id") or it.get("orderId"),
                     "client_order_id": it.get("client_order_id")})
    return rows, True


def order_row(api, account, cid):
    """This exact order as the broker describes it, or None. Never a list scan:
    an order is looked up by the id we reserved for it."""
    try:
        res = api.get_order_detail(account, cid)
        if getattr(res, "status_code", None) != 200:
            return None
        data = res.json()
    except Exception:                                         # noqa: BLE001
        return None
    rows = data.get("orders") if isinstance(data, dict) else None
    row = rows[0] if isinstance(rows, list) and len(rows) == 1 else data
    return row if isinstance(row, dict) else None


def await_fill(api, account, cid, contract, side, deadline_s):
    """(row, status, fill_price, why) once this exact order is FILLED, dead, or
    out of time. 'unknown' status means we do NOT know whether we are in."""
    end = time.time() + deadline_s
    last = "unknown"
    while True:
        row = order_row(api, account, cid)
        if row is not None:
            last = str(row.get("status") or "").upper() or "unknown"
            if str(row.get("symbol") or "").upper() != contract or \
                    str(row.get("side") or "").upper() != side:
                return row, "mismatch", None, (
                    "the broker's row for %s is %s %s, not %s %s"
                    % (cid, row.get("side"), row.get("symbol"), side, contract))
            if "FILL" in last and "PART" not in last:
                qty = _num(row, "filled_quantity", "filledQuantity",
                           "quantity", "total_quantity")
                px = _num(row, "avg_fill_price", "avgFillPrice",
                          "filled_avg_price", "average_price", "avg_price",
                          "filled_price", "price")
                if qty is not None and int(qty) != 1:
                    return row, "mismatch", None, (
                        "the broker says %s filled %g contracts, not 1"
                        % (cid, qty))
                if not px:
                    return row, "nofill_price", None, (
                        "the broker says %s is FILLED but gave no fill price"
                        % cid)
                return row, "filled", float(px), ""
            if any(k in last for k in DEAD):
                return row, "dead", None, ("the broker says %s is %s" % (cid, last))
        if time.time() >= end:
            return row, "timeout", None, (
                "%s never came back FILLED (last status: %s)" % (cid, last))
        time.sleep(POLL_S)


# --- the proof document ----------------------------------------------------
class Proof(object):
    """Every step, recorded as the broker answered it. Written only on a clean
    full pass — a half-finished run leaves no file, and no file means the
    futures door stays shut."""

    def __init__(self, contract, account):
        self.doc = {"proof_version": futures.PROOF_VERSION,
                    "written_at": None, "root": ROOT, "contract": contract,
                    "account_tail": _mask(account),
                    "module": "webull_futures.py", "module_sha256": None,
                    "stop_points": STOP_POINTS, "orders": {}, "steps": []}

    def step(self, name, ok, detail):
        self.doc["steps"].append({"name": name, "ok": bool(ok),
                                  "at": _stamp(), "detail": str(detail)[:400]})
        say("   [%s] %-18s %s" % ("PASS" if ok else "FAIL", name, detail))

    def order(self, which, **kw):
        self.doc["orders"][which] = kw

    def clean(self):
        got = {s["name"]: s["ok"] for s in self.doc["steps"]}
        return all(got.get(n) for n in futures.PROOF_STEPS)

    def write(self):
        self.doc["written_at"] = _now().isoformat(timespec="seconds")
        self.doc["module_sha256"] = futures.module_sha256()
        path = os.path.join(HERE, futures.PROOF_FILE)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path


# --- preflight -------------------------------------------------------------
def preflight(want_live):
    """(ok, client, account, api, contract, notes). Nothing is sent from here;
    every answer comes from the broker or the clock."""
    notes, bad = [], []

    now = _now()
    open_now = market_hours.futures_open(now)
    open_soon = market_hours.futures_open(now + dt.timedelta(minutes=20))
    if not open_now:
        bad.append("the CME futures session is CLOSED right now (%s)"
                   % now.strftime("%a %H:%M ET"))
    elif not open_soon:
        bad.append("the futures session closes within 20 minutes — this run "
                   "needs a live market from entry to flat")
    else:
        notes.append("futures session OPEN (%s)" % now.strftime("%a %H:%M ET"))

    try:
        import webull_options as W
        if not W.SDK_OK:
            bad.append("the Webull SDK is not installed (%s)" % str(W.SDK_WHY)[:80])
            return False, None, None, None, None, (notes, bad)
        client = W.WebullOptions(_cfg())
        acct = client.connect()
        notes.append("connected; options account %s" % _mask(acct))
    except Exception as e:                                    # noqa: BLE001
        bad.append("could not connect to Webull: %s" % str(e)[:140])
        return False, None, None, None, None, (notes, bad)

    try:
        account, api = futures._stop_api(client)              # noqa: SLF001
        notes.append("futures account %s; exact stop API present "
                     "(order_v3.place_order / get_order_detail / cancel_order)"
                     % _mask(account))
    except futures.FuturesRefused as e:
        bad.append(str(e))
        return False, client, None, None, None, (notes, bad)

    bp = client.futures_buying_power()
    if bp is None:
        bad.append("Webull would not say what the futures account's buying "
                   "power is — a number this run depends on cannot be guessed")
    elif float(bp) < MIN_FUTURES_BP:
        bad.append("futures buying power is $%.2f, under the $%.0f this run "
                   "requires" % (float(bp), MIN_FUTURES_BP))
    else:
        notes.append("futures buying power $%.2f" % float(bp))

    contract = None
    try:
        contract = futures.front_month(client, ROOT)
        if not CONTRACT_RE.match(str(contract or "").upper()):
            bad.append("front_month() answered %r, which is not an exact %s "
                       "contract code" % (contract, ROOT))
            contract = None
        else:
            contract = str(contract).upper()
            notes.append("front month resolves to %s" % contract)
    except futures.FuturesRefused as e:
        bad.append(str(e))

    rows, ok = read_positions(client, account)
    if not ok:
        bad.append("could not read the futures account's positions — this run "
                   "will not send an order it cannot then verify")
    elif rows:
        bad.append("the futures account already holds %s — flatten it (or run "
                   "this another day); a second %s position would make every "
                   "verification below ambiguous"
                   % (", ".join("%s x%d" % (r["symbol"], r["qty"]) for r in rows),
                      ROOT))
    else:
        notes.append("no %s position open" % ROOT)

    wrk, ok = read_working_orders(client, account)
    if not ok:
        bad.append("could not read the futures account's working orders — "
                   "check the Webull app by hand; nothing was sent")
    elif wrk:
        bad.append("the futures account already has %d working %s order(s): %s "
                   "— cancel them first" % (len(wrk), ROOT,
                   ", ".join(str(w.get("order_id")) for w in wrk)))
    else:
        notes.append("no working %s orders" % ROOT)

    if want_live:
        ready, why = futures.protection_proof_state()
        notes.append("entry gate today: %s (%s)"
                     % ("OPEN" if ready else "SHUT", why))

    return (not bad), client, account, api, contract, (notes, bad)


def plan_text(contract, bp):
    risk = STOP_POINTS * POINT_VALUE
    spread = SPREAD_TICKS * TICK * POINT_VALUE
    fees = 2 * COMMISSION_PER_SIDE
    return [
        "WHAT THIS IS ABOUT TO DO, in order, on YOUR real futures account:",
        "",
        "  1. BUY 1 %s at MARKET.  One contract. Not two, not the front" % contract,
        "     month of anything else.",
        "  2. Ask Webull what that order did, by its own id, until it says",
        "     FILLED with a price. It does not assume a fill.",
        "  3. Place ONE GTC STOP_LOSS to SELL 1 %s, %g points under the" % (contract, STOP_POINTS),
        "     fill (that is $%.0f of intended risk)." % risk,
        "  4. Read that stop back and match it EXACTLY: contract, side, size,",
        "     stop price, STOP_LOSS, and working at the broker.",
        "  5. Cancel the stop, then read it back again and require CANCELLED.",
        "  6. SELL 1 %s at market to go flat, and confirm flat from a" % contract,
        "     positions read.",
        "",
        "WHAT IT COSTS IF EVERYTHING GOES NORMALLY:",
        "  about $%.2f — $%.2f of spread plus $%.2f of commission" % (spread + fees, spread, fees),
        "  (%d tick x $%.0f a point, %g x $%.2f a side)." % (SPREAD_TICKS, POINT_VALUE, 2, COMMISSION_PER_SIDE),
        "",
        "WHAT IT RISKS IF SOMETHING GOES WRONG:",
        "  Between the fill and the confirmed stop you are LONG 1 %s with" % contract,
        "  NO stop. That window is seconds, but it is real: %s moves $%.0f a" % (ROOT, POINT_VALUE),
        "  point and a fast $%.0f move is $%.0f. If the stop cannot be" % (STOP_POINTS, risk),
        "  verified, this script STOPS and tells you exactly what to close by",
        "  hand — it will not quietly retry and it will not leave you guessing.",
        "",
        "  Futures buying power right now: %s" % ("$%.2f" % bp if bp is not None else "unreadable"),
    ]


# --- the sequence ----------------------------------------------------------
def run_live(client, account, api, contract, proof):
    """The real thing. Returns an exit code; writes nothing unless it all passed."""
    # 1) ENTRY ---------------------------------------------------------------
    entry_cid = _cid("proofentry")
    say("")
    say("   sending  BUY 1 %s MARKET   client id %s" % (contract, entry_cid))
    try:
        entry_oid = futures._place(client, contract, "BUY", 1,       # noqa: SLF001
                                   None, client_order_id=entry_cid)
    except futures.FuturesRefused as e:
        proof.step("entry_sent", False, "refused: %s" % str(e)[:200])
        loud("NOTHING WAS SENT — the entry was refused", [
            str(e)[:200],
            "",
            "webull_futures refuses rather than guessing, so no order should",
            "exist. Confirm it: Webull app -> Futures -> Orders, look for",
            "client id %s." % entry_cid,
            "If one IS there, cancel it by hand. Do not re-run this until the",
            "account is flat with no working %s orders." % ROOT])
        return 3
    except Exception as e:                                    # noqa: BLE001
        proof.step("entry_sent", False, "uncertain: %s" % str(e)[:200])
        loud("AN ENTRY MAY OR MAY NOT HAVE BEEN SENT", [
            "The send raised something it does not know how to read: %s" % str(e)[:140],
            "",
            "OPEN WEBULL NOW. Futures -> Orders and Positions.",
            "Client order id: %s" % entry_cid,
            "Contract: %s" % contract,
            "If there is a working order, cancel it. If you are LONG, you have",
            "NO STOP — close it by hand. Nothing else will be sent by this run."])
        return 3
    proof.order("entry", client_order_id=entry_cid, broker_order_id=str(entry_oid),
                sent_at=_stamp(), side="BUY", quantity=1, order_type="MARKET")
    proof.step("entry_sent", True, "BUY 1 %s, broker order id %s"
               % (contract, entry_oid))

    # 2) FILL, from the broker's own mouth -----------------------------------
    row, state, fill, why = await_fill(api, account, entry_cid, contract,
                                       "BUY", FILL_WAIT_S)
    if state != "filled":
        proof.step("entry_filled", False, why)
        if state == "dead":
            loud("NOTHING IS HELD — the entry never filled", [
                why, "",
                "The account should be flat. Confirm it in the Webull app",
                "(Futures -> Positions) before running this again."])
            return 4
        loud("YOU MAY BE LONG 1 %s WITH NO STOP" % contract, [
            why, "",
            "This run will NOT place a stop on a fill it cannot confirm, and",
            "it will NOT send a second order.",
            "",
            "OPEN WEBULL NOW: Futures -> Orders, client id %s." % entry_cid,
            "  - if it FILLED, you are long 1 %s with no protection." % contract,
            "    Close it by hand, or put a stop on it by hand, right now.",
            "  - if it is still working, cancel it.",
            "Nothing further will be sent by this run."])
        return 4
    proof.doc["fill"] = fill
    proof.order("entry", **dict(proof.doc["orders"]["entry"],
                                filled_at=_stamp(), fill_price=fill,
                                broker_status=str(row.get("status"))))
    proof.step("entry_filled", True, "broker says FILLED 1 %s at %g"
               % (contract, fill))

    # 3) THE PROTECTIVE STOP --------------------------------------------------
    stop_px = round((fill - STOP_POINTS) / TICK) * TICK
    stop_cid = _cid("proofstop")
    try:
        payload = futures.protective_stop_order(contract, "LONG", 1, fill,
                                                stop_px, stop_cid)
    except futures.FuturesRefused as e:
        proof.step("stop_placed", False, "payload refused: %s" % str(e)[:200])
        loud("YOU ARE LONG 1 %s AND THERE IS NO STOP" % contract, [
            "The stop could not even be built: %s" % str(e)[:160],
            "",
            "CLOSE IT BY HAND NOW: Webull app -> Futures -> Positions -> %s." % contract,
            "Entry client id %s, filled at %g." % (entry_cid, fill)])
        return 5
    say("   sending  SELL 1 %s STOP_LOSS %s GTC   client id %s"
        % (contract, payload["stop_price"], stop_cid))
    try:
        futures.submit_protective_stop(client, payload)
    except futures.FuturesRefused as e:
        proof.step("stop_placed", False, str(e)[:200])
        seen = order_row(api, account, stop_cid)
        loud("YOU ARE LONG 1 %s AND THE STOP IS UNVERIFIED" % contract, [
            str(e)[:160],
            "The broker's own answer for the stop id right now: %s"
            % (json.dumps(seen)[:160] if seen else "nothing came back"),
            "",
            "THE POSITION IS NOT PROTECTED AND THIS RUN WILL SEND NOTHING ELSE.",
            "A stop may still be working, so an automatic flatten could leave a",
            "resting order that opens a SHORT later. Do it by hand, in order:",
            "  1. Webull app -> Futures -> Orders. Cancel anything with client",
            "     id %s (or any working %s order)." % (stop_cid, contract),
            "  2. Then Positions -> close the 1 %s you are long." % contract,
            "Entry client id %s, filled at %g." % (entry_cid, fill)])
        return 5
    proof.order("stop", client_order_id=stop_cid, placed_at=_stamp(),
                side=payload["side"], stop_price=payload["stop_price"],
                order_type=payload["order_type"],
                time_in_force=payload["time_in_force"], quantity=1)
    proof.step("stop_placed", True, "submit_protective_stop accepted %s at %s"
               % (stop_cid, payload["stop_price"]))

    # 4) READ IT BACK AND MATCH IT EXACTLY -----------------------------------
    try:
        status = futures.protective_stop_status(client, payload)
    except futures.FuturesRefused as e:
        proof.step("stop_verified", False, str(e)[:200])
        loud("YOU ARE LONG 1 %s AND THE STOP DID NOT VERIFY" % contract, [
            str(e)[:160],
            "",
            "Same drill, by hand, in this order:",
            "  1. cancel any working order with client id %s" % stop_cid,
            "  2. then close the 1 %s you are long." % contract,
            "Entry client id %s, filled at %g." % (entry_cid, fill)])
        return 5
    proof.step("stop_verified", True,
               "re-read matched exactly: %s %s STOP_LOSS %s GTC x1, status %s"
               % (payload["side"], contract, payload["stop_price"], status))

    # 5) CANCEL, AND PROVE THE CANCEL ----------------------------------------
    say("   cancelling the stop...")
    try:
        outcome = futures.cancel_protective_stop(client, payload)
    except futures.FuturesRefused as e:
        proof.step("stop_cancelled", False, str(e)[:200])
        loud("THE STOP MAY STILL BE WORKING, AND YOU ARE STILL LONG", [
            str(e)[:160],
            "",
            "Nothing else will be sent: flattening under a live stop can leave",
            "a resting order that opens a SHORT after you are flat.",
            "  1. Webull app -> Futures -> Orders: cancel client id %s" % stop_cid,
            "  2. Then Positions: close the 1 %s." % contract,
            "Entry client id %s, filled at %g." % (entry_cid, fill)])
        return 6
    if outcome == "filled":
        proof.step("stop_cancelled", False,
                   "the stop FILLED before the cancel — the market reached %s"
                   % payload["stop_price"])
        rows, ok = read_positions(client, account)
        loud("THE STOP FILLED INSTEAD OF CANCELLING — NO PROOF WRITTEN", [
            "The market traded down to %s and the stop did its job: you were"
            % payload["stop_price"],
            "stopped out for about $%.0f. That is the stop WORKING, but it is"
            % (STOP_POINTS * POINT_VALUE),
            "not proof that a cancel is confirmable, so the door stays shut.",
            "",
            ("Positions read says %s." % ("FLAT" if ok and not rows else
             ("still holding %s" % ", ".join("%s x%d" % (r["symbol"], r["qty"])
                                             for r in rows)) if ok else
             "unreadable — check the app")),
            "Check it yourself, then run this again on a calmer tape."])
        return 7
    proof.step("stop_cancelled", True, "cancel_protective_stop returned %s" % outcome)

    try:
        status = futures.protective_stop_status(client, payload)
    except futures.FuturesRefused as e:
        proof.step("cancel_confirmed", False, str(e)[:200])
        loud("THE CANCEL IS NOT CONFIRMED — DO NOT ASSUME IT IS GONE", [
            str(e)[:160],
            "",
            "  1. Webull app -> Futures -> Orders: check client id %s" % stop_cid,
            "  2. Then Positions: close the 1 %s if you are still long." % contract])
        return 6
    if status != "CANCELLED":
        proof.step("cancel_confirmed", False,
                   "re-read says %s, not CANCELLED" % status)
        loud("THE CANCEL IS NOT CONFIRMED (broker says %s)" % status, [
            "Cancel client id %s by hand, then close the 1 %s."
            % (stop_cid, contract)])
        return 6
    proof.step("cancel_confirmed", True,
               "re-read of %s says CANCELLED" % stop_cid)

    # 6) FLAT ----------------------------------------------------------------
    flat_cid = _cid("proofflat")
    say("   sending  SELL 1 %s MARKET to go flat   client id %s"
        % (contract, flat_cid))
    try:
        flat_oid = futures._place(client, contract, "SELL", 1,       # noqa: SLF001
                                  None, client_order_id=flat_cid)
    except Exception as e:                                    # noqa: BLE001
        proof.step("position_flattened", False, str(e)[:200])
        loud("YOU ARE STILL LONG 1 %s AND THERE IS NO STOP ON IT" % contract, [
            "The flatten could not be sent: %s" % str(e)[:140],
            "The protective stop was already cancelled, so nothing is guarding",
            "this position.",
            "",
            "CLOSE IT BY HAND NOW: Webull app -> Futures -> Positions -> %s." % contract,
            "Flatten client id %s, entry client id %s." % (flat_cid, entry_cid)])
        return 8
    proof.order("flatten", client_order_id=flat_cid,
                broker_order_id=str(flat_oid), sent_at=_stamp(),
                side="SELL", quantity=1, order_type="MARKET")
    row, state, exit_px, why = await_fill(api, account, flat_cid, contract,
                                          "SELL", FLAT_WAIT_S)
    if state != "filled":
        proof.step("position_flattened", False, why)
        loud("THE FLATTEN IS NOT CONFIRMED — YOU MAY STILL BE LONG", [
            why, "",
            "There is NO stop on this position: it was cancelled two steps ago.",
            "CLOSE IT BY HAND NOW: Webull app -> Futures -> Positions -> %s." % contract,
            "Flatten client id %s." % flat_cid])
        return 8
    proof.step("position_flattened", True,
               "broker says the SELL filled at %g (%s)" % (exit_px, flat_cid))

    rows, ok = read_positions(client, account)
    if not ok:
        proof.step("flat_confirmed", False, "the positions read did not answer")
        loud("COULD NOT CONFIRM YOU ARE FLAT", [
            "The exit order says FILLED, but the positions read did not answer,",
            "and an unreadable read is not a flat account.",
            "Check Webull -> Futures -> Positions yourself. No proof written."])
        return 8
    if rows:
        proof.step("flat_confirmed", False,
                   "still holding %s" % ", ".join("%s x%d" % (r["symbol"], r["qty"])
                                                  for r in rows))
        loud("YOU ARE NOT FLAT", [
            "Positions still show: %s" % ", ".join("%s x%d" % (r["symbol"], r["qty"])
                                                   for r in rows),
            "There is no stop on it. Close it by hand now."])
        return 8
    proof.step("flat_confirmed", True, "positions read shows no %s position" % ROOT)

    pl = (exit_px - fill) * POINT_VALUE - 2 * COMMISSION_PER_SIDE
    say("")
    say("   round trip: in %g, out %g, about $%.2f after commission"
        % (fill, exit_px, pl))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Prove the Webull futures fill -> stop -> verify -> cancel "
                    "loop on one real MES contract.")
    ap.add_argument("--live", action="store_true",
                    help="actually send the orders (G only, and he still has "
                         "to type YES)")
    ap.add_argument("--dry-run", action="store_true",
                    help="preflight and print the plan, send nothing (default)")
    a = ap.parse_args(argv)
    live = bool(a.live) and not a.dry_run

    say("")
    say(BAR)
    say("  FUTURES PROTECTION PROOF  -  %s  -  %s"
        % ("LIVE, ONE REAL MES CONTRACT" if live else "DRY RUN, NOTHING SENT",
           _stamp()))
    say(BAR)
    say("")
    say("  PREFLIGHT")
    ok, client, account, api, contract, (notes, bad) = preflight(live)
    for n in notes:
        say("   [ OK ] %s" % n)
    for b in bad:
        say("   [ NO ] %s" % b)
    if not ok:
        say("")
        say("  REFUSED. Nothing was sent, and nothing will be until every line")
        say("  above is [ OK ]. The futures entry gate stays shut.")
        say("")
        return 2

    bp = client.futures_buying_power()
    say("")
    for ln in plan_text(contract, bp):
        say("  " + ln)
    say("")

    if not live:
        say(BAR)
        say("  DRY RUN — nothing was sent, no order exists, nothing changed.")
        say("")
        say("  If the plan above is what you want, YOU run it:")
        say("      python futures_protection_proof.py --live")
        say("  and watch the Webull futures screen while it goes.")
        say(BAR)
        say("")
        return 0

    say(BAR)
    say("  This will place REAL orders on your REAL futures account, now.")
    say("  Type YES (capitals) to go ahead, anything else to stop.")
    say(BAR)
    try:
        typed = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        typed = ""
    if typed != "YES":
        say("")
        say("  Stopped. Nothing was sent.")
        say("")
        return 2

    proof = Proof(contract, account)
    proof.step("preflight", True,
               "session open, %s front month, stop API present, futures BP %s, "
               "no %s position, no working %s orders"
               % (contract, ("$%.2f" % bp) if bp is not None else "unknown",
                  ROOT, ROOT))
    code = run_live(client, account, api, contract, proof)
    say("")
    if code == 0 and proof.clean():
        path = proof.write()
        say(BAR)
        say("  PROVED. Every step verified at the broker, and you are flat.")
        say("  Written: %s" % os.path.basename(path))
        say("  Webull futures OPENs are now allowed. Restart the bridge")
        say("  (RESTART BRIDGE.bat) so /status and the popup pick it up.")
        say("")
        say("  This proof dies the moment webull_futures.py is edited — the")
        say("  file's sha256 is in it. Change that file, run this again.")
        say(BAR)
    else:
        say(BAR)
        say("  NOT PROVED. No proof file was written; Webull futures entries")
        say("  stay refused. Read the block above and finish it by hand.")
        say(BAR)
    say("")
    return code


if __name__ == "__main__":
    sys.exit(main())
