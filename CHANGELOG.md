# Changelog

All notable changes to `tableau-prep-etl-skill` will be documented here.
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
starting from the initial `v0.9.0-preview` release.

## [Unreleased]

### Added
- Templates for the WHS CX survey and DNFSB report flows:
  `whs_cx` (four wrappers over `lib/whs_cx_core.py.j2` — KPI Long,
  Comments, Respondent, YoY Summary; Summary hangs off KPI Long and
  aggregates its output), `entity_extract` (spaCy NER, long-form),
  `dnfsb_crawler` (headed-Chromium listing crawl behind Akamai, via
  `web_crawl` + `extra.crawl_mode: "listing"`), and `pdf_text_extract`
  (WAF-warmed PDF fetch + pdfplumber with an OCR fallback limited to the
  first `max_ocr_pages` pages, flagged `_partial` when that limit cuts
  text). Fail-closed by design: a missing spaCy model, an empty
  `domains_allowlist` (rejected at plan time for `pdf_text_extract`), a
  bad `$<max_reports_env>` override, or a WAF block on any listing page
  raises instead of emitting a short or unredacted table.
  `skill/tests/test_new_templates.py` (30 tests) covers them with fake
  browser / OCR / spaCy stand-ins.
- `reference/examples/synthetic_multiview.md` — one trigger → N
  `script → hyper` branches, with every node importing one shared
  deterministic scenario module so the extracts stay consistent. Covers
  shrinking a seed flow to its Excel input, `add_branch` append and
  name-idempotency behavior, the `folder` trigger column, and a
  cross-extract coherence harness that runs before prep-cli. Drawn from
  the JADC2 eight-view and DHA ARMOR UC5 capacity builds.
- `reference/tabpy_setup.md`: `get_output_schema()` must return a
  `pd.DataFrame` of `prep_*()` helpers (a plain dict crashes TabPy);
  emit flags as 0/1 `prep_decimal()`; a guarded `sys.path` insert for
  importing a shared module from script nodes; and restart TabPy after
  editing a shared module, since `sys.modules` keeps the old copy and
  prep-cli still reports success (observed: a stale string shipped in
  the Hyper).
- `SKILL.md`: "Where Prep stops" scoping note (real-time, interactive
  what-if, alert delivery, dashboards belong above the extracts).
- `reference/llm_backends.md` — recipe for LLM calls inside script
  nodes: OpenAI-compatible gateway vs Cohere Chat API v2 wire shapes
  (`message.content` is a list of typed blocks, not a string), the
  reasoning-model thinking-budget trap (unbounded reasoning eats
  `max_tokens` → `finish=MAX_TOKENS`, empty text, 0 rows; fix is
  `thinking.token_budget` + `max_tokens >= budget + 2000`;
  `thinking:disabled` is a 422), latency being output-bound not
  reasoning-bound, and per-row concurrency via a bounded thread pool
  (~11 min → ~3 min on 1,298 rows). Proven on the DNFSB Cohere arm.
  Linked from SKILL.md → Configuration.
- `reference/tabpy_setup.md`: "API keys for script nodes: read a config
  file at call time" (GUI TabPy doesn't inherit the shell env; a
  chmod-600 `~/.tableau-prep-etl/config.json` key read per call needs no
  daemon restart to rotate) and troubleshooting for the
  "Wait for cache write operation has terminated due to a failed write"
  Prep run error (stale/cancelled-run cache or full disk — not a script
  bug; check `df -h`, restart Builder, clear the extract cache).
- `reference/server_publishing.md`: the project-URL integer
  (`vizportalUrlId`, e.g. `.../projects/2365970`) is NOT the project
  LUID and is not resolvable via REST / Metadata API — resolve target
  projects by name (+ parent for nested children), never by the URL
  number.
- 10 advanced-route use-case flows (embassy_threat_monitor_v2,
  centcom_supplier_risk, sled_grant_clawback_risk,
  nursing_home_collapse_risk, wildfire_staging_gap,
  federal_kev_exposure, space_domain_convergence,
  grant_outcome_equity, post_disaster_grant_velocity,
  oversight_vs_execution), each archived with its SAT-brief /
  collections-plan / collections-log quartet under
  `flows/<name>/v2/advanced_route/`.
- `load_env.sh.example` — Keychain-backed env-var template matching
  `server_creds.py`, so a fresh machine can reconstruct the shell
  helper the docs reference.
- `SECURITY.md` — vulnerability-disclosure policy pointing at GitHub
  private reporting; documents the credential / SSRF-guard /
  host-approval surface.
- README "Prerequisites you must obtain" section (Tableau Prep
  Builder license, LLM gateway, Server/PAT) and bootstrap fixes
  (`mkdir -p ~/.claude/skills`, `pip install tabpy`,
  portable `$(which tabpy)`), plus an expanded `.env.example`.

### Fixed
- `tflb_lib/publishing.py::list_projects` now walks `TSC.Pager`
  instead of `server.projects.get()` (first page only), so the
  publish picker sees freshly-created child projects on busy sites.

### Prior unreleased work
- `docker/` — optional docker-compose stack: unauth loopback-only
  TabPy sidecar + a Python 3.11 skill runner with `requirements.txt`
  pre-installed. Bind-mounts the repo at `/workspace`; connector
  cache persists in a named volume. Prep CLI itself stays on host
  (macOS-only). Publishes TabPy to `127.0.0.1:9099` only.
