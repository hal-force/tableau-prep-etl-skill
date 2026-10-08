# Advanced route — Intelligence-style collections planning

The skill offers **two entry routes**:

- **Simplified (one-shot).** You hand the skill a clean ask or a
  spec.json and it produces a `.tfl` + Hyper + optional publish in a
  single pass. Defaults to internal-first source scan, then external.
  Documented in `operator_quickstart.md`.
- **Advanced (collections planning).** You hand the skill a
  decision-driving question and it runs a structured-analytic-techniques
  workflow: refine the question into indicators tied to underlying
  factors, build a collections plan that maps each indicator to the
  data required to address it, then iteratively collect data
  (internal first, external second) over up to three passes —
  declaring any remaining gaps explicitly in the final deliverable's
  description. The output of the advanced route hands off to the
  simplified one-shot route once the collection plan is satisfied
  enough to build a dashboard.

This page documents the advanced route. Pick it when the user has a
**question** rather than a **dataset in mind**, or when answering the
question requires reasoning across multiple data sources that you'd
otherwise have to discover ad-hoc.

## When to use the advanced route

| Signal | Route |
|---|---|
| "Pull GDELT into Tableau" | Simplified — source is named. |
| "Refresh my CSV folder weekly" | Simplified — shape is obvious. |
| "I have a spec.json from last quarter, rerun it" | Simplified. |
| "How exposed are our embassies to political violence?" | Advanced — the data set hasn't been picked yet. |
| "Which suppliers concentrate the most schedule risk?" | Advanced — indicators need to be derived before data is scoped. |
| "What would tell us our hiring pipeline is choking?" | Advanced — the question contains a hypothesis, not a query. |

If the user gives you a question and a partial answer ("I think it's
in the procurement DS, look there"), still run the advanced route
but pre-seed the collections plan with their hint as a candidate
source.

## Workflow

The advanced route adds a **Phase 0.5** that sits between intake and
source planning. The simplified route's Phases 1-11 run unchanged
after Phase 0.5 produces a definitive source list.

```
Question → SAT refinement → Factors → Indicators →
  Collections plan → Iterative collection (≤3 passes, internal-first) →
    Gap declaration → spec.json hand-off → Phases 1-11 (simplified route)
```

### Step 1 — Refine the question (Structured Analytic Techniques)

Treat the user's question as a hypothesis to be **decomposed**, not
a query to be executed. The skill uses a lightweight SAT loop based
on the intelligence community's foundational techniques (the names
matter — they let the user redirect when the chosen technique doesn't
fit):

1. **Question decomposition.** Rewrite the user's prompt into a
   crisp, decision-driving question — one that has a verb, a subject,
   and a horizon. *"How exposed are our embassies?"* becomes *"Which
   US diplomatic posts are at elevated physical-security risk over
   the next 30 days, ranked by composite threat score?"*
2. **Key Assumptions Check.** List the assumptions baked into the
   question and surface the ones that, if wrong, change the answer
   shape. Examples: *"physical security only" (excludes cyber),
   *"future-looking" (so historical incident counts must be
   recency-weighted, not raw totals),* *"post-level granularity, not
   country-level".*
3. **What Would Tell Us?** For each assumption, name the **factor**
   that drives the answer. A factor is the underlying real-world
   thing being measured (proximity of unrest, severity of recent
   incidents, US-actor involvement). A factor is not yet a dataset
   or a column — keep them at the conceptual level.
4. **Indicators of Change.** For each factor, name 1-3 **indicators**
   — observable, measurable signals that move when the factor
   changes. Indicators are the bridge to data: each indicator should
   have a clear answer to *"what column or computation, on what data
   source, would let me see this signal?"* Indicators must be:
   - **Operationalizable** — expressible as a metric or banding.
   - **Recency-aware** — say over what window (last 24h, 7d, 30d).
   - **Falsifiable** — a low value of the indicator should mean
     something definite, not just "we didn't look hard enough".

The output of Step 1 is a small structured artifact:

```
question: "Which US diplomatic posts are at elevated physical-security risk over the next 30 days?"
assumptions:
  - physical security only (not cyber, not financial)
  - post-level granularity
  - recency-weighted, not lifetime counts
factors:
  - F1. Proximity of recent unrest events
  - F2. Severity of recent unrest
  - F3. US-actor involvement
  - F4. Trend (escalating vs cooling)
indicators:
  - F1.1 Count of events within 50mi within 30d
  - F1.2 Min distance of any event within 7d
  - F2.1 Max CAMEO root code in window (mass violence = 20)
  - F2.2 Weighted incident count (severity × recency decay)
  - F3.1 Share of events with Actor1/2 country = USA
  - F4.1 Week-over-week change in F2.2
```

