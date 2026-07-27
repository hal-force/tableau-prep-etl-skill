# Collections log — Space-domain convergence

## Pass 1 — internal scan (2026-07-24)

- TLE Satellites (89) — F1/F2
- CNEOS Sentry (84) — F3
- OpenSky US (58) — F4 dashboard-time

## Pass 1 — external acquisition

- TLE via tle.ivanstanojevic.me (Space-Track mirror), 20 pages × 100.
- Sentry via ssd-api.jpl.nasa.gov (~2000 rows).
- OpenSky retained as dashboard join to avoid coupling refresh
  cadence.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | days_since_epoch |
| F1.2 | GREEN | Stale flag derived |
| F2.1 | GREEN | Orbital regime substring bin |
| F2.2 | GREEN | trend_analysis |
| F3.1 | GREEN | palermo_band existing |
| F3.2 | GREEN | days_since_last_obs |
| F4.1 | GREEN | Dashboard-time |
| F5.1 | GREEN | Tableau calc |

## Final status

8 GREEN + 0 AMBER + 0 RED.

## Gap declaration (verbatim for DS description)

```
Scope note (not a gap): "convergence" here is COINCIDENT ANALYST
INTEREST plus temporal overlap, NOT physical intercept. Real
collision / conjunction analysis requires SGP4 propagation and is
out of scope for this build. Orbital regime buckets are inferred
from TLE mean motion (line2 columns 53-62), which is a heuristic.
```
