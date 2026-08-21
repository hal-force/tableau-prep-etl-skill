# Collections log — MOD JEWOSC EW Fusion v2 (2026-07-27)

## Pass 1 — internal-first acquisition + primary probe

**Internal scan.** The strongest internal footprint we've seen on a
demo run. v1 of *this* flow is already a published DS
(`Prep Agent / 31 - MOD JEWOSC EW Fusion Demo`), and three sibling
demo flows already prove the exact ingestion shapes v2 needs:

| Internal DS | Ingestion shape proven | Reuse in v2 |
|---|---|---|
| MOD JEWOSC EW Fusion (v1) | live JSON array + Python fusion step | v2 spine, unchanged |
| OpenSky US Live Air Traffic | `/states/all` bbox JSON array | same endpoint, UK/NW-Europe bbox (= v1) |
| NOAA SWPC Alerts | product-feed JSON | environment-layer candidate (F3.1) |
| Active Satellite TLE Catalog | paginated catalogue JSON | space-object-density candidate (F3.1) |

9 of 13 indicators are **GREEN-inherited** from v1 on Pass 1 without
touching a new upstream: F1.2, F2.1, F3.2, F4.1, F4.2, F5.1, F5.2
(the whole fusion + physics + threat spine) plus F1.1's air feed.

**v1 spec re-validated** against the current validator:
`python3 -m skill.scripts.spec_validation --spec .../v1/spec.json` →
exit 0. Safe to inherit.

**Net-new work isolates to two things:** the F3.1 environment layer,
and the versioned dashboard artifact (F6/F7/F8). Pass 1 probed the two
environment feeds live:

### SWPC space-weather — UP ✅
- `services.swpc.noaa.gov/products/noaa-scales.json` → HTTP 200. The
  `"0"` block is the **current-state** NOAA scales:
  `R` (radio blackout / HF-propagation degradation), `S` (solar
  radiation), `G` (geomagnetic). Exactly the snapshot-time EM-environment
  scalar F3.1 wants. Example current state: `R0 / S0 / G0` ("none").
- `services.swpc.noaa.gov/products/noaa-planetary-k-index.json` → 200,
  a clean 3-hourly `Kp` time-series (latest `Kp≈3.0`). Good backup
  scalar.
- The sibling flow's `alerts.json` (128 rows) also up, but it's
  free-text `message` — worse for a single `em_environment_band` than
  the scales object.

### TLE space-object catalogue — DOWN ❌
- `tle.ivanstanojevic.me/api/tle` returned **0 bytes** on the first
  attempt and **HTTP 406 Not Acceptable** on retry (even with an
  explicit `Accept: application/json` and a browser UA). The mirror is
  not serving right now. The sibling `tle_satellites` flow wraps this
  exact endpoint, so it works when the mirror is up — but it is not
  available at build time today.

## Pass 2 — F3.1 mechanism check + TLE gap-fill attempt

Two problems surfaced, both mechanism/availability rather than
data-absence:

**(a) Fusing a 1-row environment scalar onto every track.** The
environment state is a *single current-state record*, not a per-track
feed. To attach it to every track row we need one of:
- a `join` on a constant key — but there's no constant/literal
  `json_derived_columns` kind (confirmed: the 13 kinds are
  year_month_iso, concat, list_join, dict_field, list_first_field,
  dotted_path, numeric_bin, epoch_ms_iso, days_since, days_between,
  substring, map_values, list_length — **no `constant`/`literal`**),
  and no cross-join / broadcast primitive in the planner; or
- **fetch the environment state inside the fusion script itself** and
  broadcast it across the dataframe.

The second is the clean path and matches how v1 already works (the
fusion step is a Python Script node that can do I/O). Decision: extend
`ew_fusion.py.j2` in v2 to pull `noaa-scales.json` once at fuse time
and stamp `em_environment_band` (+ the R/S/G scale digits and a
`hf_propagation_note`) onto every row. This keeps F3.1 a genuine
cross-domain fuse (air track × space-weather EM environment) without
inventing a new planner primitive.

