# Health reviews — newest first

# Health — 2026-09-16 — 364fddc1596b91b8a695

The session is active, but all listed Whop tabs are reported as having readers that have not beaten in a while. This suggests stale or missing heartbeat data for those feeds, but the evidence does not confirm whether the tabs are quiet by normal operation or experiencing an outage.

## Findings
- in_session is true, and five tabs are flagged with "reader hasn't beaten in a while": Whop 2K Challenge, Whop Day Trades, Whop Futures, Whop High Risk, and Whop Swing Trades. Verify the source heartbeat or reader status for each tab against the expected update interval before classifying the feeds as unavailable. If the feeds are supposed to update continuously, treat this as a possible stale-data condition requiring source confirmation.

## Limitations
- No timestamp, threshold, or heartbeat interval is provided for what counts as "in a while."
- The evidence shows an active session, but it does not prove whether the tabs are intentionally quiet or actually experiencing an outage.
- No raw reader payloads or source-side confirmations are included, so missing updates cannot be distinguished from zero updates.
- The text lists issue labels only; it does not provide the underlying parser output or transport status.

---

# Health — 2026-09-16 — 087380cfdff6c952081c

The session is marked in_session=true, and the evidence reports multiple alert sources as ON while having no corresponding tab in this browser. This suggests a source-availability or browser-association discrepancy that should be verified, but it does not by itself confirm an outage, error, or intentional configuration.

## Findings
- in_session=true; issues list includes many entries of the form "<alert source> is ON but has no tab in this browser" (for example: AbTrades Alert Bot, Brick Alerts, Demon day-trades, Ducci Alerts, FloridaManFinance, Hog Alerts, Jon Tran Alerts, Maguro Alerts, Mugzone Options, Nando Alerts, OWLS all-alerts, OWLS jon-and-kian, Optionality free-trades, PhiccDuck Alerts, Quantum Alerts, Xephyr Alerts, eli). Verify the source inventory against the browser/tab inventory to determine whether these ON statuses reflect missing tabs, intentionally detached/hidden sources, or stale status data. Do not assume a confirmed parser or system bug without source-side confirmation.

## Limitations
- The evidence only reports browser tab presence/absence for alert sources; it does not show alert delivery, message contents, or broker-confirmed outcomes.
- There is no baseline provided for how many tabs should exist in this browser, so absence cannot be treated as zero or as a confirmed outage.
- The evidence does not distinguish between quiet rooms, hidden tabs, disconnected sessions, and actual source failures.
- No numerical trade results, prices, fills, or premium units are provided, so none can be inferred.

---

# Health — 2026-09-16 — ba422a747837657445e7

The evidence shows the session is active, but 32 alert channels are reported as ON while having no tab in this browser. This is a visibility/mapping issue to verify, not a confirmed outage or parser defect.

## Findings
- in_session=true; issues list contains 32 entries of the form "<channel> is ON but has no tab in this browser" (for example: AbTrades Alert Bot, Aristotle, Mugzone Options, Platinum equity, Quantum Alerts, Xephyr Alerts, shabs). Verify the source of truth for browser/tab inventory and confirm whether these channels are expected to exist in a different window, profile, or device. If they are meant to be present here, reconcile the tab mapping before treating the missing-tab state as an outage.

## Limitations
- The evidence provides only presence/absence flags for tabs; it does not include tab IDs, timestamps, or the underlying alert content.
- Missing tab information is not the same as zero alerts, and the data does not establish whether the tabs are closed, hidden, in another browser context, or whether the inventory is stale.
- No broker-confirmed fills, quotes, or trade outcomes are present, so no performance or execution conclusions can be drawn.

---

# Health — 2026-09-15 — 364fddc1596b91b8a695

The session is active, and multiple Whop tabs (2K Challenge, Day Trades, Futures, High Risk, Swing Trades) are reported as open but without a recent reader heartbeat. This suggests possible reader inactivity or stale updates, but the evidence does not confirm an outage versus an intentionally quiet room.

## Findings
- in_session: true; issues list says each of the five Whop tabs is "open but its reader hasn't beaten in a while." Verify the last heartbeat timestamps and the expected update cadence for each tab, and confirm whether the readers are intentionally idle or have stopped reporting.

## Limitations
- No timestamps or heartbeat intervals are provided, so "hasn't beaten in a while" cannot be quantified.
- The evidence does not distinguish a quiet room from a reader outage.
- There is no broker-confirmed trade data, only tab-status text.
- The issue list does not indicate whether the condition affects all tabs equally or only their readers.
- No parser bug can be confirmed from this evidence alone.

