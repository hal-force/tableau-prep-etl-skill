# Workflow & Decision Gates

The operating rules for the Tableau Prep ETL skill, in one place: the
end-to-end workflow and the specific decision gates that steer a run.
This is the "what does the skill decide, and when" reference — the
mechanics of each phase live in `../SKILL.md` and the per-topic docs
this file links to.

Every gate below is enforced in `scripts/`, not just described here;
where a gate is doc-only (not yet automated), it says so explicitly.

## Workflow at a glance

```
                    ┌─ simplified (default, automated) ──────────────┐
request / spec ─────┤                                                 │
                    └─ advanced (agent-run methodology, NOT a flag) ──┘
                                        │
   Phase 1a  discover Tableau creds (only if the run touches a site)
   Phase 1b  INTERNAL data scan ....................... [Gate 2]
   Phase 1   intake: NL → spec.json (qa_tier, eval_strategy) [Gate 6]
   Phase 2   plan + confirm (human approval before creds/data)
   Phase 3   source planning (per-source strategy)
   Phase 4   acquire sample + infer schema
   Phase 5   generate .tfl (branched DAG if joins)
   Phase 6   synthesize eval rig
   Phase 7   bounded test loop (run prep-cli → verify Hyper) . [Gate 5]
   Phase 8   report
   Phase 9   hand off .tfl + report            ← default STOPS here
   Phase 10  publish ............................ opt-in only [Gate 3, 4]
   Phase 11  metadata write-back (DS + column descriptions) . [Gate 7]
             then: archive .............................. [Gate 8]
```

## The decision gates

### Gate 1 — Route: simplified vs advanced

- **Trigger:** the *shape of the ask*, not the data. A known
  source/spec → simplified. A *question* rather than a dataset →
  advanced.
- **Branches:**
  - **Simplified (default).** The full automated pipeline below. This
    is the only route wired into the CLI.
  - **Advanced (collections planning).** A Structured-Analytic-
    Techniques front-end (question → factors → indicators →
    collections plan → up to 3 internal-first acquisition passes) that
    emits a `spec.json` the simplified pipeline then consumes. See
    `advanced_collections_route.md`.
- **Where decided / caveat:** **The advanced route is an agent-run
  methodology, not an automated code path.** `run_loop.py` has **no
  `--route` and no `--question` argument** — passing `--route advanced`
  errors in argparse today. To run advanced, *follow*
  `advanced_collections_route.md` by hand until it produces a spec,
  then feed that spec to the simplified route. (SKILL.md currently
  describes `--route advanced` as if it were a flag; treat that as
  aspirational until the flag lands.)
- **User consulted?** At invocation — the operator chooses the route.

### Gate 2 — Internal data first (Phase 1b)

- **Trigger:** any run whose site creds are discoverable, unless
  bypassed (below).
- **Branches:**
  - Scan the connected site (Metadata API GraphQL) for a published DS
    matching the request. **Candidates found** → bounce
    `needs_user_decision` to the orchestrator; the user picks one (→
    `internal_published_ds` source) or opts out.
  - **No match / skipped / error** → fall through to external source
    planning.
- **Silently skipped when:** `--skip-scan` is passed, the spec already
  has an `internal_published_ds` source, OR no creds are discoverable
  (env → Keychain → secret-tool → file all miss).
- **Where decided:** `run_loop.py` Phase 1b (`~line 666-693`),
  `scripts/server_scan.py`.
- **User consulted?** Yes when candidates exist. The scan **never**
  rewrites the spec on its own.
- **Rule:** external acquisition is only reached after internal is
  exhausted or the user declines it.

### Gate 3 — Publish is opt-in

- **Trigger:** `--publish` on the CLI. Absent it, the run **stops at
  Phase 9** (local `.tfl` + report) and touches no server.
- **Branch on project:** exact project match → use it; missing/
  ambiguous → return candidates + near-matches for the user to pick;
  `--auto-create-project` pre-authorizes creating the (optionally
  nested) project.
- **Where decided:** `run_loop.py` (`--publish` is `store_true`,
  default False; `_maybe_publish` only fires under it),
  `scripts/publish.py`, `tflb_lib/publishing.py`.
- **User consulted?** At invocation (the flag) and again if the project
  is ambiguous.
- **Rule:** never write to a server without an explicit greenlight, and
  never embed credentials in the published artifact.