Keep the artifact in `runtime/<run>/sat_brief.md` for audit.

### Step 2 — Draft the collections plan

For every indicator, list the **data required** and **candidate
sources**. Internal sources go first; external sources are the
fallback. Each entry has a clear acceptance criterion (what does the
data need to look like for this indicator to be answerable?).

```
F1.1  Count of events within 50mi within 30d
  data required:
    - event records with lat/lon, event date, severity class
    - post roster with lat/lon (authoritative)
  candidates (in preference order):
    1. INTERNAL: published DS "Diplomatic Posts Master" (if it
       exists on the site — check Phase 0 scan)
    2. INTERNAL: any DS with "embassy" or "post" + "lat/lon" columns
    3. EXTERNAL: state.gov public posts directory (web crawl)
    4. EXTERNAL: GDELT 1.0 events feed for the event side
  acceptance: roster contains post_name + post_country + lat/lon
              for >=N posts; event feed has >=M rows over the last
              30d with non-null lat/lon
```

Two structural rules for the plan:

- **Internal-first is non-negotiable** unless the user explicitly
  says otherwise. The Phase 0 scan is the first thing the
  collections planner consults; if any internal candidate matches
  *any* indicator's data-required spec, surface it to the user
  before reaching for external sources. *"We already have a
  certified DS for X; should we use that?"* is the most common
  unlock and skips a lot of acquisition friction.
- **One indicator → multiple candidates.** Always list at least two
  candidates per indicator when feasible — the second slot is the
  fallback when the first attempt produces unusable data. This is
  what makes the three-pass loop converge instead of stall.

Save the plan to `runtime/<run>/collections_plan.json` and present
it to the user before executing — they may add internal sources you
couldn't see, or rule out external sources for compliance reasons.

### Step 3 — Iterative collection (3-pass cap)

Execute the plan one indicator at a time. Each pass:

1. **Acquire** the top-preference candidate data per indicator —
   internal source via Phase 4 ingest if it's published; external
   via Phase 3 source planner (folder, API, crawl, etc.).
2. **Validate** against the acceptance criterion. Did the data
   actually arrive? Are the columns the indicator needs present
   and populated? Run a small sample-check, not the full pull.
3. **Score** the indicator as one of:
   - **GREEN** — data is present, columns match, acceptance met.
   - **AMBER** — data partially present (e.g. roster exists but
     misses lat/lon for some posts). Move to the next candidate
     for the missing fragment only; don't re-fetch what's already
     GREEN.
   - **RED** — data absent or unusable. Move to the next candidate.

After each pass, you have a per-indicator status table:

```
F1.1   GREEN  internal DS "Diplomatic Posts Master" + GDELT
F1.2   GREEN  same
F2.1   GREEN  GDELT CAMEO root
F2.2   GREEN  derived from F2.1 + window math
F3.1   AMBER  GDELT actor cols present; rate of non-null lower than expected
F4.1   GREEN  derived
```

**Pass cap is three.** If an indicator is still RED after three
passes, stop. Three passes is enough to know the answer for *this
indicator with these candidates*; further iteration produces
diminishing returns and the user should hear about the gap rather
than waiting on more passes.

What "three passes" means concretely:

- Pass 1: try top-preference candidate.
- Pass 2: try next candidate, OR re-shape the indicator if the data
  almost works (e.g. relax window from 30d to 90d).
- Pass 3: try one more candidate, OR substitute a proxy indicator
  if the user pre-approved proxies in the plan.

The skill records the per-pass attempt log in
`runtime/<run>/collections_log.md` so the user can audit what was
tried.

**Expect public sources to fail on the first try.** For a run against
global public sources, plan a fallback for each one before Pass 2
starts. Failures seen in practice:

| Source | Failure | Fallback |
|---|---|---|
| Wikipedia API | 429 rate limit | Backoff, then Wikidata (P625 for coordinates) |
| OpenStreetMap Overpass | 504 on area-filtered queries | One flat tag query, then filter locally |
| Akamai-fronted sites (e.g. usembassy.gov) | 403 to plain `requests` | `curl_cffi` with browser TLS impersonation |
| UCDP GED API | 401 without a token | Public candidate-events CSV, with its lag stated |
| GDACS | 400 on the MAP endpoint | Paged SEARCH endpoint |
| Keyed sources (ACLED) | No key in the environment | Build and schema-test the loader anyway. Record `SKIPPED_NO_CREDENTIALS` and mark the indicator RED |

