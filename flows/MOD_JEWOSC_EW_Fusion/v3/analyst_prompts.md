# JEWOSC analyst prompts — MCP / natural-language search

Drop these into an MCP natural-language search over the published data
source **`MOD JEWOSC EW Fusion v3`** (`Prep Agent / 31 - MOD JEWOSC EW
Fusion Demo`, LUID `6f0bf957-1c92-4410-8a74-9bf8fc586656`). They are
grounded in the DS's real column names + the column descriptions
applied at publish, so an NL query planner (VizQL Data Service / Tableau
Agent / "Ask Data"-style) can resolve each field.

> All data is SYNTHETIC / NOTIONAL — an unclassified JEWOSC demo. These
> prompts exercise the *workflow*, not real threat intelligence.

> **Catalog lag:** if a query can't find fields in the first ~10–30 min
> after publish, Tableau Cloud's Catalog index is still catching up — the
> descriptions are on the DS (verified via .tds), the semantic index just
> lags. Retry shortly.

---

## 1. Reprogramming triggers — the core EWOS mission
- Show every intercept where `is_reprogram_trigger` is true, with measured frequency, PRI, pulse width, band, sensor, and detect time.
- How many unknown cuts (`match_quality` = unknown) are there, broken down by `band` and `sensor_id`? Which sensor sees the most?
- List unknown cuts within 100 nautical miles range (`range_nm`) of own-ship, sorted by range — these are the priority reprogramming candidates.
- **Split the reprogramming queue by `trigger_cause`** — how many are `novel_emitter` (genuinely new signals) vs `library_ambiguity` (de-interleave couldn't separate) vs `correlator_miss` (correlator failed on a known emitter)? This is the workload breakdown, not one conflated count.
- Of the `novel_emitter` cuts only, show measured parametrics, band, sensor, and `range_nm` — these are the true new-signal reprogramming candidates.

## 1a. Correlator calibration — the confusion matrix
- Cross-tabulate `correlator_outcome` into a matrix: ground-truth class (rows) vs correlator call (columns). Where does the correlator disagree with truth?
- How many cuts are `truth:ambiguous / call:unknown` — genuinely library-resolvable signals the gate dumped into "unknown"? (This is the calibration gap: widen the second-distance ratio and these move off the reprogramming queue.)
- What is the false-trigger count (`truth:clean / call:unknown`) versus the true-novel-emitter count (`truth:unknown / call:unknown`)?

## 1b. Temporal picture (detect_time_iso now a real timestamp)
- Show intercept volume by hour of `detect_time_iso` — when is collection densest?
- List the most recent 20 intercepts by `detect_time_iso`, with emitter, lethality, and range.
- Break `is_reprogram_trigger` counts down by hour — are new signals clustering in a particular window?

## 2. Threat triage & prioritisation
- Rank matched emitters by `lib_threat_priority` descending; show `lib_nato_name`, `lib_system_type`, `lib_lethality`, `lib_assoc_weapon`, and the count of intercepts on each.
- Show all intercepts matched to `lib_lethality` = critical, with `eob_primary_affiliation`, `range_nm`, and `bearing_deg`.
- Which critical- or high-lethality emitters were detected inside their weapon's reach — where `range_nm` is within `lib_max_range_km` converted to nautical miles?

## 3. Match confidence & ambiguity
- List all ambiguous cuts (`match_quality` = ambiguous), showing `match_distance` versus `match_second_distance` — where is the de-interleave weakest?
- For matched cuts, show the 20 loosest matches (highest `match_distance` still under tolerance).
- Compare measured vs library parametrics for matched cuts: `meas_freq_ghz` vs `lib_centre_freq_ghz`, `meas_pri_us` vs `lib_pri_us`, `meas_pw_us` vs `lib_pw_us`. Flag the biggest deltas.

## 4. Mission-data-file coverage gaps
- Which matched emitters have the largest `coverage_gap_count`? Show `lib_nato_name`, `lib_lethality`, and `uncovered_platforms`.
- For high- and critical-lethality emitters, which platforms are blind to them (`uncovered_platforms`)? This is the MDF reprogramming priority list.
- Cross-tabulate `coverage_gap_count` against `lib_lethality` — are our worst coverage gaps on the most dangerous emitters?

## 5. Electronic Order of Battle & affiliation
- Break intercepts down by `eob_primary_affiliation` (RED / NEUTRAL / BLUE). For RED, show emitter NATO name, `eob_site_count`, and `eob_confirmed_count`.
- Show emitters where `eob_confirmed_count` is 0 but intercepts still matched to them — detections with no confirmed site on file.
- Which emitters have the most known sites (`eob_site_count`), and what is their affiliation spread (`eob_affiliations`)?
- **EOB contradiction set:** which matched emitters have `eob_active_count` = 0 but `eob_site_count` > 0 — assessed inactive by the Order of Battle, yet we are actively collecting them? Show NATO name, site/confirmed/active counts, and intercept count. (These 4 emitters are EOB-update triggers, distinct from reprogramming triggers.)

## 6. Own-ship tactical picture
- Show the closest 15 threats to own-ship by `range_nm`, with `bearing_deg`, `lib_nato_name`, `lib_lethality`, and `match_quality`.
- Which bearing sector (`bearing_deg` band) has the highest concentration of critical-lethality emitters?
- Are there any critical- or high-lethality matched emitters within 40 nautical miles of `own_ship_label`?

## 7. Sensor / collection performance
- Per `sensor_id`, what fraction of cuts resolve to matched vs ambiguous vs unknown? Which sensor produces the cleanest de-interleave?
- Distribution of `snr_db` by `match_quality` — do low-SNR cuts drive the unknowns?

---

### Note for the live demo
These double as the LLM-grounding seed set for the interactive demo
(see `dashboard/demo_guide.md`). Each maps to a real field, so when the
user free-types a variant ("what can't my Typhoon see?" → `uncovered_platforms`
filtered to a platform), the model has a concrete column to ground to.
