# Example: advanced route, end to end (threats to staff at every US post)

User request:

> Collect a series of sources to help me understand threats to embassy staff
> globally, for every US embassy and consulate, within 50 miles.

This is a **question**, not a dataset, so it runs the advanced collections route
(`reference/advanced_collections_route.md`). The request names no source, the
population (every post) has to be built first, and the answer needs several
threat families on one scale. This page records what the route produced and
which problems came up, so the next multi-source question run can skip them.

## What this exercises

- SAT refinement → 8 factors → 14 indicators → collections plan
- Three acquisition passes, INTERNAL first, with failure-and-fallback per source
- Calibration of machine-coded media events before any score is accepted
- A plan the `run_loop` spec templates can't express: multi-source spatial union
  with shared scoring, built with the multi-view builder instead
- A sample test variant whose scores and ranks must equal the full run
- A QA gate before prep-cli, and gap text carried verbatim into DS descriptions

## Step 1: question, factors, indicators

Refined question: *For every US embassy, consulate and diplomatic mission, what
physical threats to US government staff exist within 50 miles of the post, how
severe and how recent are they, are they directed at US persons, and are they
escalating week over week?*

Unit of analysis: post × threat category (seven categories plus an "All" roll-up),
with host-country context. The key assumptions check changed the plan in three
places:

| Assumption | Outcome | What it changed |
|---|---|---|
| A public roster with coordinates exists | Holds (314 posts) | QA fails on any post without coordinates |
| News-coded events track violence near a post | **Only partly**: they track media attention | Calibration step (below) became mandatory |
| An open, global, geocoded crime dataset exists | **Fails** | Street crime declared RED up front, with proxies |

Factors: post baseline, armed conflict, terrorism and targeted violence, civil
unrest, crime / kidnapping / detention, natural hazards, health, official US
posture. Fourteen indicators hang off those factors. Each one lists at least two
candidate sources and an acceptance criterion in `collections_plan.json`.

## Step 3: acquisition passes

**Pass 1 (INTERNAL).** The Metadata API scan found an earlier embassy monitor
(60 curated posts, GDELT only) and a significant-quakes DS. Neither covered the
full roster, so the route reused their *logic* (CAMEO severity, banding) and not
their data. Re-checking the reused CAMEO labels against the codebook turned up
errors. They have since been fixed in `templates/embassy_threat_join.py.j2`.

**Pass 2 (primary external).** Every source below worked only after a fallback.
These are the failures to expect from the same public sources:

| Source | Failure | Fallback that worked |
|---|---|---|
| Wikipedia (post list + coordinates) | 429 rate limit | Backoff, then Wikidata P625 for coordinates |
| OpenStreetMap Overpass (`diplomatic=*`) | 504 on area-filtered query | One flat global tag query, then match to posts locally |
| usembassy.gov post directory | 403 (Akamai) to plain `requests` | `curl_cffi` with browser TLS impersonation |
| UCDP GED API | 401 without a token | Public monthly candidate-events CSV (state the publication lag) |
| GDACS event list | 400 on the MAP endpoint | Paged SEARCH endpoint, with impact polygons fetched per Orange/Red alert |
| GDELT 1.0 daily files | ~115k rows/day, mostly irrelevant | Keep threat CAMEO roots + city-level geocodes within 50 mi only. Download incrementally. Keep an all-event volume count per post for normalisation |
| State Dept advisories | Some areas don't map to a country. Some countries are missing from the feed | Map shared codes with max level + merged flags. Label a missing country "No advisory in feed (posture scored 0)" rather than NaN |

**Pass 3 (gap fill and proxies).** ACLED needs a registered key. The loader is
built and reads `ACLED_EMAIL` / `ACLED_API_KEY` from the environment only. With
no key set, the indicator is RED and recorded as `SKIPPED_NO_CREDENTIALS`.
Street crime has no open global source (OSAC needs authentication; municipal
portals are few and inconsistent). It ends RED, with the advisory crime
indicator and GDELT assault events as proxies.

Final coverage: **GREEN 4, AMBER 8, RED 2.** The acquisition pre-step writes a
`cache/` directory and an `acquisition_manifest.json` (one row per fetch: URL,
status, rows, fallback used). The manifest becomes its own extract, so every
number traces back to a fetch.