**(b) TLE space-object-density half of F3.1.** Retried the TLE mirror
— still `406`. The space-object-density scalar (count of catalogued
objects overhead the theatre bbox at snapshot time) would be a *second*
environment dimension. Two blockers stack: the mirror is down today,
AND even when up, TLE gives orbital elements — deriving "objects over
this bbox right now" requires SGP4 propagation to sub-satellite points,
which is a modelling step well beyond what the sibling `tle_satellites`
flow does (it only adds `days_since_epoch` + an orbital-class bin).
That's a genuine scope expansion, not a config tweak.

## Pass 3 — final resolution

- **F3.1 (space-weather half) → AMBER, planned build-task.** The data
  is available (`noaa-scales.json`, live, verified) and the mechanism
  is understood (fetch the current-state scales inside the fusion
  Script node and broadcast `em_environment_band` + `space_wx_r/s/g` +
  `hf_propagation_note` across every track). But that requires
  extending `ew_fusion.py.j2` — a template change that belongs to the
  flow-BUILD step, not to this collections-planning pass. It is NOT yet
  implemented in code. The hand-off spec below therefore ships the
  proven v1 air+EOB fusion spine as-is; the environment columns are
  specified here as the first build-task for the flow-generation step,
  to be turned GREEN there (gated so v1 renders stay byte-identical,
  golden hashes reblessed, fuse() verified on sample rows) before any
  publish. Recorded AMBER — data present, transform not yet built —
  rather than GREEN, so the plan does not overclaim.
- **F3.1 (space-object-density half) → declared GAP.** Dropped from v2
  for two stacked reasons: the TLE mirror was unavailable at build time
  (406), and turning TLE elements into "objects over the bbox now"
  needs SGP4 propagation this demo doesn't carry. Declared explicitly
  in the DS description; named as the obvious next scenario.
- **F6.1 / F6.2 / F7.1 / F8.1 → GREEN via dashboard artifact.**
  Authored `v2/dashboard/dashboard_spec.md` specifying the five
  operator constructs, the PPI_X/PPI_Y + threat_rank calcs, the
  escalation colour ramp, the dashboard actions, and the mandatory
  synthetic-data footer.

## Final status

| Indicator | Status |
|---|---|
| F1.1 (>=3 feed shapes fused) | **AMBER** — air feed GREEN now; space-weather feed adds the 2nd shape once the F3.1 build-task lands. Ingestion shapes all proven by internal siblings. |
| F1.2 (live-refresh feed) | GREEN — hourly air snapshot (inherited) |
| F2.1 (>=25-col fused row) | GREEN now — 31 v1 cols; grows to 35 after the F3.1 build-task |
| F3.1 (air × environment correlation) | **AMBER (space-weather: data ready, transform is a build-task); RED/GAP (space-object density)** |
| F3.2 (EOB fuse) | GREEN — inherited |
| F4.1 (range/bearing/aspect) | GREEN — inherited |
| F4.2 (Friis rx_dbm) | GREEN — inherited |
| F5.1 (threat_band) | GREEN — inherited |
| F5.2 (fusion_confidence) | GREEN — inherited |
| F6.1 (PPI polar spec) | GREEN — dashboard artifact |
| F6.2 (geo + track list + RF de-interleave) | GREEN — dashboard artifact |
| F7.1 (decision-first + drill) | GREEN — dashboard artifact |
| F8.1 (synthetic boundary declared 2×) | GREEN — DS description + dashboard footer |

**Status at end of collections planning:** 9 indicators GREEN today
(the full v1 fusion + physics + threat spine, inheritable immediately);
3 deliverable-indicators (F6.1/F6.2/F7.1/F8.1) GREEN via the dashboard
artifact; F3.1 space-weather half AMBER (data verified-available, one
template build-task away); F3.1 space-object-density half declared a
GAP. The hand-off spec ships the GREEN spine now and carries the AMBER
build-task as its first flow-generation step. Nothing is published
until F3.1 is either built-and-verified or the deliverable is
knowingly shipped air+EOB-only.

