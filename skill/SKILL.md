---
name: tableau-prep-etl
description: >-
  Build a Tableau Prep flow (.tfl) from a natural-language ETL request.
  Handles local-folder ingestion, REST/GraphQL APIs, native Tableau
  connectors, web-crawl pipelines (Crawl4AI; opt-in — uncomment
  crawl4ai in requirements.txt), and PKI-authenticated
  endpoints. Runs the built flow via `tableau-prep-cli`, verifies the
  produced Hyper against a deterministic QA gate, and optionally
  publishes the flow + a Hyper-backed published data source to Tableau
  Server / Cloud. Output: a working .tfl ready to open in Tableau Prep
  Builder.
  Use when the user asks to: "build a Prep flow that…", "create a Tableau
  ETL pipeline for…", "ingest <data source> into Tableau", "set up an
  ongoing crawl into Prep", or "publish my flow to Tableau Server /
  Cloud".
---

# Tableau Prep ETL Skill

This skill takes a natural-language ETL request and produces a tested
Tableau Prep `.tfl` file. It plans the source acquisition strategy
from the user's request, generates the flow programmatically, runs it
via `tableau-prep-cli`, verifies the produced Hyper against a
deterministic QA gate (schema, null counts, distinct-value bounds),
and emits a final report plus the working `.tfl`.

Optional `--publish` uploads the .tfl and a Hyper-backed published
data source to Tableau Server / Cloud, then round-trips column-level
descriptions through the .tds writer. See `reference/server_publishing.md`.

## When to invoke

The skill is the right tool when a user says things like:

- "Process this folder of PDFs and extract <fields>."
- "Pull GDELT data daily and load into Tableau."
- "Crawl this topic and surface trending entities."
- "Use my ArcGIS server as a data source."
- "Publish this flow + its extract to Tableau Server / Cloud."

It is **not** the right tool for:

- Modifying an existing flow's individual transformations (use Tableau
  Prep Builder directly).
- Conductor schedule introspection / management beyond the
  basic-cadence wiring `--publish` already does.
- Running production ETL ad-hoc (run the produced `.tfl` via
  `tableau-prep-cli` directly).

**Where Prep stops.** Requirements docs (RFIs especially) often bundle
asks that belong to the layer above the extracts. Build the data layer
and say up front which parts sit elsewhere:

- **Real-time / event-driven** — Prep is scheduled or triggered batch;
  an extract is only as fresh as its last run.
- **Interactive what-if** — Prep can bake a fixed set of named
  scenarios (baseline / tasking / surge) as rows; a live
  move-the-slider re-model is a workbook, extension, or app.
- **Alert delivery** — Prep can compute the breach flag; sending the
  notification is Server subscriptions/data-driven alerts or a
  downstream service.
- **Dashboards** — Prep produces `.hyper` / published data sources; a
  workbook draws the views.

When no real source is reachable (classified or PHI systems of
record), build a deterministic synthetic scenario and label it as such:
`reference/examples/synthetic_multiview.md`.

## Routes — Simplified vs Advanced

The skill has two entry routes. Pick the one that matches the user's
ask, not the data shape.

- **Simplified (one-shot).** Default. The user has a known source or
  a spec and wants the .tfl + Hyper + optional publish in a single
  pass. Phase 0 still runs INTERNAL-first; everything after it is
  the straight pipeline below. Cold-start how-to:
  `reference/operator_quickstart.md`.
- **Advanced (collections planning).** The user has a *question*
  rather than a dataset. Inserts a **Phase 0.5** ahead of the
  pipeline: Structured-Analytic-Techniques question refinement →
  factors → indicators → collections plan → up to **three passes**
  of iterative data acquisition (INTERNAL-first, then external) →
  explicit gap declaration for any indicator that ends RED. The
  collections plan then emits a `spec.json` that Phases 1-11 below
  consume unchanged. Full workflow + templates:
  `reference/advanced_collections_route.md`.

The advanced route is a **manual, agent-driven methodology**, not a
`run_loop.py` flag — there is no `--route` or `--question` argument.
To run it, follow `reference/advanced_collections_route.md` by hand
(question → factors → indicators → collections plan → acquisition
passes) until it produces a `spec.json`, then feed that spec to the
simplified route: `python3 -m skill.scripts.run_loop --spec <plan>.json`.
The simplified route is the default and the only automated entry point.