- `docs/authoring_a_spec.md` and `docs/worked_examples.md` — split
  out of the top-level README. README trimmed from 456 → 363 lines;
  the 37-row worked-examples table now lives in `docs/`.
- Unit tests for `metadata_writer` (pure helpers + .tds injection
  round-trip via a fake TSC server) and for `run_loop` pure helpers
  (`_new_run_id` / `_safe_tfl_basename` / `_spec_from_dict`) —
  `skill/tests/test_metadata_writer.py`, `test_run_loop.py`. Total
  suite is now 140 tests; runs in <0.3 s with no live TabPy /
  Tableau / LLM dependency.
- Synthetic-sample generation in `archive_flow._synthesize_sample`:
  string values in the 5-row archived sample for non-open-source
  flows are now Faker-generated based on column-name heuristics
  (`email` → `Faker.email()`, `phone` → `Faker.phone_number()`,
  `_name`/`first_name`/`last_name`, `address`/`city`/`state`/`zip`,
  `uuid`/`guid`, `url`/`website`, `company`/`organization`/`agency`).
  Faker is seeded per-hyper-path so rebuilds don't churn. Falls back
  to the historic `<redacted>` placeholder when Faker isn't installed
  — archive shape is identical either way. Added
  `skill/tests/test_archive_sample.py` (13 tests).
- `Faker>=20.0` added to `requirements.txt` as an optional dep.

### Changed
- `server_creds.py` trimmed from 610 → 441 LOC (28% reduction). The
  three platform-specific `StorageOption` help-text blocks
  (`_macos_suggestions` / `_linux_suggestions` / `_windows_suggestions`)
  moved to `skill/scripts/_creds_suggestions.py`; `server_creds.py`
  now imports and delegates. Public surface unchanged — `StorageOption`
  and `suggestions()` still importable from `server_creds` for
  backwards compat. Added `skill/tests/test_creds_suggestions.py`
  (8 tests) locking down per-platform contract and dataclass shape.
- `spec_validation` now validates `server_publish.cadence` against
  the publisher-compatible set (`hourly | daily | weekly | monthly`)
  at spec-validation time. Sub-daily aliases like `every_3_hours`
  are still accepted on top-level `refresh_cadence` but must
  collapse to `hourly` for `server_publish.cadence`; the error
  message points at `skill/reference/server_publishing.md`.
- `tflb_lib.publishing` `ValueError`s for unknown cadences now
  reference `server_publish.cadence` explicitly and point at the
  same doc, instead of a bare `Unknown cadence 'x'`.

## [0.9.0-preview]

Public preview release. The skill is functional end-to-end (spec →
plan → .tfl → verified Hyper → optional publish + metadata write) and
has been exercised across 40+ archived flows on Tableau Cloud. Marked
`preview` because parts of the CLI surface (env var names, spec.json
schema for less-common source types) may still shift before `1.0`.

### Added
- `LICENSE` (Apache-2.0), `NOTICE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- GitHub issue + PR templates under `.github/`.
- `.github/workflows/ci.yml` — pytest + py_compile + spec-validation
  sweep on push and PR, across Python 3.11 / 3.12 / 3.13.
- Dependabot config for weekly pip + actions updates.
- Golden-file test for `source_planner.plan_sources` across three
  representative spec shapes (`skill/tests/test_planner_golden.py`).
- Platform-support matrix section in the README (macOS primary,
  Linux + Windows beta).
- `TABPY_BIND_IP = 127.0.0.1` in the canonical TabPy config so the
  server does not listen on public interfaces by default.
- `TABLEAU_PREP_ETL_CONNECTOR_CACHE` env var to override the per-user
  connector cache location.

### Changed
- Connector cache moved from `skill/connectors/<hash>/` (committed to
  the repo) to `~/.tableau-prep-etl/connectors/` (per-user, gitignored).
  A shipped seed `index.json` bootstraps the per-user cache on first
  use.
- TabPy setup docs no longer hard-code
  `/Library/Frameworks/Python.framework/Versions/3.13/bin/tabpy` —
  now uses `$(which tabpy)` so the recipe works on Homebrew installs
  and non-macOS platforms.
- SKILL.md description trimmed: removed "closed-loop refinement /
  ground-truth extraction / propose-and-promote agent versions"
  claims that describe v2 roadmap features rather than shipped v1
  behavior. The verification loop in `run_loop.py` runs the flow up
  to N times to ride out transient TabPy / DNS flakiness but does
  NOT LLM-mutate the underlying template between iterations.
- Removed all references to a specific Tableau Cloud pod / site
  identifier from docs and code — replaced with `<your-pod>` /
  `<your-site>` placeholders. The site is a deployment concern, not a
  property of the skill.

### Fixed
- Repo-tracked `hyperd.log` (11 MB engine debug log) removed; `*.log`
  is now globally gitignored.
- `pythonSupport.json` gitignored so local Tableau Prep credentials
  never enter the repo.

### Security
- TabPy `TABPY_BIND_IP = 127.0.0.1` is now the documented default.
  Deploying TabPy on `0.0.0.0` without auth allows anyone reachable
  on the interface to execute arbitrary Python as the TabPy user —
  the new default closes that hole for local development.

[Unreleased]: https://github.com/hal-force/tableau-prep-etl-skill/compare/v0.9.0-preview...HEAD
[0.9.0-preview]: https://github.com/hal-force/tableau-prep-etl-skill/releases/tag/v0.9.0-preview
