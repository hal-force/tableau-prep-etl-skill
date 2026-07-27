# Collections log — Nursing-home quality-collapse

## Pass 1 — internal scan (2026-07-24)

All three feeder DSes exist on-site:

- CMS Deficiencies (score 94) — F1/F2/F3
- CMS Nursing Home Providers (82) — provider identity
- HealthData Hospital Capacity (61) — F4 spillover

This flow's job: publish a NEW composite risk score keyed on ccn,
pulling the same upstream endpoints as the feeder DSes so the flow
is standalone (not dependent on cross-DS joins at build time).

## Pass 1 — external acquisition

Called the same three data.cms.gov / healthdata.gov endpoints.

- CMS Deficiencies (r5ix-sfxw): 12mo window, expect ≥5000 rows.
- CMS Nursing Home Providers (4pq5-n9py): ~15k providers.
- HealthData Hospital Capacity: state-level series.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | Deficiency category populated |
| F1.2 | GREEN | Widespread citation count |
| F2.1 | GREEN | Distinct survey_date count |
| F2.2 | GREEN | Max citations per survey |
| F3.1 | GREEN | days_to_correction column |
| F3.2 | GREEN | Open-past-60d share |
| F4.1 | GREEN | State occupancy |
| F4.2 | GREEN | State z-score |
| F5.1 | **RED** | PBJ staffing not available on-site or via approved external hosts |

8 GREEN + 1 RED.

## Pass 2 — F5 gap-fill attempt

Tried:

1. CMS PBJ direct data.cms.gov endpoint. Endpoint exists but the
   data is per-facility quarterly staffing-hours which requires a
   different join key (Facility_ID vs ccn maps but with lag).
   Payload volume ~2GB — dominates the build budget for this demo.
2. Nursing Home Compare bulk downloads. Same problem — bulk file,
   different join key, would require its own dedicated flow.

Decision: DECLARE AS GAP. Substitute F1 F-tag clustering (already
GREEN) as the staffing-signal proxy per SAT step-3 substitution
rules.

## Pass 3 — n/a

## Final status

8 GREEN + 1 RED declared. Composite risk score computes on the 8
GREEN indicators with F1-clustering acting as the staffing proxy.

## Gap declaration (verbatim for DS description)

```
This data source addresses the question "Which CMS-certified nursing
homes show the highest quality-collapse risk?" via 8 GREEN indicators
+ 1 RED (declared gap).

Scope:
- CMS-certified nursing home providers (~15,000 nationally).
- 12-month rolling deficiency window; state-level hospital capacity
  spillover.
- Composite score is a LEADING INDICATOR, not a regulatory
  determination. Actual escalation uses CMS Special Focus Facility
  (SFF) status; we surface signals correlated with SFF-adjacent
  trajectories.

RED indicator (declared gap):
- F5.1 Staffing signal from CMS Payroll-Based Journal (PBJ). PBJ
  data lives on a separate CMS endpoint with a different join key
  (Facility_ID vs ccn, with mapping lag). Payload volume (~2GB
  quarterly) would dominate this build. Effect on the answer:
  facilities under-staffed but with an otherwise clean recent
  deficiency history will not be flagged by the current score.
  Substituted proxy: F1 F-tag clustering (widespread-severity
  citation density) — this captures the DOWNSTREAM manifestation
  of understaffing but with a lag of one survey cycle (~12 months).

To fill this gap: stand up a dedicated PBJ ingest flow with
Facility_ID → ccn mapping and a per-provider quarterly staffing
hours-per-resident-day trend, then join into the composite score
in a v2.
```