**Internal-first sourcing** applies to both routes — Phase 0 always
runs first unless `--skip-scan` is passed. The advanced route makes
this preference structural: every indicator in the collections plan
lists internal candidates ahead of external ones, and the planner
won't reach for external sources until the INTERNAL scan + any named
warehouse connections are exhausted.

## Workflow

When invoked, the skill walks through these phases. Each phase has a
script under `scripts/`; the skill orchestrates them. The advanced
route's Phase 0.5 is described in
`reference/advanced_collections_route.md`; Phases 0 + 1-11 below run
identically in both routes.

### Phase 0: INTERNAL data scan (`scripts/server_scan.py`)

**Tableau Server INTERNAL data sources are checked first.** Before the
external source planner runs, the skill scans the connected site for
published data sources matching the user's request - re-using a
certified DS already on the site is almost always preferable to
re-acquiring the upstream feed.

The scan uses Tableau's Metadata API (GraphQL at
`/api/metadata/graphql`) and authenticates via the same PAT env vars
the publish step uses. No creds on disk.

When the scan returns candidates, the orchestrator surfaces them to the
user via `AskUserQuestion` and bounces the run back as
`{"status": "needs_user_decision", "candidates": [...]}`. The user
either:

- Picks an existing DS - its luid + project flow into a
  `source.type == "internal_published_ds"` entry on the spec.
- Opts out (`--skip-scan` on rerun) and the planner walks straight
  through to external sources.

The scan is **silently skipped** when:

- `--skip-scan` is passed.
- The spec already has an `internal_published_ds` source (the user
  has already chosen).
- `TABLEAU_SERVER_*` env vars are missing AND no Keychain / secret-tool
  / config-file fallback supplies them.

### Phase 1: Intake (`scripts/intake.py`)

Parse the user's request into a structured `spec.json`. Calls the LLM
gateway (configured via `LLM_GATEWAY_URL` / `LLM_GATEWAY_KEY` /
`LLM_GATEWAY_MODEL`; defaults to `claude-sonnet-4-6`) to extract:

- `sources`: list of source descriptors (type, location, auth).
- `transformations`: list of cleansing / join / pivot / validate steps.
- `outputs`: target outputs (.hyper, published data source, CSV).
- `qa_tier`: `none` | `deterministic` | `llm`.
- `eval_strategy`: `extract_from_source` | `sample_validation` |
  `synthesized` | `user_supplied` | `self_consistency`.
- `deployment`: `local` | `tableau_server`. With `tableau_server`, the
  spec must include a `server_publish` block (project, cadence,
  hour_utc, etc.) and `--publish` triggers the upload via TSC.
- `server_publish.project`: target project name. The publish picker
  will prompt if it doesn't exist; pass `--auto-create-project` to
  pre-authorize creating it.
- `server_publish.parent_project`: optional parent project name (or
  id). When set, `project` is resolved as the child under this
  parent — the project lookup is scoped accordingly, and
  `--auto-create-project` creates the child nested under the
  parent. Used for the Prep Agent demo collection's
  `Prep Agent / 01 - Federal Outlays`-style nested layout.

If confidence is low on any field, the skill asks the user 1–2
clarifying questions before continuing.

### Phase 2: Plan + Confirm

Show the user a one-page summary: source strategy, eval strategy,
output, any flagged risks (PKI auth, OAuth, rate limits). Get approval
before any credentials or data are touched.

### Phase 3: Source Planning (`scripts/source_planner.py`)

For each `spec.sources[*]`, pick a strategy:

