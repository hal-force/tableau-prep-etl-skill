# Prep Agent — 10-Test Demo Collection Report

**Site:** `<pod>.online.tableau.com / <site>` (sanitized)
**Parent project:** `Prep Agent` (luid `8f69f297-91df-4e0a-bb57-98417e70a375`)
**Date completed:** 2026-06-19
**Repo range:** `9556015..7e5929e` (11 commits)

## What this collection demonstrates

The **Agentic Prep ETL skill** turns a natural-language ETL request
into a tested, server-published Tableau Prep flow. The Prep Agent
collection is **a scope-of-capability demo**: ten public-sector
verticals, ten different upstream-data shapes, one end-to-end pipeline
each — all built on the same skill, all published side-by-side as
nested child projects under `Prep Agent` so a customer can browse
them in one place and see what's possible.

Specifically, this collection demonstrates that the skill can:

1. **Plan an ingestion strategy from upstream API shape**, not just
   "REST or not". The 10 sources cover JSON pagination (3 styles),
   POST + body queries, nested envelopes, list-of-list positional
   rows, ZIP-wrapped CSV bulk downloads, OData `$top/$skip`, ArcGIS
   feature services. Each requires different fetcher behavior; the
   skill handles each via `extra.*` knobs in the spec — no per-source
   custom code.

2. **Apply per-row enrichment without dropping into Python.** Seven
   declarative `json_derived_columns` kinds (`year_month_iso`,
   `concat`, `list_join`, `list_first_field`, `dict_field`,
   `days_since`, `days_between`) cover the common shapes — flattening
   nested dict/list fields, computing day deltas for SLA / aging
   buckets, building ISO date strings from year+period codes.

3. **Produce statistically-enriched outputs analysts can use
   immediately.** Eight of the 10 flows pair a row-level Detail data
   source with a long-form Stats data source via the `trend_analysis`
   transformation: monthly counts, 30-365 day rolling baselines,
   year-over-year deltas + pct-change, z-score anomalies vs lifetime
   baseline (configurable threshold), lifetime rank and pct_of_total.
   Joinable to the Detail extract from a Tableau workbook on
   `(dimension, value, year, month)`.

4. **Land cleanly on Tableau Cloud despite Cloud's
   no-script-nodes-on-backgrounder constraint.** Every flow runs
   locally via `prep-cli` to produce its `.hyper` extracts; the skill
   then uploads each as a published data source via TSC, AND
   publishes the `.tfl` for visibility/code-review/scheduling. This
   "local prep + Hyper-as-PDS" pattern is automatic when the publish
   target is a Cloud site.

5. **Organize demos in nested projects** for browseability.
   `parent_project` on the spec's `server_publish` block resolves
   `project` as a child under the named parent (auto-creating both
   under `--auto-create-project`).

## The 10 tests

Each test row carries: vertical • source • upstream shape feature •
output rows • Detail/Stats Hyper sizes • capability shipped to the
skill during this run.

