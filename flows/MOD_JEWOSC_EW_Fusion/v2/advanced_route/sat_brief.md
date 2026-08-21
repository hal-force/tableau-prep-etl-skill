# SAT brief — MOD JEWOSC EW Fusion demonstration (v2)

## Step 1.1 — Question decomposition

Customer's original phrasing (UK MoD, Joint Electronic Warfare
Operational Support Cell):

> "It would be helpful to see how Tableau performs against complex
> Defence EW datasets, supports data fusion and modelling workflows,
> and presents information to end users in an operational context. A
> demonstration using representative scenarios would allow us to
> assess the maturity of the solution."

This is an **evaluation question, not an analytic one**. The customer
is not asking "what is the EW picture over the UK" — they are asking
"can this tool credibly handle *our kind* of work." That reframes the
whole exercise: the deliverable is judged on whether it **exhibits
capabilities**, not on whether it answers a threat question. The
data-fusion result is the vehicle; the capability demonstration is the
cargo.

The customer names three evaluation axes explicitly. Treat them as the
top-level structure:

1. **Complex Defence EW datasets** — can it ingest and hold the shape
   of real EW data (high-dimensional, multi-sensor, parametric RF,
   kinematic tracks, heterogeneous update rates)?
2. **Data fusion and modelling workflows** — can it *combine* sources
   and *derive* new intelligence (correlation across feeds, physics
   models, threat scoring), not just visualise a single table?
3. **Operational-context presentation** — does the end-user surface
   read like an operator's picture (PPI/geo, threat prioritisation,
   glance-then-drill), not a management BI dashboard?

Refined decision-driving question:

> **Across a set of representative unclassified EW scenarios, does the
> Tableau Prep → Server → Desktop chain (a) ingest and normalise
> multi-domain, high-dimensional sensor data, (b) fuse those feeds and
> apply physics-based + rule-based models to derive threat-relevant
> intelligence, and (c) present the result to an operator in a
> recognisably operational surface — to a standard that lets JEWOSC
> judge production maturity?**

A demonstration that answers this needs three things the v1 flow only
partially provides:

- **Breadth of source shape.** v1 fuses one feed (OpenSky ADS-B) with a
  static synthetic library. "Complex datasets" implies *multiple*
  feeds of *different* shapes fused together — an air picture plus a
  space/RF-environment layer plus a spectrum/geomagnetic-environment
  layer — so the fusion is genuinely cross-domain.
- **Visible modelling, not just enrichment.** The physics (Friis,
  great-circle geometry) and the rule-based threat banding must be
  *legible* as models the customer can critique and tune — parametrics
  exposed, thresholds documented, confidence surfaced.
- **An operator surface, versioned with the data.** The PPI / tactical
  geo / prioritised-track constructs must be specified as part of the
  deliverable, so "operational context" is demonstrated, not asserted.

## Step 1.2 — Key Assumptions Check

Assumptions baked into the demonstration. The ones that change the
answer shape if wrong are flagged ⚠.

- ⚠ **Unclassified proxies are acceptable stand-ins for classified EW
  feeds.** The entire demo rests on this. Civil ADS-B stands in for a
  cooperative-track feed; a synthetic Electronic Order of Battle
  stands in for the real EOB; space-object catalogues and space-weather
  feeds stand in for the RF-environment layer. If JEWOSC needs the demo
  to run against *actual* classified parametrics, this is the wrong
  vehicle and the answer is "evaluate in an accredited enclave." We
  assume the unclassified-proxy framing is what "representative
  scenarios" invites — and we state the synthetic/notional nature
  loudly, everywhere.
- ⚠ **Fusion breadth matters more than any single feed's fidelity.**
  The customer said "complex datasets" (plural) and "fusion." We
  assume a multi-domain fuse (air + space + environment) demonstrates
  maturity better than a deeper single-domain pull. If they actually
  wanted depth in one domain, the scenario set is wrong.
- **Snapshot cadence is enough.** OpenSky is a live snapshot; the space
  catalogue and space-weather feeds are periodic. We assume an hourly
  refresh demonstrates "operational" adequately — JEWOSC's real feeds
  are faster, but the *workflow* is what's under evaluation, not the
  latency.
- **The models are illustrative, and that is a feature not a bug.** The
  emitter parametrics, threat thresholds, and fusion-confidence values
  are notional. We assume a JEWOSC analyst evaluating *maturity* wants
  to see a model they can *reason about and retune*, and that a
  transparent-but-notional model serves that better than an opaque
  "realistic" one.
- **Own-ship reference is a fixed site.** RAF Odiham (51.3762N,
  -1.3086E), inherited from v1. A moving own-ship is a later scenario;
  fixed-site keeps the geometry legible for a first evaluation.
- **English/metric-and-nm mix is fine.** Altitudes in metres (ADS-B
  native), ranges in nautical miles (operator-native). We assume the
  audience reads both.

## Step 1.3 — Factors driving the answer

Underlying real-world drivers of a "yes, this is mature" verdict (not
yet datasets). Grouped under the customer's three named axes.

**Axis A — complex Defence EW datasets**
- **F1. Source-shape coverage.** Does the demo ingest genuinely
  different data shapes — bbox-filtered live JSON arrays, paginated
  catalogue records, periodic environmental time-series — through one
  toolchain?
- **F2. Dimensionality.** Does the fused row carry the high column
  count real EW data does (kinematics + parametrics + geometry +
  derived threat), so the tool is shown holding EW-scale width?

**Axis B — data fusion and modelling**
- **F3. Cross-source correlation.** Are independent feeds actually
  *joined/related* into one picture, rather than shown side by side?
