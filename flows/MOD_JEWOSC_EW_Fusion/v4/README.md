# MOD JEWOSC EW Fusion — v4 (fusion as native Prep join nodes, demo-hardened)

**Same JEWOSC analytic as [v2](../v2/README.md), restructured to
*demonstrate* fusion.** v2 fused the threat library, EOB laydown, and
platform coverage inside a single Python Script node (baked as
literals). That produces the right numbers but hides the fusion — a
reviewer sees one opaque node, not a unification. v3 breaks the
reference sources into **separate Prep input nodes joined natively**,
so the fusion is visible on the canvas as three join steps.

> **⚠ SYNTHETIC / NOTIONAL — NOT operational, NOT classified.** Every
> emitter parametric, the EOB laydown, platform mission-data coverage,
> and all ELINT intercepts are fabricated for an unclassified demo.
> NATO-reporting-name-style designations are for audience resonance
> only. Theatre: Baltic / NATO eastern flank; notional own-ship
> `BLUE-ISR ORBIT ALPHA`. Full disclaimer is baked into the output DS
> description and both script/build headers.

## The honest split: modelling vs fusion

The core question v3 answers cleanly: **what genuinely has to be Python,
and what is a join?**

- **MODELLING (Python, unavoidable).** Correlating a measured cut to
  the threat library is a *nearest-neighbour* search in normalized
  freq/PRI/PW space — the closest emitter, within a tolerance. Nearest
  neighbour is not equality, so it cannot be a native Prep `SuperJoin`.
  This is the one thing that must stay in a Script node. It bakes
  **only the numeric fingerprint** it needs (emitter_id + freq/PRI/PW)
  and emits `emitter_id` as a clean join key, plus match_quality,
  the reprogramming-trigger flag, and own-ship range/bearing.
- **FUSION (native Prep SuperJoins).** Once each intercept carries an
  `emitter_id`, relating it to the reference tables is textbook
  equality-join territory. Three reference sources, each keyed **1:1 on
  emitter_id**, are joined onto the matched intercepts as visible nodes.

```
ELINT Intercepts ─▶ EW Intercept Match ─┐  (Script: fuzzy parametric → emitter_id)
  (local CSV)         (modelling only)   │
                                         ├─▶ ⋈ Threat Library      (SuperJoin on emitter_id)
Threat Library     ──────────────────────┘        │
  (local CSV)                                       ▼
EOB Laydown Rollup ──────────────────────▶ ⋈ EOB Laydown          (SuperJoin on emitter_id)
  (local CSV)                                       │
                                                    ▼
Platform MDF Cov.  ──────────────────────▶ ⋈ Platform Coverage    (SuperJoin on emitter_id)
  (local CSV)                                       │
                                                    ▼
                                    WriteToHyper → "MOD JEWOSC EW Fusion v4"
```

Chained left-deep: `((match ⋈ library) ⋈ eob_rollup) ⋈ coverage`. All
joins are **leftOuter**, so unknown/changed cuts (`emitter_id = ""`)
pass through with NULL enrichment — *a threat with no library record is
itself the reprogramming-trigger signal*, now expressed structurally as
a join miss rather than an if-branch inside Python.

## Sources (four input nodes)
- **`ELINT Intercepts`** — `synthetic_data/intercepts.csv` (500 cuts;
  the refreshable operational feed). Declares its post-read schema via
  `csv_schema`.
- **`Threat Library`** — `synthetic_data/threat_library.csv` (25 rows,
  1 per emitter). Descriptive record: NATO name, system type, band,
  library parametrics (`lib_*`), lethality, associated weapon, priority.
- **`EOB Laydown Rollup`** — `synthetic_data/eob_rollup.csv` (25 rows).
  Per-emitter rollup of the 40-site EOB (site count, primary
  affiliation, confirmed/active counts) — rolled up so the join stays
  1:1 and doesn't fan out the intercept grain.
- **`Platform MDF Coverage`** — `synthetic_data/platform_coverage.csv`
  (25 rows). Per-emitter coverage gap: how many of the 8 BLUE platform
  MDFs recognise the emitter and which are blind to it.

The three reference CSVs are **derived products** built by
`synthetic_data/build_spec.py` from the raw `emitters.csv` /
`eob_sites.csv` / `platforms.csv`. Reference sources deliberately carry
**no `csv_schema`** (LoadCsv infers types) so their columns don't merge
into the match node's declared `INPUT_SCHEMA`.

## Why roll the EOB and coverage up to 1:1?

The raw EOB has 40 sites across 25 emitters (many sites per emitter),
and platform coverage is many-to-many. Joining those raw would
**fan out** the one-row-per-intercept grain (an intercept matched to a
3-site emitter would triple). "Nearest EOB site" is geometry, not
equality — it belongs in the match node, not a join. So v3 rolls the
EOB and coverage up to one row per emitter before the join: the fusion
stays native *and* the grain is preserved. This is the standard Prep
pattern (aggregate to the join grain, then join).

## Output
- `MOD JEWOSC EW Fusion v4` (Hyper locally). **500 rows × 51 columns**
  = 13 passthrough intercept cols + 10 match cols + 14 library + 8 EOB
  rollup + 6 coverage (Maestro keeps the right-side `emitter_id-1/-2/-3`
  duplicate keys; the left `emitter_id` is authoritative). Of the 51, the
  three `emitter_id-*` join-residue keys are **hidden in the published DS**
  → **48 visible fields**. DS description carries the full
  synthetic/notional disclaimer.