| #  | Vertical (intended use)              | Source                                                   | Upstream shape feature                                          | Detail / Stats     | Capability added                                                |
|----|--------------------------------------|----------------------------------------------------------|-----------------------------------------------------------------|--------------------|-----------------------------------------------------------------|
| 01 | **Finance** — federal spending track | Treasury Fiscal Data MTS Table 5 (2018-2025, level=1)    | JSON:API `page[number]/page[size]` walk + `record_calendar_year` filter | 128 KB / 65 KB     | `json_paginate` index-mode, `json_schema` declared coercion, parent_project nested layout, Hyper-as-PDS upload |
| 02 | **HR** — federal headcount trends    | BLS Public Data API CES (5 federal series, 2018-2025)    | POST + JSON body, nested `Results.series[*].data[*]` + flatten  | 65 KB / 65 KB      | `json_http_method=POST`, `json_body`, `json_records_path`, `json_flatten_inner_key`, `json_derived_columns: year_month_iso` |
| 03 | **Cyber** — exploit SLA dashboard    | CISA Known Exploited Vulnerabilities catalog             | List-typed `cwes` field, `dateAdded → dueDate` SLA window       | 393 KB / 65 KB     | `json_derived_columns: list_join`, `json_derived_columns: days_between`, JSON_BODY null-rendering fix |
| 04 | **Case Mgmt** — regulatory backlog   | Federal Register API documents (2025+)                   | Nested `agencies: [{name, slug, ...}]` flatten, page-walk        | 2.4 MB / 65 KB     | `json_derived_columns: list_first_field`, `json_derived_columns: days_since` |
| 05 | **Public Safety** — disaster cases   | OpenFEMA Disaster Declarations Summaries v2 (2022+)      | OData `$top/$skip`, custom envelope `DisasterDeclarationsSummaries` | 197 KB / 65 KB     | Paginated walk uses `_extract_json_records` (envelope-aware on every page), `json_records_path` resolver |
| 06 | **Health** — long-term-care surveillance | CMS Provider Data — Nursing Home Health Deficiencies   | Limit/offset pagination with publisher-imposed page-size + offset cap | 852 KB / 65 KB     | `_http_get_bytes` 4xx-immediate (no retry), paginated walk treats mid-walk 4xx as "done" if rows already collected |
| 07 | **Education** — institution comparisons | College Scorecard "Most Recent Cohorts" bulk ZIP        | ZIP-wrapped CSV (3308 cols → 23-col slice), `PrivacySuppressed` sentinels | 1.2 MB             | New `csv_zip` format, `csv_zip_member` selector, CSV per-column int/decimal/bool coercion |
| 08 | **Transportation** — live airspace   | OpenSky Network /api/states/all (US bbox)                | Positional `[icao24, callsign, …]` arrays instead of dicts      | 459 KB             | `json_array_columns` positional projection                       |
| 09 | **Environment** — air-quality surveillance | EPA Air Quality System Data API (CA ozone, Jan 2024)   | Strict-API rejection of unexpected `Content-Type` on GET         | 131 KB / 65 KB     | Drop `Content-Type` on bodyless GET in both `_http_get_bytes` + `_http_request_json` |
| 10 | **Procurement** — federal contract awards | USAspending.gov spending_by_award (H1 2025)            | POST body-side pagination, `page_metadata.hasNext` cursor, nested NAICS dict | 524 KB / 131 KB    | `json_page_in_body`, `json_has_next_path` cursor termination, `json_derived_columns: dict_field` |

## Server-side collateral (LUIDs are clickable in Tableau)

All entities live under the `Prep Agent` parent project on the
active Tableau Cloud site (site details sanitized in this repo).

### 01 - Federal Outlays  (project `d11fc726-106f-4213-86d1-184ee4d29839`)
- Flow: `Federal Outlays Trend` — `97b40277-4399-4162-9c49-23aed26ccb76`
  — schedule **Federal Outlays Monthly Refresh** (next: 2026-07-01 13:00 UTC)
- DS:   `Federal Outlays Detail` — `db010c2b-40e8-48e1-8bf1-415fdf60385f`
- DS:   `Federal Outlays Stats`  — `0c876948-f3db-465f-9d66-d3168e4d0441`

### 02 - Federal Workforce  (project `6cfa2766-39b6-431a-9811-2c8c5c7d2210`)
- Flow: `Federal Workforce Trend` — `0b4aa2d5-4dad-4c2d-b8e7-04f28bcfb440`
  — schedule **Federal Workforce Monthly Refresh** (next: 2026-07-05 13:30 UTC)
- DS:   `Federal Workforce Detail` — `f539f9a6-6632-4981-9473-34eee1d731fd`
- DS:   `Federal Workforce Stats`  — `c5026e8d-4c16-41b2-9039-0493c803c257`

### 03 - CISA KEV  (project `4103d252-6685-4621-abac-d6272c18b48c`)
- Flow: `CISA KEV Trend` — `bfa1dc8c-4825-4399-9cc6-90cbecca722f`
  — schedule **CISA KEV Weekly Refresh** (next: 2026-06-23 13:00 UTC)
- DS:   `CISA KEV Detail` — `237e69ea-a62c-41d2-b4dc-6f879e8e10a3`
- DS:   `CISA KEV Stats`  — `fe00cf10-fa12-4117-b930-3b494d4eaef9`

### 04 - Federal Register Actions  (project `21f76a14-c597-418a-bc6b-110a68a91bc0`)
- Flow: `Federal Register Actions` — `40295e9b-dc3f-4ec3-89b9-4fbf529014ff`
  — schedule **Federal Register Weekly Refresh** (next: 2026-06-22 13:00 UTC)
- DS:   `Federal Register Detail` — `4afdaf55-c468-4cd9-b5c2-a0c579b752c2`
- DS:   `Federal Register Stats`  — `9c729a30-5418-4d3f-b4fb-98d892a6c57d`

