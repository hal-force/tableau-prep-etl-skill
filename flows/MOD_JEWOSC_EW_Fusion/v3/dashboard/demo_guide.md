# MOD JEWOSC EW Fusion v3 — LLM-grounded demo dashboard guide

A recommended dashboard **for a live demo where an LLM dynamically
grounds itself in the data as the user interacts.** The point of the
demo is not a static ops picture — it is to show that a JEWOSC analyst
can *converse* with a Defence EW dataset in natural language, and that
the LLM answers by grounding to real fields, real rows, and a live
visual, not by hallucinating.

Built on the published data source **`MOD JEWOSC EW Fusion v3`**
(`Prep Agent / 31 - MOD JEWOSC EW Fusion Demo`, LUID
`6f0bf957-1c92-4410-8a74-9bf8fc586656`), whose columns carry the
descriptions the LLM/MCP retriever grounds against. v4 produces 51
columns, of which 48 are visible (the three `emitter_id-*` join-residue
keys are hidden — see §6).

> SYNTHETIC / NOTIONAL — unclassified demo. Keep the disclaimer footer
> on every view (see §7).

---

## 1. The demo thesis: three grounding surfaces

"Dynamically ground as the user interacts" means the LLM is wired to
**three** sources of truth, in priority order. Design the dashboard so
all three stay in lockstep:

1. **Schema grounding** — the column descriptions on the DS. When the
   user asks "which platforms are blind to the SA-N-long shooter?", the
   retriever matches *blind → `uncovered_platforms`*, *SA-N-long →
   `lib_assoc_weapon`*. This is why the metadata write mattered.
2. **Data grounding** — the LLM issues a query (VizQL Data Service /
   Ask Data / an MCP `query_datasource` tool) and answers from the
   returned rows, citing actual values (`INT-0267`, `GRAVE STONE-N`,
   `coverage_gap_count = 4`). Never from memory.
3. **Visual grounding** — the answer *drives the dashboard*: the model
   emits a filter/selection (e.g. `match_quality = unknown`,
   `range_nm < 100`) that the workbook applies, so the user sees the
   spoken answer light up on the scope and map.

The demo lands when the analyst types a question, hears a cited answer,
**and** watches the tactical picture reframe to match — all in one beat.

---

## 2. Layout — decision-first, conversation-alongside

An EW operator asks, in order: *what is the highest threat, where is it
relative to me, what is it?* The panels answer top-down; the assistant
rail runs down the right so talk and picture sit side by side.

```
+----------------------------------------------------------------------+
| STATUS STRIP   Critical:N  Triggers:N  Ambiguous:N  Closest:NN nm     |
+--------------------------------------+-------------------------------+
|                                      |                               |
|   TACTICAL GEO (centre)              |   ASSISTANT RAIL              |
|   map; own-ship * at BLUE-ISR ORBIT  |   - NL question box           |
|   ALPHA (55.10, 18.30);              |   - cited answer (rows/values)|
|   tracks coloured by lib_lethality,  |   - "grounded on: <fields>"   |
|   shaped by match_quality            |   - suggested follow-ups      |
|                                      |   (seed set = analyst_prompts)|
+--------------------------------------+   - [Apply to dashboard] btn  |
|   PPI POLAR (bearing / range rings)  |                               |
+--------------------------------------+-------------------------------+
| PRIORITISED TRACK LIST         |  RF DE-INTERLEAVE (freq x PRI)      |
| sort: lethality, range, gaps   |  measured cut vs library point     |
+--------------------------------------+-------------------------------+
| FOOTER: SYNTHETIC / NOTIONAL disclaimer (mandatory)                  |
+----------------------------------------------------------------------+
```

---

## 3. Worksheets (all on v3 columns)

### WS1 — Status strip (glance layer)
Big-number tiles, escalation order:
- `Critical` = `COUNT(intercept_id)` where `lib_lethality = "critical"`.
- `Reprogram triggers` = `COUNT(intercept_id)` where `is_reprogram_trigger`.
- `New signals` = `COUNT` where `trigger_cause = "novel_emitter"` (56) — the
  honest subset of the trigger count that is *actually* new (see WS6). Lead
  with this rather than the conflated 128.
- `Ambiguous` = `COUNT(intercept_id)` where `match_quality = "ambiguous"`.
- `Unknown / unmatched` = `COUNT` where `match_quality = "unknown"`.
- `EOB contradictions` = `COUNTD(emitter_id)` where `eob_active_count = 0`
  AND `eob_site_count > 0` AND matched (4) — see WS8.
- `Closest active threat` = `MIN(range_nm)` over matched, lethality ≥ medium.
- `Widest MDF gap` = `MAX(coverage_gap_count)`.

### WS2 — Tactical geo (centrepiece)
- Map on `lat` / `lon` (generated lat/lon roles).
- **Colour:** `lib_lethality` (palette in §5).
- **Shape:** `match_quality` (filled = matched, half = ambiguous, hollow
  = unknown) — so an unmatched *trigger* reads as a hollow mark instantly.
- **Own-ship layer:** second marks layer fixed at `55.10, 18.30`, star,
  labelled `own_ship_label`.
