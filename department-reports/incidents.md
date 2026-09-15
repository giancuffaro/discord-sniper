# Incident reviews — newest first

# Incident — 2026-09-14 — 07065cb7710876c3e06e

During an active session, the evidence reports enabled alert sources without tabs in this browser and stale reader heartbeats for four open Whop tabs. These are potential monitoring gaps requiring verification, not confirmed outages or parser bugs.

## Findings
- Multiple sources are reported ON but without a tab in this browser, including AbTrades Alert Bot, Aristotle, Brando Alerts, OWLS channels, Platinum channels, Xephyr Alerts, eli, and shabs. Verify the complete supplied list against intended source coverage, browser ownership, and reader deployment records. Determine whether each source requires a local tab or is monitored elsewhere before classifying it as a coverage failure.
- Whop 2K Challenge, Whop Day Trades, Whop Futures, and Whop High Risk have open tabs, but their readers reportedly have not sent heartbeats 'in a while.' Verify last-heartbeat timestamps, expected heartbeat intervals, reader logs, and browser lifecycle state. Compare source activity with ingestion records to assess any missed alerts; do not treat room inactivity alone as evidence of an outage.

## Limitations
- The evidence is marked untruncated, but provides no observation timestamp, heartbeat ages, timeout thresholds, or duration of the reported conditions.
- The tab observations apply only to this browser; coverage in other browsers or background services is unknown.
- No source messages, ingestion logs, or delivery records are supplied, so missed alerts and downstream impact cannot be confirmed.
- No parser inputs, broker-confirmed results, or simulation results are supplied.

---

# Incident — 2026-09-14 — 11f42d85322e0d7bbdd1

The in-session evidence reports enabled alert sources without tabs in this browser. This is a potential monitoring-coverage gap requiring verification, not proof of an outage or missed alerts.

## Findings
- The supplied issues consistently report that an alert source is ON but has no tab in this browser, including AbTrades Alert Bot, Aristotle, OWLS all-alerts, and multiple Platinum channels. Verify the issue list against current source settings and the browser tab inventory. Confirm whether each source requires a tab in this browser or is monitored through another browser, process, or ingestion route before classifying a coverage failure.
- The snapshot has in_session set to true but includes no source-message timestamps, ingestion logs, connection health, or delivery acknowledgments. For each flagged source, compare recent original-source activity with ingestion and delivery records. Distinguish a quiet room from an ingestion outage; identify missed alerts only when source messages and corresponding processing gaps are verified.

## Limitations
- Evidence is marked untruncated, but it contains only a session flag and issue descriptions, not underlying operational records.
- The scope is this browser; coverage through other browsers or services is unknown.
- No snapshot timestamp, incident duration, missed-alert count, or trading impact is provided.
- No parser failure or completed remediation is established by this evidence.

---

