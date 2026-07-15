# tableau-prep-etl-skill

A Claude Code skill that takes a natural-language ETL request and
produces a tested, refined Tableau Prep `.tfl` flow. Publishes flows
+ data sources + column metadata to Tableau Server / Cloud.

## What's in the box

```
tableau-prep-etl-skill/
├── tflb_lib/                 # domain-agnostic .tfl JSON mutation library
│   ├── nodes.py              # make_script_node, make_join_node, …
│   ├── inputs.py             # rewire_input_to_local_excel
│   ├── topology.py           # prune_nodes_by_name, rewrite_script_paths
│   ├── builder.py            # build() top-level read/mutate/write
│   └── publishing.py         # PAT auth, project/schedule wiring (TSC)
│
├── skill/                    # the Claude Code skill
│   ├── SKILL.md              # frontmatter + workflow spec
│   ├── scripts/              # intake, source_planner, generate_flow, run_loop, etc.
│   ├── templates/            # Jinja templates for connector / api_caller /
│   │                         #   crawler / trend_features / eoc_fire_metrics /
│   │                         #   graph_analyzer / etc.
│   └── reference/            # tfl_format, tabpy_setup, server_publishing,
│                             #   metadata_api, examples
│
└── flows/                    # archived per-flow artifacts (cred-scrubbed)
    ├── otf_grants/v1/
    ├── us_wildfires_eoc/v1/
    ├── us_grid_network/v1/
    └── gdelt_global/v1/
```

## First-run setup

### 1. Clone and link

```sh
git clone https://github.com/hal-force/tableau-prep-etl-skill.git
cd tableau-prep-etl-skill
ln -s "$PWD/skill" ~/.claude/skills/tableau-prep-etl
```

The symlink lets Claude Code discover the skill while the canonical
source stays in this repo for version control.

### 2. Python deps

The skill code itself runs in your project's Python (3.10+):

```sh
pip install -r requirements.txt
```

**Separately**, TabPy uses its own interpreter for script-node
execution. Install the same deps into TabPy's Python — see
`skill/reference/tabpy_setup.md` for the exact paths and the
canonical recipe.

### 3. TabPy on :9099 (required for any flow with script nodes)

Almost every flow this skill produces has script nodes (api_caller,
trend_features, graph_analyzer, etc.). prep-cli's auth path to TabPy
is broken on recent macOS builds. The working recipe is unauth TabPy
on port 9099 with a 600-second evaluate timeout:

```sh
cat > /tmp/tabpy_smoke.conf <<'EOF'
[TabPy]
TABPY_PORT = 9099
TABPY_EVALUATE_ENABLE = true
TABPY_EVALUATE_TIMEOUT = 600
EOF

/Library/Frameworks/Python.framework/Versions/3.13/bin/tabpy \
    --config=/tmp/tabpy_smoke.conf --disable-auth-warning &
```

Then point prep-cli at it:

```sh
cat > "$HOME/Documents/My Tableau Prep Repository/Command Line Repository/Credentials/pythonSupport.json" <<'EOF'
{"host":"localhost","port":"9099","username":"","password":"","requireSsl":"no","sslCertificate":""}
EOF
```

Verify: `curl -s http://localhost:9099/info | head` should return JSON.
**Don't skip the 600s timeout** — graph_analyzer on ≥10k edges and
api_caller on big ArcGIS pulls both blow past the 30s default.

### 4. Tableau Server / Cloud credentials

If you want to publish flows / data sources / metadata, the skill
needs a Personal Access Token (NOT a password — Cloud's MFA breaks
username/password auth). On macOS, store them in Keychain via:

```sh
python3 -m skill.scripts.server_creds --load
```

The discovery walks env vars → macOS Keychain → Linux libsecret →
`~/.tableau-prep-etl/server.json` (chmod 600 plaintext, dev only).
On first run, it saves what it finds in Keychain for future shells:

```sh
source ~/.tableau-prep-etl/load_env.sh   # exports TABLEAU_SERVER_*
```

Required env vars (any one of these paths sets them):

```
TABLEAU_SERVER_URL          # e.g. https://prod-useast-a.online.tableau.com
TABLEAU_SERVER_PAT_NAME
TABLEAU_SERVER_PAT_SECRET
TABLEAU_SERVER_SITE         # site contentUrl ("" for default site on Server)
```

