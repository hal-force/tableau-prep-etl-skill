# Tableau Server / Cloud publishing

The skill publishes a built `.tfl` to Tableau Server or Tableau Cloud
when `--publish` is passed to `run_loop.py`. The publish step is
PAT-authenticated, project-pickered, schedule-aware, and Cloud-aware.

## What `--publish` actually does

1. **Auth.** `tflb_lib.publishing.config_from_env()` + TSC sign-in
   using a Personal Access Token. Required env vars:

   ```
   TABLEAU_SERVER_URL          # e.g. https://<your-pod>.online.tableau.com
   TABLEAU_SERVER_PAT_NAME
   TABLEAU_SERVER_PAT_SECRET
   TABLEAU_SERVER_SITE         # site contentUrl ("" for default site on Server)
   ```

2. **Project picker.** `_maybe_publish` lists site projects, matches
   `spec.server_publish.project` exactly. If no match, returns
   `needs_user_decision` with candidates + near-matches so the
   orchestrator can prompt the user — UNLESS `--auto-create-project`
   was passed, in which case the project is created with a generic
   description.

3. **Cloud-vs-Server flow execution.** Flows in this repo carry
   `published_data_source` outputs. On Server, a backgrounder run
   executes the flow and creates the DS. **On Cloud, backgrounder
   cannot run script nodes** (TabPy is not supported in Cloud's
   flow runner per
   `https://help.tableau.com/current/prep/en-us/prep_scripts_TabPy.htm`).
   The Cloud-friendly pattern this skill uses:

   - Run the flow locally via `prep-cli` to produce a `.hyper` extract.
   - Upload that `.hyper` as a published data source via
     `TSC.Server.datasources.publish(item, path, mode="Overwrite")`.
   - Publish the `.tfl` itself with `--publish` so the flow definition
     and schedule are visible on the site (the schedule is a no-op
     on Cloud for script-bearing flows, but the artifact is preserved
     for code review and re-running locally).

4. **PublishExtract routing patch.** Before upload,
   `_patch_publish_extract_routing` resolves the project LUID and:

   - Swaps any local `WriteToHyper` nodes carrying `_pds_target_*`
     markers (left over from `local_iteration` mode) back into
     `.v1.PublishExtract` nodes.
   - Patches every `.v1.PublishExtract` with `projectLuid` +
     `serverUrl`. Maestro requires the LUID — project names alone
     are non-unique site-wide and the Cloud backgrounder rejects
     run tasks without it.

5. **Schedule wiring.** Per `spec.server_publish.cadence` /
   `hour_utc` / `minute_utc`. On Cloud, hour/minute are stored as
   UTC; the skill returns `next_run_utc` so the user knows when to
   expect the next run.

### Publisher cadence map — sub-daily workaround

`tflb_lib.publishing` only maps four Cloud schedule primitives:
`hourly | daily | weekly | monthly`. Top-level `refresh_cadence`
accepts semantic values like `every_3_hours`, `every_6_hours`,
`every_12_hours` — but `server_publish.cadence` is validated
against the publisher-compatible set at spec-validation time. Using
a sub-daily alias there now raises `SpecValidationError` up-front
(older builds raised `KeyError` deep in publish).

Working pattern for sub-daily flows (embassy_threat_monitor_v2,
doe_data_center_energy_hourly):

```jsonc
{
  "refresh_cadence": "every_3_hours",          // semantic — validated but not publisher-consumed
  "server_publish": {
    "project": "…",
    "parent_project": "…",
    "cadence": "hourly",                        // publisher-compatible
    "schedule_name_hint": "… Every 3h Refresh"  // encodes the intended interval for the operator
  }
}
```

The operator can retune the schedule interval in the Cloud UI
post-publish; the schedule-name hint tells them what to set it to.
Extending `tflb_lib.publishing` to emit hour-count intervals
(`<interval hours="3"/>`) is on the v2 backlog.

## local_iteration mode

`run_loop` flips `local_iteration=True` whenever the spec has any
`published_data_source` output OR any `internal_published_ds` source
has been downloaded (Phase 4a). In this mode:

- Every `published_data_source` output becomes a local
  `WriteToHyper` carrying `_pds_target_*` markers.
- Every `internal_published_ds` source becomes a `LoadCsv` reading
  the Phase 4a download.
- The flow runs end-to-end locally with no live server auth (which
  bypasses MFA on Cloud sites).

At publish time, `_patch_publish_extract_routing` does the inverse
swap so the .tfl uploaded to the server has the proper
PublishExtract shape.

## Local-dev helper: macOS Keychain auto-load

The skill has a `~/.tableau-prep-etl/load_env.sh` convention. On
first setup, run:

```sh
python3 -m skill.scripts.server_creds --load
```

Walks env → macOS Keychain (`security find-generic-password`) →
Linux libsecret (`secret-tool`) → `~/.tableau-prep-etl/server.json`
(chmod 600 plaintext, local dev only). Stores the values it finds
in Keychain so future shells just `source ~/.tableau-prep-etl/load_env.sh`.

Keychain accounts under service `tableau-prep-etl`:

- `url`, `pat-name`, `pat-secret`, `site` — REQUIRED for publish.
- `tableau-username`, `tableau-password` — only used to synthesize
  prep-cli credentials.json for `sqlproxy` connections (legacy
  Server path; not needed on Cloud).

## MFA / Tableau Cloud — PATs only

Tableau Cloud's MFA-on-every-login blocks prep-cli's
`credentials.json` username/password path entirely. The PAT path
works because PATs don't go through the interactive auth flow.
For MFA-protected sites:

- All server interactions use PAT auth (REST + Metadata API).
- Flow execution stays local (script nodes can't run on Cloud
  backgrounder anyway).
- Data sources are published via TSC's `datasources.publish` rather
  than left to backgrounder.

## Project picker: avoiding silent project creation

By default, missing projects bounce back as `needs_user_decision`
so the orchestrator can prompt before creating anything. The user
can:

- Pick an existing project (replaces `spec.server_publish.project`).
- Type a different name (re-prompts; recursive).
- Approve creating the configured project.

`--auto-create-project` flips this to auto-approve — useful for
CI / batch runs where there's no interactive user.

**Cache-warmup quirk:** if `--auto-create-project` creates a project
and the publish step runs in the same TSC session, `publish_run`'s
project lookup may not see the freshly-created project (TSC re-fetches
projects but the server-side index sometimes lags by a few seconds).
Workaround: when this fails, rerun `--publish` without
`--auto-create-project` — the project exists by then and the publish
lands cleanly. See `feedback_publish_project_create_quirk.md`.

**Fully manual publish path (recovery):** when the whole run_loop
can't be re-driven (e.g. the local verify run has already succeeded
and we only need to attach the artifact to a new project on Cloud),
skip `run_loop.py --publish` entirely and invoke the pieces directly:

1. `publish.py <spec> <run_dir>/<flow>.tfl --run-dir <run_dir>` publishes
   the TFL + creates the schedule (this alone does NOT create the
   project; use `publish.py --create-project "<name>"` if needed).
2. If the CLI-created project landed at the site root (no `parent_id`
   set), reparent it via TSC: `p.parent_id = <prep-agent-id>` then
   `server.projects.update(p)` — `--create-project` doesn't accept a
   parent flag.
3. Invoke `_upload_hypers_as_published_datasources(spec, run_dir,
   publish_result)` from `run_loop` in a Python REPL, passing a
   hand-built `publish_result` dict with `status="ok"`, `is_cloud=True`,
   and the flow/project ids from step 1.
4. Inject the returned DS LUIDs into `publish_result["datasources"]`
   and call `_maybe_write_metadata(spec, publish_result, run_dir)`.
5. `archive_flow.py --spec … --run-dir … --flow-name …` to snapshot.

All five steps are idempotent — safe to re-run individually. This
is the same pattern the SLED batches (flows 21-30) settled on when
the auto-create-project cache quirk left projects half-attached.

## Output

The `--publish` step adds a `publish` block to the run result:

```json
{
  "publish": {
    "status": "ok",
    "flow_id": "0919ba1d-2eb3-40a7-9765-f33498fece4a",
    "flow_name": "OTF Grants Enriched",
    "project_id": "a201202f-28bd-43b2-ab2c-f59a2c31ad3e",
    "project_name": "Grants",
    "schedule_id": "1b7f521a-...",
    "schedule_name": "OTF Grants Monthly Refresh",
    "task_id": "4a8ab79c-...",
    "fire_hour": 8,
    "fire_minute": 0,
    "cadence": "monthly",
    "web_url": "https://...",
    "is_cloud": true,
    "next_run_utc": "2026-07-01T12:00:00Z"
  }
}
```

The DS itself (for the Cloud-friendly local-prep-then-publish-DS
pattern) is uploaded **separately** via TSC after the local prep-cli
run; see `flows/otf_grants/v1/`, `flows/us_wildfires_eoc/v1/`, and
`flows/us_grid_network/v1/` for worked examples that show the full
sequence.

## Catalog indexing lag on Tableau Cloud

Cloud has two separate views of a published DS:

- **REST + TSC** — `datasources.get_by_id(luid)` reflects publish
  state synchronously. Authoritative.
- **GraphQL Metadata API + the lineage / Data Details browser pages**
  — backed by an async Catalog index that lags **10-30+ minutes**
  after a publish. The lineage page typically returns
  *"Information for this page not found. It may still be loading,
  or you don't have permissions to view it."* during the window.

Don't gate post-publish verification on the GraphQL readback or the
lineage page. Use the REST DS-info call to confirm the artifact is
on the site; use a re-download of the .tdsx + XML parse to verify
column descriptions made it through the .tds round-trip. Both of
those are synchronous.

When a user reports a 404 on the lineage page right after publish:
verify via REST first, then tell them to wait 10-30 min. It is not
a publish failure or a permissions problem.

## pds_uploads LUID injection

For Cloud-friendly local-prep flows, `_maybe_publish_pds_uploads`
returns the LUID of every freshly-uploaded DS. **Inject those LUIDs
into `publish_result['datasources'][i]['luid']` before the metadata
writer runs.** Otherwise the writer falls back to a name-based
lookup that races the same Catalog search index — leading to writes
against the wrong DS, or silent skips when the index hasn't caught
up. See `feedback_pds_luid_injection.md`.

## Phase 11: post-publish metadata writer

After a successful `--publish`, `_maybe_write_metadata` runs against
each `published_data_source` output. It looks up the DS LUID by
name in the target project (since flow-publish doesn't carry DS
LUIDs), then:

1. Calls `metadata_writer.generate_descriptions` (LLM-assisted
   descriptions; needs `LLM_GATEWAY_URL/KEY/MODEL` configured).
2. Always saves the proposal to
   `runtime/<run>/metadata_<output>.json` as audit trail.
3. Calls `metadata_writer.apply_descriptions`:
   - DS-level via TSC `datasources.update`.
   - Per-column via the .tds round-trip (see `metadata_api.md`).

`--review-metadata` stops after step 2 so the user can approve
the proposal before push.