---

# Health — 2026-09-15 — 7c15c343d8f67a266bf6

The session is marked in-session, but many alert sources are reported as ON without a corresponding tab in this browser, and several Whop tabs have readers that "haven't beaten in a while." This looks like a browser/session visibility or stale-reader status issue, not a confirmed outage or confirmed data loss.

## Findings
- Status messages report many sources as ON but with no tab in this browser, including AbTrades Alert Bot, Brick Alerts, Demon day-trades, Ducci Alerts, FloridaManFinance, Hog Alerts, Jon Tran Alerts, Maguro Alerts, Mugzone Options, Nando Alerts, OWLS all-alerts, OWLS jon-and-kian, Optionality free-trades, PhiccDuck Alerts, Quantum Alerts, Xephyr Alerts, and eli. Verify whether these sources are intentionally hidden, moved to another browser/profile, or whether the tab inventory is stale. Do not treat the missing tabs as confirmed outages without source-side confirmation.
- Several Whop tabs are open but their reader "hasn't beaten in a while": Whop 2K Challenge, Whop Day Trades, Whop Futures, Whop High Risk, Whop Swing Trades, and shabs. Check whether these readers are simply quiet or whether their heartbeat/reader process is stalled. Source verification is needed before concluding the rooms are inactive or broken.

## Limitations
- The evidence is a status list only; it does not include timestamps, heartbeats, tab counts, or source-side confirmation.
- An "ON but has no tab" message indicates a visibility or sync mismatch, but it does not prove the source is down.
- A reader that "hasn't beaten in a while" may indicate a quiet room, delayed updates, or a stalled reader; the evidence does not distinguish among these cases.
- No trade prices, fills, or numerical performance data are present, so no broker-confirmed results can be assessed.

---

# Health — 2026-09-15 — c512fd208f809dee240a

The evidence indicates a browser coverage gap: many alert sources are reported as ON but have no tab in this browser. A smaller set of Whop tabs are open but their readers have not beaten in a while, which may indicate stale updates or inactivity, but this is not confirmed from the provided data.

## Findings
- Multiple sources are listed as "ON but has no tab in this browser" (for example: AbTrades Alert Bot, Aristotle, Brando Alerts, Brick Alerts, Demon day-trades, Ducci Alerts, FloridaManFinance, Hog Alerts, Honeydrip daytrades, Jon Tran Alerts, Maguro Alerts, Midas, Mugzone Options, Nando Alerts, OWLS all-alerts, OWLS jon-and-kian, Option Alerts, Optionality free-trades, PhiccDuck Alerts, Platinum day-trades, Platinum ei-alerts, Platinum equity, Platinum nitro, Quantum Alerts, Shoof Alerts, TTT Lotto, Vero 1, Vero 2, Xephyr Alerts, eli, shabs). Verify whether these sources are intentionally absent from the current browser session or whether tabs failed to load; treat this as missing source coverage, not as a confirmed outage.
- Whop 2K Challenge, Whop Day Trades, Whop Futures, Whop High Risk, and Whop Swing Trades are reported as open but their reader "hasn't beaten in a while." Check the reader heartbeat or refresh status for these tabs to determine whether the room is quiet, stale, or experiencing an update failure; do not assume an outage without source confirmation.

## Limitations
- The evidence only describes browser/tab state and reader heartbeat status; it does not confirm whether the underlying alert rooms are live, quiet, or down.
- No timestamps, heartbeat thresholds, or last-seen values are provided, so staleness cannot be quantified.
- The word "ON" indicates source state in the input, but the data do not prove active delivery to this browser session.
- This report does not verify any broker, market, or trading results.

---

# Health — 2026-09-15 — ba422a747837657445e7

The session is reported as active, but the evidence lists many alert sources as ON while also saying they have no tab in this browser. This is a source-verification issue: the report does not confirm whether the tabs are hidden, open in another browser/profile, intentionally closed, or whether the alert inventory is stale.

## Findings
- Evidence shows "in_session": true and an issues list containing repeated entries of the form "<source> is ON but has no tab in this browser". Verify against the authoritative browser/tab inventory and session source before treating these sources as disconnected or unhealthy.

## Limitations
- The evidence does not include timestamps, so freshness cannot be confirmed.
- No independent browser/tab inventory is provided, so the missing-tab condition cannot be distinguished from tabs open in another profile, window, or browser.
- The text only states ON status; it does not confirm alert delivery, broker interaction, or any downstream execution.
- The report does not show whether these are expected omissions or a synchronization delay, so this should not be treated as a confirmed parser or system bug.