### 5. LLM gateway (for intake + metadata generation)

Intake parses natural-language requests into spec.json via an LLM
gateway. Production uses `claude-sonnet-4-6`. Three ways to set it
up:

```sh
# Option A: env vars (production)
export LLM_GATEWAY_URL='https://your-gateway/chat/completions'
export LLM_GATEWAY_KEY='<bearer token>'
export LLM_GATEWAY_MODEL='claude-sonnet-4-6'

# Option B: local-only dev config
python3 -m skill.scripts.llm_config   # interactive; writes ~/.tableau-prep-etl/config.json

# Option C: skip intake entirely
python3 -m skill.scripts.run_loop --spec runtime/specs/<your_flow>.json
```

If no gateway is configured, intake-driven runs fail with a clear
"LLM gateway not configured" message; pre-built specs (Option C)
work without a gateway. Metadata generation also needs the gateway,
but the .tds-roundtrip *apply* path works without one — you can
hand-author descriptions and call `apply_descriptions(...)` directly.

### 6. Optional: PDF OCR deps

Required only if a flow ingests PDFs:

```sh
brew install tesseract poppler
```

### 7. macOS Tableau Prep CLI path

Default in `run_loop.py` is the standard macOS install location. Override
if yours is different:

```sh
export TABLEAU_PREP_CLI='/Applications/Tableau Prep Builder (Apple silicon) 2026.1.app/Contents/scripts/tableau-prep-cli'
```

## Use

### From Claude Code

```
/tableau-prep-etl <your request>
```

Examples:

- "Process this folder of PDFs and extract Standard Form 1034 fields."
- "Pull GDELT events for the US daily into a Hyper extract."
- "Crawl news about <topic> ongoingly. Topic should be configurable
  from the dashboard."
- "Get parcel data from my ArcGIS server (PKI auth) and load into Tableau."

### Direct CLI

```sh
# Build + verify locally (no publish):
python3 -m skill.scripts.run_loop --spec runtime/specs/otf_grants.json \
    --flow-name otf_grants --skip-scan

# Publish to server (auto-creates project if missing):
python3 -m skill.scripts.run_loop --spec runtime/specs/otf_grants.json \
    --flow-name otf_grants --skip-scan --publish --auto-create-project
```

Flags:

- `--spec PATH`: load a hand-authored spec.json (skip intake / LLM).
- `--flow-name NAME`: groups runs under `runtime/<flow_name>/<run_id>/`.
- `--skip-scan`: skip the Phase 0 INTERNAL site scan (use when you
  already know the source you want).
- `--skip-cli`: just generate the .tfl + scripts; don't run prep-cli.
  Useful for CI / structural smoke tests on machines without prep-cli.
- `--publish`: upload the .tfl + schedule it. Requires the env vars
  in step 4.
- `--auto-create-project`: pre-authorize creating the configured
  project if missing.
- `--review-metadata`: stop the metadata writer after generating
  proposals — surface to the user before push.

## Authoring a spec from scratch (no LLM gateway needed)

Most users start by copying the closest archived spec and editing.
The full path with no LLM gateway / no `/tableau-prep-etl` invocation:

```sh
# 1. Pick the closest archive (see table below). Trend by date? Copy
#    fed_outlays. POST + body? Copy fed_workforce. ZIP CSV? Copy
#    college_scorecard. Live snapshot? Copy opensky_us.
cp flows/fed_outlays/v1/spec.json runtime/specs/my_flow.json

# 2. Edit it. Required edits per section:
#
#    sources[0]:
#      url           - the publisher's endpoint
#      extra.json_schema (or csv_schema) - declare every column you'll keep
#      extra.json_records_path - dotted path if records aren't at top level
#      extra._skip_auto_casts: true - safest default; the cast planner has
#                                     edge cases on CamelCase column names
#
#    transformations[]:
#      kind: "trend_analysis" - YoY/rolling/anomaly per dimension. Need a
#                               date_col on the source.
#      kind: "graph_analysis" - networkx centralities + spring layout.
#                               Need source_id_col + target_id_col on edges.
#      kind: "eoc_fire_metrics" - WFIGS/NIFC fire-incident enrichment.
#      kind: "join"           - multi-source flows; index sources by branch.
#      kind: "pii_redaction"  - mask PII per category, plus audit table.
#      []                      - empty: just publish raw + derived columns.
#
#    outputs[]:
#      One published_data_source entry per terminal node. trend_analysis
#      and pii_redaction emit two siblings (Features+Stats / Redact+Audit) -
#      both need an output with `source: "<NodeName>"` to land in Hyper.
#
#    server_publish:
#      project + parent_project (both name strings). The publish step
#      auto-creates the child under the named parent if --auto-create-project
#      is passed.

# 3. Verify locally (no server work):
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan --skip-cli   # generate scripts only
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan              # generate + verify with prep-cli

# 4. Publish to server (will auto-create parent/child project if missing):
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan --publish --auto-create-project
# If publish fails with "project not found" right after auto-create
# (cache lag), rerun without --auto-create-project:
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan --publish

# 5. Archive the working version once it lands cleanly:
RD=$(ls -t runtime/my_flow/ | head -1)
python3 -m skill.scripts.archive_flow \
    --spec runtime/specs/my_flow.json \
    --run-dir runtime/my_flow/$RD \
    --flow-name my_flow --open-source     # --open-source: copies real Hyper sample
```

