# Collections log — CENTCOM supplier concentration risk

## Pass 1 — internal scan (2026-07-24)

Phase 0 metadata-API scan:

| DS | Project | Score | Verdict |
|---|---|---:|---|
| DoD Award Detail | 11 - DoD Contract Awards | 72.0 | PARTIAL — FY2026 window, no CENTCOM country filter |
| DoD Award Stats | 11 - DoD Contract Awards | 62.0 | Rollup on the same base |
| USASpending Contracts | Prep Agent | 48.0 | Broader USASpending feed |

None match the *specific* rolling-12mo + CENTCOM-adjacent shape.
DoD Award Detail is a reasonable base but its API call scope is
different. Correct pass: build a new external pull with the
CENTCOM country filter.

## Pass 1 — external acquisition (2026-07-24)

Called `api.usaspending.gov/api/v2/search/spending_by_award/` with
POST body:

- `agencies=[{type:awarding, tier:toptier, name:'Department of Defense'}]`
- `place_of_performance_scope=foreign` + explicit `country_code` list
  for the CENTCOM AOR (BH, IQ, JO, KW, OM, QA, SA, SY, YE, AF, EG,
  IR, LB, IL, KZ, KG, TJ, TM, UZ, PK)
- `award_type_codes=[A, B, C, D]`
- `time_period=[{start_date: 2025-07-24, end_date: 2026-07-24}]`

Result acceptance: rows landed, Place of Performance Country Code
populated ≥99%.

## Indicator status after Pass 1

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | Dollar concentration computable |
| F1.2 | GREEN | HHI derivable in trend_analysis |
| F1.3 | GREEN | Count + avg via trend stats |
| F2.1 | GREEN | End Date + open_window flag |
| F2.2 | GREEN | days_of_performance from json_derived_columns |
| F2.3 | GREEN | Slip share derivable |
| F3.1 | GREEN | Sub-agency diversity |
| F4.1 | GREEN | MoM change via trend_analysis |
| F5.1 | GREEN | Award Type field returned |

9 / 9 GREEN. No pass 2/3 needed.

## Gap declaration (for DS description)

```
This data source addresses the question "Which DoD prime contractors
concentrate the most dollar and schedule risk on CENTCOM-adjacent
awards over a rolling 12-month window?" via 9 / 9 planned indicators.

Scope:
- CENTCOM-adjacency proxied via Place-of-Performance country codes
  (BH, IQ, JO, KW, OM, QA, SA, SY, YE, AF, EG, IR, LB, IL, KZ, KG,
  TJ, TM, UZ, PK). This is a proxy — USASpending does not expose
  formal combatant-command tags.
- Rolling 12-month window (2025-07-24 through 2026-07-24).
- Award types A/B/C/D only. IDVs (Indefinite Delivery Vehicles) and
  grants excluded.
- DoD top-tier awarding agency only.
- Prime-award tier only. Sub-contracts not included; USASpending
  sub-award data is out of scope.
```

## Hand-off

Spec.json emitted next.
