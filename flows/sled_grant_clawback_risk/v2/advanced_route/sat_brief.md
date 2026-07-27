# SAT brief — SLED grant clawback risk

## Step 1.1 — Question decomposition

Original:
> "Which FY24 SLED grants show the highest risk of being clawed back
> based on recipient eligibility drift and program status?"

Refined:
> **Which state / local / educational grants disbursed by federal
> agencies in FY24 show the highest composite clawback-risk score,
> computed from (a) recipient-side signals (name-change / recipient
> type churn / recipient-outlay stagnation), (b) program-side signals
> (Federal Register termination or scope actions affecting the
> awarding sub-agency), and (c) the FY24 vs FY25 award-renewal
> pattern for the same recipient?**

## Step 1.2 — Key Assumptions Check

- ⚠ **"Clawback risk" is a proxy score, not a formal recovery
  determination.** Actual clawbacks require GAO / Inspector General
  findings that USASpending does not carry. We surface the *signals
  correlated with* eventual clawback.
- ⚠ **FY24 = 2023-10-01 through 2024-09-30.** Federal fiscal year,
  not calendar.
- ⚠ **"SLED" = state/local/educational.** Excludes nonprofits and
  for-profit primes even if they're SLED-adjacent.
- **Award type codes 02/03/04/05** (Block, Formula, Project,
  Cooperative Agreement). Contracts and IDVs excluded.
- **Fed Register signal window = 24 months** (FY23 - present) to
  capture terminations that affect FY24 awards.
- **Total Outlays field is a proxy for disbursement progress.** A
  large awarded amount with tiny outlays 18mo+ later is a stagnation
  flag.

## Step 1.3 — Factors

- **F1. Recipient churn.** Recipient name change, recipient type
  reclassification, or new registration in SAM.gov (proxy: same
  prime_award_recipient_id with different Recipient Name).
- **F2. Outlay stagnation.** Awarded amount vs Total Outlays gap on
  awards past their Start + 180d point.
- **F3. Program-status signal.** Federal Register actions affecting
  the Awarding Sub Agency in the 24 months around the award.
- **F4. Renewal pattern.** Whether the same recipient received a
  FY25 award from the same sub-agency (positive signal for
  low-risk; absence is a mild negative signal but ambiguous).
- **F5. Concentration.** Awards from sub-agencies with high
  program-termination signal density are systematically higher-risk.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Distinct Recipient Names per prime_award_recipient_id | over full FY24-25 |
| F2.1 | F2 | (Award Amount - Total Outlays) / Award Amount for awards ≥180d past Start | as-of today |
| F2.2 | F2 | Absolute unspent dollars per award | as-of today |
| F3.1 | F3 | Count of Federal Register "termination", "rescission", "amendment" actions per Awarding Sub Agency | 24mo |
| F3.2 | F3 | Days since latest such action (recency-weighted) | 24mo |
| F4.1 | F4 | Boolean: same recipient has ≥1 FY25 award from same sub-agency | full FY25 |
| F5.1 | F5 | Sub-agency clawback-signal density (F3.1 normalized by award count) | 24mo |

## Acceptance criteria

- USASpending returns ≥1000 FY24 SLED grants.
- Total Outlays populated on ≥80% of rows.
- Federal Register returns ≥200 actions over 24mo where a
  sub-agency can be identified.

## Out-of-scope

- Recipient-side name/entity resolution beyond
  prime_award_recipient_id.
- Actual clawback determinations (GAO reports not accessible).
- Sub-award / pass-through recipients.
- Nonprofit and for-profit recipients — SLED only.

## What "good" looks like

Two published DSes:

- **SLED Grants FY24 Detail** — one row per grant, with all
  enrichment + a per-award composite clawback_risk_score.
- **SLED Grants Sub-Agency Signals** — one row per Awarding Sub
  Agency, with F3.1 / F3.2 / F5.1 / renewal stats + a signal_density
  banding.