### 05 - FEMA Disaster Cases  (project `a2c86539-f845-47f3-b4cd-0dfaeaae64b7`)
- Flow: `FEMA Disaster Cases` — `69409449-e0ae-4b3d-a347-727c6198def9`
  — schedule **FEMA Disaster Monthly Refresh** (next: 2026-07-05 18:00 UTC)
- DS:   `FEMA Disaster Detail` — `de26b181-727f-4fd1-bc45-324863e8e275`
- DS:   `FEMA Disaster Stats`  — `7e6f2268-222a-4bd7-8ef2-ea1e2abdd7bc`

### 06 - CMS Nursing Home Surveillance  (project `9cdb9a86-3730-4e0e-a5f8-db1e5a5f3e02`)
- Flow: `CMS Nursing Home Deficiencies` — `61919335-bb3f-4379-b25f-35a528c70a83`
  — schedule **CMS Deficiencies Monthly Refresh** (next: 2026-07-05 18:00 UTC)
- DS:   `CMS Deficiency Detail` — `774213e6-b851-40c5-a715-98911aa3fd74`
- DS:   `CMS Deficiency Stats`  — `9deb5efb-9e76-4250-ac92-526a63f5e376`

### 07 - College Outcomes  (project `0a858b2a-3615-4ff6-b1b7-717385fe7d28`)
- Flow: `College Scorecard Outcomes` — `d6f4a1cd-ebbc-4a64-af28-5014d979dd5e`
  — schedule **College Scorecard Monthly Refresh** (next: 2026-07-07 18:30 UTC)
- DS:   `College Scorecard Outcomes` — `0da80e0a-c750-4c17-b278-5ee9c0850e1f`

### 08 - Live US Air Traffic  (project `e1391519-59b4-4dd9-b23f-d59134ee85a3`)
- Flow: `OpenSky US Live States` — `fe3d64be-cf3e-44ef-a60f-7324e996ddfc`
  — schedule **OpenSky 5min Refresh** (hourly cadence; next: 2026-06-19 04:00 UTC)
- DS:   `OpenSky US Live States` — `7b09f4ac-3dda-485b-a9d9-b178674acc14`

### 09 - EPA Air Quality  (project `8cd1d729-d0e6-4972-b0f4-de773891ea0b`)
- Flow: `EPA Ozone Surveillance` — `cbca791d-bf0b-4713-ad46-257a68117f18`
  — schedule **EPA Ozone Monthly Refresh** (next: 2026-07-07 18:00 UTC)
- DS:   `EPA Ozone Detail` — `e839b508-91fe-400a-a4f6-e195b8ce91c3`
- DS:   `EPA Ozone Stats`  — `a5de5682-61a8-4f97-b223-f767ac26586f`

### 10 - Federal Contract Awards  (project `420d431d-2185-442d-bfd8-457de8604500`)
- Flow: `USAspending Contract Awards` — `ed9ac149-bae5-425d-9c09-7dcd3e5e2905`
  — schedule **USAspending Monthly Refresh** (next: 2026-07-07 18:30 UTC)
- DS:   `Federal Award Detail` — `05578bb7-b94c-48b9-8361-84332fd3d051`
- DS:   `Federal Award Stats`  — `806d1b55-d951-4fe8-92bb-e1ade0b489d1`

**Site-side totals:** 1 parent project + 10 child projects, 10
flows, 17 published data sources, 10 schedules.

## Repo collateral

Per-flow archives live at `flows/<flow>/v1/`. Each carries:

```
flows/<flow>/v1/
├── README.md              # auto-generated (planner summary + sample stats)
├── spec.json              # cred-scrubbed spec; the canonical reproducible artifact
├── flow.tfl               # PublishExtract shape (server-ready, not local-iteration)
└── sample_output/
    └── *.hyper            # real Hyper sample (these are public open-data feeds)
```

Run any archived flow cold with:

```sh
python3 -m skill.scripts.run_loop \
    --spec flows/<flow>/v1/spec.json \
    --flow-name <flow> --skip-scan
```

## Skill capabilities shipped during the sweep

The 10 tests added 11 commits to the skill. Each commit added a
single capability driven by a real upstream-data shape, never
speculative — the bar is "a real flow we want to ship needs this."