- **Tooltip:** `intercept_id`, `lib_nato_name`, `lib_system_type`,
  `match_quality`, `range_nm`, `bearing_deg`, `lib_assoc_weapon`,
  `coverage_gap_count`, `eob_primary_affiliation`.

### WS3 — PPI polar scope (operator-native)
- Own-ship at origin, N-up. `bearing_deg` = angle, `range_nm` = radius.
- Range rings at 50 / 100 / 150 nm. Colour by `lib_lethality`.
- This is the view EW operators read fastest; keep it prominent.

### WS4 — Prioritised track list
- Rows = `intercept_id`. Columns: `lib_nato_name`, `band`,
  `lib_lethality`, `match_quality`, `range_nm`, `bearing_deg`,
  `coverage_gap_count`, `eob_primary_affiliation`.
- Default sort: `lib_threat_priority` desc, then `range_nm` asc.
- Selecting a row filters WS2/WS3 (this is also the surface the
  assistant drives — see §4).

### WS5 — RF de-interleave (the modelling story)
- Scatter: `meas_freq_ghz` (x) × `meas_pri_us` (y), colour `match_quality`.
- Overlay library points from `lib_centre_freq_ghz` × `lib_pri_us` as a
  reference layer. Distance between a cut and its library point *is*
  `match_distance` made visible — shows why unknowns fall out.

### WS6 — Reprogramming queue, split by cause (v4)
The single "128 triggers" number conflates three different workloads.
`trigger_cause` (added by the match node) splits it:
- Bar/tile breakdown of `COUNT(intercept_id)` by `trigger_cause` over
  `is_reprogram_trigger = True`:
  - **`novel_emitter` (56)** — genuinely not in the library. *This* is the
    real new-signal reprogramming workload.
  - **`library_ambiguity` (68)** — resolvable against the library, but the
    de-interleave couldn't separate two close emitters. A tolerance-tuning
    problem, not a new threat.
  - **`correlator_miss` (4)** — truth says a clean library emitter, but the
    correlator failed to match it. A correlator defect.
- The demo line: *"only 56 of the 128 are actually new signals — the other
  72 are correlator/library problems we can fix without a reprogramming
  cycle."* One honest number becomes three actionable ones.

### WS7 — Correlator calibration / confusion matrix (v4)
Turns the known ambiguous-gate defect into a *feature* rather than hiding it
(per the design call: exposing the miscalibration is stronger than papering
over it). `correlator_outcome` encodes each cut's `truth:<class>/call:<quality>`
cell:
- Matrix (heat table): rows = ground-truth class (`clean`/`ambiguous`/
  `unknown`), columns = correlator call (`matched`/`ambiguous`/`unknown`),
  cell = `COUNT(intercept_id)`.
- The diagnostic cell to point at: **`truth:ambiguous / call:unknown = 68`** —
  68 genuinely library-resolvable cuts the gate dumps into "unknown" instead
  of "ambiguous". That single cell *is* the calibration story: widen the
  second-distance ratio and those 68 move from the reprogram queue to the
  de-interleave-review queue.
- Off-diagonal = correlator error; diagonal = correct. `truth:clean/call:unknown
  = 4` are the false triggers; `truth:unknown/call:unknown = 56` are the true
  novel emitters (100% caught — the gate is deliberately biased to never miss
  a genuine unknown, at the cost of the 68 false ambiguous→unknown).

### WS8 — EOB contradiction set (v4)
Four emitters the Order-of-Battle assesses as **inactive** yet we are
**actively collecting** — an intelligence-value discrepancy worth surfacing on
its own. Filter: `match_quality = "matched"` AND `eob_active_count = 0` AND
`eob_site_count > 0` (known sites, none assessed active, but detected).
- Table: `lib_nato_name`, `emitter_id`, `eob_site_count`,
  `eob_confirmed_count`, `eob_active_count`, `COUNT(intercept_id)` as cuts,
  `MIN(range_nm)`.
- Yields **4 emitters / 46 cuts** (BIG BIRD-N, GRILL PAN-N, FLAP LID-N,
  PALM FROND-N). The demo line: *"the EOB says these are cold; our own sensors
  say otherwise — that contradiction is an EOB-update trigger, distinct from a
  reprogramming trigger."* (Note: emitters with `eob_site_count = 0` are a
  coverage GAP, not a contradiction — kept out of this set deliberately.)

---

## 4. The interaction model — how the LLM grounds live

Wire the assistant rail as an MCP client over the published DS. Each
turn runs this loop:

1. **Retrieve** — embed the user's question, match it against the DS
   column descriptions (§1.1). Resolve intent to concrete fields.
   *"what can't my Typhoon see" → `uncovered_platforms` contains
   "PLT-01", grain = emitter.*
2. **Query** — call the MCP `query_datasource` / VizQL Data Service tool
   with an aggregation over those fields. Get real rows back.
3. **Answer with citations** — the model states the answer and cites the
   rows/values it used, and prints **"grounded on: `<field list>`"** so
   the audience sees it is reading the schema, not guessing.