Run acquisition as a **pre-step** that writes a `cache/` directory and an
`acquisition_manifest.json` (one row per fetch: URL, HTTP status, rows
kept, fallback used). Don't run it inside the script nodes. The TabPy
container then needs no network, and the manifest can be published as its
own extract so every number traces back to a fetch.

### Step 3b — Calibrate before accepting a score

When an indicator is built from **machine-coded media events** (GDELT,
or any news-derived event feed), the first full run is almost always
miscalibrated. The feed measures media attention, and that's not the
same as events on the ground. Check the top of the ranking against
common sense before Step 4. The corrections that were needed for a
post-level GDELT threat score:

1. **Dateline inflation.** Media hubs pick up coverage of distant wars
   that is filed from them. Where neither actor is from the host country,
   down-weight the event (×0.25).
2. **Media volume.** Hubs produce more of every event class. Normalise
   per location by `sqrt(median_volume / volume)`, clipped to `[0.2, 1]`.
   This needs an all-event volume count kept alongside the filtered
   threat events.
3. **Uncorroborated categories.** CAMEO 19x ("fight") is often figurative.
   Down-weight it (×0.1) unless an independent source (UCDP, the
   advisory) corroborates it.
4. **Aggregation.** A noisy-OR across categories rewards breadth over
   intensity. `0.7 × max + 0.3 × mean(top 3)` ranked conflict zones above
   busy capitals.
5. **Frozen scale.** Fix saturation constants (e.g. K per category at
   about p95 of the first accepted run). If they move each refresh, the
   trend is an artefact of re-normalisation.
6. **Check the codebook.** Verify reused code→label maps against the
   source codebook. Inherited CAMEO labels had 175, 176 and 133-138
   wrong.
7. **Language.** GDELT 1.0 is English-only. Declare the under-coverage of
   non-English-media locations as a gap.

Free-text matching on official text (advisory posture flags) needs the
same scrutiny. "All U.S. consulates … have suspended operations"
matched an *embassy*-suspension pattern. Keep distinct flags for
distinct postures, and quote the matched sentence into the output so a
reader can audit it.

Record each correction in `collections_log.md` with the before/after
effect.

### Step 4 — Gap declaration

For every indicator that ended RED (or AMBER and the user accepts
it), the gap must be **explicit in the published DS description**.
Not in a sidecar doc, not in a slide deck — in the description that
the metadata writer pushes to the data source on Tableau Server, so
the dashboard reader sees it.

Template:

```
This data source addresses {question} via {N} of {M} planned
indicators. Gaps:

- {indicator name}: {what was attempted across passes 1-3, why it
  failed}. Effect on the answer: {what conclusions are weakened or
  unsupported by this gap}.
- ...

To fill these gaps, the most likely next steps are:
- {concrete suggestion 1, e.g. "publish an authoritative post
  roster as an internal DS"}
- {concrete suggestion 2}
```

**Where the gap text lives.** The validator does NOT accept a
top-level `gaps_addendum` output field. Fold the verbatim gap
declaration into the `output.description` string in `spec.json` —
the metadata writer's DS-level description prompt incorporates the
description as-is, so the gap text reaches the site that way. The
authoritative artifact for review remains `collections_log.md`
alongside the run.

Two non-negotiable rules for gap declaration:

- **Be specific.** *"We couldn't find good data"* is useless.
  *"Phase 0 scan found no internal posts roster; state.gov crawl
  returned 188 posts but only 142 had geocodes; we used those 142.
  The 46 posts without geocodes are excluded from the per-post
  rollup"* is what the dashboard reader needs.
- **Be load-bearing about effect.** If the gap means a metric is
  biased low, say so. If it means a category is unmeasured, say so.
  Dashboards built on this DS should not silently misattribute.

### Step 5 — Hand off to the simplified route

Once the collections plan is satisfied (every indicator GREEN, or
AMBER/RED gaps documented), the planner emits a normal `spec.json`
that the simplified route consumes. The advanced route's artifact
trail (`sat_brief.md`, `collections_plan.json`, `collections_log.md`)
lives alongside the run for audit and gets archived under
`flows/<flow>/v<N>/` along with the .tfl on a successful publish.

**Server-publish is the default.** Step 5's `spec.json` MUST include a
`server_publish` block targeting the Prep Agent (or operator-named)
parent project with the next sequential `NN - Title` child-project
name. The handed-off run command always uses
`--publish --auto-create-project` unless the operator explicitly asks
for local-only. The deliverable is a Server-side asset, not a local
Hyper.

**`output.source` is a string.** Route an output to a specific
upstream by setting `"source": "<name>"` where `<name>` is either a
transformation's name or one of `spec.sources[*].name`. The validator
rejects the dict form `{"transformation": "..."}`. Sibling outputs
hanging off un-joined source branches resolve via the source-name
lookup; outputs that name a joined branch resolve to the join tail.

