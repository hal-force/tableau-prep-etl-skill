# Collections log — US diplomatic post physical-security exposure

## Pass 1 — internal scan (2026-07-24)

Phase 0 metadata-API scan against the connected site surfaced the
following candidates ranked by topic-match score:

| DS | Project | Score | Verdict |
|---|---|---:|---|
| Embassy Threat Events v2 | Embassy Threat Monitor v2 | 92.0 | This IS the answering DS. |
| Embassy Risk Summary v2 | Embassy Threat Monitor v2 | 92.0 | Companion summary DS. |
| GDELT Global Events (Threat Filter) | Prep Agent | 34.0 | Upstream feed to the above. |

Verdict: the question already has canonical internal DSes on-site.
Under the internal-first rule the correct pass is to *refresh* the
existing spec.json against the same upstream, not re-plan external
acquisition.

## Pass 1 — indicator status against the published DSes

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | Events DS carries per-event within-radius rows. |
| F1.2 | GREEN | embassy_threat_join haversine distance column. |
| F2.1 | GREEN | Max CAMEO root observed per post. |
| F2.2 | GREEN | Weighted threat score column on Summary DS. |
| F2.3 | GREEN | event_summary + source URL columns are the v2 addition. |
| F3.1 | GREEN | us_actor_share column. |
| F4.1 | AMBER | WoW delta folded into the weighted score's decay term, not surfaced separately. |
| F4.2 | GREEN | 5-band risk_band column. |
| F5.1 | AMBER | GDELT 1.0 dedup is heuristic (URL-per-row shape). |

7 GREEN + 2 AMBER; 0 RED. No pass 2 needed — the ambers are known
scope decisions, not acquisition failures.

## Pass 2 — n/a

Not run. Pass 1 hit acceptance across every indicator at GREEN or
AMBER-with-scope-decision.

## Pass 3 — n/a

Not run.

## Final status

| Id | Final |
|---|---|
| F1.1, F1.2, F2.1, F2.2, F2.3, F3.1, F4.2 | GREEN |
| F4.1, F5.1 | AMBER — declared as scope notes below |

## Gap declaration (verbatim — for DS description)

```
This data source addresses the question "Which US diplomatic posts
are at elevated physical-security risk over the next 30 days?" via
9 of 9 planned indicators (7 GREEN, 2 AMBER with declared scope
decisions).

Scope:
- 60-post curated US diplomatic roster (Ambassador + Consular; not
  representative missions).
- CAMEO EventRootCode ∈ {13, 14, 17, 18, 19, 20} — protest through
  mass violence. Economic sanctions and diplomatic censure not
  included.
- 50mi haversine radius from each post's coordinates.
- Recency-weighted over a 90-day trailing window; refresh every 3
  hours.

AMBER notes:
- Week-over-week trend (F4.1): folded into weighted_threat_score
  via a recency-decay term, not surfaced as its own column. A v3
  would split this out for direct dashboard use.
- Distinct-event deduplication (F5.1): GDELT 1.0 emits one row per
  source URL; downstream dedup is heuristic on (SQLDATE +
  ActionGeo_Lat/Long + EventCode). NumMentions is retained as the
  URL-inflation proxy. GDELT 2.0 GKGRECORDID would upgrade this to
  GREEN but changes the upstream contract.
```

## Hand-off to simplified route

The `spec.json` at `flows/embassy_threat_monitor_v2/v1/spec.json`
already implements this collections plan and publishes both target
DSes every 3 hours via a local-render-plus-upload path (see
[[feedback_cloud_vs_server_execution]]). No new spec is emitted for
this pass; the round-trip validation is that the existing spec
still passes `validate_spec_strict` and renders byte-identical
scripts against the render-diff harness.
