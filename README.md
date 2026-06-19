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

The bottom 10 are the **Prep Agent demo collection** — published
together under a nested `Prep Agent` parent project on Cloud, each
in its own `01 - Federal Outlays`, `02 - Federal Workforce`, …
child project for browseable side-by-side demos.

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
  project picker, local_iteration mode.
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
| `An integer/string/datetime type is required for field [X]` | Schema mismatch. Check the rendered `INPUT_SCHEMA` in `runtime/<run>/scripts/<step>.py` matches the upstream cast nodes. |
| `Project 'Foo' not found on this site` immediately after `--auto-create-project` | TSC project-list cache lag. Rerun `--publish` without `--auto-create-project`. |
| `Currently not signed in to any Tableau server` during prep-cli verify | Spec has a `published_data_source` output but `local_iteration` didn't kick in. Confirm `run_loop.py` is current — the trigger covers any PDS output. |
| Metadata API `Internal Server Error(s) while executing query` on `updateField` / `updateColumn` | Cloud's Metadata API is read-only. Use the .tds-roundtrip writer (`apply_descriptions`). |

## v2 roadmap (not yet implemented)

- Conductor schedule wiring for `internal_published_ds` sources whose
  refresh_cadence implies a recurring backgrounder pull.
- Cross-flow dependency management (output of flow A as input to B).
- Connector-defaults registry: per-org overrides for ArcGIS PKI cert
  paths, ODBC drivers, etc., so specs stay portable.