---

# Health — 2026-09-14 — a33fba3169239be41603

The session is active, and four Whop tabs are open, but each is reported as not having had a recent beat. This may indicate a quiet room, delayed updates, or an outage; the evidence does not distinguish among them.

## Findings
- "Whop 2K Challenge tab is open but its reader hasn't beaten in a while" Verify the source feed for this tab to determine whether the lack of beats is expected inactivity or a stalled reader/update issue.
- "Whop Day Trades tab is open but its reader hasn't beaten in a while" Check whether the reader is still connected and receiving messages; confirm with source-side activity before treating this as a parser or system fault.
- "Whop Futures tab is open but its reader hasn't beaten in a while" Confirm whether the tab is supposed to be quiet during this window or whether the source has stopped producing updates.
- "Whop High Risk tab is open but its reader hasn't beaten in a while" Review source timestamps and recent message history to verify whether this is normal inactivity or an interruption in data flow.

## Limitations
- The evidence does not include timestamps, beat thresholds, or expected activity levels, so inactivity cannot be classified confidently.
- No source-confirmed message history is provided, so quiet rooms cannot be distinguished from outages with certainty.
- The text is a status summary only; it does not prove a parser bug or a transport failure.

---

# Health — 2026-09-14 — 714af717e5ddb0a70d9d

The evidence shows an active session with many alert sources reported ON but not represented by a browser tab, plus several open tabs whose readers have not beaten recently. This is a source-mapping and freshness-verification issue, not proof of a parser fault or a confirmed outage.

## Findings
- Multiple sources are listed as "ON but has no tab in this browser" (for example: AbTrades Alert Bot, Brando Alerts, Brick Alerts, Demon day-trades, Ducci Alerts, FloridaManFinance, Hog Alerts, Jon Tran Alerts, Maguro Alerts, Midas, Mugzone Options, Nando Alerts, OWLS all-alerts, OWLS jon-and-kian, Option Alerts, Optionality free-trades, PhiccDuck Alerts, Platinum day-trades, Platinum ei-alerts, Platinum equity, Platinum nitro, Quantum Alerts, Shoof Alerts, TTT Lotto, Vero 2, Xephyr Alerts, eli, and shabs). Verify the source-to-tab inventory for each named alert channel: confirm whether the tab is intentionally absent, hidden in another window, disconnected, or should be opened and monitored in this browser.
- Several tabs are present but "the reader hasn't beaten in a while" (Aristotle small tab, Whop 2K Challenge, Whop Day Trades, Whop Futures, and Whop High Risk). Verify whether these readers are merely quiet, paused, or stale. Check the last successful heartbeat/source timestamp before classifying them as outages or inactive rooms.

## Limitations
- The evidence contains status labels only; it does not include timestamps, heartbeat intervals, or message content.
- A quiet room cannot be distinguished from an outage from this evidence alone.
- No broker-confirmed fills, quotes, or alert payloads are provided, so there is no basis for trade outcome or signal-quality conclusions.
- The phrase "hasn't beaten in a while" is relative and unquantified here, so staleness cannot be measured precisely.
- This evidence supports verification tasks only; it does not confirm a parser bug or a system failure.

---

# Health — 2026-09-14 — 07065cb7710876c3e06e

The browser state shows many alert sources marked ON while no corresponding tab is present, and several Whop tabs are open but their reader heartbeat has not updated recently. This is a source-availability/monitoring discrepancy that needs verification; it is not enough evidence to confirm an outage or parser defect.

## Findings
- Multiple entries state that sources are "ON but has no tab in this browser," including examples such as "AbTrades Alert Bot is ON but has no tab in this browser," "Aristotle is ON but has no tab in this browser," "Option Alerts is ON but has no tab in this browser," and "shabs is ON but has no tab in this browser." Verify whether these sources are expected to be present in a different browser profile, a different window, or intentionally closed. If they should be monitored here, confirm the source-to-tab mapping and restore the missing tabs before treating the feed as healthy.
- Several tabs are reported as open but stale: "Whop 2K Challenge tab is open but its reader hasn't beaten in a while," "Whop Day Trades tab is open but its reader hasn't beaten in a while," "Whop Futures tab is open but its reader hasn't beaten in a while," and "Whop High Risk tab is open but its reader hasn't beaten in a while." Verify the heartbeat/reader mechanism for these tabs. Confirm whether the tabs are genuinely idle, blocked, or simply not emitting updates, and check whether the stale status is due to missing data rather than a true outage.

