# SAT brief — Grant-outcome equity (pass-3 proxy substitution demo)

## Step 1.1 — Question decomposition

Original:
> "Which US counties receive federal grant dollars that are
> misaligned with their underlying health-outcome needs, indicating
> equity gaps in federal grant distribution?"

Refined:
> **For each US county, is the volume of federal SLED grant dollars
> awarded in the trailing period proportional to a proxy for
> health-outcome need (CDC PLACES health_outcomes measures)? Which
> counties are the most out-of-proportion (high need, low grant
> dollars per capita) and vice versa? Note that direct
> grant-outcome linkage requires per-grant impact data we do NOT
> have; this is the CANONICAL pass-3-proxy-substitution demo.**

## Step 1.2 — Key Assumptions Check

- ⚠ **We CANNOT measure grant OUTCOMES directly.** Per-grant
  outcome data (did the program achieve its goal?) is largely
  private to the recipient's reporting; USASpending has amount
  awarded and disbursed but not impact metrics.
- **Substituted proxy:** CDC PLACES county-level health outcomes
  as a NEED indicator; the question becomes "does grant flow
  match need?" instead of "did grants improve outcomes?"
- **Grant dollars aggregated by recipient state** in USASpending
  (county-level roll-up requires county field which is inconsistent
  on grants).
- ⚠ **"Equity" is a scoped word.** We surface DOLLARS-PER-NEED
  ratios, not any normative determination.
- **State-level** aggregation for USASpending (recipient state
  code) vs **county-level** PLACES; join happens at state.
- "Grant flow" = FY24 SLED grants (already pulled by flow #3).

## Step 1.3 — Factors

- **F1. State-level SLED grant dollars.** Sum of Award Amount by
  recipient state in the trailing period.
- **F2. State-level health-outcome burden.** Aggregate of CDC
  PLACES health_outcomes measures (weighted by population).
- **F3. Population normalization.** Federal reg estimate of state
  population.
- **F4. Grant-per-capita.** F1 / F3.
- **F5. Outcome-burden-per-capita.** F2 / F3 (population-weighted
  average).
- **F6. Equity ratio.** F4 / F5.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Total SLED FY24 grant $ per state | FY24 |
| F2.1 | F2 | State-level population-weighted health-outcomes score | 2023 PLACES |
| F3.1 | F3 | State population (from PLACES totalpopulation) | 2023 |
| F4.1 | F4 | Grant $ per capita | derived |
| F5.1 | F5 | Health-outcome burden per capita | derived |
| F6.1 | F6 | Equity ratio = F4.1 / F5.1 | derived |

## Acceptance criteria

- CDC PLACES: 3143 counties covered, health_outcomes measures
  populated ≥95%.
- USASpending SLED FY24: state-level rollup coverage on all 50
  states + DC.

## Out-of-scope

- Per-grant outcome verification (RED — data not available).
- County-level grant aggregation (grants field inconsistency).
- Federal (non-SLED) grants.
- Weighting by grant type.

## What "good" looks like

Two DSes on Cloud:

- **Grant-Outcome Equity Detail** — one row per state, showing
  grant $, burden score, and equity ratio.
- **PLACES County Burden Detail** — one row per (county, measure)
  showing burden bands for drill-through.
