"""An EDITED alert replaces the one it corrects — it never runs beside it.

The live case, 2026-09-14, real money: "PT | ei trades" posted
`Entry — Contract: TSLA $357.5c — Price: $1.42` at 10:21 in Platinum nitro and
then EDITED that same Discord message to `357.5p`. The bridge armed two
round-number pullbacks off the ONE message —

    10:21:21  PULLBACK TSLA CALL: waiting for a dip to $358
    10:22:17  PULLBACK TSLA PUT:  waiting for a bounce to $359

— nothing cancelled the first, and at 10:24:04 the stale CALL arm bought
TSLA 357.5C for $740: the wrong side of a corrected call.

Mock broker, mock book, no network, no orders.
"""
import os
import time
import unittest
from unittest import mock

import alert_revision
import bridge

def _repo_file(*parts):
    """The repo copy, whether this test is run from the folder or elsewhere."""
    for base in (os.path.dirname(os.path.abspath(bridge.__file__)),
                 os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        path = os.path.join(base, *parts)
        if os.path.exists(path):
            return path
    raise AssertionError("can't find %s" % "/".join(parts))

CALL = {"action": "OPEN", "trader": "PT | ei trades", "symbol": "TSLA",
        "side": "CALLS", "strike": 357.5, "expiry": "2026-09-16",
        "limit": 1.42, "entry_mode": "pullback",
        "message_id": "chat-messages-1334-999"}
PUT = dict(CALL, side="PUTS")


class FakeBook(object):
    def __init__(self, state=None, fill=None, bid=None, kind="option"):
        self.state = state
        self.fill = fill
        self.bid = bid
        self.kind = kind
        self.cancelled = []
        self.sold = []
        self.be = []
        self.marked = []
        self.be_ok = True
        self.quotes = None

    def state_of(self, key):
        return self.state

    def info(self, key):
        if not self.state:
            return None
        return {"fill": self.fill, "state": self.state, "kind": self.kind,
                "live": True, "occ": "TSLA260916C00357500",
                "last_bid": self.bid}

    def stop_to_breakeven(self, key):
        self.be.append(key)
        return self.be_ok

    def mark_edit_breakeven(self, key):
        self.marked.append(key)
        return True

    def cancel_entry(self, key, why="pulled"):
        self.cancelled.append((key, why))
        return 0

    # A revision must NEVER reach any of these. Entries only: the ratchet owns
    # every exit.
    def close(self, *a, **k):
        self.sold.append(a)
        raise AssertionError("a revision tried to SELL")

    def plan_exit(self, *a, **k):
        raise AssertionError("a revision tried to exit")


class FakePullback(object):
    def __init__(self, hits=1):
        self.hits = hits
        self.calls = []

    def cancel_order(self, order):
        self.calls.append(dict(order))
        return self.hits

    def cancel_for(self, trader):
        raise AssertionError("a revision must not cancel a trader's whole book")


class Harness(unittest.TestCase):
    def setUp(self):
        bridge._REVISIONS = alert_revision.Revisions()
        self.lines = []
        self.book = FakeBook()
        self.pb = FakePullback()
        patches = [
            mock.patch.object(bridge, "note", self.lines.append),
            mock.patch.object(bridge, "BOOK", self.book),
            mock.patch.object(bridge, "_PULLBACK", self.pb),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def arm(self, order, key="k1", **kw):
        bridge._REVISIONS.record(order, key, **kw)

    def log(self):
        return "\n".join(self.lines)


class SameMessageEdit(Harness):
    def test_edit_call_to_put_cancels_the_first_arm(self):
        self.arm(CALL)
        bridge._revision_check(PUT)
        self.assertEqual(len(self.pb.calls), 1)
        stood_down = self.pb.calls[0]
        self.assertEqual(str(stood_down["side"]), "CALLS")
        self.assertEqual(float(stood_down["strike"]), 357.5)
        self.assertIn("EDITED", self.log())
        self.assertIn("TSLA", self.log())
        self.assertIn("PT | ei trades", self.log())
        self.assertIn("357.5C → 357.5P", self.log())
        self.assertIn("the earlier pullback is cancelled", self.log())
        self.assertIn("only the new one stands", self.log())

    def test_the_new_arm_is_not_cancelled_with_it(self):
        self.arm(CALL)
        bridge._revision_check(PUT)
        self.assertEqual(bridge._REVISIONS.superseded_by(PUT), [])

    def test_resting_entry_order_is_pulled_too(self):
        self.book.state = bridge.positions.WORKING
        self.arm(CALL, key=bridge.tkey(CALL))
        bridge._revision_check(PUT)
        self.assertEqual(len(self.book.cancelled), 1)
        self.assertIn("resting bid pulled", self.log())


KEY = bridge.tkey(CALL)          # the real book key, not a hand-written one


class AlreadyFilled(Harness):
    """THE EDIT EXCEPTION (9/15, G: "if in profit keep the ratchet and set the
    stop to breakeven, if it's a losing trade, close it automatically"). This
    is not a room exit: the caller corrected the CONTRACT, so what we are
    holding is our own misread of their call."""

    def filled(self, fill=7.40, bid=None):
        self.book.state = bridge.positions.FILLED
        self.book.fill = fill
        self.book.bid = bid
        self.arm(CALL, key=KEY)

    def test_green_moves_the_stop_to_breakeven_and_sells_nothing(self):
        self.filled(bid=7.52)
        with mock.patch.object(bridge, "_place_impl",
                               side_effect=AssertionError("sold a winner")):
            bridge._revision_check(PUT)
        self.assertEqual(self.book.be, [KEY])
        self.assertEqual(self.book.marked, [KEY])
        self.assertEqual(self.book.sold, [])
        self.assertIn("EDITED   TSLA — PT | ei trades changed 357.5C \u2192 "
                      "357.5P, but the 357.5C already filled at 7.40 and is "
                      "green (bid 7.52) — stop moved to breakeven, ratchet "
                      "keeps it", self.log())

    def test_flat_counts_as_green(self):
        self.filled(bid=7.40)
        bridge._revision_check(PUT)
        self.assertEqual(self.book.be, [KEY])

    def test_red_closes_through_the_existing_exit_path(self):
        self.filled(bid=7.06)
        with mock.patch.object(bridge, "_place_impl",
                               return_value=(True, "sold")) as sell:
            bridge._revision_check(PUT)
        self.assertEqual(self.book.be, [])
        self.assertEqual(sell.call_count, 1)
        sent = sell.call_args.args[0]
        self.assertEqual(sent["action"], "CLOSE")
        self.assertEqual(sent["source"], "edit")
        self.assertEqual(sent["symbol"], "TSLA")
        self.assertEqual(sent["strike"], 357.5)
        self.assertEqual(str(sent["side"]), "CALLS")
        self.assertIn("edit replacement", sent["raw"])
        self.assertIn("already filled at 7.40 and is red (bid 7.06) — closed "
                      "at market, wrong contract", self.log())

    def test_it_is_never_a_new_sell_routine(self):
        """The resting stop is pulled by claim() inside the same _place_impl
        CLOSE the pullback stock exit uses. Asserted by the route taken."""
        import inspect
        src = inspect.getsource(bridge._edit_close)
        self.assertIn("_place_impl", src)
        self.assertNotIn("place_stop", src)
        self.assertNotIn(".sell(", src)

    def test_a_refused_close_leaves_it_open_and_says_so(self):
        self.filled(bid=7.06)
        with mock.patch.object(bridge, "_place_impl",
                               return_value=(False, "market is closed")):
            bridge._revision_check(PUT)
        self.assertIn("the broker refused", self.log())
        self.assertIn("still open", self.log())

    def test_no_quote_falls_back_to_log_only(self):
        self.filled(bid=None)
        with mock.patch.object(bridge, "_place_impl",
                               side_effect=AssertionError("sold blind")):
            bridge._revision_check(PUT)
        self.assertEqual(self.book.be, [])
        self.assertEqual(self.book.sold, [])
        self.assertIn("no live bid to judge it by", self.log())
        self.assertIn("LEFT ALONE", self.log())
        self.assertIn("ratchet owns it", self.log())

    def test_a_stop_that_cannot_move_is_said_out_loud(self):
        self.filled(bid=7.52)
        self.book.be_ok = False
        bridge._revision_check(PUT)
        self.assertEqual(self.book.marked, [])
        self.assertIn("could not be moved to breakeven", self.log())

    def test_a_price_only_edit_touches_nothing(self):
        """Same contract, new price — not a revision at all, so the filled
        branch never runs and nothing is sold or moved."""
        self.filled(bid=7.06)
        with mock.patch.object(bridge, "_place_impl",
                               side_effect=AssertionError("sold on a price edit")):
            bridge._revision_check(dict(CALL, limit=1.55))
        self.assertEqual(self.book.be, [])
        self.assertNotIn("EDITED", self.log())

    def test_a_different_message_never_closes_a_filled_position(self):
        self.filled(bid=7.06)
        with mock.patch.object(bridge, "_place_impl",
                               side_effect=AssertionError("sold on another call")):
            bridge._revision_check(dict(PUT, message_id="chat-messages-1334-1000"))
        self.assertNotIn("EDITED", self.log())

    def test_the_no_id_fallback_still_reaches_the_filled_branch(self):
        old = dict(CALL); old.pop("message_id")
        self.book.state = bridge.positions.FILLED
        self.book.fill, self.book.bid = 7.40, 7.06
        self.arm(old, key=bridge.tkey(old))
        with mock.patch.object(bridge, "_place_impl",
                               return_value=(True, "sold")) as sell:
            bridge._revision_check(dict(old, strike=360))
        self.assertEqual(sell.call_count, 1)
        self.assertIn("357.5C \u2192 360C", self.log())


class NoMessageIdFallback(Harness):
    """A legacy build (or voice/vision) sends no message id. Then the only
    evidence of a correction is the same caller, the same ticker, a different
    contract, inside five minutes."""

    def test_same_trader_same_symbol_new_strike_replaces(self):
        old = dict(CALL); old.pop("message_id")
        new = dict(old, strike=360)
        self.arm(old)
        bridge._revision_check(new)
        self.assertEqual(len(self.pb.calls), 1)
        self.assertIn("357.5C → 360C", self.log())

    def test_beyond_five_minutes_is_a_fresh_call(self):
        old = dict(CALL); old.pop("message_id")
        new = dict(old, strike=360)
        self.arm(old, now=time.time() - 400)
        bridge._revision_check(new)
        self.assertEqual(self.pb.calls, [])
        self.assertNotIn("EDITED", self.log())


class NotRevisions(Harness):
    def test_a_different_trader_never_cancels_your_arm(self):
        mine = dict(CALL); mine.pop("message_id")
        theirs = dict(mine, trader="Vero", side="PUTS")
        self.arm(mine)
        bridge._revision_check(theirs)
        self.assertEqual(self.pb.calls, [])
        self.assertNotIn("EDITED", self.log())

    def test_a_different_message_is_a_second_call_not_an_edit(self):
        self.arm(CALL)
        second = dict(CALL, strike=360, message_id="chat-messages-1334-1000")
        bridge._revision_check(second)
        self.assertEqual(self.pb.calls, [])

    def test_identical_repost_is_still_only_deduped(self):
        self.arm(CALL)
        bridge._revision_check(dict(CALL))
        self.assertEqual(self.pb.calls, [])
        self.assertEqual(self.book.cancelled, [])
        self.assertNotIn("EDITED", self.log())

    def test_the_second_leg_of_a_two_strike_call_is_a_sibling(self):
        self.arm(CALL)
        leg2 = dict(CALL, strike=360, sibling=True)
        bridge._revision_check(leg2)
        self.assertEqual(self.pb.calls, [])

    def test_only_entries_are_revised(self):
        self.arm(CALL)
        bridge._revision_check(dict(PUT, action="CLOSE"))
        self.assertEqual(self.pb.calls, [])


class Payload(unittest.TestCase):
    """The preferred path needs the Discord message id in the order payload."""

    def test_background_sends_message_id_and_flags_siblings(self):
        with open(_repo_file("extension", "background.js"),
                  encoding="utf-8") as f:
            src = f.read()
        for want in ("message_id: String(mid || \"\")",
                     "sibling: !!sig.sibling",
                     "sendOrder(sig, qty, c, msg.author, msg.postedAt, msg.mid)"):
            self.assertTrue(want in src,
                            "extension/background.js no longer sends: " + want)

    def test_content_script_reads_the_row_id(self):
        with open(_repo_file("extension", "content.js"),
                  encoding="utf-8") as f:
            src = f.read()
        self.assertTrue("mid: li.id" in src,
                        "extension/content.js stopped reading the row id")


if __name__ == "__main__":
    unittest.main()
