# SAT brief — Nursing-home quality-collapse early warning

## Step 1.1 — Question decomposition

Original:
> "Which CMS-certified nursing homes are showing early signs of
> quality collapse based on deficiency clustering, staffing signals,
> and hospital-capacity spillover?"

Refined:
> **Which CMS-certified nursing home providers show the highest
> composite quality-collapse-risk score, computed from (a) severity
> and cluster-density of recent health-inspection deficiencies,
> (b) time-to-correction lag on prior citations, and (c) local
> hospital-capacity spillover (bed occupancy trend within the same
> HRR / state), evaluated as of the most recent survey window?**

## Step 1.2 — Key Assumptions Check

- ⚠ **"Quality collapse" is a leading-indicator score, not a
  regulatory determination.** CMS uses the SFF (Special Focus
  Facility) designation for actual escalation; we surface signals
  correlated with SFF-adjacent trajectories.
- ⚠ **Deficiency severity is category-driven** (immediate jeopardy
  vs pattern vs isolated). Raw citation counts without severity are
  misleading.
- **Staffing data (PBJ) is out of scope for this build.** CMS's
  Payroll-Based Journal data isn't on our site; declared as gap.
  Substitute proxy: deficiency-category F-tag clustering serves as
  the staffing-signal stand-in per SAT redirect.
- **Hospital-capacity spillover is a state-level proxy** (per-state
  bed occupancy from HealthData), not a HRR / facility-level
  proximity join.
- **"Recent" = surveys in the last 12 months.** CMS surveys occur
  every 9-15 months; 12mo captures roughly one cycle.

## Step 1.3 — Factors

- **F1. Deficiency severity.** Category (A-L) and F-tag class of
  each citation.
- **F2. Deficiency clustering.** Multiple citations in a single
  survey vs distributed across multiple surveys.
- **F3. Correction lag.** Days between survey_date and
  correction_date; long lags indicate compliance drag.
- **F4. Local hospital spillover.** State-level inpatient bed
  occupancy trend — high hospital load correlates with LTC
  discharge pressure, which stresses receiving facilities.
- **F5. Staffing signal.** OUT OF SCOPE — declared as gap; F1 F-tag
  proxy substitutes.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Max deficiency category (A-L, encoded 1-12) per provider | 12mo |
| F1.2 | F1 | Count of category >= "F" (widespread) citations | 12mo |
| F2.1 | F2 | Distinct survey_date count per provider | 12mo |
| F2.2 | F2 | Max citations in a single survey (survey_date bucket) | 12mo |
| F3.1 | F3 | Median days_to_correction per provider | 12mo |
| F3.2 | F3 | Share of citations with correction_date null past 60d | 12mo |
| F4.1 | F4 | Rolling 30d state hospital inpatient occupancy % | 30d |
| F4.2 | F4 | State-level occupancy z-score vs prior year | 30d |
| F5.1 | F5 | (RED — declared as gap) | — |

## Acceptance criteria

- CMS Deficiencies: ≥5000 rows in the last 12mo, category field
  populated ≥98%.
- CMS Nursing Home Providers: ≥15000 provider rows with state.
- HealthData Hospital Capacity: state-level occupancy series
  refreshed within the last 30 days.

## Out-of-scope

- Facility-level HRR proximity join to hospitals (state-level proxy
  is our scope).
- CMS PBJ staffing data — not on-site; declared as gap.
- Substantiated complaints (separate CMS dataset).
- Life Safety Code deficiencies (F-tag scope, not K-tag).

## What "good" looks like

Two DSes on Cloud:

- **Nursing Home Collapse Risk Detail** — one row per provider,
  with per-indicator columns + composite collapse_risk_score +
  provider identity + state.
- **Nursing Home Deficiency Cluster Detail** — one row per
  (provider, survey_date bucket), with category max, count, tag
  spread; drill-through source.
