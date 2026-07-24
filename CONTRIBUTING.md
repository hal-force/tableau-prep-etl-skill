# Contributing

Thanks for your interest in contributing to tableau-prep-etl-skill.

## Ground rules

- **Preview status.** The project is at `v0.9.0-preview`. Interfaces may
  change; do not assume archived flow specs will render identically
  across versions.
- **License.** All contributions are licensed under Apache-2.0 (see
  `LICENSE`). By opening a pull request you agree your contribution is
  yours to submit under that license.
- **No secrets in commits.** PATs, API keys, `.env` files, `pythonSupport.json`,
  `~/.tableau-prep-etl/server.json`, and anything under `runtime/` are
  gitignored. If a check accidentally stages one, stop and rotate.
- **No live data in the tree.** `flows/**/sample_output/*.csv` files
  ship as synthetic samples only. Any real row-level data must be
  redacted or replaced with fixture data before commit.

## Development setup

```sh
git clone https://github.com/hal-force/tableau-prep-etl-skill.git
cd tableau-prep-etl-skill
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
pytest skill/tests/
```

See `README.md` for the full runtime prerequisites (TabPy, Prep CLI,
optional PDF/OCR tooling).

## Making a change

1. **Fork + branch.** Branch names: `type/short-desc`, e.g.
   `fix/dns-flake-retry`, `feat/pki-connector`.
2. **Add or update tests.** Any change to `skill/scripts/spec_validation.py`
   or `skill/scripts/host_trust.py` requires a test; other modules are
   test-encouraged.
3. **Run the local checks.**
   ```sh
   pytest skill/tests/ -q
   python3 -m py_compile skill/templates/*.py.j2 || true   # informational
   ```
4. **PR description.** Explain *why*, not just what. Reference an issue
   if you have one.

## Areas we especially welcome help on

- Non-macOS TabPy setup recipes (Linux systemd unit, Windows service).
- Native-connector templates (Snowflake, Postgres, SQL Server) with
  attribute-schema coverage.
- Cross-platform CI (currently macOS-first; Linux and Windows runners
  in the roadmap).
- New source-type support in `api_caller.py.j2` (documented via a
  worked flow under `flows/<name>/v1/`).

## Areas that need care

- **`skill/scripts/spec_validation.py`.** This is the load-bearing
  boundary between user/LLM input and generated code. Changes here
  need thorough test coverage and a security-review flag on the PR.
- **`skill/scripts/host_trust.py`.** SSRF and typosquat mitigations.
  Same bar as spec_validation.
- **`skill/scripts/server_creds.py`.** Credential discovery. Add a
  new path only if the existing four (env / Keychain / libsecret /
  chmod-600 JSON) do not cover a real deployment.

## Reporting security issues

Do **not** open a public issue for security-relevant bugs. Email the
maintainers or use GitHub's private "Report a vulnerability" flow on
the repo. Include steps to reproduce and the smallest failing spec.

## Code of Conduct

See `CODE_OF_CONDUCT.md`. In short: be constructive and generous;
attack ideas, not people.
