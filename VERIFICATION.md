# v1 verification report

Run before each push. Each row of the original 9-case verification plan
is checked off here with the actual evidence.

## v1 status

| # | Case | Status | Evidence |
|---|---|---|---|
| 1 | Skill loads cleanly | **PASS** | Frontmatter present in `skill/SKILL.md`; all `skill.scripts.*` modules import via package path. |
| 2 | Invoice regression (auto_refine still works) | **PASS** | `tfl_builder.py` refactored to import from `tflb_lib`; produces identical 22-node .tfl with same 10 script paths as baseline. Verified during the auto_refine refactor step. |
| 3 | Local folder example (any folder of files) | **PASS (structural)** | spec → plan → flow.tfl pipeline works for `local_folder` with PDF, JSON, and generic formats. PDF walker template renders to a Script node that uses pdfplumber. **Live tableau-prep-cli run** deferred — needs TabPy + a real folder. |
| 4 | Online API pull | **PASS (structural)** | spec → plan → flow.tfl works for `rest_api`. `api_caller.py.j2` renders with URL, auth, headers, retry logic. **Live HTTP call** deferred — needs a non-credentialed test endpoint. |
| 5 | Native connector | **PASS (structural)** | Source planner emits an `input` node with the connector class set. **Live native connector** deferred — needs Snowflake/Postgres credentials we shouldn't supply. |
| 6 | PKI connector | **PASS (structural)** | `pki_connector.py.j2` renders with cert env vars + ESRI feature-service convention. **Live cert-auth call** deferred — needs a real client cert. |
| 7 | Crawl4AI flow | **PASS (structural)** | `crawler.py.j2` renders with Tableau Prep parameter wiring for the query string. **Live crawl** deferred — needs `crawl4ai` installed in TabPy's interpreter, headless Chrome. |
| 8 | Bounded verification loop | **PASS (verify-only)** | `run_loop.py` runs the flow up to `MAX_REFINEMENT_ITERATIONS` (default 3) times, verifying the produced Hyper against the deterministic QA gate on each pass. LLM-driven mutation of the underlying template on failure is v2 roadmap material — not part of v1. |
| 9 | QA tier | **PASS (structural)** | `qa_reviewer.py.j2` and `statistical_analyst.py.j2` render and emit Tableau-Prep-compatible Script nodes. **Live LLM-backed QA review** deferred — needs `LLM_GATEWAY_KEY` configured. |

## End-to-end smoke (no LLM, no live source)

```
spec → plan → flow.tfl → eval rig → report
```

Confirmed the chain works on a synthetic `rest_api` spec:

- 1 input + 1 transform + 1 QA + 1 output → 4-node .tfl
- 2 templates rendered (`api_caller.py`, `validator.py`)
- eval rig stub written under `eval/ground_truth/`
- trigger.xlsx generated for the input node

## Known gaps (intentional v1 cuts)

These are **structural placeholders** in v1 that need real-world
hardening for v2:

1. **Closed-loop template refinement**: v1 runs the same flow up to
   `MAX_REFINEMENT_ITERATIONS` times to ride out transient TabPy / DNS
   flakiness. v2 will ask the LLM to mutate the underlying template
   (e.g. tighten an API pagination loop, swap an OCR DPI) when the
   deterministic QA gate flags a systematic problem.
2. **Synthesized GT**: stubbed. v2 will use the LLM gateway to
   generate up to 20 expected records from the spec.
3. **Sample validation GT**: emits a `USER_SUPPLY_GROUND_TRUTH.md`
   placeholder. v2 will pull a real sample from the source and ask
   the user to confirm.
4. **Tableau Server publishing**: SHIPPED. PAT auth, .tfl publish,
   Hyper-backed published data source, project auto-create, schedule
   wiring, and column-metadata write (.tds round-trip) all work via
   `--publish` (`skill/scripts/publish.py`, `tflb_lib/publishing.py`).
   See `skill/reference/server_publishing.md`. Remaining deferred bits:
   sub-daily schedule emission and cross-flow dependency ordering
   (see the README v2 roadmap).
5. **Native-connector full config**: v1 emits a `LoadSql` skeleton
   with the connector class noted in `description`. v2 needs the
   per-connector attribute schemas (Snowflake account/warehouse,
   Postgres host/port/db, etc).

## How to run a smoke yourself

```sh
cd /path/to/tableau-prep-etl-skill
export LLM_GATEWAY_URL='...'
export LLM_GATEWAY_KEY='...'
python3 -m skill.scripts.run_loop "ingest CSVs from /tmp/data and produce a Hyper extract"
```

The skill writes everything under `runtime/<run_id>/` and prints a
JSON summary at the end.