### Gate 4 — Always ship the final product *with* metadata

- **Trigger:** a successful publish that produced a
  `published_data_source`.
- **Branches:**
  - **Auto-apply (default).** Generate a DS-level description + one per
    column and write them back: DS description via REST, columns via
    the `.tds` XML round-trip (Cloud's Metadata API mutations are
    read-only, so this is the only working path — see
    `metadata_api.md`).
  - **`--review-metadata`** → write the proposal to
    `runtime/<run_id>/metadata_<output>.json` and stop for approval;
    rerun without the flag to apply.
- **Where decided:** `run_loop.py` Phase 11, `scripts/metadata_writer.py`.
- **User consulted?** Only under `--review-metadata`; the proposal is
  saved to disk either way as an audit trail.
- **Rule:** a published data source is not "done" until it carries a DS
  description and column descriptions. Standing preference: apply by
  default.

### Gate 5 — QA tier & the meaning of "passed"

- **Trigger:** `qa_tier` and `eval_strategy` are chosen at intake
  (Gate 6) from the source shape.
- **Branches:** `none` | `deterministic` | `llm`.
  - Script-node flows generally use **`qa_tier: none`**. There,
    `passed:false` / `final_mean:0.0` is **expected** — self-consistency
    has nothing to score. The **Hyper is ground truth**; inspect it,
    don't trust `passed`.
  - `deterministic` (default for structured sources) scores schema,
    null counts, distinct-value bounds.
- **Loop behavior:** the test loop is **bounded** (default 3
  iterations) and does **not** mutate the flow between runs — retries
  only absorb transient TabPy/DNS flakiness.
- **Where decided:** intake system prompt (`scripts/intake.py`), test
  loop in `scripts/run_loop.py`.

### Gate 6 — Intake confidence

- **Trigger:** every NL request goes through the LLM gateway to become
  a `spec.json`.
- **Branch:** low confidence on any required field → ask the user 1-2
  clarifying questions before proceeding; otherwise continue to plan +
  confirm.
- **Where decided:** `scripts/intake.py`, `scripts/llm_config.py`.
- **User consulted?** Only when confidence is low.

### Gate 7 — Credential discovery order

- **Trigger:** any phase that talks to the site (scan, publish,
  metadata) or any `internal_published_ds` source.
- **Order (most secure first):** already-set env vars → macOS Keychain
  → Linux secret-tool → `~/.tableau-prep-etl/server.json` (chmod 600,
  dev only).
- **Auth split:** **PAT** for scan / publish / metadata (TSC / REST /
  GraphQL). **Username + password** (separate Keychain entries) *only*
  for local prep-cli verify runs of internal-DS flows — Prep CLI
  v2026.1 rejects PATs in its `credentials.json`. The synthesized temp
  `credentials.json` is chmod 600 and deleted after the CLI exits.
- **On miss:** return `needs_user_decision` with platform-tailored
  secure-storage setup commands. The user is **never** asked to type a
  secret into the conversation.
- **Where decided:** `scripts/server_creds.py`. Full detail:
  `security.md`.

### Gate 8 — Archive after publish

- **Trigger:** every successful publish.
- **Action:** `scripts/archive_flow.py` snapshots into
  `flows/<name>/vN/` — TFL + spec + README + **sample rows only**.
  Never commit bulk or synthetic extracts (`.hyper`, full CSVs).
- **Rule:** standing preference — archive on every publish, no need to
  ask.

## One-line summary of the rails

1. **Simplified route by default** (advanced is a manual methodology, not a flag).
2. **Internal data before external** — always scan the site first unless told not to.
3. **Credentials from env/Keychain, never disk or artifact**; never typed into chat.
4. **Publish only on `--publish`.**
5. **Resolve or (with opt-in) create the target project.**
6. **Ship the DS with metadata** — DS + column descriptions, auto-applied.
7. **`qa_tier: none` for Script flows** — the Hyper is truth, `passed:false` is fine.
8. **Bounded, non-mutating test loop.**
9. **Archive every publish** — sample rows only.

## See also

- `../SKILL.md` — phase-by-phase mechanics and CLI flags.
- `operator_quickstart.md` — cold-start how-to.
- `advanced_collections_route.md` — the advanced route methodology.
- `server_publishing.md`, `metadata_api.md` — publish + metadata detail.
- `security.md` — credential storage and the no-creds-on-disk rule.