## Gap declaration (verbatim — folded into output.description)

```
This data source is an UNCLASSIFIED demonstration for UK MoD JEWOSC.
It assesses the Tableau Prep -> Server -> Desktop chain against three
evaluation axes: ingesting complex Defence-EW-shaped data, fusing and
modelling it, and presenting it in an operational context.

Sources (all public, keyless, auth:none):
- Air picture: OpenSky Network /states/all, bbox UK & NW-Europe
  (lat 48-61, lon -8..8). One row per aircraft state vector at snapshot
  time. Live; hourly refresh.
- Electronic Order of Battle: SYNTHETIC and NOTIONAL. Emitter class,
  primary_emitter, RF band, centre frequency, PRI, PW, ERP, and mode
  are illustrative reference values baked into the fusion step. They
  are NOT drawn from any classified source and must not be read as
  real emitter parametrics.
- EM environment: NOAA SWPC current-state space-weather scales
  (noaa-scales.json) — R (radio-blackout / HF-propagation), S (solar
  radiation), G (geomagnetic) — stamped onto every track as the
  electromagnetic-environment context at snapshot time.

Models applied in-flow: great-circle range/bearing/aspect from a fixed
own-ship (RAF Odiham, 51.3762N -1.3086E); Friis free-space received
power (dBm) at own-ship from notional ERP + range + frequency; a
documented rule-based threat_band (Non-hostile / Search / Track /
Engage / Critical) and a 0..1 fusion_confidence. All thresholds are
illustrative decision surfaces intended to be inspected and retuned by
a JEWOSC analyst, not operational doctrine.

Gaps:
- Space-object density (F3.1, second dimension): a per-snapshot count
  of catalogued space objects over the theatre was planned as a second
  EM-environment dimension. Three passes attempted. Pass 1/2 — the TLE
  catalogue mirror (tle.ivanstanojevic.me) returned HTTP 406 at build
  time. Pass 3 — even when available, deriving "objects over this bbox
  now" from TLE elements requires SGP4 propagation to sub-satellite
  points, which this demonstration does not carry. Declared out of
  scope. Effect on the answer: the EM-environment layer reflects
  space-WEATHER state only, not orbital-object congestion. Readers
  should not infer space-object density from this data source.
- Emitter geolocation (deliberate non-goal): the demo models received
  power at a KNOWN own-ship from a KNOWN track position; it does not
  solve the inverse problem of locating an emitter from intercepts
  (TDOA/FDOA). This is the most obvious next scenario.

To extend this demonstration:
- Add an SGP4-propagated space-object-density layer once the TLE feed
  is reliable (or via a Space-Track account).
- Add a moving / multi-ship own-ship scenario.
- Replace the synthetic EOB with a real (accredited-enclave) EOB to
  move from capability demonstration to operational evaluation.
```

## Hand-off to simplified route

`spec.json` written next: single `rest_api` source (OpenSky UK/NW-Europe
bbox, inherited from v1), a v2 `ew_fusion` transform that additionally
fetches `noaa-scales.json` and stamps the environment columns, one
`published_data_source` output carrying the gap declaration above.
Target project `Prep Agent / 31 - MOD JEWOSC EW Fusion Demo`
(overwrite v1), hourly. Dashboard artifact ships alongside under
`v2/dashboard/`.

Run command:
```bash
python3 -m skill.scripts.run_loop \
    --spec flows/MOD_JEWOSC_EW_Fusion/v2/spec.json \
    --flow-name MOD_JEWOSC_EW_Fusion \
    --publish --auto-create-project
```
(TabPy must be up on :9099 for the fusion Script node; the environment
fetch inside the fusion step needs outbound HTTPS to services.swpc.noaa.gov.)
