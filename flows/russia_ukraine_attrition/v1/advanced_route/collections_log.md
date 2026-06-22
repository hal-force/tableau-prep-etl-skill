# Collections log — Russia/Ukraine losses dry-run

## Pass 1 — primary acquisition (2026-06-22)

User pointed at Kaggle dataset `piterfm/2022-ukraine-russian-war`.
Kaggle page didn't render content via WebFetch (cookie/JS-gated) and
`/data` path 404s. Traced the upstream provenance to GitHub:
**`PetroIvaniuk/2022-Ukraine-Russia-War-Dataset`** — the dataset
author's canonical repo. Kaggle is a mirror. Switched the source to
the GitHub `raw.githubusercontent.com` paths so the flow doesn't
depend on Kaggle's authenticated API.

Three load-bearing files probed under `raw.githubusercontent.com`:

### `russia_losses_personnel.json`
- 1,578 rows. Daily-granular. Range 2022-02-25 → 2026-06-21 (yesterday).
- Cols: `date, day, personnel, personnel*, POW`. `personnel*` carries
  Ukraine MoD's "about" qualifier on most rows — flag the rounding
  uncertainty.
- Latest: 1,391,950 personnel, 0 POW reported on 2026-06-21.

### `russia_losses_equipment.json`
- 1,578 rows. Daily-granular. Range 2022-02-25 → 2026-06-21.
- 13+ classes: tank, APC, IFV-equivalent (rolled into APC),
  field artillery, MRL, AA warfare, aircraft, helicopter, drone,
  naval ship, submarines, cruise missiles, fuel tank, military auto,
  vehicles and fuel tanks, special equipment, ground robotic systems.
- Some classes appeared later in the war (`ground robotic systems`,
  `submarines`, `cruise missiles`, `special equipment`) — early rows
  have missing keys, must coerce-fill nulls to 0 downstream.

### `russia_losses_equipment_oryx.json`
- 338 rows. Per-model, NOT a time series. One row per Russian
  equipment model with a `losses_total` count Oryx has visually
  confirmed.
- Cols: `equipment_oryx, model, manufacturer, losses_total, equipment_ua`.
- `equipment_ua` is the bridge column — maps Oryx's model-level
  taxonomy onto the UA MoD's class-level buckets.

## Indicator status after Pass 1

| Id | Status | Notes |
|---|---|---|
| F1.1 | **GREEN** | UA MoD equipment series satisfies cumulative-by-class. |
| F1.2 | **GREEN** | Derived from F1.1; rolling window in Tableau. |
| F1.3 | **GREEN** | Derived from F1.1. |
| F2.1 | **GREEN** | Personnel JSON satisfies cumulative personnel. |
| F2.2 | **GREEN** | Derived from F2.1. |
| F2.3 | **GREEN** | Derived from F2.1. |
| F3.1 | **GREEN** | Derived from F1.1; mix is a row-share computation. |
| F3.2 | **GREEN** | Derived from F1.1; top-3 by recent share. |
| F4.1 | **RED — Pass 1** | Dataset has no territory polygons / sq-km. |
| F4.2 | **RED — Pass 1** | Derived from F4.1; can't be satisfied. |
| F5.1 | **AMBER** | Oryx JSON has no per-row listing-date — only `losses_total`. The per-loss-event detail (which Oryx exposes on its web pages) isn't in this normalized mirror. Lag is uncomputable from this dataset. |
| F5.2 | **GREEN** | The Oryx file IS by definition photo-confirmed (Oryx's curation contract). Add a flag column on join. |

## Pass 2 — gap-filling for F4 (territory) and F5.1 (Oryx lag)

Tried two alternatives for F4:

1. **ISW interactive map JSON** — page is interactive Tableau-style
   tooltips with no documented JSON endpoint; data is behind their
   ArcGIS service. Possible to scrape but lives in a different
   geospatial schema and would dominate the build.
2. **DeepStateMap.live** — Ukrainian OSINT polygons but the same
   "behind an interactive layer" problem.

For F5.1 the Oryx mirror in this repo is a *normalized rollup*, not
the row-per-loss feed. To get listing dates we'd have to scrape Oryx
directly — and Oryx is HTML-rendered + anti-scraping. Out of scope
for a "what does the trajectory look like" dashboard.

## Pass 3 — final relaxation

Re-shape F4 / F5.1 instead of acquiring new data:

- **F4 (territory)** — drop from this deliverable. Declare it as a
  gap. A territory-aware companion dashboard is the right home; this
  dashboard is *attrition* not *terrain*.
- **F5.1 (Oryx lag)** — drop. F5.2 (the confirmation-method flag)
  still carries enough of the provenance story for the reader.

## Final status

| Indicator | Status |
|---|---|
| F1.1, F1.2, F1.3 | GREEN |
| F2.1, F2.2, F2.3 | GREEN |
| F3.1, F3.2 | GREEN |
| F4.1, F4.2 | **RED — declared as gap** |
| F5.1 | **RED — declared as gap** |
| F5.2 | GREEN |

10 / 13 indicators satisfied. 3 declared as gaps in the published DS
description below.

## Gap declaration (verbatim — for DS description)

```
This data source addresses the question "How have Russian military
losses in Ukraine evolved over the past 24 months, and what does the
trajectory suggest about the tempo of the conflict?" via 10 of 13
planned indicators.

Sources:
- Daily personnel + equipment loss series: Ukraine Ministry of
  Defence self-reports, normalized by PetroIvaniuk/2022-Ukraine-
  Russia-War-Dataset on GitHub. UA MoD figures run higher than
  independent OSINT estimates; "about" qualifier preserved on
  personnel rows.
- Per-model OSINT confirmation: Oryx visual-confirmation register
  (mirrored to russia_losses_equipment_oryx.json), photo-backed
  per Oryx curation policy.

One-sided framing — Russian losses only. Ukrainian losses are out
of scope for this dataset. Any "war progression" reading must be
weighed against that.

Gaps:
- F4 territorial change (net sq-km, cumulative since invasion):
  Three passes attempted. Pass 1 — dataset carries no territory.
  Pass 2 — ISW interactive map data lives behind their ArcGIS
  service and would dominate the build. DeepStateMap shows the
  same access pattern. Pass 3 — declared out of scope; a
  territory-aware dashboard is its own deliverable. Effect on the
  answer: "trajectory" here is attrition-only. Readers should not
  infer territorial change from these numbers.
- F5.1 OSINT confirmation lag (median days from event to listing):
  The Oryx mirror in this dataset is a normalized rollup, not a
  per-loss-event feed with listing dates. Scraping Oryx directly
  is out of scope. Effect: we cannot quantify how much the recent
  30/90-day windows are under-counted by lag — readers should
  treat recent-window figures as floors, not ceilings.

To fill these gaps in a follow-on build:
- Publish an authoritative daily territory series (sq-km
  Russian-controlled in Ukraine) as an internal data source on
  this site.
- Stand up a row-per-loss Oryx feed (e.g. via Naalsio26 or Tom
  Cooper's CSV mirrors) with both event_date and listing_date so
  F5.1 becomes computable.
```

## Hand-off to simplified route

Spec.json written next, pointing at the three GitHub raw URLs as
REST/JSON sources, with per-source `extra.json_root: "[]"` and the
trend-analysis transformation across the equipment + personnel
series. Two outputs (Detail + Summary) mirroring the Embassy Threat
Monitor pattern.
