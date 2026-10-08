# tableau-prep-etl-skill

A Claude Code skill that turns a natural-language ETL request into a
working Tableau Prep flow. You describe the data you want. The skill
writes the `.tfl`, runs it through `tableau-prep-cli` and TabPy, checks
the output Hyper against a deterministic QA gate and, if you ask,
publishes the flow and its extracts to Tableau Server / Cloud with
data source and column descriptions filled in.

## How it works

```
request ──> 0. INTERNAL scan    reuse a published DS on the site before going external
            1. Intake           request -> spec.json (sources, transforms, outputs, QA tier)
            2. Plan + confirm   one-page plan; nothing touches creds or data before approval
            3. Source planning  pick a strategy per source (table below)
            4. Acquire + infer  pull a small sample, derive the output schema
            5. Generate         render templates -> script nodes; tflb_lib assembles the .tfl
            6. Eval rig         expected values: from source / sample / synthesized / user / consensus
            7. Run + verify     prep-cli + TabPy -> Hyper -> QA gate (schema, nulls, bounds,
                                spec post-conditions); bounded retry, up to 3 iterations
            8-9. Report         .tfl + report.md (attention list, anomalies, run manifest)
           10. Publish          opt-in: flow + Hyper-backed published data sources (TSC, PAT auth)
           11. Metadata         DS + per-column descriptions via .tds round-trip, read back to verify
```

**Two routes.** The *simplified* route (the default) is the
one-shot pipeline above, for when you know the source. The *advanced*
route is for when you start with a **question** rather than a dataset.
It applies structured analytic techniques to break the question into
factors and indicators, then a collections plan, then up to three
acquisition passes, internal sources first. Any indicator it can't fill
is declared as a gap. The output is a `spec.json` that feeds the
simplified route. See
[`skill/reference/advanced_collections_route.md`](skill/reference/advanced_collections_route.md).

### What it can build

| Source strategy | How |
|---|---|
| `local_folder` | folder listing + per-file script node (PDF text / OCR, CSV, Excel) |
| `local_csv` / `native_connector` | native `LoadCsv` / `LoadExcel` / `SqlConnection` inputs |
| `rest_api` / `graphql_api` | `api_caller` template: JSON, JSONL, CSV, ZIP-of-CSV, ArcGIS features. Handles every common pagination shape, POST bodies, nested envelopes, derived columns and query-string keys ([knobs](skill/reference/api_caller_knobs.md)) |
| `web_crawl` | Crawl4AI crawler template (opt-in) and a site-specific PDF crawler pattern |
| `pki_endpoint` | certificate-authenticated fetcher |
| `internal_published_ds` | native input bound to a published DS LUID (no Python) |

| Transform | Output |
|---|---|
| `join` | native Prep `SuperJoin`s across branches (left-deep for chains) |
| `trend_analysis` | row-level calendar features + long-form stats (rolling, YoY, z-score anomalies) |
| `graph_analysis` | networkx centralities + spring layout per node |
| `pii_redaction` | redacted rows + an audit table holding a sha256 per detection, never the original |
| `entity_extract`, LLM script nodes | spaCy entities; LLM classification / summarization per row ([backends](skill/reference/llm_backends.md)) |
| domain kinds | EOC fire metrics, EW fusion / intercept match, spatial event-to-post joins and risk bands, survey CX roll-ups |

**Multi-view flows.** When one model has to feed several dashboard
views, a single trigger fans out to N `script -> hyper` branches. Every
branch imports one shared core module, so the extracts stay mutually
consistent and a cross-extract coherence gate can check them. A
production flow can keep a small-input **test variant** that calls a
second entry function in the same scripts (one filing instead of 150,
seconds instead of minutes). See
[`synthetic_multiview.md`](skill/reference/examples/synthetic_multiview.md)
and [`tabpy_setup.md`](skill/reference/tabpy_setup.md).

## What's in the box

