# SAT brief — Russian losses in Ukraine, war progression

## Step 1.1 — Question decomposition

User's original phrasing:
> "Tell me about Russian losses in Ukraine in order for me to
> understand how the war is progressing."

This is a learning question, not a decision question. Two things to
pin down before we can pick data:

1. The visible metric the user wants ("Russian losses") — equipment,
   personnel, territory, or all three.
2. The decision-driving angle ("how the war is progressing") — *trend*
   matters more than *absolute totals*, because "progressing" implies
   change over time vs prior baseline.

Refined question:

> **How have Russian military losses in Ukraine evolved over the past
> 24 months — by category (personnel, equipment by class, territory)
> — and what does the trajectory of those losses suggest about the
> tempo and intensity of the conflict?**

A dashboard that answers this needs three things:

- A long enough time series to show **trajectory**, not just current
  totals.
- A **category breakdown** so the user can see whether attrition is
  concentrated in (e.g.) armor, aircraft, or personnel.
- A **trend overlay** — rolling windows, week-over-week change, and
  cumulative-vs-recent split.

## Step 1.2 — Key Assumptions Check

Assumptions baked into the question. The ones that would change the
answer shape if wrong are flagged ⚠.

- ⚠ **"Losses" = combat losses (destroyed / captured / abandoned), not
  withdrawals or rotation.** If the user wanted total personnel
  *deployed* or unit *strength*, this is a different question.
- ⚠ **One-sided framing — Russian losses only.** The user did not ask
  about Ukrainian losses. We'll note this in the description because
  any "war progression" reading from one-sided numbers is partial; a
  dashboard reader needs to know they're seeing one side of the
  ledger.
- **No claim to ground-truth.** Every public counter of Russian
  losses in Ukraine is a *claim* — either Ukrainian MoD self-report
  (high), Russian MoD self-report (low; rarely published), or
  independent open-source-intelligence (OSINT) verification (middle,
  conservative). We pick the middle path (OSINT) and disclose the
  source.
- **Daily granularity is enough.** Hourly tempo is irrelevant for a
  "how is the war progressing" framing.
- **Equipment categories matter** (armor, artillery, air defense,
  aircraft, ships). Personnel are a single bucket; equipment is not.
- **Geographic detail is secondary.** "Progression" can be answered
  with national-level loss curves; the front-line geography is a
  separate question.

## Step 1.3 — Factors driving the answer

Underlying real-world drivers (not yet datasets):

- **F1. Equipment attrition rate** — how fast Russia is losing
  tanks / IFVs / artillery / aircraft, and whether the rate is
  accelerating or slowing.
- **F2. Personnel attrition rate** — daily / weekly casualty pace and
  cumulative total.
- **F3. Compositional shift** — what *kind* of equipment is being
  lost most. Heavy armor vs trucks vs glide-bomb-capable aircraft tell
  different stories.
- **F4. Territorial change** — net territory gained / lost. This is the
  one factor that doesn't fit cleanly into "losses" but is the most
  common shorthand for "is the war progressing."
- **F5. Reporting confidence / time-lag** — OSINT verification lags
  real events by days-to-weeks. Recent windows are systematically
  under-counted. This is a *meta-factor* the dashboard must surface.

## Step 1.4 — Indicators (operationalized)

Each indicator maps to a column or computation on a candidate data
source. Indicators are recency-aware (windowed) and falsifiable
(a low value means something definite).

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | Cumulative equipment losses by class (tanks, IFVs, APCs, artillery, MLRS, AD, aircraft, helicopters, UAVs, naval) | full war to date |
| F1.2 | F1 | 30-day rolling equipment loss count by class | 30d |
| F1.3 | F1 | Week-over-week %change in equipment loss rate by class | 7d vs prior 7d |
| F2.1 | F2 | Cumulative personnel losses (KIA + WIA + POW where reported; OSINT-confirmed KIA where available) | full war to date |
| F2.2 | F2 | 30-day rolling personnel loss count | 30d |
| F2.3 | F2 | Week-over-week %change in personnel loss rate | 7d vs prior 7d |
| F3.1 | F3 | Equipment-loss mix — % of total losses by class for the last 90 days vs the prior-war average | 90d |
| F3.2 | F3 | Top 3 equipment classes by recent loss share | 30d |
| F4.1 | F4 | Net Russian-controlled territory change (sq km) | 30d |
| F4.2 | F4 | Cumulative territory change since invasion | full war to date |
| F5.1 | F5 | OSINT confirmation lag — median days between loss event and confirmed listing | last 90d |
| F5.2 | F5 | Share of recent-window losses with photographic / geolocated confirmation | 30d |

## Acceptance criteria

For each indicator, the data source(s) must provide:

- Daily-granular records spanning at least Feb 2022 → present.
- A loss-class taxonomy that maps cleanly onto our 10 equipment buckets
  (tanks, IFVs, APCs, artillery, MLRS, air-defense, aircraft,
  helicopters, UAVs, naval), or one we can derive.
- A `confirmed_by` or equivalent field for F5 — we need to know how
  each loss was verified.
- For territory (F4): a daily polygon or sq-km estimate of
  Russian-controlled area.
- For personnel (F2): a single number per day per side, with a
  transparent source.

## Out-of-scope (deliberate)

- Ukrainian losses — flagged as a known one-sided gap, will appear in
  the published DS description.
- Frontline geography / map layer — separate dashboard.
- Strategic / political assessment — out of scope; this is an
  attrition dashboard, not a policy brief.
- Cyber, information, and economic losses — only kinetic / territorial.

## What "good" looks like at the end

A two-DS deliverable matching the Embassy Threat Monitor pattern:

- **`Russia Ukraine Losses Detail`** — one row per day per loss-class
  (tank / IFV / artillery / etc.), with cumulative and rolling fields.
- **`Russia Ukraine Loss Summary`** — daily-grain rollup with all
  classes pivoted into columns + territorial change + a single
  composite "tempo" index so a Tableau line chart immediately
  shows trajectory.

The DS description on Server explicitly names:
- The source(s) used and their confidence tier.
- The one-sided framing (Russian losses only).
- Any F-indicator that ended RED after 3 passes.