Reference for the `extra.*` knobs honored by api_caller (every JSON
pagination shape, every derived column kind):
**`skill/reference/api_caller_knobs.md`**.

## Worked examples

Each archived flow has a self-contained spec.json + flow.tfl + sample
Hyper output you can run cold:

| Flow | Source | Highlights |
|---|---|---|
| `flows/gdelt_global/v1/` | GDELT 1.0 events index | csv_index_then_zip + 115K rows/day |
| `flows/otf_grants/v1/` | otf.ca/open CSVs | 3-source multi-CSV join, bilingual headers, Latin-1 encoding |
| `flows/us_wildfires_eoc/v1/` | NIFC/WFIGS ArcGIS | EOC analyst metrics (size_class, growth_band, region_key) |
| `flows/us_grid_network/v1/` | HIFLD transmission lines | networkx centralities + Fruchterman-Reingold layout |
| `flows/fed_outlays/v1/` | Treasury Fiscal Data | JSON:API page[number]/page[size] paginated walk (3K rows) |
| `flows/fed_workforce/v1/` | BLS Public Data API | POST + JSON body, flatten inner records, derived obs_date |
| `flows/cisa_kev/v1/` | CISA KEV catalog | list_join + days_between (exploit SLA window) |
| `flows/fed_register_actions/v1/` | Federal Register API | list_first_field + days_since (regulatory case-mgmt) |
| `flows/fema_disasters/v1/` | OpenFEMA OData v2 | $top/$skip pagination + nested envelope |
| `flows/cms_deficiencies/v1/` | CMS Provider Data | 4xx-graceful pagination + page-size cap discovery |
| `flows/college_scorecard/v1/` | Dept of Ed bulk ZIP | csv_zip + per-column CSV_SCHEMA coercion |
| `flows/opensky_us/v1/` | OpenSky Network | json_array_columns positional projection (3.5K aircraft) |
| `flows/epa_aqs_ozone/v1/` | EPA AQS Data API | Drop Content-Type on bodyless GET (EPA strict-API fix) |
| `flows/usaspending_contracts/v1/` | USAspending.gov | json_page_in_body + has_next + dict_field flatten |
| `flows/russia_ukraine_attrition/v1/` | PetroIvaniuk dataset (GitHub) | Multi-source join + per-branch output routing; built via advanced collections route |
| `flows/embassy_threat_monitor_v2/v1/` | GDELT × US diplomatic-post roster | Haversine spatial join + weighted risk-bands + narrative event_summary. Every-3h cadence via publisher-cadence workaround. |
| `flows/doe_data_center_energy_monthly/v1/` | EIA Open Data v2 (retail-sales + state-profiles) | `auth: query_key` (`?api_key=…`) — first flow to exercise the new query-string auth path. Monthly. |
| `flows/doe_data_center_energy_hourly/v1/` | EIA Open Data v2 (RTO region-data) | Sub-daily hourly RTO demand pull (PJM/ERCOT/CAISO/MISO); every-6h refresh via publisher-cadence workaround. |

The first 14 form a baseline; flows 1-10 of the **Prep Agent demo
collection** are the ten archived flows below
`flows/russia_ukraine_attrition/v1/` (the eleventh sits in slot 11).
The collection lives under a nested `Prep Agent` parent project on
Cloud, each in its own `01 - Federal Outlays`, `02 - Federal Workforce`,
… child project for browseable side-by-side demos.

