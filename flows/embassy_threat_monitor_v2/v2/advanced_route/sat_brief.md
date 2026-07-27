# SAT brief — US diplomatic post physical-security exposure

## Step 1.1 — Question decomposition

User's original framing:
> "How exposed are our embassies to political violence?"

Refined, decision-driving form:

> **Which US diplomatic posts are at elevated physical-security risk
> over the next 30 days, ranked by composite threat score derived
> from recent (90-day) political-violence event proximity, severity,
> US-actor involvement, and trend direction?**

A dashboard that answers this needs:

- A **per-post ranking** (60-post curated US diplomatic roster), not
  a country-level rollup.
- **Recency-weighted** severity — a mob-siege 3 days ago outweighs a
  protest 60 days ago.
- **Forward-looking framing** — the 90-day event window is the
  *evidence*; the ask is about the *next* 30 days.
- **Named events** on the rollup so an operations reader sees *why*
  a post is banded where it is without drilling.

## Step 1.2 — Key Assumptions Check

Assumptions the question bakes in; ⚠ marks ones that would change
the answer shape if wrong:

- ⚠ **Physical security only.** Cyber, financial, insider-threat are
  out. If the user wants "exposure" in the broad sense, this is a
  different dashboard.
- ⚠ **Post-level granularity.** Not country-level, not region-level.
  A "high-risk country with a low-exposure post" (e.g. inland
  compound vs coastal port) is a distinct signal.
- **Recency-weighted, not lifetime.** Cumulative event counts over
  the last 4 years would drown out the acute-window signal.
- **CAMEO subset defines "political violence".** Root codes 13, 14,
  17, 18, 19, 20 (protest → mass violence → unconventional mass
  violence). Not economic sanctions, not diplomatic censure.
- **50-mile radius from post is meaningful.** Trades off between
  capturing area-of-operation events and swamping urban posts with
  every downtown protest.
- **US-actor involvement matters.** Events where Actor1 or Actor2 is
  coded USA/US Gov are higher-weight than same-region events without
  US involvement.
- **GDELT 1.0 volume calibration.** GDELT emits one row per source
  URL, not per event — thresholds are set against inflated row
  volume per [[feedback_gdelt_volume_calibration]].

## Step 1.3 — Factors driving the answer

Real-world drivers, not yet datasets:

- **F1. Proximity of recent unrest events.** Distance from post to
  event, count of events inside radius.
- **F2. Severity of recent unrest.** Event class (protest vs mass
  violence), Goldstein-scale, casualty proxy (num-mentions weighted).
- **F3. US-actor involvement.** Direct-target events are step-changes
  in exposure, not incremental additions.
- **F4. Trend / escalation.** A single incident in a quiet corridor
  is different from a 4-week accelerating pattern.
- **F5. Reporting confidence.** GDELT 1.0 catches every source URL
  reporting an event, so recency lag is minimal, but the
  URL-inflation means raw counts overstate — normalize by
  distinct-event heuristic.

## Step 1.4 — Indicators (operationalized)

Each indicator is (a) expressible against a column, (b) recency-aware,
(c) falsifiable.

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Count of CAMEO 13/14/17/18/19/20 events within 50mi of post | 90d |
| F1.2 | F1 | Min haversine distance of any qualifying event | 30d |
| F2.1 | F2 | Max CAMEO root code observed within radius | 90d |
| F2.2 | F2 | Weighted incident score: severity × recency-decay × mentions-weight | 90d |
| F2.3 | F2 | Named top-severity event summary + source URL | 30d |
| F3.1 | F3 | Share of qualifying events with Actor1_CountryCode or Actor2_CountryCode = "USA" | 90d |
| F4.1 | F4 | Week-over-week change in F2.2 (7d vs prior 7d) | 7d rolling |
| F4.2 | F4 | 5-band risk classification: CRITICAL / HIGH / ELEVATED / GUARDED / LOW | 90d cumulative → banded |
| F5.1 | F5 | Distinct source-URL count per event (deduplication check) | 90d |

## Step 1.5 — Acceptance criteria

For each indicator to be answerable the data must provide:

- **Roster** (F1.x, F2.x, F3.x, F4.x): ≥60 US posts with
  post_name + city + country + lat + lon.
- **Events** (F1.x, F2.x, F3.x, F5.x): CAMEO EventRootCode +
  EventCode, ActionGeo_Lat / _Long, SQLDATE, Actor1CountryCode,
  Actor2CountryCode, GoldsteinScale, NumMentions, SOURCEURL,
  Actor1Name, Actor2Name, ActionGeo_FullName.
- **Freshness** for the forward-looking framing: events feed no
  older than 3-6 hours (matches every_3_hours refresh cadence).

## Out-of-scope (deliberate)

- **Cyber threat exposure** — separate dashboard.
- **Country-level rollup** — the ask is post-level.
- **Insider / physical-security procedural risk** (badge audits, HRA
  reviews) — not sourceable from open feeds.
- **Non-US posts / allied missions** — 60-post curated US roster only.

## What "good" looks like at the end

Two published data sources on Tableau Cloud (already live as
`Embassy Threat Events v2` + `Embassy Risk Summary v2`):

- **Events DS** — one row per (post, GDELT event) within 50mi;
  carries per-event columns including composed event_summary
  (Actor1Name + CAMEO verb + Actor2Name @ ActionGeo_FullName on
  YYYY-MM-DD) and source URL.
- **Summary DS** — one row per post; 5-band risk classification,
  weighted threat score, per-class event counts, top_event_summary,
  top_event_source_url.

DS description carries the CAMEO scope, roster limit, GDELT volume
caveat, and any gaps declared during collection.