## Limitations
- The evidence is browser-state text only; it does not confirm whether missing tabs are intentional, moved, or actually unavailable.
- No timestamps are provided for the "hasn't beaten in a while" status, so the duration of staleness cannot be assessed.
- There are no broker-confirmed results, quotes, or execution records in the supplied evidence.
- The data does not identify whether the browser session is using multiple profiles or windows, which could explain the missing-tab reports.
- This review cannot confirm a parser bug; it can only flag items that require source verification.

---

# Health — 2026-09-14 — 11f42d85322e0d7bbdd1

The session is reported as in_session=true, but many alert sources are flagged as ON while having no tab in this browser. This indicates missing browser-tab visibility for those channels, not a confirmed service outage.

## Findings
- Issue list repeatedly states "X is ON but has no tab in this browser" for many channels, including AbTrades Alert Bot, Aristotle, Aristotle small, Brando Alerts, Brick Alerts, Demon day-trades, Ducci Alerts, FloridaManFinance, Hog Alerts, Honeydrip daytrades, Jon Tran Alerts, Maguro Alerts, Midas, Mugzone Options, Nando Alerts, OWLS all-alerts, OWLS jon-and-kian, Option Alerts, Optionality free-trades, PhiccDuck Alerts, Platinum day-trades, Platinum ei-alerts, Platinum equity, Platinum nitro, Quantum Alerts, Shoof Alerts, TTT Lotto, Vero 2, Xephyr Alerts, eli, and shabs. Verify whether these alert channels are expected to be open in another browser/profile/workspace, or whether the current browser context is missing tabs that should be present. Do not treat this as a confirmed outage without source verification.

## Limitations
- The evidence does not confirm whether missing tabs mean the channels are closed, unsupported, hidden in another window, or unavailable.
- No source data is provided for alert content, delivery success, or browser state beyond the single issue list.
- This report cannot distinguish a quiet room from an outage for these channels; it only shows absence of tabs in the current browser.
- No numerical health metrics or timestamps are provided to quantify impact or duration.

---

# Health — 2026-09-13 — 9a9f8c621e6e482b9e1b

The supplied health evidence reports an observer queue backlog exceeding 20 messages, but it does not by itself confirm an outage or alert failure. The session is marked as not in session, so the backlog may reflect idle or deferred processing rather than active loss.

## Findings
- {"in_session": false, "issues": ["Observer queue backlog exceeds 20 messages"]} Verify the queue depth over time, whether messages are still being processed, and whether any alerts were delayed or dropped before treating this as an incident.

## Limitations
- Only one health record is provided; there are no timestamps, trend data, or queue capacity details.
- The evidence does not indicate whether the backlog is transient, persistent, or already cleared.
- No direct alert-delivery or broker-confirmed outcome is included, so impact on trading alerts cannot be confirmed.

---

# Health — 2026-09-13 — c66a13a056578bbbe7e3

The evidence describes a Sunday preflight state with `market_open: false`, fresh lanes for `discord` and `whop`, and observer fields showing no queued work and no started worker. This does not confirm an outage; the missing heartbeat/readiness signal should be treated as unverified until the source system defines the expected preflight behavior.

## Findings
- `instruction_context` says "Sunday preflight; missing heartbeat is unverified readiness, not proof of a market-hours outage." The observer shows `worker_started: false` with `preflight: true` and `market_open: false`. Verify from the source system whether a worker is expected to remain stopped during Sunday preflight, and whether a missing heartbeat should be interpreted as normal unavailability or as a readiness failure.
- `observer.last_provider` is an empty string and `observer.last_error` is also empty, while `observer.last_finished` is `0` and `observer.queue_remaining` is `0`. Confirm with the source schema whether empty strings and zeroes mean 'unset/no data' versus explicit 'none' values, so missing provider/error details are not mistaken for confirmed zero activity.
- Both lanes are marked fresh: `{"lane": "discord", "fresh": true, "version": "3.8.21"}` and `{"lane": "whop", "fresh": true, "version": "3.8.21"}`. Verify whether lane freshness alone is sufficient for readiness, or whether additional heartbeat/provider evidence is required before concluding the alert path is healthy.

## Limitations
- The supplied evidence is untrusted and should be source-verified before drawing operational conclusions.
- No broker-confirmed results, prices, exits, or trade outcomes are provided here.
- The record does not include timestamps for the observer fields, so recency beyond the provided `context_hours` cannot be confirmed.
- An empty string or zero may indicate 'missing' rather than 'none'; the schema is not defined in the evidence.

---