4. **Apply to the visual** — the model emits a filter spec
   (`{match_quality: "unknown", range_nm: "<100"}`). The workbook applies
   it via a parameter/filter action, and WS2/WS3/WS4 reframe. The
   [Apply to dashboard] button makes this explicit and demo-safe (the
   presenter chooses when the picture moves).
5. **Suggest follow-ups** — surface 2–3 next questions from the seed set
   in `analyst_prompts.md`, so a nervous presenter always has a next line.

**Guardrails that make the demo trustworthy (and worth showing):**
- *No-answer honesty:* if retrieval finds no matching field, the model
  says "that isn't in this dataset" rather than inventing one — a strong
  moment to demo against an EW audience wary of hallucination.
- *Citation always on:* every numeric claim links to the query result.
- *Synthetic reminder:* the system prompt states the data is notional so
  the model never implies real-world intelligence.

### A scripted 90-second opener
1. *"How many reprogramming triggers do we have, and where?"* → count of
   `is_reprogram_trigger`; hollow marks light up on WS2.
2. *"Of those, which are within 100 miles of own-ship?"* → adds
   `range_nm < 100`; scope zooms to the close ones.
3. *"What's the most lethal emitter my platforms can't see?"* → joins the
   analyst's mental model of *lethality* (`lib_lethality`) + *coverage*
   (`uncovered_platforms`) — the payoff line: **the LLM answers a fusion
   question because the fusion already happened in Prep.**

That third question is the whole demo: it only works because v3 fused
the threat library, EOB, and MDF coverage into one row-per-intercept
surface. The LLM is impressive; the *fused data model under it* is why
the answer is correct.

---

## 5. Colour & shape

- **`lib_lethality` (sequential threat ramp):** none `#5A6B7B` · low
  `#3C8DBC` · medium `#F0AD4E` · high `#E8743B` · critical `#D9302A`.
  Unknown/unmatched (null lethality) → neutral `#8A8A8A` so triggers
  read as "unresolved", not "safe".
- **`match_quality` (shape on WS2, colour on WS5):** matched = filled ●,
  ambiguous = half ◐, unknown = hollow ○.
- **`eob_primary_affiliation`:** RED `#D9302A`, NEUTRAL `#B0B0B0`, BLUE
  `#3C8DBC`, NONE hollow.

---

## 6. Calculations to pre-build (so the LLM can reference them)
- `in_weapon_reach` = `range_nm <= [lib_max_range_km] / 1.852` — is the
  intercept inside the emitter's notional reach? (v3 leaves WEZ to the
  viz layer deliberately; this is the calc.)
- `threat_score` = `[lib_threat_priority] * IIF([is_reprogram_trigger],1.5,1)`
  — nudge unmatched cuts up the list.
- `bearing_sector` = `ROUND([bearing_deg]/45)*45` — for "which sector"
  questions.
- `lethality_rank` = map none→0 … critical→4, for sorting/filtering.
- `is_eob_contradiction` = `[match_quality]="matched" AND [eob_active_count]=0
  AND [eob_site_count]>0` — the WS8 filter as a reusable boolean (4 emitters).
- `detect_date` = `DATE([detect_time_iso])` and `detect_hour` =
  `DATEPART('hour',[detect_time_iso])` — now that `detect_time_iso` is a real
  TIMESTAMP (v4 fix), these enable the temporal dimension: time-of-day
  intercept density, "cuts in the last 6 hours", trend-over-window. This was
  impossible in v3 when the column was an unparseable `...Z[UTC]` string.

Expose these as named fields so an NL query ("show threats in reach")
resolves to a real calculated field rather than reconstructing the math.

**Hidden fields (v4):** `emitter_id-1`, `emitter_id-2`, `emitter_id-3` are
join-residue duplicate keys (Maestro auto-renames the right-side key on each
of the three chained joins). They carry no analytic value and are hidden in
the published DS, so they don't clutter the data pane or the LLM's field
list. The authoritative key is `emitter_id`.

---

## 7. Mandatory footer
Every view carries: *"SYNTHETIC / NOTIONAL demonstration data — NOT
operational, NOT classified. NATO-reporting-name-style designations and
all parametrics are fabricated for a UK MoD JEWOSC maturity-evaluation
demo of Tableau + agentic Prep ETL."* Matches the DS description.

---

## 8. Build order for the demo
1. Connect a workbook to the published DS; confirm the visible fields (48
   after the 3 join-residue keys are hidden) + their descriptions appear
   in the data pane.
2. Build WS1–WS8; wire WS4 selection → WS2/WS3 filter actions. WS6–WS8
   (cause split, calibration matrix, EOB contradictions) can sit on a
   second "analyst / calibration" tab behind the tactical picture.
3. Stand up the assistant rail as an MCP client (schema + query +
   filter-emit tools). Seed follow-ups from `analyst_prompts.md`.
4. Rehearse the §4 opener. Confirm the [Apply to dashboard] path moves
   the picture. Confirm a deliberately out-of-scope question ("what's the
   fuel state?") produces the honest no-answer.
5. Keep the footer on. Keep the story straight: **Prep did the fusion;
   the LLM makes it conversational.**