- **F4. Physics-based modelling.** Are real propagation/geometry models
  (great-circle range/bearing/aspect, Friis received power) computed
  in-flow and exposed?
- **F5. Rule-based / decision modelling.** Is there a derived decision
  surface (threat banding, mode elevation, confidence) an analyst can
  inspect and retune?

**Axis C — operational-context presentation**
- **F6. Operator-native views.** Do the presentation constructs match
  how an EW operator actually works (PPI polar, tactical geo,
  prioritised track list, RF de-interleave), not generic BI?
- **F7. Decision-first information hierarchy.** Does the surface answer
  "highest threat → where → what" in that order, with glance-then-drill
  interaction?

**Cross-cutting**
- **F8. Provenance / honesty.** Is the synthetic/notional boundary
  explicit everywhere, so a Defence evaluator trusts the demo's
  framing? For this audience, undeclared synthetic data would sink the
  evaluation faster than a modest feature set.

## Step 1.4 — Indicators (operationalized)

Each indicator is an observable property the *demonstration artifact*
must exhibit. Recency/window is mostly N/A here (this is a capability
demo, not a monitoring dashboard) — the "window" column instead notes
the acceptance grain.

| Id | Factor | Indicator (what the demo must show) | Grain |
|---|---|---|---|
| F1.1 | F1 | ≥3 independent live/periodic feeds of *different* ingestion shapes fused into one deliverable | per-source |
| F1.2 | F1 | At least one live-snapshot feed (air picture) refreshed on schedule | per-run |
| F2.1 | F2 | Fused output row carries ≥25 columns spanning kinematics, RF parametrics, geometry, and derived threat | per-row |
| F3.1 | F3 | Air tracks correlated with a space/RF-environment layer so a single view shows both domains | per-row |
| F3.2 | F3 | Each track fused with an EOB library keyed on inferred emitter class | per-row |
| F4.1 | F4 | Great-circle range / bearing / aspect from a fixed own-ship computed in-flow | per-row |
| F4.2 | F4 | Friis free-space received power (dBm) at own-ship computed from ERP + range + frequency | per-row |
| F5.1 | F5 | Categorical threat_band (Non-hostile→Critical) derived from a documented, inspectable rule set | per-row |
| F5.2 | F5 | fusion_confidence (0..1) exposed so low-confidence inferences are visible | per-row |
| F6.1 | F6 | Dashboard spec includes a PPI polar (own-ship at origin, bearing=clock angle, range=radius) | deliverable |
| F6.2 | F6 | Dashboard spec includes tactical geo + prioritised track list + RF de-interleave (freq×PRI) | deliverable |
| F7.1 | F7 | Presentation ordered highest-threat→location→identity, with select-to-drill actions | deliverable |
| F8.1 | F8 | Synthetic/notional boundary declared in DS description AND on the dashboard surface | deliverable |

## Acceptance criteria

For the demonstration to score GREEN on an indicator:

- **F1.x** — sources must actually differ in shape (not three JSON
  arrays from the same API), and at least one must be live-refreshing.
- **F2.1 / F3.x / F4.x / F5.x** — the named column(s) must be present
  and populated in the produced Hyper, verified by the QA gate, not
  just declared in the spec.
- **F6.x / F7.1** — the dashboard construct must be specified in a
  versioned artifact (`dashboard/` note or `.twb`) that names the
  worksheets and the calcs (PPI_X/PPI_Y, threat_rank), so JEWOSC can
  reproduce it — not just described in prose.
- **F8.1** — the disclaimer text must be in the `output.description`
  string (so the metadata writer pushes it to Server) *and* called out
  as a required dashboard footer in the dashboard artifact.

## Out-of-scope (deliberate)

- **Actual classified parametrics / real EOB.** Explicit non-goal;
  every emitter value is notional. This is the load-bearing disclaimer.
- **Real-time / sub-second cadence.** The feeds are snapshot/periodic;
  a genuine tactical data-link latency demo is a separate, in-enclave
  exercise.
- **Moving own-ship / multi-ship.** Fixed site (RAF Odiham) only.
- **Emitter geolocation / TDOA/FDOA multilateration.** The demo models
  received power at a *known* own-ship from a *known* track position —
  it does not solve the inverse (locating an emitter from intercepts).
  Flagged as the most obvious "next scenario."
- **Live spectrum / SIGINT captures.** No I/Q, no real intercept data.
  RF parametrics come from the synthetic EOB, not measured signals.

## What "good" looks like at the end

A **multi-source fused deliverable** that extends v1 from one feed to a
cross-domain picture, matching the two-DS Embassy/Russia pattern where
it helps:

- **`MOD JEWOSC EW Fusion`** (primary published DS) — one row per
  airborne track in the UK / NW-Europe bbox at snapshot time, fused
  with (a) the synthetic EOB library and (b) a space/RF-environment
  layer (space-object density + space-weather HF-propagation state)
  that contextualises the electromagnetic environment each track sits
  in. All v1 fusion columns retained; environment columns added.
- A **versioned dashboard artifact** (`v2/dashboard/`) specifying the
  five operator constructs (status strip, tactical geo, PPI polar,
  prioritised track list, RF de-interleave), the calcs, the escalation
  colour ramp, and the mandatory synthetic-data footer.

The DS description on Server explicitly names:
- Every source used and its unclassified-proxy role.
- The notional/synthetic nature of all emitter parametrics and threat
  bands (F8.1).
- Any F-indicator that ended RED after 3 passes.
