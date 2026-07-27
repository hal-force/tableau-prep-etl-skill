# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security-relevant bugs.**

Use GitHub's private ["Report a vulnerability"](https://github.com/hal-force/tableau-prep-etl-skill/security/advisories/new)
flow on this repository, or email the maintainers. Include steps to
reproduce and the smallest failing `spec.json`.

We aim to acknowledge reports within a few business days.

## Scope

This project generates and runs Tableau Prep flows, executes
generated Python in a TabPy sidecar, and makes outbound HTTP requests
to user-specified data sources. Security-relevant areas include:

- **Credential handling** — env vars / OS keystore; see the
  credential-precedence chain in `skill/scripts/server_creds.py`.
- **SSRF / request-target validation** — outbound URL guards in the
  `api_caller` path (metadata endpoints and private ranges are
  rejected; see `skill/tests/test_spec_validation.py`).
- **Host-approval gate** — `TPE_HOST_APPROVAL` controls which API
  hosts a spec may contact (`skill/reference/security.md`).

## Not in scope

- Secrets you place in a local `.env` or `~/.tableau-prep-etl/`
  (dev-only, gitignored, never committed).
- The proprietary Tableau Prep CLI and Tableau Server/Cloud tenants
  you connect to — report those to Tableau/Salesforce directly.
