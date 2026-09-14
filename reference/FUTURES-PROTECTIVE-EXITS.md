# Futures protective exits (Webull, MES/MNQ)

Current state: **Webull futures entries and the index mirror are blocked.**
No stop, target, or ratchet currently manages a Webull futures fill. A number
stored in the position book is not an exit order.

Webull supports standalone `STOP_LOSS` orders with `GTC` time in force, but
its futures API does not support OTO/OCO/OTOCO. Two independent exits (stop
and target) could both execute and reverse the one-lot position. The design
therefore uses **one broker-held exit order**:

1. Admit a new entry only after the exact contract, account, size, side and
   broker API capability have been verified. Place the entry with a durable,
   unique client order ID. Confirm its own fill quantity and price through
   the futures account; do not borrow a fill from another order or position.
2. Immediately calculate the posted stop or default 25-point risk from the
   confirmed fill. Submit one opposite-side `STOP_LOSS` ×1 with `GTC` and a
   separately durable client order ID. Query that exact ID and require a
   matching contract, side, size, trigger price, type and working status.
3. If submission/confirmation is uncertain, never send a duplicate stop or
   claim protection. Surface an urgent unresolved state with both order IDs;
   reconcile the broker order and position before any further exit attempt.
4. On a caller CLOSE or future target trigger, **replace the same stop order
   with MARKET**, which Webull documents as supported for futures stops.
   Query the same order ID for its fill. If its status is uncertain, do not
   submit an additional market exit. A filled stop and a requested manual
   exit are the same one-lot exit, never two orders.
5. Tighten a ratchet only by replacing the same stop's trigger price after a
   reliable futures quote feed is available. Never loosen it. If quote feed
   is unavailable, the original broker stop continues to protect the trade;
   no client-side target or ratchet is claimed. At expiry/session boundaries,
   reconcile any GTC stop with the actual position before touching it.

The offline payload, exact order-detail verification and same-order
stop-to-market replacement helpers are in `webull_futures.py` with fake-broker
tests. They are intentionally not connected to live entries. Before lifting
the hard entry gate, the remaining work is: durable ID reservation before
submission, exact futures-account fill reconciliation, stop placement from
that confirmed fill, restart recovery, and a supervised broker execution
test proving a working stop, replacement, cancellation/partial-fill races,
and a flat end state. The mirror's 25/50 replay also needs to be rerun against
the actual exit policy; its present historical result is hypothetical.
