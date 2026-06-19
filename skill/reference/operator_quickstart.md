# Operator Quickstart

A cold-start guide for using `tableau-prep-etl` without prior session
context. Read top-to-bottom the first time; after that, the section
headers are an index.

## What this skill does

You give it a natural-language ETL request (or an existing spec.json).
It plans the source acquisition, generates a Tableau Prep `.tfl`,
runs it locally via `tableau-prep-cli`, optionally scores against
ground truth, and optionally publishes the flow + a published data
source to Tableau Server / Cloud, then writes LLM-generated
descriptions back to the site.

The full workflow is documented in `SKILL.md` (Phases 0-11). This
page is the "I want to drive it" guide.

## Prerequisites — install once

1. **Tableau Prep Builder** (bundled `tableau-prep-cli`). Default
   path the skill expects:
   `/Applications/Tableau Prep Builder (Apple silicon) 2026.1.app/Contents/scripts/tableau-prep-cli`.
   Override via `TABLEAU_PREP_CLI`.

2. **TabPy on `:9099` with auth disabled** — the only working pattern
   for prep-cli on macOS. Recipe in `tabpy_setup.md`. Critical knob:
   `TABPY_EVALUATE_TIMEOUT = 600`.

3. **Python modules in TabPy's interpreter** (NOT the project venv):
   ```sh
   /Library/Frameworks/Python.framework/Versions/3.13/bin/pip install \
     pandas networkx rapidfuzz \
     PyPDF2 pdfplumber pdf2image pytesseract \
     python-dateutil openai certifi tableauserverclient tableauhyperapi
   ```

4. **LLM gateway env vars** (intake + metadata writer):
   ```sh
   LLM_GATEWAY_URL=https://.../chat/completions
   LLM_GATEWAY_KEY=...
   LLM_GATEWAY_MODEL=claude-sonnet-4-6   # production model
   ```
   For self-signed dev gateways: `LLM_GATEWAY_VERIFY_SSL=false`.

5. **Tableau Server creds** — only needed for publish, INTERNAL scan,
   and metadata writer. Store in macOS Keychain:
   ```sh
   security add-generic-password -s tableau-prep-etl -a url         -U -w 'https://prod-useast-a.online.tableau.com'
   security add-generic-password -s tableau-prep-etl -a pat-name    -U -w 'YOUR_PAT_NAME'
   security add-generic-password -s tableau-prep-etl -a pat-secret  -U -w 'YOUR_PAT_SECRET'
   security add-generic-password -s tableau-prep-etl -a site        -U -w 'usfederaldemos'
   ```
   Then load them into the shell:
   ```sh
   source ~/.tableau-prep-etl/load_env.sh
   ```

   **PATs only — no passwords in artifacts.** Cloud's MFA-on-every-login
   blocks user/password auth via prep-cli; PATs work because they
   bypass interactive auth. Server-side writes are PAT-authenticated
   end-to-end.

## Run a flow from an existing archive

The repo has 14 archived flows under `flows/<name>/v1/` — each with
`spec.json`, `flow.tfl`, and a sample Hyper. The fastest path to "is
my environment working?" is to re-run one of them:

```sh
cd ~/claude-projects/tableau-prep-etl-skill
source ~/.tableau-prep-etl/load_env.sh

# Rebuild + run locally (no publish):
python3 -m skill.scripts.run_loop \
    --spec flows/gdelt_global/v1/spec.json \
    --flow-name gdelt_global

# Build + run + publish + write descriptions to Cloud:
python3 -m skill.scripts.run_loop \
    --spec flows/gdelt_global/v1/spec.json \
    --flow-name gdelt_global \
    --publish --auto-create-project
```

`--auto-create-project` is needed on the **first** publish to a new
project. On subsequent runs, drop it. (See
`feedback_publish_project_create_quirk.md` for why this two-step
exists — same-session create + publish has a race against the
project-search cache.)

## Author a new flow

Two routes:

**A. Natural-language intake** — let the skill propose a spec from
scratch:

```sh
python3 -m skill.scripts.run_loop \
    --request "Pull GDELT daily and load into Tableau, geocode events" \
    --flow-name my_flow
```

The skill returns `{"status": "needs_user_decision", ...}` for any
clarifying questions; rerun with the resolved fields.

**B. Copy the closest archive** — fastest for known shapes:

1. Pick the closest flow under `flows/<name>/v1/` (full catalog in
   the project memory, but `flows/PREP_AGENT_REPORT.md` is a good
   index).
2. Copy `flows/<closest>/v1/spec.json` to `runtime/specs/<my>.json`.
3. Edit `url` / `json_schema` / `transformations` / `outputs`.
4. Validate generation only: `--skip-cli`.
5. Verify locally: `--skip-scan`.
6. Publish once happy: `--publish --auto-create-project`.