```
tableau-prep-etl-skill/
├── tflb_lib/                 # domain-agnostic .tfl JSON mutation library
│   ├── nodes.py              # make_script_node, make_join_node, …
│   ├── inputs.py             # rewire_input_to_local_excel
│   ├── topology.py           # prune_nodes_by_name, rewrite_script_paths
│   ├── builder.py            # build() top-level read/mutate/write
│   └── publishing.py         # PAT auth, projects, flow/DS publish, schedules (TSC + REST)
│
├── skill/                    # the Claude Code skill
│   ├── SKILL.md              # frontmatter + workflow spec
│   ├── scripts/              # intake, server_scan, source_planner, generate_flow,
│   │                         #   run_loop, publish, metadata_writer, server_creds,
│   │                         #   spec_validation, host_trust, archive_flow, …
│   ├── templates/            # ~30 Jinja script-node templates: api_caller, crawler,
│   │                         #   pdf_text_extract, entity_extract, trend_*, graph_analyzer,
│   │                         #   pii_redactor/audit, qa_reviewer, statistical_analyst, …
│   ├── reference/            # tabpy_setup, server_publishing, metadata_api, tfl_format,
│   │                         #   api_caller_knobs, llm_backends, security,
│   │                         #   advanced_collections_route, examples/
│   └── tests/                # pytest suite (CI on Ubuntu, Python 3.11-3.13)
│
├── docs/                     # authoring_a_spec, worked_examples
├── docker/                   # TabPy + Python deps container recipe
└── flows/                    # 55 archived per-flow artifacts (cred-scrubbed)
    ├── gdelt_global/v1/       #   e.g. otf_grants, us_wildfires_eoc,
    ├── otf_grants/v1/         #   cisa_kev, fema_disasters, la_crime_2024, …
    └── …                      #   see docs/worked_examples.md for the full set
```

## Platform support

| Platform | Status | Notes |
|---|---|---|
| **macOS** (Apple silicon + Intel) | ✅ Primary | Every flow in this repo was built and verified on macOS 14/15. `run_loop.py` defaults to the Apple-silicon Prep Builder path; override with `TABLEAU_PREP_CLI=/path/to/tableau-prep-cli`. |
| **Linux** | ⚠️ Beta | Core skill code is pure-python and CI runs on Ubuntu across Python 3.11 / 3.12 / 3.13 (see `.github/workflows/ci.yml`). Tableau Prep Builder itself is not available on Linux — a Linux host can build + validate specs and .tfl artifacts, and publish them to Tableau Server / Cloud, but cannot run flows locally via prep-cli. |
| **Windows** | ⚠️ Beta | Tableau Prep Builder for Windows exists and prep-cli is available. Set `TABLEAU_PREP_CLI` to the Windows path and use `%USERPROFILE%\Documents\My Tableau Prep Repository\...` for the `pythonSupport.json` path. Loopback TabPy setup is the same recipe minus the macOS-specific `dscacheutil` DNS pre-warm. Not yet exercised end-to-end by the maintainers — reports welcome. |

Requires:

- Python 3.11 or newer (skill code)
- Python 3.10+ inside TabPy's interpreter (see `skill/reference/tabpy_setup.md`)
- Tableau Prep Builder 2025.3 or newer for local `.tfl` execution
- Tableau Server 2022.3+ or Tableau Cloud for `--publish`

Prefer Docker for TabPy + Python deps? See **[`docker/README.md`](docker/README.md)**.
The Tableau Prep CLI is a host-side binary either way — install it on
macOS or Windows (see the Platform support table above); it is not
available inside the Linux container.

### Prerequisites you must obtain (not `pip`-installable)

Two dependencies require access/licensing that no setup script can
grant — arrange these **before** you start, as they can take days:

| Prerequisite | Needed for | How to obtain |
|---|---|---|
| **Tableau Prep Builder** 2025.3+ | Running `.tfl` flows locally (any run that isn't `--skip-cli`) | Licensed product. Bundled with **Tableau Creator**; download from [tableau.com/products/prep](https://www.tableau.com/products/prep). A 14-day trial works for evaluation. The bundled `tableau-prep-cli` binary is what this skill drives. |
| **LLM gateway** | Natural-language intake + column-metadata generation | Any OpenAI-compatible `/chat/completions` endpoint serving `claude-sonnet-4-6`. At Salesforce, request access to the internal AI gateway; otherwise point `LLM_GATEWAY_URL`/`LLM_GATEWAY_KEY` at your own provider. **Not required** if you author `spec.json` by hand and run with `--spec` (see step 5, Option C). |
| **Tableau Server / Cloud** + PAT | Publishing flows, data sources, and metadata (`--publish`) | Only needed to publish. Use an existing org tenant or a Tableau Cloud trial; create a Personal Access Token under **My Account Settings → Personal Access Tokens**. Local-only flow authoring needs none of this. |

Everything else — the skill code, TabPy, Python deps — installs from
this repo and `pip`. If you only want to **build and validate** flows
(no local execution, no publish), you can skip the Prep Builder and
Tableau Server rows entirely and run with `--skip-cli`.

## First-run setup

### 1. Clone and link

```sh
git clone https://github.com/hal-force/tableau-prep-etl-skill.git
cd tableau-prep-etl-skill
mkdir -p ~/.claude/skills   # first-time: the skills dir may not exist yet
ln -s "$PWD/skill" ~/.claude/skills/tableau-prep-etl
```

The symlink lets Claude Code discover the skill while the canonical
source stays in this repo for version control.

### 2. Python deps

The skill code itself runs in your project's Python (3.11+):

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
pip install tabpy                # once, into the interpreter you'll launch it from

cat > /tmp/tabpy_smoke.conf <<'EOF'
[TabPy]
TABPY_PORT = 9099
TABPY_EVALUATE_ENABLE = true
TABPY_EVALUATE_TIMEOUT = 600
EOF

"$(which tabpy)" --config=/tmp/tabpy_smoke.conf --disable-auth-warning &
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
On first run, it saves what it finds in Keychain for future shells.
Copy [`load_env.sh.example`](load_env.sh.example) to
`~/.tableau-prep-etl/load_env.sh` (it reads secrets from your OS
keystore — never commit it), then source it:

```sh
source ~/.tableau-prep-etl/load_env.sh   # exports TABLEAU_SERVER_*
```

For a non-Keychain / CI setup, copy [`.env.example`](.env.example) to
`.env` (gitignored) and fill in the values, or export them directly.

Required env vars (any one of these paths sets them):

```
TABLEAU_SERVER_URL          # e.g. https://<your-pod>.online.tableau.com
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

## Authoring a spec

Most users start by copying the closest archived spec and editing.
Full walkthrough (no LLM gateway needed) is in
**[`docs/authoring_a_spec.md`](docs/authoring_a_spec.md)**.

Reference for the `extra.*` knobs honored by api_caller (every JSON
pagination shape, every derived column kind):
**`skill/reference/api_caller_knobs.md`**.

## Worked examples

55 archived flows live under `flows/<name>/v*/`, each with a
self-contained spec.json + flow.tfl + sample Hyper you can run cold.
A representative table with per-flow highlights and reproduction
commands:
**[`docs/worked_examples.md`](docs/worked_examples.md)**.

Quick pointers by shape:

| Shape | Copy from |
|---|---|
| JSON:API page[number]/page[size] pagination | `flows/fed_outlays/v1/` |
| POST + JSON body pagination | `flows/fed_workforce/v1/`, `flows/usaspending_contracts/v1/` |
| ZIP-of-CSV bulk download | `flows/college_scorecard/v1/` |
| ArcGIS feature service | `flows/us_wildfires_eoc/v1/` |
| Multi-source join | `flows/otf_grants/v1/`, `flows/russia_ukraine_attrition/v1/` |
| graph_analysis (networkx) | `flows/us_grid_network/v1/` |
| trend_analysis (YoY / rolling) | `flows/fed_outlays/v1/` |
| Spatial join + risk bands | `flows/embassy_threat_monitor_v2/v1/` |
| `auth: query_key` (`?api_key=…`) | `flows/doe_data_center_energy_monthly/v1/` |

Reproduce any archived flow with:

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

### Publishing and catalog metadata

- **Projects.** Nested layouts are supported: `parent_project` +
  `project` resolves or creates `Parent / NN - Flow` children. The
  picker asks before it creates anything.
- **Data sources.** Uploads use Overwrite, so LUIDs survive re-runs and
  dashboards stay connected.
- **Flow artifact.** `publish_flow(..., description=...)` sets the
  description with a direct REST PUT, because TSC's `flows.update()`
  drops that field.
- **Descriptions.** Each data source gets a 2-4 sentence description,
  and each column gets one sentence. They are LLM-generated by default.
  For domain flows whose column meanings live in code, you can author
  them by hand and pass them to `apply_descriptions`. Columns are
  written by downloading the `.tdsx`, injecting `<desc>` elements into
  the `.tds` and republishing, because Cloud's Metadata API has no
  write path. Every proposal is saved as an audit JSON.
- **Verification.** `metadata_writer.verify_column_descriptions`
  re-downloads the `.tdsx` and checks every column, which is
  synchronous. The Catalog / GraphQL view can lag 10-30+ minutes, so
  it isn't used to verify.

## Tableau Prep product gaps found along the way

Each of these is worked around in the skill and documented in
`skill/reference/`.

| Gap | Impact | Workaround |
|---|---|---|
| Tableau Cloud's flow runner can't execute TabPy script nodes | Script-heavy flows can't be scheduled on Cloud | Run locally via prep-cli, publish the Hyper outputs as data sources, and publish the `.tfl` as an unscheduled artifact |
| `prep-cli` `credentials.json` accepts username/password only; PATs are rejected | Local runs of flows that read published data sources need a password, which breaks MFA-first setups | Temporary per-run credentials file built from Keychain, deleted after the run |
| Cloud Metadata API is read-only (`updateField` / `updateColumn` return 500s) | No API path for column descriptions | `.tds` round-trip and republish with Overwrite |
| The Catalog index lags 10-30+ minutes after publish | Lineage / Data Details pages 404 and GraphQL readbacks are stale | Verify via REST and a `.tdsx` re-download |
| TSC `flows.update()` doesn't serialize `description` | Flow descriptions silently don't save | REST PUT (`set_flow_description`), with a canary test for when TSC fixes it |
| TabPy caches imported modules for the life of the process | Edits to a shared module are ignored, yet the run reports success | Restart TabPy after editing shared modules, then read a changed value back out of the Hyper |
| prep-cli's authenticated TabPy path is broken on recent macOS builds; the default evaluate timeout is 30 s | Script nodes fail or time out | Loopback TabPy without auth on `:9099`, with a 600 s timeout (Docker recipe included) |

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
- `skill/reference/advanced_collections_route.md` — question-first
  route: factors, indicators, collections plan, gap declaration.
- `skill/reference/llm_backends.md` — LLM script nodes (OpenAI-compatible
  gateway or Cohere), reasoning-budget and concurrency lessons.
- `skill/reference/security.md` — spec validation, host trust, secret
  handling.
- `skill/reference/operator_quickstart.md` — cold-start how-to.
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
| `name 'null' is not defined` runtime error inside an api_caller script | Stale rendered script from before the `JSON_BODY` Jinja fix. Delete `~/.tableau-prep-etl/connectors/<sig>/` and `runtime/<flow>/` to force a re-render. |
| Metadata API `Internal Server Error(s) while executing query` on `updateField` / `updateColumn` | Cloud's Metadata API is read-only. Use the .tds-roundtrip writer (`apply_descriptions`). |
| Lineage page 404 / GraphQL shows no descriptions right after publish | Catalog index lag (10-30+ min). Verify with `verify_column_descriptions` (REST + `.tdsx` re-download) instead. |
| Flow description is blank after `flows.update()` returned 200 | TSC drops `description` on flow updates. Use `publishing.set_flow_description` or `publish_flow(..., description=...)`. |
| prep-cli says the run succeeded, but the Hyper still has old values after editing a shared module | TabPy caches `sys.modules`. Restart TabPy (`docker restart tpe-tabpy` for the container recipe) and re-run. |

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
  (`~/.tableau-prep-etl/connectors/<sig>/defaults.json`) records what
  worked for a given (type, host, auth, format) signature, but there's no
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
- 55 archived flows (incl. the Prep Agent demo collection under a
  nested parent project, and the 10 advanced-route use cases).
- Multi-view shared-core flows, LLM script-node backends, PDF crawler /
  text / entity-extraction templates.
- Flow descriptions via REST, synchronous column-description
  verification, hand-authored metadata path.
