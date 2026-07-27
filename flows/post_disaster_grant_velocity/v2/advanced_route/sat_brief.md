# SAT brief — Post-disaster grant velocity

## Step 1.1 — Question decomposition

Original:
> "After a federal disaster declaration, how quickly does federal
> grant money flow into the affected state, and where does that
> velocity break down?"

Refined:
> **For each FEMA-declared disaster in the last 24 months, what is
> the time-to-first-grant, cumulative grant dollars in the trailing
> 90 days post-declaration, and the delta versus a state-baseline
> grant flow — highlighting states where recovery-grant velocity
> lags the baseline?**

## Step 1.2 — Key Assumptions Check

- ⚠ **This is the CANONICAL 4-DS join demo.** FEMA Disasters
  (declaration events) + USASpending SLED FY24 (grant events) +
  USASpending SLED FY25-26 (renewal grants) + Fed Outlays
  (baseline). All four exist internally.
- **"Grant velocity" here is a POST-DECLARATION CUMULATIVE
  METRIC**, not a per-grant SLA. We measure how many dollars flowed
  into the state's recipient set in the 90 days AFTER the
  declarationDate.
- **Baseline** = same state's trailing 12mo average monthly SLED
  grant flow, normalized to a 90-day equivalent.
- **NOT a causal claim** that these grants are recovery grants.
  Many are unrelated program renewals. We're measuring temporal
  correlation, not causation.
- Major disaster declarations only (DR-prefix in
  femaDeclarationString).

## Step 1.3 — Factors

- **F1. Disaster identity.** disasterNumber, declarationDate,
  state, incidentType.
- **F2. Post-declaration grant flow.** Sum of Award Amount in the
  state, in the 90 days after declarationDate.
- **F3. Baseline grant flow.** Same state's 12mo monthly average
  × 3 (90-day-equivalent).
- **F4. Velocity ratio.** F2 / F3.
- **F5. First-grant lag.** min(days) from declarationDate to first
  grant Start Date in the state.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | disasterNumber, declarationDate, state, incidentType | 24mo |
| F2.1 | F2 | Post-decl 90d grant $ per (disaster) | 24mo |
| F3.1 | F3 | State 12mo monthly baseline | trailing |
| F4.1 | F4 | Velocity ratio | derived |
| F5.1 | F5 | First-grant lag days | 24mo |

## Acceptance criteria

- FEMA disasters: ≥1000 declarations in the last 24 months.
- USASpending grants: joinable by recipient state.

## Out-of-scope

- Per-disaster grant attribution (need CFDA/HMGP crosswalk).
- Insurance / private funding.
- FEMA Individual Assistance dollars (separate DS).
- Trump-era disaster fund pauses (macro-context).

## What "good" looks like

Two DSes on Cloud:

- **Post-Disaster Grant Velocity Detail** — one row per disaster
  with F1/F2/F5 fields.
- **Post-Disaster Grant Velocity Stats** — state-level rollups.
