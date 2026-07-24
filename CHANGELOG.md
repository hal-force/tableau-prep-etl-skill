# Changelog

All notable changes to `tableau-prep-etl-skill` will be documented here.
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
starting from the initial `v0.9.0-preview` release.

## [Unreleased]

### Changed
- Nothing yet.

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
