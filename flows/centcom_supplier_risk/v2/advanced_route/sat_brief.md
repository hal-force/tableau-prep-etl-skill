# SAT brief — CENTCOM supplier concentration risk

## Step 1.1 — Question decomposition

Original ask:
> "Which suppliers concentrate the most schedule + dollar risk across
> CENTCOM-adjacent awards?"

Refined:
> **Which prime contractors concentrate the most combined dollar and
> schedule-slip risk across DoD awards with CENTCOM-adjacent
> place-of-performance and description signals over the last 12
> rolling months, ranked by a composite risk score that surfaces
> both dollar-concentration and delivery-window exposure?**

## Step 1.2 — Key Assumptions Check

- ⚠ **CENTCOM-adjacent is inferrable from award metadata.** USASpending
  doesn't expose combatant-command tags. We proxy via
  place-of-performance country codes (Bahrain, Iraq, Jordan, Kuwait,
  Oman, Qatar, Saudi Arabia, Syria, UAE, Yemen, Afghanistan, Egypt,
  Iran, Lebanon, Israel, Kazakhstan, Kyrgyzstan, Tajikistan,
  Turkmenistan, Uzbekistan, Pakistan) plus description-text keyword
  scan.
- ⚠ **Concentration = HHI-style share of dollars per prime.** A
  single dominant vendor at 40% of AOR dollars is different from
  four vendors at 10% each even though the top-line dollar sum is
  identical.
- **Schedule risk = ratio of days_of_performance vs. reported
  end-date drift.** USASpending gives Start/End dates on the award;
  delta between End Date and today, plus contract age, are the
  proxies.
- **12-rolling-month window.** Not FY-boundary; the ask is
  operational, not accounting.
- **DoD top-tier awarding agency only.** Do not include
  DHS/Coast Guard even where they operate CENTCOM-adjacent.
- **Award type codes A/B/C/D** (BPA Calls, POs, DOs, Definitive).
  IDVs and grants excluded.

## Step 1.3 — Factors

- **F1. Dollar concentration.** How much of AOR-adjacent DoD spend
  flows through the top primes.
- **F2. Schedule exposure.** How much of that spend sits in
  long-tail delivery windows still open today.
- **F3. Sub-agency dependence.** Whether the primes are diversified
  across Army/Navy/AF/DLA or concentrated in a single sub-agency.
- **F4. Trend.** Whether concentration is increasing (net-new
  awards to top primes) or stabilizing.
- **F5. Vehicle diversity.** Definitive Contract vs POs vs DOs —
  the mix reveals procurement style.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Top-10 primes' share of total AOR-adjacent dollars | 12-month rolling |
| F1.2 | F1 | HHI (sum of squared prime shares × 10000) | 12-month rolling |
| F1.3 | F1 | Award count and dollar-weighted avg award size per prime | 12mo |
| F2.1 | F2 | Sum of open-window dollars (End Date >= today) per prime | as-of today |
| F2.2 | F2 | Median days_of_performance per prime | 12mo |
| F2.3 | F2 | Share of prime's awards with End Date slipping >90d past today | 12mo |
| F3.1 | F3 | Sub-agency diversity index per prime (distinct sub-agencies / max) | 12mo |
| F4.1 | F4 | Month-over-month change in F1.1 (top-10 share) | rolling 12mo |
| F5.1 | F5 | Award-type-code mix share per prime (A/B/C/D) | 12mo |

## Acceptance criteria

- USASpending returns ≥5000 rows over the 12mo window with the
  CENTCOM-adjacent country filter applied.
- Place of Performance Country Code populated on ≥95% of rows.
- days_of_performance derivable on ≥90% of rows (Start + End both
  present).

## Out-of-scope

- Sub-contractor tier — USASpending only reports prime awards for
  this filter.
- Non-DoD CENTCOM-affiliated spend (DOS FMF, USAID stabilization).
- CENTCOM combatant-command official tagging — not available.
- Ceiling-vs-obligation split on IDVs — excluded via award-type
  filter.

## What "good" looks like

Two published DSes:

- **CENTCOM Supplier Awards Detail** — one row per award, with
  prime, sub-agency, dollars, dates, days_of_performance,
  CENTCOM-adjacent country tag, and derived open_window_flag.
- **CENTCOM Supplier Risk Summary** — one row per prime, with
  concentration + schedule + trend indicators computed.

Description on Server includes the CENTCOM-adjacency proxy
methodology and any AMBER indicators.
