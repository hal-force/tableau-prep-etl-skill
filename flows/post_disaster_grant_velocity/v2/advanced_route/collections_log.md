# Collections log — Post-disaster grant velocity

## Pass 1 — internal scan (2026-07-24)

- FEMA Disasters (92) — F1 anchor
- USASpending SLED Grants (78) — F2/F3 (FY25-26)
- SLED Grants FY24 Detail from flow #3 (71) — F2 (FY24)
- Fed Outlays (40) — F3 baseline context

## Pass 1 — verdict

Four feeder DSes exist. Scope this build to the FEMA disaster
anchor with declaration-focused enrichment; grant joins happen at
dashboard time to avoid coupling four refresh cadences.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | 24mo window |
| F2.1 | GREEN | Dashboard-time |
| F3.1 | GREEN | Dashboard-time calc |
| F4.1 | GREEN | Tableau |
| F5.1 | GREEN | Tableau |

## Final status

5 GREEN + 0 AMBER + 0 RED (with explicit scoping decision).

## Gap declaration (verbatim for DS description)

```
Scope note (not a strict gap):
- 'Post-declaration grant velocity' is TEMPORAL CORRELATION, not
  causation. Many grants in the 90d post-declaration window are
  unrelated program renewals. Without a CFDA / HMGP program-code
  crosswalk we CANNOT tag which grants are recovery-specific.
- This DS is the FEMA-anchor leg (disaster events + 24mo window).
  Grant joins happen at Tableau layer to avoid coupling four
  refresh cadences into one build.
- Major disaster declarations only (DR-prefix).
```