From here, Phases 1-11 of the simplified route apply unchanged.

**When the plan outgrows `run_loop`.** The spec templates cover one
source → transforms → outputs, or native joins of branches. Some plans
can't be expressed that way: a multi-source *spatial* union, scoring
shared across several outputs, or acquisition that has to run before
the flow. For those, build with the multi-view builder pattern
(`examples/synthetic_multiview.md`): one trigger fans out to N
`script → hyper` branches via `tflb_lib.topology.add_branch`, and every
script imports one shared core module. Then:

- Still emit `spec.json` from the plan, for the record (sources, model
  constants, outputs with gap-bearing descriptions). Archive it with the
  SAT brief and logs, and say in the README that it documents the build
  rather than driving it.
- Put a QA gate in front of prep-cli that checks the model, not just the
  schemas: radius bounds, key resolution across extracts, the indicator
  count against the plan, and sample = full when there's a test variant.
- Publish the extracts as DSs with the same gap text in each description,
  scoped to the indicators that extract depends on.

Worked example: `examples/us_post_threat_picture.md`.

## Internal-first preference — what counts as internal?

The user's stated preference is internal sources before external,
which the planner enforces in three places:

1. **Phase 0 scan** runs against the user's connected Tableau Server
   site and surfaces published data sources by topic-match. Always
   the first acquisition attempt for any indicator. See
   `metadata_api.md`.
2. **Internal warehouse / database connections.** When the spec
   mentions a named connection (`native_connector` source kind), it
   counts as internal even if it's not a published DS — query
   against it before reaching for an external API of the same
   topic.
3. **Local files the user already has.** A `local_folder` source
   the user supplies up front is internal-tier.

External is everything else: REST/GraphQL APIs, web crawls,
public-data ZIPs, PKI endpoints reaching outside the org. External
sources require explicit acquisition steps and (per the project's
host-trust policy) a first-time-host approval prompt.

If the user wants to *invert* this preference — e.g. for a
greenfield demo against a public dataset where the internal scan
will be noisy — they say so explicitly and the planner records
the inversion in `collections_plan.json`.

## What the user gets at the end

The advanced route's final deliverable is a normal Tableau Prep
flow + Hyper + (optionally) published DS, identical in shape to
what the simplified route produces. The differences are:

- The DS description on Tableau Server contains the explicit gap
  declaration.
- `flows/<flow>/v<N>/` carries the SAT brief and collections log
  alongside the .tfl.
- The dashboard built on top of the DS can reference indicators by
  name (they map cleanly to columns), so the question-to-data
  trace is preserved.

## When the advanced route is overkill

Don't run the advanced route when:

- The user's request is already a clean spec or a clear "do X
  against Y" instruction.
- The data set is named and the question is just "load it".
- Time pressure precludes a planning pass and the user wants a
  best-effort one-shot.

The advanced route adds ~10-20 min of planning + collection time
before any code runs. That's worth it for ambiguous, high-stakes
questions. It's overhead for "rebuild the GDELT flow with a wider
window".

## Quick command-line shape

The advanced route is **not** a `run_loop.py` flag — there is no
`--route` or `--question` argument. It is a manual, agent-driven
methodology: work through the SAT refinement → factors → indicators →
collections plan → acquisition passes above (with a human in the loop),
and the product is a `spec.json`. You then hand that spec to the
simplified route, which is the only automated entry point:

```bash
# 1. Advanced route (this document): produce a collections-plan spec.json
#    by hand — e.g. for the question "Which US diplomatic posts are at
#    elevated physical-security risk over the next 30 days?" — and save it.

# 2. Simplified route runs that spec (the standard one-shot pipeline):
python3 -m skill.scripts.run_loop \
    --spec flows/embassy_threat_monitor/v1/spec.json \
    --flow-name embassy_threat_monitor \
    --publish --auto-create-project
```

Wiring the advanced route to an actual `--route`/`--question` flag (and
automating Phase 0.5) is roadmap work; today the phase is executed by
the agent, not by `run_loop.py`.

## Related references

- `operator_quickstart.md` — simplified route + environment setup.
- `metadata_api.md` — Phase 0 internal scan (load-bearing for
  internal-first acquisition).
- `server_publishing.md` — DS-level description path used to
  publish the gap declaration.
- `SKILL.md` — full phase reference; advanced route is Phase 0.5
  ahead of the standard pipeline.
- `examples/us_post_threat_picture.md` — the full route on a global,
  multi-source question: 14 indicators, three passes, calibration, a
  multi-view build with a sample variant, and gap text in the published DSs.
