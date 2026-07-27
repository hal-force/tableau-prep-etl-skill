# SAT brief — Wildfire staging-resource gap

## Step 1.1 — Question decomposition

Original:
> "Where are wildfire incidents outrunning the staging and personnel
> capacity that's been assigned to them?"

Refined:
> **Which active US wildfire incidents show a large gap between
> incident scale (size, growth rate, complexity) and assigned
> firefighting resources (total personnel, cost-to-date), on a
> per-incident basis, and where does the surrounding grid /
> jurisdictional infrastructure add cascading risk?**

## Step 1.2 — Key Assumptions Check

- ⚠ **"Staging gap" is a heuristic proxy, not an operational
  determination.** Real staging is managed by IMTs (Incident
  Management Teams) via ICS resource orders. We infer gap from
  reported TotalIncidentPersonnel and EstimatedCostToDate relative
  to size/growth.
- ⚠ **NIFC/WFIGS TotalIncidentPersonnel is self-reported and
  updated on the IMT's cadence** — can lag actual staffing by a
  shift.
- **US Grid Network is a state-level power infrastructure DS**,
  used as a spillover-risk indicator (heavily-loaded transmission
  states with active fires = grid impact risk), not a facility-
  level proximity check.
- **"Active" = ActiveFireCandidate=1** on the WFIGS FeatureServer.
- Prescribed burns are FILTERED OUT (IncidentTypeCategory != RX)
  since staging gap has a different meaning for planned burns.

## Step 1.3 — Factors

- **F1. Incident scale.** Current size (acres), growth rate,
  discovery age.
- **F2. Assigned resources.** Personnel count, cost to date,
  IncidentManagementOrganization complexity level.
- **F3. Staging gap.** Personnel-per-acre ratio, cost-per-acre
  ratio, benchmarked against complexity level.
- **F4. Grid spillover.** Presence of major transmission
  infrastructure in the fire's state (from us_grid_network DS).
- **F5. Jurisdictional signal.** Multi-agency incidents with
  jurisdictional complexity.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | IncidentSize (acres) | current |
| F1.2 | F1 | days_since_discovery | current |
| F1.3 | F1 | daily_growth_rate (existing eoc_fire_metrics field) | current |
| F2.1 | F2 | TotalIncidentPersonnel | current |
| F2.2 | F2 | EstimatedCostToDate | current |
| F2.3 | F2 | IncidentComplexityLevel (Type 1-5) | current |
| F3.1 | F3 | personnel_per_100acres | current |
| F3.2 | F3 | cost_per_acre | current |
| F3.3 | F3 | resource_gap_flag (complexity-adjusted threshold) | current |
| F4.1 | F4 | grid_state_load (join to us_grid_network by POOState) | current |
| F5.1 | F5 | POOJurisdictionalAgency + POOProtectingAgency mismatch flag | current |

## Acceptance criteria

- WFIGS: ≥50 active incidents in the active feed; personnel + cost
  populated on ≥70% of rows.
- Grid: state-level load / capacity metrics current within 90 days.

## Out-of-scope

- Facility-level asset proximity (nearest station, nearest hydrant).
- Wildfire smoke-plume dispersion modeling.
- Multi-fire complex resource sharing (CpxName join deferred).
- Prescribed burns and controlled fires.

## What "good" looks like

Two DSes on Cloud:

- **Wildfire Staging Gap Detail** — one row per active incident,
  with F1/F2/F3/F5 indicators, resource_gap_flag boolean, tooltip,
  geometry.
- **Wildfire Staging Gap Stats** — long-form per-(state, complexity)
  rollup showing where gaps cluster.
