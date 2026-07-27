# SAT brief — Oversight vs execution (RED graceful degrade)

## Step 1.1 — Question decomposition

Original:
> "Where do federal oversight signals (Fed Register actions,
> Congressional interest) diverge from actual execution (DoD
> contracts, USASpending grants) — pointing to programs under
> scrutiny that keep executing anyway, or vice versa?"

Refined:
> **For federal sub-agencies, is the trend in Federal Register
> oversight signals (rules / notices / proposed rules referencing
> the sub-agency) correlated with the trend in the sub-agency's
> execution volume (DoD contract obligations, SLED grants)? Where
> is oversight surging with execution flat, or execution surging
> with oversight quiet?**

## Step 1.2 — Key Assumptions Check

- ⚠ **RED indicator, graceful degrade demo.** Congressional
  hearings and CRS report activity are NOT publicly available at
  a structured DS level — declared RED. We degrade to Fed Register
  as the sole oversight-signal proxy.
- **Fed Register agency mapping is coarse.** Not every action
  cleanly maps to a sub-agency; parent-agency granularity is
  reliable.
- **DoD Contracts + SLED Grants** are the execution-volume
  proxies. They cover the two dominant civilian + defense flow
  channels but not everything (e.g., no Medicare CMS payment
  data).
- ⚠ **Divergence is a QUESTION-RAISER, not an answer.** Programs
  under oversight often SHOULD keep executing (oversight is a
  process, not a stop); we surface the pattern for analyst
  triage.
- **Trailing 18 months** — Fed Register Actions DS window.

## Step 1.3 — Factors

- **F1. Oversight volume.** Fed Register document count per
  parent agency, trailing 18 months.
- **F2. Execution volume.** DoD contract obligations count/dollars,
  SLED grant count/dollars, trailing 18 months.
- **F3. Divergence pattern.** Correlation between monthly F1 and
  monthly F2 per agency.
- **F4. Congressional interest.** RED — hearings/CRS data not
  available as structured DS.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Monthly Fed Register doc count per agency | 18mo |
| F1.2 | F1 | Monthly Fed Register rule vs notice mix | 18mo |
| F2.1 | F2 | Monthly DoD contract obligations $ per sub-agency | 18mo |
| F2.2 | F2 | Monthly SLED grant $ per sub-agency | 18mo |
| F3.1 | F3 | Rolling Spearman correlation | 6mo window |
| F3.2 | F3 | Divergence flag (F1 z-score >2 AND F2 z-score <0) | 18mo |
| F4.1 | F4 | (RED — Congressional interest) | — |

## Acceptance criteria

- Fed Register Actions DS covers 18mo.
- DoD Contracts / SLED Grants DSes cover 18mo.

## Out-of-scope

- Specific bill / hearing tracking (RED).
- IG reports (separate DS, not on-site).
- Court filings.

## What "good" looks like

Two DSes on Cloud:

- **Oversight vs Execution Detail** — Fed Register documents with
  agency + type + calendar features, refreshed 18mo.
- **Oversight vs Execution Stats** — trend statistics for
  divergence detection.