| Source type | Strategy |
|---|---|
| `local_folder` | folder-listing input + per-file Script node |
| `local_csv` | a CSV already on disk read via the `LoadCsv`/textscan path. Distinct from `native_connector` (format=csv); honors `extra.csv_schema` / `casts` / `_skip_auto_casts`. Used by the internal-DS extract-download fallback. |
| `native_connector` | `.v1.SqlConnection` / `.v1.LoadCsv` / `.v1.LoadExcel` |
| `rest_api` | `templates/api_caller.py.j2` Python step. Format-aware: `json`, `jsonl/ndjson`, `csv`, `csv_zip`, `csv_index_then_zip`, `arcgis_features`. Honors paginated walks (index, offset, body-side), POST + body, nested envelopes, derived columns, and per-column schema coercion. See `reference/api_caller_knobs.md`. |
| `graphql_api` | `templates/api_caller.py.j2` (GraphQL variant) |
| `web_crawl` | `templates/crawler.py.j2` Crawl4AI step + Prep parameter for query (opt-in — requires `pip install crawl4ai>=0.4` in TabPy's interpreter) |
| `pki_endpoint` | `templates/pki_connector.py.j2` cert-auth Python step |
| `internal_published_ds` | Native Tableau Server input bound to a published DS LUID (no Python step). Resolved at backgrounder run time via the user's site session. |

**Transformation kinds dispatched in `source_planner.py`:**

| Kind | Template | Output shape |
|---|---|---|
| `join` | (planner-emitted `.v2018_2_3.SuperJoin`) | Native Maestro join. Multi-source flows; references `left_branch`/`right_branch` indices. |
| `trend_analysis` | `trend_features.py.j2` + `trend_stats.py.j2` (siblings) | Two outputs: row-level Features (calendar features added) + long-form Stats (per dimension × value × year × month with monthly_count, rolling, YoY, z-score anomalies, lifetime rank). |
| `graph_analysis` | `graph_analyzer.py.j2` | Per-node centralities (degree, betweenness, eigenvector, pagerank, closeness) + Fruchterman-Reingold spring layout x/y. One row per edge endpoint. |
| `eoc_fire_metrics` | `eoc_fire_metrics.py.j2` | EOC analyst metrics for WFIGS/NIFC fire incidents (size_class, growth_band, containment_band, days_since_discovery, region_key, incident_summary). |
| `pii_redaction` | `pii_redactor.py.j2` + `pii_audit.py.j2` (siblings) | Two outputs: row-preserving Redacted (PII masked in place) + long-form Audit (one row per detection, sha256 of original — never the original). |

**Domain-specific transform kinds** (also dispatched in
`source_planner.py`; built for specific demo collections rather than
general use — the template name matches the kind):

| Kind | Template | Output shape |
|---|---|---|
| `ew_fusion` | `ew_fusion.py.j2` | JEWOSC EW: fuse live ADS-B track vectors with a synthetic Electronic Order of Battle. |
| `ew_intercept_fusion` | `ew_intercept_fusion.py.j2` | JEWOSC EW: fuse ELINT/ES intercept "cuts" (measured parametrics) to mission-data-file emitter records. |
| `ew_intercept_match` | `ew_intercept_match.py.j2` | JEWOSC EW: parametric nearest-neighbour MATCH half of the intercept pipeline (modelling only). |
| `embassy_threat_join` | `embassy_threat_join.py.j2` | Spatial join of GDELT events to US diplomatic posts. |
| `embassy_acled_join` | `embassy_acled_join.py.j2` | Spatial join of ACLED events to US diplomatic posts. |
| `embassy_risk_summary` | `embassy_risk_summary.py.j2` | Per-post weighted risk-band roll-up of the embassy event-level pairs. |

### Phase 4: Source Acquisition + Schema Inference

Instantiate the chosen strategy and pull a small sample (≤50 rows /
≤5 records). Derive the canonical output schema from the sample.

### Phase 5: Flow Generation (`scripts/generate_flow.py`)

Render the chosen Jinja templates into `runtime/<run_id>/scripts/*.py`,
then call `tflb_lib.builder.build()` to assemble the `.tfl`. The flow
shape is:

```
input(s) → cleansing step → optional QA reviewer + Statistical Analyst → output
```

#### Multi-source flows (joins in Prep, not Python)

When the spec has more than one source AND `transformations` contains
`{"kind": "join", ...}` entries, `generate_flow.py` emits a
**branched DAG** rather than a linear chain. Each source gets:

- Its own per-branch `branch_<i>/` directory with a unique
  `trigger.xlsx`
- Its own `connections.<id>` entry (`excel-direct`)
- Its own input node (`Input 1`, `Input 2`, …)
- Its own rendered Python script with per-branch suffix
  (`api_caller_b0.py`, `api_caller_b1.py`, …) — without distinct
  filenames, the last render wins for everyone and Maestro fails with
  `InvalidLeftConditionColumnMsg`

Each `transformations.kind == "join"` entry references two branches
by index and a join column:

```json
{"kind": "join", "args": {
  "name": "Grants + Cities",
  "left_branch": 0, "right_branch": 1,
  "on": "city", "join_type": "leftOuter"
}}
```

The planner emits one `.v2018_2_3.SuperJoin` per join. Two invariants
the planner enforces (skip these and Maestro NPEs at compile time):

- `join_type` is normalized to Maestro's `JoinType` enum
  (`inner|left|right|full|notInner|leftOnly|rightOnly`). SQL synonyms
  like `leftOuter` are aliased automatically.
- Edges feeding into the `SuperJoin` set `nextNamespace: "Left"` /
  `"Right"`. Edges out of the join stay `"Default"`.

Chained joins use the convention: each subsequent join sets
`left_branch=0`, because branch 0's tail becomes the previous join's
output id. This produces a left-deep tree:

```
((branch0 ⋈ branch1) ⋈ branch2) ⋈ branch3 …
```

Worked example: `reference/examples/otf_grants_multisource.md`
(three OTF CSVs, two joins, single Hyper output).

### Phase 6: Eval Rig Synthesis (`scripts/synthesize_eval.py`)

Branch by `eval_strategy`:

- `extract_from_source`: parse expected values out of source documents
  (the SF1034 invoice case).
- `sample_validation`: compare against a hand-supplied small CSV.
- `synthesized`: ask the LLM to generate a small expected-output set
  from the spec. Capped at 20 examples.
- `user_supplied`: wire the user's CSV/JSON directly into the holdout
  builder.
- `self_consistency`: run the flow N times, treat consensus as truth
  (deterministic pipelines only).

### Phase 7: Test Loop (`scripts/run_loop.py`)

Bounded verification loop (default 3 iterations). Per iteration:

1. Run `tableau-prep-cli -t flow.tfl`.
2. Verify the produced Hyper against the deterministic QA gate
   (schema conformance, null counts, distinct-value bounds, and any
   spec-declared post-conditions).
3. If verification fails, log the failure detail and re-run (Prep's
   TabPy path is occasionally flaky on cold DNS / large paginated
   fetches — a bounded retry masks that transient noise).
4. Stop as soon as verification passes, or when the iteration cap
   is hit. Closed-loop LLM-proposed refinements are v2 roadmap
   material — this phase does not currently mutate the flow between
   iterations.

### Phase 8: Final Report

Produce `runtime/<run_id>/report.md` with:

- **Attention list**: priority-ordered (invoice_id, issues, recommended action).
- **Suggestion inbox**: deduplicated improvement suggestions across the
  run, keyed by scope (global / submitter / field / agent).
- **Statistical anomalies**: per-submitter / per-field / drift signals.
- **Run manifest**: code signature, model used, timing, error count.

### Phase 9: Output

Hand the user the `.tfl` path + the report path.

### Phase 10: Publish (opt-in only)

**Default is local-only.** Server upload happens only when the user
explicitly opts in. Never write to a server with embedded credentials
in the artifact — auth must come from `TABLEAU_SERVER_{URL,PAT_NAME,
PAT_SECRET,SITE}` env vars at runtime, never from disk.

When the user asks to publish:

1. Pass `--publish`. The orchestrator signs in, lists site projects,
   and either uses `spec.server_publish.project` (if it matches an
   existing project) or returns
   `{"status": "needs_user_decision", "candidates": [...], "near_matches": [...]}`.
2. Surface the candidates to the user via `AskUserQuestion`. Offer:
   - Pick from existing projects (top picks: `near_matches`).
   - Type a different existing project name.
   - Create a new project with the configured name (rerun with
     `--auto-create-project`).
3. After the user picks, update `spec.server_publish.project` and
   re-run with `--publish`.

For published data sources (kind `published_data_source`), the .tfl
emits a `WritePublishedDataSource` node pointing at the same project
as the flow — Tableau backgrounder writes the extract there on each
scheduled run.

### Phase 11: Metadata writer (`scripts/metadata_writer.py`)

After a successful publish, every `published_data_source` output gets
LLM-generated descriptions written back to the site:

- **DS-level description** via REST `PUT /datasources/{luid}` — a 2-4
  sentence catalog entry covering what the data is and what it's
  good for.
- **Per-column descriptions** via .tds XML round-trip — download the
  .tdsx, inject `<column><desc>` elements into the .tds, repack, and
  re-publish with `mode='Overwrite'`. This is the only working write
  path on Tableau Cloud (its Metadata API GraphQL mutations are
  read-only — `updateField`/`updateColumn` return Internal Server
  Errors). One sentence per column, mentioning units / format when
  sample rows make it obvious. See `reference/metadata_api.md`.

**Default: auto-apply.** Pass `--review-metadata` to write the
proposal to `runtime/<run_id>/metadata_<output>.json` and stop without
applying — the orchestrator surfaces it to the user via
`AskUserQuestion`. Approval flow is the same shape as publish:
inspect, then rerun without `--review-metadata` to apply.

The proposal is always saved to disk regardless, so there's an audit
trail of what got pushed to the site.

## Configuration

### Required environment variables

- `LLM_GATEWAY_URL` — full URL ending in `/chat/completions`
- `LLM_GATEWAY_KEY` — bearer token
- `LLM_GATEWAY_MODEL` — model id (default `claude-sonnet-4-6`)
- `LLM_GATEWAY_VERIFY_SSL` — optional; set `false` only for a dev
  gateway with a self-signed cert (default `true`).

### Alternate LLM backends + script-node LLM calls

The gateway above serves every built-in phase (intake, QA reviewer,
metadata writer). When a flow needs an LLM **inside a script node** —
per-row extraction / classification / enrichment on TabPy — or when
you point it at **Cohere Chat API v2** instead of the OpenAI-compatible
gateway, see **`reference/llm_backends.md`**. It covers the two wire
shapes, the reasoning-model thinking-budget trap (bounded-budget
models silently return 0 rows otherwise), per-row concurrency (a
bounded thread pool: ~11 min → ~3 min on 1,298 rows), and call-time key
discovery (`COHERE_API_KEY` env → `~/.tableau-prep-etl/config.json`
`cohere` block, read per call so no TabPy restart is needed). Concurrency
knob: `COHERE_CONCURRENCY` / `DNFSB_LLM_CONCURRENCY` (default 6; drop to
1–2 on trial keys).

### Tableau Server (publish + INTERNAL scan + metadata writer)

All four are required for any operation that talks to the site
(scan, publish, metadata writer). When unset, those phases are
silently skipped and the skill behaves as a local-only build tool.

- `TABLEAU_SERVER_URL` — e.g. `https://<your-pod>.online.tableau.com`
- `TABLEAU_SERVER_PAT_NAME`
- `TABLEAU_SERVER_PAT_SECRET`
- `TABLEAU_SERVER_SITE` — site contentUrl (use `""` for the default
  site on Tableau Server; required on Tableau Cloud)

#### Auto-discovery + secure storage (`scripts/server_creds.py`)

When a spec implies server work (an `internal_published_ds` source, a
`published_data_source` output, or `--publish` on the CLI), Phase 1a
runs **before** any other server-touching phase and tries to populate
those env vars in this order:

1. Already-set env vars (production / CI path — preferred).
2. macOS Keychain via `security find-generic-password` with service
   `tableau-prep-etl` and accounts `{url, pat-name, pat-secret, site}`.
3. Linux libsecret via `secret-tool lookup` (same service/account scheme).
4. `~/.tableau-prep-etl/server.json` (chmod 600 plaintext, local dev only).

If discovery fails, run_loop returns
`{"status": "needs_user_decision", "credentials": {...}}` with a list
of platform-tailored secure-storage options the orchestrator surfaces
via `AskUserQuestion`. The user is **never** asked to type a secret
into the conversation — guidance directs them to OS-native stores
(Keychain on macOS, GNOME Keyring / KWallet on Linux, Credential
Manager on Windows) with copy-paste commands that put values into the
secret store, not into argv or transcripts.

**No creds on disk by default.** Env vars are read at call time and
never persisted alongside the spec. The local plaintext file is
opt-in, chmod 600, and listed last in the suggestion order.

#### Local prep-cli runs of `internal_published_ds` flows

Tableau Prep CLI v2026.1 has a product gap: its `credentials.json`
(`-c <path>`) only accepts `username` / `password` — PATs are
explicitly rejected by the deserializer. To run such flows locally
through prep-cli, store username + password as additional Keychain
entries:

```bash
security add-generic-password -s tableau-prep-etl -a tableau-username -U \
    -w 'YOUR_TABLEAU_USERNAME'
security add-generic-password -s tableau-prep-etl -a tableau-password -U \
    -w 'YOUR_TABLEAU_PASSWORD'
```

`run_loop._run_prep_cli` synthesizes a temp `credentials.json` per
sqlproxy connection in the .tfl, passes it via `-c`, and deletes the
file after the CLI exits regardless of outcome. The synth uses
chmod 600 and never touches the audit log.

PATs remain primary auth for **publish, scan, and metadata writer**
(those code paths use TSC / REST / GraphQL, all of which accept PATs
correctly). The username/password is *only* used for prep-cli's local
verify run when the flow sources from a published DS.

#### CLI usage for credentials

```bash
# Cheap env-only check (used by orchestrators / CI):
python3 -m skill.scripts.server_creds --check

# Full discovery: env -> Keychain -> secret-tool -> file.
python3 -m skill.scripts.server_creds --load

# Print platform-tailored secure-storage setup commands:
python3 -m skill.scripts.server_creds --suggest

# Save to ~/.tableau-prep-etl/server.json (LOCAL DEV ONLY):
python3 -m skill.scripts.server_creds --save \
    --url 'https://...' --pat-name 'name' --pat-secret 'secret' --site 'site'
```

### CLI flags relevant to Phase 0 + Phase 11

- `--skip-scan` — bypass the INTERNAL data scan and fall through
  straight to external sources.
- `--review-metadata` — pause after generating the description
  proposal so the user can review before applying.

### Optional

- `CORPUS_DIR` — input data location (default: `<run_id>/inputs/`)
- `OUTPUTS_DIR` — Hyper output location (default: `<run_id>/outputs/`)
- `TABLEAU_PREP_CLI` — path to tableau-prep-cli binary (default:
  `/Applications/Tableau Prep Builder (Apple silicon) 2026.1.app/Contents/scripts/tableau-prep-cli`)

### System dependencies

- **TabPy** running on `localhost:9099` (or wherever Tableau Prep is
  configured to find Python). See `reference/tabpy_setup.md`.
- **Tesseract** + **Poppler** if any source involves PDF OCR
  (`brew install tesseract poppler`).
- **Tableau Prep CLI** (bundled with Tableau Prep Builder).

## Library: `tflb_lib`

The skill depends on `tflb_lib`, a domain-agnostic Python library for
mutating Tableau Prep `.tfl` JSON. `tflb_lib` lives at the repo root.
The skill's `scripts/lib/__init__.py` adds it to `sys.path`.

`tflb_lib` exposes:

- `make_script_node()`, `make_join_node()`, `make_hyper_node()`,
  `add_edge()`, `new_id()` — node-construction primitives.
- `rewire_input_to_local_excel()` — swap a cloud input for a local file.
- `prune_nodes_by_name()`, `prune_to_keep_set()` — graph mutation.
- `rewrite_script_paths()` — repoint Script nodes per a slot→path map.
- `add_branch()` — generic chain attachment.
- `build()` — top-level read/mutate/write entry point.

See `reference/tfl_format.md` for the `.tfl` JSON shape we mutate.

## Worked examples

See `reference/examples/`:

- `local_folder_etl.md` — the SF1034 invoice case (matches `auto_refine/`).
- `gdelt_pull.md` — online API pull.
- `arcgis_pki.md` — custom PKI Python connector.
- `ongoing_crawl.md` — Crawl4AI + Prep parameter for the query.
- `otf_grants_multisource.md` — three CSVs (grants + 2 concordance files)
  joined natively in Prep with Maestro `SuperJoin` nodes.
- `yrp_crime_trends.md` — YRP ArcGIS occurrence data with the
  `trend_analysis` transformation: per-row temporal + per-dimension
  trend stats (monthly count, YoY, rolling, z-score, lifetime rank,
  is_anomaly) so a single Hyper extract powers both detail and
  dashboard views.
