# Security model

This document covers the threat model, what the skill enforces where,
how to run the linter, and the operator responsibilities the skill
cannot enforce on its own.

## Threat model (priority order)

1. **Adversarial spec input.** The intake LLM (or a hand-edited
   archived spec) parses into Python that runs inside TabPy.
2. **Adversarial external response.** The API or page the spec points
   at can return arbitrary bytes; the script reads them.
3. **MITM on the LLM gateway.** A tampered gateway response becomes
   the spec, becomes generated code.
4. **Local credential leakage.** Temp credentials written to per-run
   scratch; archived specs scrubbed by a key-name regex.
5. **Audit-log overshare.** Sample rows or LLM output may echo PII.

Out of scope: sandboxing TabPy itself, rewriting Crawl4AI internals,
network egress firewalling on the TabPy host, signed archived specs.

## Defense layers

### Layer 1 — Spec input boundary

`skill/scripts/spec_validation.py` is the single gate. Both
`intake.intake()` (LLM parse) and `run_loop._spec_from_dict()`
(archive load via `--spec`) call it before any rendering.

- **`validate_url`** — scheme allowlist (`http`/`https`),
  hard-blocks loopback / cloud-metadata IPs (incl. AWS
  `169.254.169.254`, GCP `metadata.google.internal`, Azure
  `metadata.azure.com`), soft-blocks RFC1918 unless covered by
  internal trust.
- **`validate_relative_path`** — reject `..`, absolute paths,
  NUL/control bytes.
- **`validate_output_name`** — `Path(name).name` invariant; no
  separators, no shell metachars.
- **`validate_regex`** — compile-time SIGALRM bound; rejects
  nested-quantifier shapes that signal ReDoS.
- **`validate_extra`** — per-source-type whitelist. Unknown keys
  rejected, not silently allowed.
- **`safe_*_dict`** guarded constructors prevent the LLM from
  introducing dataclass fields the skill didn't declare.

### Layer 1.5 — Host trust (per-domain approval)

`skill/scripts/host_trust.py` adds a Claude-Code-style first-time
approval flow on top of validation. Every external host in
`spec.sources[*].url` is checked against:

1. Internal trust — host matches the suffix of `$TABLEAU_SERVER_URL`
   or any line in `~/.tableau-prep-etl/internal_hosts.txt`.
2. `~/.tableau-prep-etl/known_hosts.json` — previously approved hosts.
3. Heuristic evaluator — flags suspicious TLDs (`.tk`, `.cf`, `.ml`,
   etc.), Levenshtein-near typosquats of well-known anchors
   (`data.gov`, `github.com`, `tableau.com`, …), gives the operator
   a verdict to act on.

Modes (env var `TPE_HOST_APPROVAL`):

- `interactive` (default in TTY) — prompt for unknown hosts.
- `auto-trust-known` — silent on known hosts; deny unknown.
  Recommended for unattended runs after a baseline approval pass.
- `deny-unknown` — strict CI mode; never prompt.
- `trust-all` — opt-out (local development only).

### Layer 2 — Render-time safety

`skill/scripts/generate_flow.py` hardens the Jinja env:

- `autoescape=False` (we render Python, not HTML) but every
  spec-derived value goes through `tojson`, so values land as
  Python literals — quote-injection is structurally impossible.
- `StrictUndefined` — references to missing template vars raise at
  render time rather than emitting `""`.
- After every `tpl.render(...)` we `ast.parse` the rendered output
  and fail fast with the offending template + a 5-line excerpt. A
  template that produces unparseable Python never reaches disk.

### Layer 3 — Runtime guardrails in generated scripts

- `api_caller.py.j2` and `pki_connector.py.j2`:
  - `_assert_url_safe()` re-validates `API_URL` at script-execution
    time (defense-in-depth — even a tampered `.tfl` cannot reach
    cloud-metadata or loopback).
  - `MAX_RESPONSE_BYTES` (default 500MB; configurable via
    `extra.max_response_bytes`) enforced via chunked reads, not
    `resp.read()`.
  - `JSON_MAX_ROWS` independent of `JSON_MAX_PAGES`.
  - SIGALRM-based timeout on `re.findall(INDEX_LINK_PATTERN, …)`.
- `crawler.py.j2`:
  - Refuses to run when `DOMAINS_ALLOWLIST` is empty.
  - `quote_plus` the query; assert the search URL host equals the
    configured `engine_search_host`.
  - Reject queries containing control characters.
  - `asyncio.timeout()` total wall-time bound; `MAX_RESPONSE_BYTES`
    cap on browser body.
  - Allowlist match is **host-equality / suffix** — substring
    matching (`d in href`) was vulnerable to
    `phishy-data.gov.evil.com` style trickery.