Reference for every `extra.*` knob in the api_caller template:
`api_caller_knobs.md`.

## Verify a successful run

After every run (local or publish), check four things:

1. **Hyper exists with the right schema.** `runtime/<run>/outputs/<name>.hyper`.
   If the run published a DS, the same .hyper was uploaded.
2. **Row count is plausible.** Logged in `report.md`.
3. **Metadata wrote.** If `--publish` was passed, the `runtime/<run>/metadata_<output>.json`
   audit JSON shows `applied: ok`. Cross-check by re-downloading
   the .tdsx and counting `<column>` elements in the .tds — should
   equal real cols + ≤2 Tableau-internal.
4. **Server-side health.** REST `datasources.get_by_id(luid)` returns
   the DS. The lineage / Data Details browser page may still 404
   for 10-30 min — that's Catalog indexing lag, not a failure.
   See `server_publishing.md`.

## Common breakages

- **Compile error "BasicAuthConfiguration.getPassword() is null"** —
  TabPy auth misconfig. Confirm prep-cli's
  `Command Line Repository/Credentials/pythonSupport.json` points
  at the unauth `:9099`. See `tabpy_setup.md`.

- **"Unable to connect to TabPy" but `curl /info` works** — TabPy's
  `/evaluate` returned 408 (script timeout). Confirm
  `TABPY_EVALUATE_TIMEOUT = 600` is in the conf and TabPy was
  restarted after the change.

- **Maestro "A {type} type is required for field [X]"** — schema
  mismatch between the rendered script's `get_output_schema()` and
  the actual returned dataframe. Every shipped script template ends
  with `_coerce_to_declared_schema(df)` to enforce wire types — if
  a custom template skips that, add it back.

- **Metadata write claims success, no descriptions visible** —
  either the Hyper-schema reader took the empty `public` schema
  instead of `Extract` (zero descriptions written, see
  `metadata_api.md`), or you're hitting Catalog indexing lag (the
  write is on the .tds, the GraphQL readback hasn't caught up —
  re-download the .tdsx to confirm).

- **DS published twice ends up with stale columns** — the .tds
  retains `<column>` elements from prior writes if orphan pruning
  is skipped. The skill's writer does this automatically; if you
  hand-edit the path, see `metadata_api.md` for the prune rule.

## Production-vs-demo guardrails

- **Never commit data, creds, or sample PII.** `.gitignore` covers
  `runtime/`, `corpus/`, `outputs/`, and most caches by default.
  Per-flow archives under `flows/<name>/v1/` are explicitly stripped:
  `archive_flow.py` runs a credential scrub on `spec.json` before
  copying. Spot-check before committing a new archive.
- **No creds in any pushed artifact.** PATs and gateway keys live in
  Keychain; the local plaintext file at `~/.tableau-prep-etl/server.json`
  is opt-in, chmod 600, and is *never* committed.
- **Production deployment uses env vars / secret manager**, never the
  plaintext file. Local dev only.
- **Server-side writes happen in the output node**, not in the
  rendered Python script. The script writes the .hyper locally;
  the publish step uploads it via TSC.

## Where to look next

- `SKILL.md` — full phase-by-phase workflow.
- `api_caller_knobs.md` — every knob the API caller template
  understands (pagination, headers, formats, derived columns).
- `tabpy_setup.md` — the TabPy recipe + template render conventions.
- `metadata_api.md` — REST + GraphQL surface, .tds round-trip,
  orphan pruning, Hyper schema discovery.
- `server_publishing.md` — publish flow, Catalog indexing lag, LUID
  injection.
- `tfl_format.md` — the `.tfl` JSON shape if you need to mutate
  directly.
- `security.md` — threat model + hardening (in progress).
- `examples/` — worked examples for each source shape.

## Where the skill stores artifacts

```
~/claude-projects/tableau-prep-etl-skill/
├── flows/<name>/v1/        # archived per-flow specs + sample outputs (committable)
│   ├── spec.json           # cred-scrubbed
│   ├── flow.tfl
│   └── sample_output/
├── runtime/<run_id>/       # per-run scratch (gitignored)
│   ├── spec.json
│   ├── flow.tfl
│   ├── outputs/*.hyper
│   ├── report.md
│   └── metadata_*.json     # description proposal + apply audit
└── skill/                  # the skill itself (symlinked into ~/.claude/skills)
```

Pull latest before any new work — sessions span weeks:

```sh
cd ~/claude-projects/tableau-prep-etl-skill
git status && git log -3 --oneline
```