## Calibration: the first global run is wrong

The first run ranked London, Paris and New Delhi as war zones. None of these were
code bugs; they come from how media-coded events behave. Fix them before
accepting any score:

1. **Dateline inflation.** Wars are reported from hub cities. Where neither actor
   is from the host country, multiply confidence by 0.25.
2. **Media volume.** Hubs produce more of *every* event class. Normalise per post
   by `sqrt(median_volume / post_volume)`, clipped to `[0.2, 1]`.
3. **Uncorroborated fighting.** Figurative and diplomatic coverage gets coded as
   CAMEO 19x. Multiply GDELT armed conflict by 0.1 unless UCDP or the advisory
   corroborates it.
4. **Compounding.** A noisy-OR across categories let breadth beat intensity, so
   busy capitals outranked conflict zones. Use `0.7 × worst + 0.3 × mean(top 3)`.
5. **Moving scale.** Saturating each category at a per-run percentile
   re-normalises daily, and the trend becomes an artefact. Freeze each category's
   K at about p95 of the first accepted run.
6. **Posture regex false positives.** "All U.S. consulates in Russia have
   suspended operations" matched an embassy-suspension flag. Match embassy
   suspension and consulate suspension separately, and add an explicit "staff
   reduced" flag.

Also state that GDELT 1.0 is English-language only, so Spanish- and
Portuguese-language posts are under-covered.

## Building the flow

`run_loop` spec templates are one source → transforms → outputs, or joins of
branches. This plan is a multi-source spatial union with shared scoring, which
they can't express. It was built with the multi-view builder pattern from
`synthetic_multiview.md`:

```
Trigger (trigger.xlsx)
  ├─ Post Roster script          ─→ 01 Post Roster.hyper            (post_id)
  ├─ Post Threat Events script   ─→ 02 Post Threat Events.hyper     (post_id, fetch_id)
  ├─ Country Context script      ─→ 03 Country Threat Context.hyper (iso2)
  ├─ Post Scorecard script       ─→ 04 Post Threat Scorecard.hyper  (post_id × category)
  ├─ Collection Coverage script  ─→ 05 Collection Coverage.hyper    (indicator_id)
  └─ Acquisition Manifest script ─→ 06 Acquisition Manifest.hyper   (fetch_id)
```

- Every view script imports one core module, which runs the post × event join
  once. It is memoized per profile on an input fingerprint.
- Acquisition is a separate pre-step and not a script node. The read-only TabPy
  container then never needs network, and a failed fetch can't half-write an
  extract.
- `spec.json` is still emitted from the plan, for the record: sources, model
  constants, and outputs with gap-bearing descriptions. It documents the build;
  it doesn't drive it.

## Sample test variant

Each view exposes `build()` and `build_sample()`. The sample `.tfl` (10 posts
spanning the range: active conflict, high-crime, quiet capitals) points
`scriptFunctionName` at `build_sample`. Two things kept the variant honest (see
`tabpy_setup.md`, "Test and production variants"):

- The sample takes its ranks from the global build. The nested call needs a
  re-entrant lock.
- Ranks use `method="min"`. Co-located missions tie, and ordinal ranks broke
  those ties differently in TabPy and on the host.

## QA gate (runs before prep-cli)

Schema matches `get_output_schema` · every post has coordinates · no event is
farther than the radius · every manifest fetch has a status · every event row's
`fetch_id` resolves · scorecard indices in 0-100 (check the "All" row only;
per-category rows legitimately carry NaN post-level columns) · coverage has
exactly the 14 planned indicators · sample scores and ranks equal the global run.

## Publish

Tableau Cloud can't run TabPy script nodes, so the flow is published as an
unscheduled artifact and each extract as a published DS under the next
`Prep Agent / NN - Title` child. Each DS description carries the verbatim gap
text for the indicators it depends on (e.g. the scorecard names I08 street crime
and I14 ACLED, and says a LOW band means little open-source signal, not safety).
Column descriptions are written through the .tds round-trip and checked by
reading them back.
