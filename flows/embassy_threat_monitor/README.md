# embassy_threat_monitor

**Request:** Monitor public events near US diplomatic posts. Pull GDELT
events on a 3-hour cadence, spatial-join to a curated US embassy +
consulate roster (within 50 miles), score each post-event pair on
severity / proximity / recency / US-actor flag, then aggregate to a
per-post weighted threat score with a 5-band classification
(CRITICAL / HIGH / ELEVATED / GUARDED / LOW) suitable for a State
Department physical-security operations dashboard.

## Sources

- **REST API** (`csv_index_then_zip`): http://data.gdeltproject.org/events/index.html
  GDELT 1.0 events feed. Each row is a source-URL mention of an
  event — note that this means row counts inflate vs real-world
  event counts. The downstream banding thresholds are calibrated
  against this URL-inflated volume; see
  `feedback_gdelt_volume_calibration.md`.

## Transformations

- **embassy_threat_join** — Spatial-joins GDELT events to a curated
  60-post US diplomatic roster (capital embassies + named major
  consulates) using a pure-pandas haversine. Filters to threat-class
  CAMEO root codes (13 Threaten, 14 Protest, 17 Coerce, 18 Assault,
  19 Fight, 20 Mass-violence). Emits one row per (post, event)
  within the configured 50-mile radius and lookback window. Adds
  `severity_score`, `proximity_score`, `recency_score`,
  `us_actor_flag`, and a `composite_score = severity*2 + proximity
  + recency + us_actor`.
- **embassy_risk_summary** — Per-post weighted aggregation. Sibling
  of `embassy_threat_join`: consumes the **same upstream tail** as
  the join (shared via `output.source.transformation` routing,
  documented in `tabpy_setup.md`). Applies linear recency-decay
  weighting (1.0 today → 0.0 at window edge), groups by post,
  emits one row per post in the roster — including all-clear posts
  with zero events, so the operations dashboard always shows full
  coverage rather than disappearing posts. CRITICAL escalator:
  any mass-violence event within 30 miles within 72 hours forces
  CRITICAL regardless of weighted score.

## Outputs

Two published data sources, both routed via
`output.source.transformation` to their respective sibling script
node:

- **Embassy Threat Events** — per-event-pair detail (22 cols).
  Drives the per-incident drill-down on the dashboard.
- **Embassy Risk Summary** — per-post roll-up (17 cols). Drives the
  map + risk-band heat layers on the dashboard.

## Refresh cadence

`every_3_hours` (added to `spec_validation.REFRESH_CADENCES` for
this flow). Cloud backgrounder cannot run script nodes; the flow
runs locally on a host with TabPy and uploads the .hyper as a DS
via TSC. See `feedback_cloud_vs_server_execution.md`.

## Risk-band rules

Calibrated against the URL-inflated GDELT row volume across the
60-post roster:

| Band | Trigger |
|---|---|
| CRITICAL | weighted_threat_score ≥ 500 OR mass-violence event within 30mi & 72h |
| HIGH | weighted_threat_score 150-499 |
| ELEVATED | weighted_threat_score 30-149 |
| GUARDED | weighted_threat_score 1-29 |
| LOW | weighted_threat_score = 0 (default; no events in window) |

## Production substitution: replace the demo roster

The 60-post roster is **baked into the templates** as a demo seed.
Production deployments should swap it for an authoritative roster:

- **Option A** — replace `_EMBASSY_ROSTER` in both
  `embassy_threat_join.py.j2` and `embassy_risk_summary.py.j2` with
  the customer's real roster (must keep the same shape:
  `{post_name, post_country, post_classification, post_lat, post_lon}`).
- **Option B** — switch to a multi-source flow with the roster as
  a separate `internal_published_ds` source joined into the events
  feed via Maestro `SuperJoin`. Cleaner for ongoing roster updates;
  requires the customer to maintain a published DS for the roster.

## Sample output

Not committed (this flow is included as a working seed; rerun
locally to produce your own .hyper outputs against the live GDELT
feed).

## Reproduce

```bash
source ~/.tableau-prep-etl/load_env.sh

# Local run only
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/embassy_threat_monitor.json \
    --flow-name embassy_threat_monitor

# Build + run + publish + write descriptions to Cloud
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/embassy_threat_monitor.json \
    --flow-name embassy_threat_monitor \
    --publish --auto-create-project
```

After a successful publish, archive the run:

```bash
python3 -m skill.scripts.archive_flow embassy_threat_monitor
```

## Active deployment

- **Site:** prod-useast-a.online.tableau.com / usfederaldemos
- **Project:** Prep Agent (parent) → Embassy Threat Monitor (child)
- Two DSes: "Embassy Threat Events" + "Embassy Risk Summary"
- Refresh: every 3 hours

## Related references

- `skill/reference/operator_quickstart.md` — cold-start how-to.
- `skill/reference/tabpy_setup.md` — `output.source.transformation`,
  `pyrepr` filter, Prep preamble traps.
- `skill/reference/server_publishing.md` — Cloud LUID injection,
  Catalog indexing lag.
- `skill/reference/metadata_api.md` — orphan pruning + Hyper schema
  discovery (load-bearing for this flow's metadata write).
