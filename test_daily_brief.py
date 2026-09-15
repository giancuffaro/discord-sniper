#!/usr/bin/env python3
"""daily_brief.py against fixture records — no network, no broker, no repo data.

Every test builds a throwaway repo (master CSVs, a day's reports, a dated
trades.log, an extension lane report, a HANDOFF with a Pending block), points
daily_brief at it, and reads the brief it writes.  The webhook is a stub; a
real one is never contacted.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_brief                                          # noqa: E402
import reports                                              # noqa: E402

DAY = "2026-09-14"

LEDGER_HEAD = ("date,opened,room,caller,symbol,side,strike,expiry,qty,avg_in,"
               "fill,exit_avg,pl,store_pl,state,exit_by,all_out,account,"
               "manual,stop_at_exit,why\n")

LEDGER_ROWS = [
    # ratchet: the stop finished above the fill
    (DAY + ",14:05,Aristotle,KingBeeAri,META,CALLS,700.0,2026-09-18,1,2.61,"
     "2.61,2.68,7.0,,stopped,bot stop,True,live,False,2.74,"
     "the resting stop filled before it could be pulled"),
    # born stop: the stop never moved off its birth level
    (DAY + ",14:22,shabs,Skyy,QQQ,CALLS,713.0,2026-09-14,1,0.24,0.24,0.22,"
     "-2.0,,stopped,bot stop,True,live,False,0.22,"
     "the resting stop filled before it could be pulled"),
    # BE stop: the stop sat exactly at the fill
    (DAY + ",10:23,Whop Day Trades,Trademorewiser (MOD),NVDA,PUTS,210.0,"
     "2026-09-16,1,2.40,2.40,2.38,-2.0,,stopped,,,live,False,2.40,"
     "the resting stop filled before it could be pulled"),
    # pullback stock exit
    (DAY + ",10:42,Mugzone Options,MuggZone,MU,PUTS,850.0,2026-09-16,1,2.10,"
     "2.10,2.05,-5.0,,closed,pullback stop,True,live,False,1.99,"
     "pullback stock exit at 2.05"),
    # closed by hand at the broker
    (DAY + ",10:42,Vero 2,Vero,QQQ,PUTS,705.0,2026-09-14,1,1.41,1.41,1.39,"
     "-2.0,,closed,,,live,False,1.34,"
     "closed at your broker for 1.39 — the bot didn't send this sell"),
    # THE 9/14 TSLA CASE: journal says stopped, the broker prices no exit
    (DAY + ",10:24,Platinum ei-alerts,PT | ei trades,TSLA,CALLS,357.5,"
     "2026-09-18,1,7.40,7.40,,,,stopped,,,live,False,7.00,"
     "the resting stop at Webull sold it first"),
    # G's own hand trade — never the bot's, never graded
    (DAY + ",,?,Gian,SPY,CALLS,761.0,2026-09-14,2,0.72,0.72,,,,closed,,,live,"
     "False,,in the Webull order export, in no store — a hand trade"),
]

OUTCOMES_HEAD = ("entry_time,event_time,room,caller,symbol,contract,entry,"
                 "event,reported_exit,reported_pct,profit_per_contract,"
                 "calculated_pct,implied_exit,trim_size,basis,raw\n")

OUTCOMES_ROWS = [
    # a winner the bot also traded, on a different strike
    "11:21,13:14,shabs,Skyy,QQQ,QQQ 708C @ 0.75,0.75,full exit,3.92,,,422.7,"
    ",,market bid at caller exit,",
    # a loser the bot traded on the same contract
    "10:23,12:17,Whop Day Trades,Trademorewiser (MOD),NVDA,"
    "NVDA 210P 9/16 @ 2.40,2.40,full exit,1.50,,,-37.5,,,"
    "market bid at caller exit,",
    # a winner the bot never took
    "10:13,11:07,OWLS,MuggZone,CRWD,CRWD 245C 9/18 @ 2.35,2.35,partial trim,"
    ",100.0,,,4.70,,caller-stated,",
    # no price anywhere -> unscored, never estimated
    "10:36,11:06,Platinum,@Futures Alerts,MNQ,MNQ @ 28977.50,28977.50,"
    "full exit,,,,,,,caller exit; price unavailable,",
    # the stock-price-for-a-premium row -> excluded from every list
    "11:28,12:47,Midas,Midas (Admin),SPY,SPY 760P 9/14 @ 760.40,,partial trim,"
    ",50.0,,,,,caller posted a stock price, not a premium — entry unavailable,",
    # caller-less relay row -> named by its room
    "10:11,12:49,ELITE OPTIONS: brando-alerts,,QQQ,QQQ 710C 9/16 @ 3.45,3.45,"
    "partial trim,5.50,,,59.4,,0.25,caller-stated,",
]

TRADES_LOG = "\n".join([
    DAY + "T11:07:40-04:00\tREFUSED  OPEN DRAM 58C 9/18 x1  ->  the spread is "
    "26% of the price (20% cap).",
    DAY + "T10:24:16-04:00\tPOSTCHECK FILLED TSLA — PROBLEM: TSLA is held with "
    "NO resting stop — watchdog only",
    DAY + "T10:42:28-04:00\tSTOP-WARN QQQ — Webull wouldn't hold a resting "
    "stop (417 DAY_BUYING_POWER_INSUFFICIENT).",
    DAY + "T11:12:30-04:00\tEXPIRY   MSFT 505C had no date — using "
    + DAY + ": today IS a listed expiration for MSFT, so 0DTE it is",
    DAY + "T10:20:00-04:00\tEDITED  TSLA — PT changed 357.5C -> 357.5P; the "
    "earlier pullback is cancelled",
    DAY + "T10:11:48-04:00\tIMG READ couldn't read the image (HTTP 400: "
    "credit balance too low)",
    DAY + "T09:16:23-04:00\tAI READ  no call — ai: HTTP 400",
    DAY + "T09:18:23-04:00\tAI READ  no call — ai: HTTP 400",
    DAY + "T14:00:00-04:00\tFILLED   QQQ 713C — not a fault, must not count",
    "2026-09-13T11:07:40-04:00\tREFUSED  yesterday's refusal, wrong day",
    "",
])

HANDOFF = """# HANDOFF

