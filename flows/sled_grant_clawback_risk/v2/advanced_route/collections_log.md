# Collections log — SLED grant clawback risk

## Pass 1 — internal scan (2026-07-24)

| DS | Score | Verdict |
|---|---:|---|
| USASpending SLED Grants (FY25-26 window) | 88 | Reference DS for F4.1 renewal |
| Fed Register Actions (18mo) | 74 | Partial coverage for F3 signal window |
| FedReg DoD | 32 | Not applicable |

Verdict: two internal DSes are useful. Need a new FY24 pull for the
FY24 grant rows themselves (existing DS starts 2024-10-01 = FY25).

## Pass 1 — external acquisition

New USASpending pull scoped to FY24:
- `time_period=[{start_date: 2023-10-01, end_date: 2024-09-30}]`
- `award_type_codes=[02, 03, 04, 05]`
- Same recipient_type_names as the existing SLED Grants DS.

Result: ≥1000 rows expected, Total Outlays populated on ≥80%.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | New FY24 pull + prime_award_recipient_id present |
| F2.1 | GREEN | Awarded / Outlays fields present |
| F2.2 | GREEN | Derived |
| F3.1 | AMBER | Fed Register signal window covers 18mo, not the ideal 24mo |
| F3.2 | AMBER | Downstream of F3.1 |
| F4.1 | GREEN | Cross-DS join to existing FY25 SLED DS |
| F5.1 | AMBER | Downstream of F3.1 |

5 GREEN + 3 AMBER. No RED.

## Pass 2 — n/a

Signal-window gap is a demo scope decision; pass 2 not run.

## Pass 3 — n/a

## Final status

Same. AMBER folded into the description.

## Gap declaration (verbatim — for DS description)

```
This data source addresses the question "Which FY24 SLED grants show
the highest clawback risk from recipient churn, outlay stagnation,
and program-status signals?" via 5 GREEN + 3 AMBER of 7 planned
indicators.

Scope:
- Federal FY24 (2023-10-01 through 2024-09-30).
- Award types 02 / 03 / 04 / 05 (Block, Formula, Project,
  Cooperative Agreement).
- SLED recipients only: state, county, city/township, special
  district, independent school district, state-controlled higher
  ed.
- Clawback risk is a SIGNAL score, not a formal determination.
  Actual clawbacks require GAO / IG findings not carried by
  USASpending.

AMBER notes:
- Federal Register signal window (F3.1 / F3.2 / F5.1): the referenced
  Fed Register Actions DS covers 18 months (2025-01 onward), not
  the ideal 24 months. FY24-Q1 terminations are not counted. Effect:
  the sub-agency signal density may under-flag agencies whose
  program terminations concentrated in that early window. A future
  build should backfill Fed Register to 2024-07-24.
```

## Hand-off

Spec.json written.
