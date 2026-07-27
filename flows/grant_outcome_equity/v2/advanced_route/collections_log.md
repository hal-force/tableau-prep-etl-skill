# Collections log — Grant-outcome equity

## Pass 1 — internal scan (2026-07-24)

- CDC PLACES County Health 2023 (82) — F2 burden proxy
- USASpending SLED Grants (61) — F1 grants (FY25-26)
- SLED Grants FY24 Detail from flow #3 (91) — F1 canonical

## Pass 1 — verdict

Direct grant OUTCOMES not available at scale. Escalate to pass-3
proxy substitution: substitute CDC PLACES health-outcomes as NEED
proxy. Reframe question from "did grants improve outcomes" to
"does grant flow match burden per capita".

## Pass 2 — build-time pulls

- PLACES 2023 (chronicdata.cdc.gov swc5-untb) filtered to
  categoryid=HLTHOUT.
- USASpending POST spending_by_award for FY24 SLED grants,
  aggregated by recipient_location_state_code at build time.

## Pass 2 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | State-level FY24 grant totals |
| F2.1 | GREEN | PLACES health-outcomes score |
| F3.1 | GREEN | State population from PLACES |
| F4.1 | GREEN | Tableau calc |
| F5.1 | GREEN | Tableau calc |
| F6.1 | GREEN | Tableau calc |

## Final status

6 GREEN + 0 AMBER + 0 RED (with explicit substitution).

## Gap declaration (verbatim for DS description)

```
Scope note (proxy substitution, not a strict gap):
- We CANNOT measure grant OUTCOMES directly. Per-grant impact data
  is private to the recipient's reporting. This flow SUBSTITUTES
  CDC PLACES county-level health-outcomes as a NEED proxy.
- 'Equity ratio' = grant-$-per-capita / burden-per-capita. Ratios
  above 1 indicate more grant flow than the burden proxy would
  suggest, and vice versa. This is a DIAGNOSTIC signal, NOT a
  normative determination about grant effectiveness or equity.
- Join granularity is STATE (USASpending recipient state, PLACES
  aggregated up from county to state). County-level SLED grant
  aggregation is not reliable because county fields are
  inconsistent on grant records.
- FY24 SLED window: 2023-10-01 through 2024-09-30.
```