## Operating rules
- something that is not pending.

## Pending external setup and decisions
1. In Claude: use project/PROJECT-INSTRUCTIONS.md as the Project
   instructions.
2. NinjaTrader ATM template "SNIPER": stop 100 ticks / target 200.
3. Announcer: paused since 9/2 — the Needs-you tab has the on/off button.

## Watch items (open)
- not pending, must not appear.
"""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class BriefFixture(unittest.TestCase):
    """A whole throwaway repo, rebuilt for every test."""

    full_reports = True

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="brief-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        _write(os.path.join(self.root, "master_ledger.csv"),
               LEDGER_HEAD + "\n".join(LEDGER_ROWS) + "\n")
        _write(os.path.join(self.root, "master_broker.csv"),
               "date,occ,symbol,side,status,filled,price\n"
               "2026-09-11,SPY260911C00758000,SPY,BUY,FILLED,1,1.61\n")
        _write(os.path.join(self.root, "trades.log"), TRADES_LOG)
        _write(os.path.join(self.root, "HANDOFF.md"), HANDOFF)
        _write(os.path.join(self.root, "settings.json"), '{"announcer": {}}')
        _write(os.path.join(self.root, "department-reports",
                            "extension-discord.json"),
               '{"lane": "discord", "issues": ["Chika Alerts is ON but has '
               'no tab in this browser"], "rooms_expected": 40}')
        self._point_at_fixture()
        if self.full_reports:
            # 9/15: one csv for every day and one weekly file per kind, this
            # day under its ===== header — written the way the reports do.
            import csv
            import io as _io
            rd = csv.DictReader(_io.StringIO(
                OUTCOMES_HEAD + "\n".join(OUTCOMES_ROWS) + "\n"))
            reports.write_csv_rows("caller-outcomes", DAY, rd.fieldnames,
                                   list(rd))
            reports.write_day("caller-vs-ratchet", DAY,
                   "# Caller entry versus our ratchet\n\n"
                   "- Our ratchet on the **20 paths with a caller-posted "
                   "entry**: **+976 per one-contract replay**.\n")
            reports.write_day("futures-mirror", DAY,
                   "# FUTURES MIRROR\n\n**bars: unavailable** — "
                   "BentoClientError: 422 dataset_unavailable_range\n\n"
                   "8 SPY/QQQ alert(s) were found for this date and are NOT "
                   "scored.\n")

    def _point_at_fixture(self):
        """Nothing in these tests may read the real repo, and nothing may
        touch the network — the bridge door is stubbed shut by default."""
        import broker_sync
        saved = (daily_brief.HERE, reports.HERE,
                 daily_brief._bridge_buying_power,
                 broker_sync.HERE, broker_sync.BALANCES)
        daily_brief.HERE = self.root
        reports.HERE = self.root
        daily_brief._bridge_buying_power = lambda: None
        broker_sync.HERE = self.root
        broker_sync.BALANCES = os.path.join(self.root, "balance_daily.csv")

        def restore():
            (daily_brief.HERE, reports.HERE,
             daily_brief._bridge_buying_power,
             broker_sync.HERE, broker_sync.BALANCES) = saved
        self.addCleanup(restore)

    def brief(self):
        text, summary = daily_brief.build(DAY)
        return text, summary


class TestDayMoney(BriefFixture):
    """Day P&L and balance — the three lines that read `unavailable` for
    three days because nothing pulled the broker export."""

    def _with_broker(self, day_legs=True, balances=None):
        if day_legs:
            _write(os.path.join(self.root, "master_broker.csv"),
                   "date,occ,symbol,side,status,filled,total_qty,price,"
                   "avg_price,placed_time,filled_time\n"
                   "%s,QQQ260914P00704000,QQQ,BUY,FILLED,1,1,1.13,1.13,"
                   "%s 10:36:56,%s 10:36:57\n" % (DAY, DAY, DAY))
        if balances is not None:
            _write(os.path.join(self.root, "balance_daily.csv"),
                   "date,nlv,day_pl,bp,read_at\n" + balances)
        # the ledger's broker pairing is the audit's job, not the brief's
        daily_brief._broker_day_pl = lambda _day: -321.0
        self.addCleanup(setattr, daily_brief, "_broker_day_pl",
                        daily_brief._broker_day_pl)

    def test_net_and_gross_when_both_exist(self):
        self._with_broker(balances="%s,1279.86,-333.85,1279.86,"
                                   "2026-09-14T16:41:02-04:00\n" % DAY)
        text, summary = self.brief()
        self.assertIn("Webull margin day P&L: -$333.85 net · -$321 gross on "
                      "1 broker legs (the gap is fees)", text)
        self.assertIn("day -$333.85", summary)

    def test_balance_line_carries_nlv_bp_and_when_it_was_read(self):
        self._with_broker(balances="%s,1279.86,-333.85,1279.86,"
                                   "2026-09-14T16:41:02-04:00\n" % DAY)
        text, _ = self.brief()
        line = [l for l in text.splitlines() if l.startswith("- Balance:")][0]
        self.assertIn("NLV $1279.86", line)
        self.assertIn("option BP $1279.86", line)
        self.assertIn("read 2026-09-14T16:41:02", line)

    def test_day_over_day_change(self):
        self._with_broker(
            balances="2026-09-11,1600.00,-12.00,1600.00,x\n"
                     "%s,1279.86,-333.85,1279.86,y\n" % DAY)
        text, _ = self.brief()
        line = [l for l in text.splitlines() if l.startswith("- Balance:")][0]
        self.assertIn("-$320.14 vs 2026-09-11", line)

    def test_gross_only_when_no_balance_was_recorded(self):
        self._with_broker(balances=None)
        text, _ = self.brief()
        self.assertIn("-$321 on 1 broker legs (gross of fees)", text)

    def test_an_older_balance_is_labelled_as_older_never_as_today(self):
        self._with_broker(balances="2026-09-11,1600.00,-12.00,1600.00,x\n")
        text, _ = self.brief()
        line = [l for l in text.splitlines() if l.startswith("- Balance:")][0]
        self.assertIn("last read 2026-09-11", line)
        self.assertIn("-$321 on 1 broker legs (gross of fees)", text)

    def test_the_bridge_answers_when_no_row_exists(self):
        self._with_broker(balances=None)
        daily_brief._bridge_buying_power = lambda: 1279.86
        text, _ = self.brief()
        line = [l for l in text.splitlines() if l.startswith("- Balance:")][0]
        self.assertIn("option BP $1279.86 · live from the bridge", line)

    def test_no_broker_no_bridge_no_file_says_unavailable(self):
        self._with_broker(day_legs=False, balances=None)
        text, summary = self.brief()
        self.assertIn("Webull margin day P&L: broker export missing", text)
        self.assertIn("Balance: unavailable", text)
        self.assertIn("day broker export missing", summary)


class TestSections(BriefFixture):
    def test_every_section_renders_in_order(self):
        text, _ = self.brief()
        headings = ["# SNIPER BRIEF — %s" % DAY, "## Day", "## Bot trades",
                    "## Callers right / wrong", "## What broke",
                    "## Pending (G's action)"]
        found = [text.index(h) for h in headings]
        self.assertEqual(found, sorted(found), text)
        self.assertIn("built from master_ledger.csv", text)

    def test_day_counts_bot_and_hand_apart(self):
        text, summary = self.brief()
        # 6 bot rows; Gian's SPY is his hand trade and is never the bot's.
        self.assertIn("Bot: -$4 · 6 trades, 6 contracts", text)
        self.assertIn("Hand (G): unavailable · 1 trade, 2 contracts", text)
        self.assertIn("broker export missing (last 2026-09-11)", text)
        self.assertIn("Balance: unavailable", text)
        self.assertIn("bot 6 trades", summary)
        self.assertIn("hand 1 trade", summary)

    def test_hand_trade_is_not_in_the_bot_table(self):
        text, _ = self.brief()
        table = text.split("## Bot trades")[1].split("## Callers")[0]
        self.assertNotIn("Gian", table)
        self.assertIn("KingBeeAri", table)


class TestExitReasons(BriefFixture):
    def _row(self, **over):
        row = {"state": "stopped", "exit_by": "", "why": "", "avg_in": "2.00",
               "fill": "2.00", "exit_avg": "1.90", "stop_at_exit": "1.90",
               "pl": "-10.0", "all_out": "True", "store_pl": ""}
        row.update(over)
        return row

    def test_born_stop(self):
        self.assertEqual(daily_brief.exit_words(self._row()), "born stop")

    def test_ratchet(self):
        self.assertEqual(daily_brief.exit_words(
            self._row(exit_by="bot stop", stop_at_exit="2.30",
                      exit_avg="2.30")), "ratchet")

    def test_breakeven_stop(self):
        self.assertEqual(daily_brief.exit_words(
            self._row(stop_at_exit="2.00", exit_avg="2.00")), "BE stop")

    def test_pullback_stock_exit(self):
        self.assertEqual(daily_brief.exit_words(
            self._row(exit_by="pullback stop", why="pullback stock exit at "
                      "2.05")), "pullback stock exit")

    def test_closed_by_hand(self):
        self.assertEqual(daily_brief.exit_words(
            self._row(state="closed", why="closed at your broker for 1.39 — "
                      "the bot didn't send this sell")), "closed by hand")

    def test_close_on_a_room_call(self):
        self.assertEqual(daily_brief.exit_words(
            self._row(state="closed", exit_by="room call")), "close")

    def test_edit_close_and_edit_be(self):
        self.assertEqual(daily_brief.exit_words(
            self._row(state="closed", exit_by="edit-close")), "edit-close")
        self.assertEqual(daily_brief.exit_words(
            self._row(exit_by="edit-BE")), "edit-BE")

    def test_the_table_prints_the_short_words(self):
        text, _ = self.brief()
        table = text.split("## Bot trades")[1].split("## Callers")[0]
        for word in ("ratchet", "born stop", "BE stop",
                     "pullback stock exit", "closed by hand"):
            self.assertIn(word, table)


class TestJournalVersusBroker(BriefFixture):
    def test_the_tsla_row_is_flagged(self):
        text, _ = self.brief()
        line = [l for l in text.splitlines() if "357.5C" in l]
        self.assertTrue(line, text)
        self.assertIn("⚠ journal ≠ broker", line[0])

    def test_a_priced_exit_is_not_flagged(self):
        text, _ = self.brief()
        line = [l for l in text.splitlines() if "700C" in l][0]
        self.assertNotIn("⚠", line)

    def test_a_book_versus_broker_dollar_gap_is_flagged(self):
        self.assertTrue(daily_brief.journal_disagrees(
            {"state": "closed", "exit_avg": "2.00", "pl": "-10.0",
             "store_pl": "40.0", "all_out": "True"}))

    def test_an_open_position_is_never_flagged(self):
        self.assertFalse(daily_brief.journal_disagrees(
            {"state": "filled", "exit_avg": "", "pl": "", "store_pl": "",
             "all_out": ""}))


class TestCallers(BriefFixture):
    def test_right_and_wrong_lists(self):
        text, _ = self.brief()
        block = text.split("## Callers right / wrong")[1].split("## What")[0]
        right = block.split("**Wrong**")[0]
        wrong = block.split("**Wrong**")[1]
        self.assertIn("Skyy QQQ 708C +422.7% (full)", right)
        self.assertIn("MuggZone CRWD 245C 9/18 +100.0%", right)
        self.assertIn("Trademorewiser (MOD) NVDA 210P 9/16 -37.5%", wrong)

    def test_what_the_bot_got_is_shown(self):
        text, _ = self.brief()
        block = text.split("## Callers right / wrong")[1].split("## What")[0]
        self.assertIn("bot took QQQ 713C 9/14: -$2", block)   # other strike
        self.assertIn("bot took it: -$2", block)              # same contract
        self.assertIn("bot: no", block)                       # never traded

    def test_unscored_line_names_the_price_less_exits(self):
        text, _ = self.brief()
        line = [l for l in text.splitlines() if l.startswith("unscored")][0]
        self.assertIn("@Futures Alerts MNQ", line)

    def test_stock_price_rows_are_excluded_everywhere(self):
        text, _ = self.brief()
        block = text.split("## Callers right / wrong")[1].split("## What")[0]
        self.assertNotIn("Midas", block)
        self.assertNotIn("760P", block)

    def test_caller_less_row_is_named_by_its_room(self):
        text, _ = self.brief()
        block = text.split("## Callers right / wrong")[1].split("## What")[0]
        self.assertIn("brando-alerts QQQ 710C 9/16 +59.4%", block)

    def test_ratchet_replay_line(self):
        text, _ = self.brief()
        self.assertIn("ratchet on those 20 caller-priced paths: +976", text)


class TestWhatBroke(BriefFixture):
    def test_counts_and_one_line_each(self):
        text, _ = self.brief()
        block = text.split("## What broke")[1].split("## Pending")[0]
        self.assertIn("- REFUSED 1 — OPEN DRAM", block)
        self.assertIn("- POSTCHECK PROBLEM 1 — FILLED TSLA", block)
        self.assertIn("- STOP-WARN 1 —", block)
        self.assertIn("- EXPIRY 1 — MSFT 505C had no date", block)
        self.assertIn("- EDITED 1 —", block)
        self.assertIn("- IMG READ 1 — couldn't read the image", block)
        self.assertIn("- AI READ 2 — no call", block)
        self.assertIn("- MIRROR — bars unavailable, 8 alert(s) unscored",
                      block)
        self.assertIn("- LANE discord 1 — Chika Alerts", block)

    def test_other_days_and_healthy_lines_are_not_counted(self):
        text, _ = self.brief()
        block = text.split("## What broke")[1].split("## Pending")[0]
        self.assertNotIn("yesterday's refusal", block)
        self.assertNotIn("must not count", block)

    def test_a_clean_day_says_nothing_broke(self):
        _write(os.path.join(self.root, "trades.log"), "")
        _write(os.path.join(self.root, "department-reports",
                            "extension-discord.json"),
               '{"lane": "discord", "issues": []}')
        os.remove(reports.path("futures-mirror", DAY))
        text, summary = self.brief()
        self.assertIn("## What broke\nnothing broke", text)
        self.assertIn("0 things broke", summary)


class TestPending(BriefFixture):
    def test_only_the_pending_block_at_most_six(self):
        text, _ = self.brief()
        block = text.split("## Pending (G's action)")[1].split("built from")[0]
        items = [l for l in block.splitlines() if l.startswith("- ")]
        self.assertEqual(len(items), 3)
        self.assertLessEqual(len(items), 6)
        self.assertIn("NinjaTrader ATM template", block)
        self.assertNotIn("must not appear", block)


class TestMissingInputs(BriefFixture):
    full_reports = False

    def test_missing_reports_say_unavailable_and_do_not_crash(self):
        text, summary = self.brief()
        self.assertIn("CALLER-OUTCOMES.csv unavailable", text)
        self.assertIn("ratchet replay: unavailable", text)
        self.assertIn("## Day", text)
        self.assertIn("## Bot trades", text)
        self.assertTrue(summary)

    def test_missing_ledger_and_handoff_still_build(self):
        os.remove(os.path.join(self.root, "master_ledger.csv"))
        os.remove(os.path.join(self.root, "master_broker.csv"))
        os.remove(os.path.join(self.root, "HANDOFF.md"))
        os.remove(os.path.join(self.root, "trades.log"))
        text, _ = self.brief()
        self.assertIn("Bot: none", text)
        self.assertIn("No bot trades on this date.", text)
        self.assertIn("HANDOFF.md unavailable", text)
        self.assertIn("trades.log unavailable", text)


class TestWriteAndPost(BriefFixture):
    def test_main_writes_the_file_and_is_idempotent(self):
        out = io.StringIO()
        saved, sys.stdout = sys.stdout, out
        try:
            daily_brief.main(DAY)
            first = reports.day_text("brief", DAY)
            daily_brief.main(DAY)
            second = reports.day_text("brief", DAY)
            self.assertEqual(reports.days_in("brief", DAY), [DAY])
        finally:
            sys.stdout = saved
        self.assertEqual(first.split("built from")[0],
                         second.split("built from")[0])
        self.assertNotIn("BRIEF posted", out.getvalue())

    def test_no_webhook_never_fails_the_run(self):
        out = io.StringIO()
        saved, sys.stdout = sys.stdout, out
        try:
            self.assertEqual(daily_brief.main(DAY, do_post=True), 0)
        finally:
            sys.stdout = saved
        self.assertIn("no announcer webhook", out.getvalue())

    def test_post_uploads_the_brief_as_a_file(self):
        _write(os.path.join(self.root, "settings.json"),
               '{"announcer": {"webhook_url": '
               '"https://discord.com/api/webhooks/1/fixture-not-a-real-hook"}}')
        seen = {}

        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        def fake_open(request, timeout=None):
            seen["url"] = request.full_url
            seen["type"] = request.headers.get("Content-type", "")
            seen["body"] = request.data
            return FakeResponse()

        text, summary = self.brief()
        status = daily_brief.post(DAY, text, summary, opener=fake_open)
        self.assertEqual(status, 204)
        self.assertTrue(seen["type"].startswith("multipart/form-data;"))
        body = seen["body"].decode("utf-8")
        self.assertIn('filename="BRIEF-%s.md"' % DAY, body)
        self.assertIn('name="payload_json"', body)
        self.assertIn("SNIPER BRIEF", body)
        self.assertIn("bot 6 trades", body)

    def test_a_refused_webhook_returns_its_status_and_does_not_raise(self):
        _write(os.path.join(self.root, "settings.json"),
               '{"announcer": {"webhook_url": '
               '"https://discord.com/api/webhooks/1/fixture-not-a-real-hook"}}')

        def boom(request, timeout=None):
            error = OSError("refused")
            error.code = 401
            raise error

        self.assertEqual(daily_brief.post(DAY, "x", "y", opener=boom), 401)

    def test_the_summary_fits_a_discord_message(self):
        _, summary = self.brief()
        self.assertLess(len(summary), 2000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
