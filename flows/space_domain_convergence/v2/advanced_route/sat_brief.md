# SAT brief — Space-domain convergence

## Step 1.1 — Question decomposition

Original:
> "Where do active satellites and asteroid impact-risk objects
> converge in time and orbital regime, and how does that overlap
> with airspace-adjacent flight activity?"

Refined:
> **For active satellites (from TLE catalog) and Sentry
> impact-risk asteroids, which orbital regime buckets (LEO, MEO,
> GEO, HEO, cislunar) currently show the highest population
> density, TLE staleness, and Palermo-scale risk concentration —
> and how does US flight activity (OpenSky) intersect the same
> temporal window as a proxy for public-space awareness demand?**

## Step 1.2 — Key Assumptions Check

- ⚠ **Convergence here is COINCIDENT INTEREST, not physical
  intercept.** Satellites and asteroids don't collide in this
  dataset scope; the "convergence" is analyst-attention (same
  orbital regimes trending) plus temporal coincidence (fresh TLE
  updates + recent Sentry observations + active US flights).
- **Orbital regime is inferred from TLE mean-motion**, not from
  authoritative catalog attribute. This is a heuristic.
- **OpenSky is a US-airspace ADS-B receiver network**, not a
  space-object tracker. Its inclusion is a demand-side proxy —
  "how much airspace activity is happening in the same time
  window we're triaging space-domain data."
- **Sentry catalog is small (~2000 rows)**; joins are conceptual,
  not physical.

## Step 1.3 — Factors

- **F1. Satellite catalog freshness.** days_since_epoch per TLE.
- **F2. Orbital regime distribution.** Bucketed from TLE mean
  motion (rev/day) — LEO ≥ 11.25, MEO 5-11.25, GEO ~1.0-1.1, HEO
  0.7-5, cislunar < 0.7.
- **F3. Asteroid risk concentration.** Palermo scale bands, ip
  (impact probability), days_since_last_obs.
- **F4. Airspace activity proxy.** OpenSky US aircraft state count
  in the same trailing window.
- **F5. Temporal convergence.** Overlap of fresh TLE updates + new
  Sentry observations + high OpenSky activity in the last 7 days.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | days_since_epoch per TLE | current |
| F1.2 | F1 | Stale-TLE flag (days_since_epoch > 14) | current |
| F2.1 | F2 | Orbital regime bucket per TLE | current |
| F2.2 | F2 | Population count per regime | current |
| F3.1 | F3 | palermo_band per Sentry entry | current |
| F3.2 | F3 | days_since_last_obs | current |
| F4.1 | F4 | US aircraft state count (OpenSky snapshot) | current |
| F5.1 | F5 | Composite convergence score = fresh-TLE% × elevated-palermo count × OpenSky-activity | current |

## Acceptance criteria

- TLE: ≥1000 rows (we pull 20 pages × 100).
- Sentry: full catalog ~2000 rows.
- OpenSky US snapshot: at least a snapshot count metric.

## Out-of-scope

- Physical collision analysis (needs SGP4 propagation).
- SDA conjunction assessment.
- Real-time RSO catalog updates.
- Non-US airspace.

## What "good" looks like

Three DSes on Cloud:

- **Space Convergence Satellite Detail** — TLE catalog + orbital
  regime bucket + freshness flag.
- **Space Convergence Asteroid Risk** — Sentry catalog + palermo
  band.

(Airspace activity is left as a dashboard-time indicator from the
existing OpenSky US DS to keep this build focused.)
