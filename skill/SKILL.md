---
name: tableau-prep-etl
description: >-
  Build, test, and refine a Tableau Prep flow (.tfl) from a natural-language
  ETL request. Handles local-folder ingestion, REST/GraphQL APIs, native
  Tableau connectors, web-crawl pipelines (Crawl4AI), and PKI-authenticated
  endpoints. Includes a closed-loop refinement framework: ground-truth
  extraction, scoring, holdout splits, propose-and-promote agent versions,
  per-document QA review, and statistical anomaly detection. Output: a
  working .tfl ready to open in Tableau Prep Builder.
  Use when the user asks to: "build a Prep flow that…", "create a Tableau
  ETL pipeline for…", "ingest <data source> into Tableau", "refine my
  existing .tfl", "set up an ongoing crawl into Prep", or "test my Prep
  flow against expected results".
---

# Tableau Prep ETL Skill

This skill takes a natural-language ETL request and produces a tested,
refined Tableau Prep `.tfl` file. The skill plans the source acquisition
strategy from the user's request, generates the flow programmatically,
runs it via `tableau-prep-cli`, scores the output against ground truth
(extracted, sampled, or synthesized depending on the source), proposes
refinements when scores are below threshold, and emits a final report
plus the working `.tfl`.

## When to invoke

The skill is the right tool when a user says things like:

- "Process this folder of PDFs and extract <fields>."
- "Pull GDELT data daily and load into Tableau."
- "Crawl this topic and surface trending entities."
- "Use my ArcGIS server as a data source."
- "Refine my existing Prep flow against this expected output."

It is **not** the right tool for:

- Modifying an existing flow's individual transformations (use Tableau
  Prep Builder directly).
- Schedule / Conductor management (server-side concern, v2 of this skill).
- Running production ETL ad-hoc (run the produced `.tfl` via
  `tableau-prep-cli` directly).

## Workflow

When invoked, the skill walks through these phases. Each phase has a
script under `scripts/`; the skill orchestrates them.

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
- `deployment`: `local` (v1) | `tableau_server` (v2).

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
| `native_connector` | `.v1.SqlConnection` / `.v1.LoadCsv` / `.v1.LoadExcel` |
| `rest_api` | `templates/api_caller.py.j2` Python step |
| `graphql_api` | `templates/api_caller.py.j2` (GraphQL variant) |
| `web_crawl` | `templates/crawler.py.j2` Crawl4AI step + Prep parameter for query |
| `pki_endpoint` | `templates/pki_connector.py.j2` cert-auth Python step |

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

Bounded refinement loop (default 3 iterations). Per iteration:

1. Run `tableau-prep-cli -t flow.tfl`.
2. Score the output against ground truth.
3. If overall mean < threshold (default 0.85), ask the LLM to propose
   a `v+1` variant of the worst-performing agent.
4. Register the variant; re-run; promote if it beats baseline on
   holdout AND no field regresses by > 0.10.
5. Repeat until threshold met or iteration cap hit.

### Phase 8: Final Report

Produce `runtime/<run_id>/report.md` with:

- **Attention list**: priority-ordered (invoice_id, issues, recommended action).
- **Suggestion inbox**: deduplicated improvement suggestions across the
  run, keyed by scope (global / submitter / field / agent).
- **Statistical anomalies**: per-submitter / per-field / drift signals.
- **Run manifest**: code signature, model used, timing, error count.

### Phase 9: Output

Hand the user the `.tfl` path + the report path. Tableau Server
publishing is a v2 feature behind a `--publish` flag (not in v1).

## Configuration

### Required environment variables

- `LLM_GATEWAY_URL` — full URL ending in `/chat/completions`
- `LLM_GATEWAY_KEY` — bearer token
- `LLM_GATEWAY_MODEL` — model id (default `claude-sonnet-4-6`)

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
