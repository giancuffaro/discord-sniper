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
    def __init__(self, state=None, fill=None):
        self.state = state
        self.fill = fill
        self.cancelled = []
        self.sold = []

    def state_of(self, key):
        return self.state

    def info(self, key):
        return {"fill": self.fill, "state": self.state} if self.state else None

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
        self.arm(CALL, key="pt|TSLA|357.5|CALLS|2026-09-16")
        bridge._revision_check(PUT)
        self.assertEqual(len(self.book.cancelled), 1)
        self.assertIn("resting bid pulled", self.log())


class AlreadyFilled(Harness):
    def test_a_filled_position_is_never_sold(self):
        self.book.state = bridge.positions.FILLED
        self.book.fill = 7.40
        self.arm(CALL, key="pt|TSLA|357.5|CALLS|2026-09-16")
        bridge._revision_check(PUT)
        self.assertEqual(self.book.sold, [])
        self.assertEqual(self.book.cancelled, [])
        self.assertEqual(self.pb.calls, [])
        self.assertIn("already filled at 7.40", self.log())
        self.assertIn("position stays, ratchet owns it", self.log())


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