- `pki_connector.py.j2`:
  - Cert + key paths must resolve under
    `~/.tableau-prep-etl/certs/` (or `$TPE_CERT_DIR`). Keeps a
    tampered env from pointing at `/etc/ssl/private/`.

### Layer 4 — Gateway TLS, credentials, audit hygiene

- `LLM_GATEWAY_VERIFY_SSL` env var, default ON. `false` flips off
  for local self-signed gateways. Wired in `intake.py`,
  `metadata_writer.py`, and `qa_reviewer.py.j2`.
- `archive_flow._CRED_KEYS_RE` covers `token | secret | password |
  api_key | bearer | client_secret | private_key | cert(_pem|_body|
  _content) | certificate | authorization | auth_header |
  connection(_string) | cookie | session(id) | credentials`.
- `metadata_*.json` audit files persist `raw_llm_output_sha256` +
  `raw_llm_output_len`, never the raw LLM response. The raw
  response is only written under `--debug-llm` to
  `metadata_<name>.raw.txt` (chmod 600).
- `_cli_credentials.json` is chmod 600 immediately after creation;
  cleanup failures log to the run log instead of `pass`.
- `runtime/<run>/` is created with `mode=0o700`.
- `_maybe_write_metadata` re-raises `tableauserverclient.ServerResponseError`
  / `NotSignedInError` instead of swallowing 401s under "no LUID
  found, skipping."

### Layer 5 — Operational

- `scripts/security_lint.py` — runs all spec validators against
  `flows/*/v*/spec.json` and reports any host not covered by
  internal-trust or `known_hosts.json`. Cheap pre-commit hook.
  Exit code: 0 = clean, 1 = violations, 2 = no specs found.

```bash
# lint everything
python3 scripts/security_lint.py
# lint a single spec
python3 scripts/security_lint.py flows/cisa_kev/v1/spec.json
```

## Operator responsibilities

These the skill cannot enforce; they're yours.

- **PAT rotation.** Tableau Server Personal Access Tokens are stored
  in env vars / macOS Keychain. Rotate on the cadence your
  organization requires; the skill will fail loudly when the PAT is
  invalid (no longer silently — see the LUID-lookup tightening in
  `_maybe_write_metadata`).
- **Gateway key rotation.** `LLM_GATEWAY_KEY` is read at process
  start; rotate by restarting the runner. Do not commit the key.
- **TabPy egress firewall.** The skill validates URLs but doesn't
  control the network. If TabPy can reach the public internet, an
  approved host can still be reached; if it can't reach a needed
  host, no skill change will help.
- **`internal_hosts.txt` maintenance.** Add suffixes only after
  vetting. A line like `corp.example.com` allows
  `internal-api.corp.example.com` to bypass approval (and to use
  RFC1918 IPs).
- **Cert directory hygiene.** Files under
  `~/.tableau-prep-etl/certs/` should be `0o600` and owned by the
  operator. The skill asserts the realm; permissions are yours.
- **Reviewing `metadata_*.json` before `--apply`.** Audit JSONs
  are intended for human review. Don't auto-apply over a CI hook
  without sampling at least the first proposal of each new flow.

## Where audit data lands

- `runtime/<flow>/<run_id>/metadata_<name>.json` — DS + column
  description proposals, with `raw_llm_output_sha256` only.
- `runtime/<flow>/<run_id>/metadata_<name>.raw.txt` — raw gateway
  response, only when `--debug-llm` was passed.
- `runtime/<flow>/<run_id>/_cli_credentials.json` — synthesized
  credentials.json fed to `tableau-prep-cli -c`. Removed on cleanup;
  chmod 600 during its brief lifetime.
- `runtime/<flow>/<run_id>/metadata_luid_lookup_warning.txt` —
  written when LUID lookup fails for a non-auth reason.

`runtime/` is `.gitignore`'d at the root.

## Granting / revoking host approvals

```bash
# inspect the trust store
cat ~/.tableau-prep-etl/known_hosts.json | jq

# revoke a single host (then re-run intake to re-approve interactively)
jq 'del(.hosts["api.example.gov"])' ~/.tableau-prep-etl/known_hosts.json \
    > /tmp/k.json && mv /tmp/k.json ~/.tableau-prep-etl/known_hosts.json

# bulk-trust an internal suffix (skips interactive approval entirely)
echo 'corp.example.com' >> ~/.tableau-prep-etl/internal_hosts.txt
```