| Commit (in order) | Capability                                                                  |
|---|---|
| `bdf61ec` | JSON pagination + parent-project + Hyper-as-PDS upload                       |
| `78a05f2` | JSON POST + flatten + derived columns                                        |
| `3898978` | `list_join` + `days_between` derived columns; fix `JSON_BODY` tojson         |
| `08531b3` | `list_first_field` + `days_since` derived columns                            |
| `eaa2db0` | 4xx pagination guards + sub-walk record extraction                           |
| `f18c934` | `csv_zip` format + per-column CSV schema coercion                            |
| `ee4042c` | `JSON_ARRAY_COLUMNS` positional projection                                   |
| `0d1250c` | Drop `Content-Type` on GET with no body                                      |
| `c732065` | `JSON_PAGE_IN_BODY` + `dict_field` flatten                                   |
| `774e230` | README — Prep Agent 10-flow demo collection table                            |
| `7e5929e` | Document `api_caller` knobs + nested-project publish + Prep Agent flows      |

Total surface added to `skill/templates/api_caller.py.j2`:
- 9 new `extra.*` knobs (`json_paginate`, `json_page_param`,
  `json_page_size_param`, `json_page_size`, `json_page_start`,
  `json_page_kind`, `json_max_pages`, `json_page_in_body`,
  `json_has_next_path`)
- 6 new envelope/transport knobs (`json_http_method`, `json_body`,
  `json_records_path`, `json_array_columns`, `json_flatten_inner_key`,
  `json_flatten_parent_keys`)
- 7 new derived-column kinds (`year_month_iso`, `concat`, `list_join`,
  `list_first_field`, `dict_field`, `days_since`, `days_between`)
- 1 new source format (`csv_zip` + `csv_zip_member`)
- 1 new `JSON_SCHEMA` declared-coercion path
- 4 reliability fixes (4xx no-retry, mid-walk 4xx as done, drop
  Content-Type on bodyless GET, JSON_BODY None Jinja rendering)

Documentation updates: `skill/reference/api_caller_knobs.md` (new,
catalogues every knob), README "Authoring a spec from scratch"
section, expanded troubleshooting (10 new symptom→fix rows),
SKILL.md transformation-kinds table.

## What didn't work — limits surfaced by the sweep

1. **api.data.gov DEMO_KEY exhaustion**: College Scorecard's REST API
   shares a `DEMO_KEY` rate budget with thousands of other users; the
   key was exhausted hourly. Pivoted to the keyless ZIP bulk
   download. **Implication:** for production, register a real
   api.data.gov key — DEMO_KEY is a starter, not a sustainability
   path.

2. **Socrata-fronted endpoints (NYC, CDC) intermittently
   unreachable**: `data.cityofnewyork.us` and `data.cdc.gov` both
   front-ended by `nlb.aws-us-east-1-fedramp-prod.socrata.net`,
   which timed out from this network during the sweep. Pivoted to
   keyless alternatives (FEMA, CMS) that lived on different
   infrastructure. **Implication:** any production demo that relies
   on a specific Socrata domain should have a fallback plan.

3. **CMS Provider Data publisher caps**: 1000-row page-size cap and
   ~30,000-row offset cap, undocumented. Discovered by probing.
   The 4xx-graceful pagination guard now handles publishers that
   400 past their cap mid-walk.

4. **EPA AQS strict header parsing**: `Content-Type: application/json`
   on a GET (no body) returns HTTP 400 "found unpermitted variable
   in request" — the proxy parses unexpected request headers as
   query parameters. Fixed by stripping Content-Type on bodyless
   GETs.

5. **LLM gateway not configured**: every metadata-write phase
   (column descriptions on the published data sources) errored with
   `LLM gateway not configured`. The flows + DS publish path are
   unaffected. **To complete**: set `LLM_GATEWAY_URL/KEY/MODEL` env
   vars or run `python3 -m skill.scripts.llm_config`, then re-run
   any flow with `--publish` to backfill column metadata via the
   .tds-roundtrip writer.

## Reproducibility

Anyone with PAT access to a Tableau Cloud (or Server) site can
reproduce any flow:

```sh
git clone https://github.com/hal-force/tableau-prep-etl-skill
cd tableau-prep-etl-skill
ln -s "$PWD/skill" ~/.claude/skills/tableau-prep-etl
pip install -r requirements.txt
# TabPy on :9099 + Keychain creds: see README "First-run setup"
source ~/.tableau-prep-etl/load_env.sh

# Reproduce e.g. fed_outlays:
python3 -m skill.scripts.run_loop \
    --spec flows/fed_outlays/v1/spec.json \
    --flow-name fed_outlays --skip-scan --publish --auto-create-project
# (rerun without --auto-create-project on first publish to dodge the
# project-cache-warmup quirk)
```

The full first-run path is documented in the repo's `README.md`
("Authoring a spec from scratch" section) and
`skill/reference/api_caller_knobs.md`.