Reproduce any one with:

```sh
python3 -m skill.scripts.run_loop \
    --spec flows/<flow>/v1/spec.json \
    --flow-name <flow>
```

## Cloud-vs-Server flow execution

- **Tableau Server**: backgrounder runs the .tfl directly. Script
  nodes are supported.
- **Tableau Cloud**: backgrounder cannot run script nodes (TabPy
  isn't supported in Cloud's flow runner —
  https://help.tableau.com/current/prep/en-us/prep_scripts_TabPy.htm).
  The skill works around this by:
    - Running the flow locally via prep-cli to produce a .hyper extract.
    - Uploading the .hyper as a published data source via TSC.
    - Publishing the .tfl itself for visibility / code-review.

This is automatic — `local_iteration` mode in `run_loop` flips on
whenever the spec has a `published_data_source` output. See
`skill/reference/server_publishing.md` for details.

## Per-flow archive convention

Successful runs land in `flows/<flow_name>/v<N>/` via
`skill/scripts/archive_flow.py`:

```
flows/<flow_name>/
├── v1/
│   ├── spec.json           # cred-scrubbed
│   ├── flow.tfl            # PublishExtract shape, server-ready
│   ├── README.md           # auto-generated
│   └── sample_output/      # real Hyper for open-source feeds;
│                           #   synthesized 5-row sample for PII
└── README.md               # promotes the latest version
```

Scrub regex covers `token / secret / password / api_key / bearer /
client_secret / private_key / cert_body / cert_content`. Sample
outputs are capped at 50 MB total per archive.

## Reference docs

- `skill/SKILL.md` — workflow / phase walkthrough.
- `skill/reference/tabpy_setup.md` — the working TabPy recipe (read first).
- `skill/reference/server_publishing.md` — `--publish` semantics, MFA,
  project picker, parent_project + nested layout, local_iteration mode.
- `skill/reference/api_caller_knobs.md` — every `extra` knob the
  REST/JSON/CSV/ArcGIS fetcher honors. Read this before authoring a
  new spec.
- `skill/reference/metadata_api.md` — Metadata API queries (read-only
  on Cloud) + .tds-roundtrip writes.
- `skill/reference/tfl_format.md` — Maestro deserializer notes /
  required node fields.
- `skill/reference/examples/*.md` — worked spec.json examples.

## Troubleshooting quick-ref

| Symptom | Fix |
|---|---|
| `BasicAuthConfiguration.getPassword() is null` | TabPy auth — point CLI at unauth `:9099`. See `tabpy_setup.md`. |
| `Unable to connect to the Tableau Python (TabPy) server` (despite curl /info working) | TabPy's evaluate timed out (default 30s). Set `TABPY_EVALUATE_TIMEOUT = 600` and restart. |
| `An integer/string/datetime type is required for field [X]` | Schema mismatch. Check the rendered `INPUT_SCHEMA` in `runtime/<run>/scripts/<step>.py` matches the upstream cast nodes. Most reliable shape: declare the column as `string` in `json_schema` / `csv_schema` and add `_skip_auto_casts: true` on the source. |
| `Error running flow. The script didn't return any results.` | Almost always a downstream-Maestro empty after a cast/schema mismatch upstream. (a) Set `_skip_auto_casts: true` on the source. (b) Confirm your `json_records_path` resolves to a non-empty list. (c) Check trend_analysis siblings (Features + Stats) each have an `outputs[]` entry — both branches need a terminal output. |
| `An integer type is required for field [...]` despite `JSON_SCHEMA` declaring `"int"` | Publisher serializes nulls as the string `"null"` (Treasury) or sentinel like `"PrivacySuppressed"` (College Scorecard). The fetcher coerces these to NaN automatically — but only for columns present in `json_schema`/`csv_schema`. Add the column to your schema. |
| `HTTP Error 400: Bad Request` from a paginated walk that worked once | Some publishers cap offset depth (CMS Provider Data 400s past offset=30000) or page size (CMS caps at 1000, College Scorecard API at 100). Reduce `json_page_size` / `json_max_pages` to fit. The walker treats a mid-walk 4xx as "done" if rows were already collected. |
| `HTTP Error 429: Too Many Requests` | DEMO_KEY-style shared keys (api.data.gov) are hourly-rate-limited. Either register a real key, switch to a keyless bulk-download path (e.g. csv_zip), or wait ≥1 hour. |
| `HTTPError : HTTP Error 400: Bad Request` on first call to a JSON GET | Some strict APIs (EPA AQS) reject `Content-Type: application/json` on GET. Already handled — but if you see it on a fresh source, run a curl probe with no headers to confirm. |
| `RuntimeError: query_key auth requires env var $<VAR> to be set` inside a script node | TabPy daemon was launched before `<VAR>` was added to `load_env.sh`. Daemon env is frozen at launch time. Kill + relaunch TabPy from a shell that just sourced `load_env.sh` — see `tabpy_setup.md #Restart TabPy after adding a source-credential env var`. |
| `KeyError: 'every_6_hours'` / `KeyError: 'every_3_hours'` at publish time | `tflb_lib.publishing` only maps `hourly/daily/weekly/monthly`. Set `server_publish.cadence: 'hourly'` and keep the semantic `refresh_cadence` as-is. See `server_publishing.md #Publisher cadence map`. |
| `Project 'Foo' not found on this site` immediately after `--auto-create-project` | TSC project-list cache lag. Rerun `--publish` without `--auto-create-project`. |
| `Project 'Foo' not found on this site under parent 'Bar'` | Either the parent project doesn't exist (create it first manually), or `parent_project` doesn't match exactly (case-sensitive). |
| `Currently not signed in to any Tableau server` during prep-cli verify | Spec has a `published_data_source` output but `local_iteration` didn't kick in. Confirm `run_loop.py` is current — the trigger covers any PDS output. |
| `LLM gateway not configured` during metadata-write phase | Set `LLM_GATEWAY_URL/KEY/MODEL` env vars (or run `python3 -m skill.scripts.llm_config`). The flow + DS publish succeed without it; only column metadata generation needs it. |
| `name 'null' is not defined` runtime error inside an api_caller script | Stale rendered script from before the `JSON_BODY` Jinja fix. Delete `skill/connectors/<sig>/` and `runtime/<flow>/` to force a re-render. |
| Metadata API `Internal Server Error(s) while executing query` on `updateField` / `updateColumn` | Cloud's Metadata API is read-only. Use the .tds-roundtrip writer (`apply_descriptions`). |

## v2 roadmap (not yet implemented)

- **Conductor extractRefresh wiring for `internal_published_ds`.** The
  planner attaches to an existing DS today, but `--publish` doesn't
  create/attach a recurring extractRefresh task when the spec declares
  a `refresh_cadence` on that source. `tflb_lib.publishing` only reads
  existing `tasks/extractRefreshes` — no create-and-attach code path.
- **Cross-flow dependencies** (output of flow A as input to flow B),
  including topological ordering at publish time and downstream-flow
  scheduling that fires after the upstream flow completes.
- **Sub-daily schedule emission in `tflb_lib.publishing`.** The
  publisher's cadence map only handles `hourly / daily / weekly /
  monthly`; sub-daily intervals (`every_3_hours`, `every_6_hours`)
  require the workaround documented in
  `server_publishing.md #Publisher cadence map`. Extending the emitter
  to output `<interval hours="N"/>` + preferring an existing matching
  Cloud schedule closes the gap.
- **Connector per-org override layer.** The connector cache
  (`skill/connectors/<sig>/defaults.json`) records what worked for a
  given (type, host, auth, format) signature, but there's no
  higher-precedence override for org-specific values like ArcGIS PKI
  cert paths, ODBC driver names, or org-internal timeout norms.
  Envisioned shape: `~/.tableau-prep-etl/connector_overrides.json`
  keyed the same way, merged on top of `defaults.json`.

Already shipped since this section was first drafted (not roadmap
anymore, listed for cross-reference):
- Production-hardening layers 1-5 (`spec_validation.py`,
  `host_trust.py`, `security_lint.py`, `skill/reference/security.md`).
- `auth: 'query_key'` for `?api_key=…` URL-string auth (EIA v2,
  NREL, Data.gov).
- Metadata writer + .tds-roundtrip column-description apply
  (`metadata_api.md`).
- 10-flow Prep Agent demo collection under a nested parent project.
