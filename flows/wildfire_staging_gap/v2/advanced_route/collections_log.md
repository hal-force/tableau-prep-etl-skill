# Collections log — Wildfire staging gap

## Pass 1 — internal scan (2026-07-24)

- US Wildfires EOC (score 91) — F1/F2/F3/F5
- US Grid Network (58) — F4 dashboard-time

## Pass 1 — external acquisition

Re-pulled the WFIGS FeatureServer (ActiveFireCandidate=1) with the
same eoc_fire_metrics enrichment. Filtered prescribed burns out.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | IncidentSize populated |
| F1.2 | GREEN | days_since_discovery derived |
| F1.3 | GREEN | daily_growth_rate derived |
| F2.1 | AMBER | Personnel self-reported, lags shift |
| F2.2 | AMBER | Cost self-reported |
| F2.3 | AMBER | Complexity level only on typed incidents |
| F3.1 | GREEN | Derived |
| F3.2 | GREEN | Derived |
| F3.3 | GREEN | Derived |
| F4.1 | GREEN | Dashboard-time join |
| F5.1 | GREEN | Derived |

## Pass 2 — n/a (no RED)

## Final status

8 GREEN + 3 AMBER + 0 RED.

## Gap declaration (verbatim for DS description)

```
This data source addresses the question "Which active US wildfire
incidents show a gap between scale and assigned resources?" via
8 GREEN indicators + 3 AMBER (self-reported IMT data lags shift).

Scope:
- Active US wildfire incidents from NIFC/WFIGS
  (ActiveFireCandidate=1), excluding prescribed burns.
- Personnel / cost / complexity are IMT self-reported and update
  per shift; the resource-gap flag may over/under-fire on the most
  recent shift. Refresh cadence: hourly to minimize lag.
- Staging gap is a HEURISTIC proxy, not an operational
  determination. Real staging goes through ICS resource orders.
- Grid spillover is a state-level indicator (US Grid Network DS
  join by POOState), not a facility-level proximity check.

To fill AMBER: no external substitute exists; the IMT self-report
via WFIGS is the authoritative feed. Latency is inherent.
```
