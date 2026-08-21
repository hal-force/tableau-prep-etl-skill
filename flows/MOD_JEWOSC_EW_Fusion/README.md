# MOD JEWOSC EW Fusion

**Latest:** [v3/](v3/README.md)

All versions:

- [v3](v3/README.md) — **fusion as native Prep join nodes.** Same
  JEWOSC analytic as v2, restructured so the fusion is *visible on the
  canvas*: a lean Python MATCH node (fuzzy parametric nearest-neighbour,
  the one thing that can't be an equality join) assigns each intercept
  an `emitter_id`, then the threat library, EOB laydown rollup, and
  platform MDF coverage are fused with **three native SuperJoins on
  emitter_id**. 4 inputs → match → 3 joins → Hyper. Verified locally
  (500×49); match distributions identical to v2.
- [v2](v2/README.md) — advanced collections route; **multi-source
  intercept → mission-data fusion**. A synthetic ELINT feed (500 cuts)
  fuzzy-matched against a 25-emitter threat library + 40-site EOB +
  8-platform MDF coverage; surfaces matched/ambiguous/unknown emitters,
  reprogramming triggers, WEZ membership, and coverage gaps. Verified
  locally (500×33). JEWOSC maturity-evaluation demo. All data synthetic.
- [v1](v1/README.md) — OpenSky ADS-B + synthetic EOB fusion (single feed).