## v4 refinements (2026-07-28)
Five demo-hardening changes on top of the v3 fusion structure:
1. **`detect_time_iso` is now a real TIMESTAMP** (was an unparseable
   `...Z[UTC]` string that blocked all date math). The match node strips the
   Java `ZonedDateTime` zone suffix, emits a clean ISO string, and declares
   `prep_datetime()` so the Hyper carries a native timestamp. *Unlocks the
   temporal dimension.* (This was the capability-blocking fix — done first.)
2. **`trigger_cause`** splits the 128-cut reprogram queue by cause:
   **56 `novel_emitter` / 68 `library_ambiguity` / 4 `correlator_miss`** —
   three distinct workloads instead of one conflated number.
3. **`correlator_outcome`** (truth-vs-call confusion-matrix cell) exposes the
   ambiguous-gate miscalibration as a *feature*: the `truth:ambiguous /
   call:unknown = 68` cell is the calibration story, surfaced rather than
   hidden.
4. **`emitter_id-1/-2/-3` hidden** in the published DS (join residue).
5. **EOB-contradiction set** (dashboard view): 4 emitters assessed inactive
   yet actively collected (`eob_active_count=0 AND eob_site_count>0`).

Items 2, 3, 5 are new columns / views documented in `dashboard/demo_guide.md`
(WS6–WS8) and `analyst_prompts.md`.

## Verified locally (TabPy :9099, tableau-prep-cli)
- Flow runs clean; Hyper produced with all joined columns present; 500×51.
- **match_quality: 310 matched / 62 ambiguous / 128 unknown** — matches
  v2 byte-for-byte (identical fingerprint math + tolerance 0.12), so the
  restructure preserved the model exactly.
- **trigger_cause on the 128-cut queue: 56 novel_emitter / 68
  library_ambiguity / 4 correlator_miss.** EOB-contradiction set: **4
  emitters / 46 cuts.** `detect_time_iso` verified as Hyper TIMESTAMP with
  working MIN/MAX aggregation.
- All **310 matched** cuts carry populated library + EOB + coverage
  columns via the joins; all **128 unknown** cuts get NULL enrichment
  through the leftOuter (the trigger signal, now structural).
- 128 reprogramming triggers. Lethality (matched only): 114 low / 94
  high / 80 medium / 55 critical / 29 none. EOB primary affiliation:
  264 RED / 72 NEUTRAL / 27 BLUE / 9 none.
- Full skill test suite: **140 passed** (golden render hashes reblessed
  for the updated `ew_intercept_match.py.j2` template + v3 rendered script).

A representative 5-row spread (critical / high / high-gap / ambiguous /
unknown) is in `sample_output/`. The full 500-row extract is **not**
committed (synthetic EW data stays out of the repo/net per policy).

## What's new in the skill (vs v2)
- **`ew_intercept_match.py.j2`** — the lean modelling template
  (fn `match_intercepts`): fuzzy parametric match + own-ship geometry
  only, emits `emitter_id` as a join key. Sibling to (not replacement
  for) `ew_intercept_fusion.py.j2`; v2 remains valid.
- **`ew_intercept_match` planner dispatch** in `source_planner.py`.
- Reuses the existing native-join path (`{"kind":"join",...}`) and the
  `local_csv` source type — no new join machinery needed.

## Reproduce
```bash
# 1. (re)generate the raw synthetic data + derive ref products + spec
python3 flows/MOD_JEWOSC_EW_Fusion/v4/synthetic_data/generate_synthetic_ew.py
python3 flows/MOD_JEWOSC_EW_Fusion/v4/synthetic_data/build_spec.py

# 2. build + verify locally (TabPy must be up on :9099)
python3 -m skill.scripts.run_loop \
    --spec flows/MOD_JEWOSC_EW_Fusion/v4/spec.json \
    --flow-name MOD_JEWOSC_EW_Fusion_v4 --skip-scan

# self_consistency eval reports mean 0.0 under qa_tier=none (nothing to
# score); the Hyper is ground truth — inspect it directly.
```

`--skip-scan` is required (the INTERNAL scan surfaces unrelated site
DSes otherwise). `qa_tier` is `none` (the match Script node declares its
own schema; the joins pass columns through natively — a Validator would
drop them).

## Published (Tableau Cloud — `usfederaldemos`)
Published 2026-07-28 to **`Prep Agent / 31 - MOD JEWOSC EW Fusion Demo`**.

- **Published data source:** `MOD JEWOSC EW Fusion v4`
  (LUID `35a44b68-03cb-45f0-b473-e64fc8e95835`), 500 rows × 51 cols (48 visible; the three
  `emitter_id-*` join-residue keys hidden).
- **Flow** `MOD JEWOSC EW Fusion v4` (id `0811f5d2-feec-47fe-98a6-e6042f3814c0`)
  + hourly schedule for artifact visibility.
- **Metadata:** DS-level disclaimer + **all 48 visible column descriptions**
  applied via the .tds round-trip + 3 residue keys hidden. Descriptions
  authored directly (no LLM gateway configured) and saved to
  `metadata_applied.json` for audit.

Because v4 has a Script (match) node, it uses the Cloud-friendly path:
run locally → upload the .hyper as the DS → publish the .tfl (the
schedule is a no-op on Cloud for script-bearing flows) → apply column
metadata. See `feedback_cloud_vs_server_execution`.

> **Catalog lag:** column descriptions are authoritative immediately via
> REST/.tds, but Cloud's Catalog index (what an NL/MCP search reads) can
> lag 10–30 min after publish. The DS is queryable at once; the semantic
> search catches up shortly after.

See `analyst_prompts.md` for JEWOSC-analyst NL queries to drop into an
MCP search, and `dashboard/demo_guide.md` for the LLM-grounded demo
dashboard recommendation.
