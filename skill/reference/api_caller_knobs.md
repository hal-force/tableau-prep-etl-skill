# `api_caller` source knobs reference

Every `source.type == "rest_api"` (and `graphql_api`) entry on a
spec.json renders the `templates/api_caller.py.j2` Python step. The
`source.extra` block is a flat dict of knobs that configure the
fetcher, schema declaration, pagination, and post-fetch column
synthesis.

This page is the canonical reference for every knob the template
honors today. Every flow in `flows/<name>/v1/spec.json` is a worked
example — when in doubt, copy the closest one and edit.

## Top-level source fields

```jsonc
{
  "type": "rest_api",         // 'rest_api' | 'graphql_api' | 'native_connector' | 'local_folder' | 'web_crawl' | 'pki_endpoint' | 'internal_published_ds'
  "name": "Source Display",   // shows up as the input node label in Tableau Prep
  "description": "...",       // becomes the input node description
  "url": "https://...",       // base URL; pagination knobs append query params or POST a JSON body
  "format": "json",           // 'json' | 'jsonl' | 'ndjson' | 'csv' | 'csv_zip' | 'csv_index_then_zip' | 'arcgis_features'
  "auth": "none",             // 'none' | 'api_key' | 'basic' | 'query_key'
  "extra": {                  // EVERYTHING below goes here
    "...": "..."
  }
}
```

`extra._skip_auto_casts: true` is set on every Prep Agent demo
spec — it disables the cast planner so the schema declared in
JSON_SCHEMA / CSV_SCHEMA flows through verbatim. Skip this and the
cast planner can introduce ChangeColumnType nodes that don't match
the actual data shape, dropping rows silently.

## HTTP transport

| Knob                | Default                | Use                                                                   |
|---------------------|------------------------|-----------------------------------------------------------------------|
| `verify_ssl`        | `true`                 | Set to `false` only for self-signed dev endpoints.                    |
| `timeout_s`         | `120`                  | Per-request timeout. Bump for slow public APIs (EPA AQS, Federal Register at scale). |
| `max_retries`       | `3`                    | Retries on `URLError` / `TimeoutError` and 5xx / 429. 4xx other than 429 is treated as permanent. |
| `api_key_env`       | `'API_KEY'`            | (auth=='api_key' \| 'query_key') env var holding the bearer token / query-string key. Never put the secret in the spec. |
| `user_env`          | `'API_USER'`           | (auth=='basic') env var holding the username.                         |
| `pwd_env`           | `'API_PASSWORD'`       | (auth=='basic') env var holding the password.                         |
| `query_key_param_name` | `'api_key'`         | (auth=='query_key') the URL query-string parameter that carries the key. EIA v2 → `api_key`, some Data.gov endpoints → `apikey`, NREL → `api_key`. |

**`auth: 'query_key'`** — for publishers that authenticate via
`?<param>=<secret>` on the URL rather than a Bearer header. Set
`auth: 'query_key'`, `extra.api_key_env: 'EIA_API_KEY'` (or
whatever env var carries the secret; must be exported into the
TabPy daemon's environment — see
`tabpy_setup.md #Restart TabPy after adding a source-credential env var`),
and optionally `extra.query_key_param_name` if the publisher uses
a param name other than `api_key`. Worked example:
`flows/doe_data_center_energy_hourly/v1/spec.json`.

**Strict-API gotcha:** the helper drops `Content-Type: application/json`
on bodyless GET requests. Some publishers (notably EPA AQS) parse
unexpected request headers as query parameters and return HTTP 400
"found unpermitted variable" if the header is set. No knob — handled
automatically.

## JSON sources (`format: "json" | "jsonl" | "ndjson"`)

### Schema + envelope

| Knob                  | Default     | Use                                                                            |
|-----------------------|-------------|--------------------------------------------------------------------------------|
| `json_schema`         | `{}`        | `{column_name: 'string'\|'int'\|'decimal'\|'bool'\|'date'\|'datetime'}`. Required for any flow that declares trend_analysis or has downstream Maestro casts — otherwise Tableau rejects with type mismatches. |
| `json_records_path`   | `''`        | Dotted path through the response envelope to the records list. `''` falls back to common keys (`results`, `data`, `items`, `records`, `rows`). Use for nested envelopes (BLS: `'Results.series'`, OpenFEMA: `'DisasterDeclarationsSummaries'`, USAspending: `'results'`). Numeric segments index into lists. |
| `json_array_columns`  | `[]`        | Names for positional-array rows. OpenSky returns `[[icao24, callsign, country, …], …]` instead of dicts; this knob assigns a column name to each index. Length determines how many positions are kept. |
| `json_flatten_inner_key`    | `''`  | When the records list is `[{parent_field, inner: [{...}, ...]}, ...]`, this is the key on each parent that holds the inner list to expand. BLS uses `'data'`. |
| `json_flatten_parent_keys`  | `[]`  | Companion to the above: list of fields on the parent dict to copy onto each emitted row. BLS uses `["seriesID"]` so the seriesID flows down to each monthly observation row. |

### POST + body

| Knob                | Default | Use                                                                       |
|---------------------|---------|---------------------------------------------------------------------------|
| `json_http_method`  | `'GET'` | Set to `'POST'` for APIs that take filter / query bodies (BLS, USAspending). |
| `json_body`         | `null`  | Dict to send as the JSON body. Sent verbatim. For APIs like USAspending, this is your `filters`/`fields`/`limit` envelope. |

### Pagination

`json_paginate: true` is the master switch. The walker handles
three pagination styles: index-style page numbers (`page=1,2,3`),
offset-style (`offset=0,N,2N`), and body-side page tokens. All three
walk until the publisher signals "done" (total-pages reached, empty
page, underfilled page, `has_next == false`, or 4xx mid-walk after
rows already collected).

| Knob                    | Default        | Use                                                                       |
|-------------------------|----------------|---------------------------------------------------------------------------|
| `json_paginate`         | `false`        | Master switch. When false, a single request is made.                      |
| `json_page_kind`        | `'index'`      | `'index'` (page=1,2,3) or `'offset'` (offset=0,N,2N).                    |
| `json_page_param`       | `'page[number]'` | Query-string key for the page or offset. `'page'`, `'offset'`, `'$skip'`, etc. |
| `json_page_size_param`  | `'page[size]'` | Query-string key for the page size. `''` to skip emitting it.            |
| `json_page_size`        | `1000`         | Rows per page. **Cap to whatever the publisher allows** — CMS Provider Data caps at 1000, College Scorecard API caps at 100. When unsure, probe with curl first. |
| `json_page_start`       | `1`            | First page index (use `0` for zero-indexed APIs like College Scorecard).  |
| `json_max_pages`        | `200`          | Hard cap to prevent runaway loops on broken APIs.                         |
| `json_page_in_body`     | `false`        | When true (and method=POST and body set), the page param goes IN the body, not the URL. USAspending et al. |
| `json_has_next_path`    | `''`           | Dotted path to a boolean termination flag (USAspending: `'page_metadata.hasNext'`). When that field is `false`, the walk ends. |

### Post-fetch column synthesis

`json_derived_columns` is a list of dicts; each one synthesizes a
new column from existing columns, AFTER fetch but BEFORE the JSON_SCHEMA
trim. Kinds available today:

| Kind               | Args                                                                     | Output                                                              |
|--------------------|--------------------------------------------------------------------------|---------------------------------------------------------------------|
| `year_month_iso`   | `{name, year_col, period_col}`                                           | `'YYYY-MM-01'` ISO-string from year + BLS-style `M01..M12`.        |
| `concat`           | `{name, cols, sep}`                                                      | Joins string-cast cols with a separator.                            |
| `list_join`        | `{name, source_col, sep}`                                                | Flattens a list-valued column to a delimited string. CISA KEV `cwes`. |
| `list_first_field` | `{name, source_col, field}`                                              | Pulls a named field out of the FIRST dict in a list-valued column. Federal Register `agencies[0].name`. |
| `dict_field`       | `{name, source_col, field}`                                              | Pulls a named field out of a dict-valued column. USAspending `NAICS.code`. |
| `days_since`       | `{name, source_col}`                                                     | Calendar days from an ISO-date column to today (UTC).               |
| `days_between`     | `{name, start_col, end_col}`                                             | Calendar days between two ISO-date columns.                         |

Declared derived columns must also appear in `json_schema` (with
their target type) or they get trimmed out before the dataframe
reaches Tableau Prep.

## CSV sources (`format: "csv" | "csv_zip"`)

| Knob               | Default   | Use                                                                   |
|--------------------|-----------|-----------------------------------------------------------------------|
| `csv_encoding`     | `'utf-8'` | Some open-data publishers ship Latin-1 (OTF). Set to `'latin-1'`.    |
| `csv_rename_map`   | `{}`      | Rename columns post-read (helpful for bilingual headers).             |
| `csv_schema`       | `{}`      | `{column_name: 'string'\|'int'\|'decimal'\|...}`. Same coercion semantics as `json_schema` — every declared column gets coerced after read, so sentinel strings like `'PrivacySuppressed'` (College Scorecard) become NaN cleanly. |
| `csv_usecols`      | `[]`      | Trim a wide CSV to a useful subset. Applied post-rename.              |
| `csv_zip_member`   | `''`      | (csv_zip only) Name of the CSV inside the ZIP. Defaults to the first `.csv` member. |

## ArcGIS sources (`format: "arcgis_features"`)

| Knob                         | Default  | Use                                                                  |
|------------------------------|----------|----------------------------------------------------------------------|
| `arcgis_where`               | `'1=1'`  | ArcGIS WHERE clause for server-side filtering.                       |
| `arcgis_out_fields`          | `'*'`    | Comma-separated field list. Cap to what you need; full `*` makes Maestro unhappy on wide layers. |
| `arcgis_field_types`         | `{}`     | Pin types per field (`{ID: 'string', VOLTAGE: 'decimal'}`). **Always wins over heuristics** — use this when CamelCase field names trip the cast planner (e.g. `ActiveFireCandidate` heuristically looks date-like). |
| `arcgis_page_size`           | `1000`   | Records per page. ArcGIS often caps at 2000.                         |
| `arcgis_max_records`         | `0`      | Hard cap on total rows (0 = no cap).                                 |
| `arcgis_return_geometry`     | `true`   | Emit `latitude`/`longitude` (point) or `start_lon/lat + end_lon/lat` (polyline). |
| `arcgis_geometry_kind`       | `'point'`| `'point'` or `'polyline'`.                                           |
| `arcgis_out_sr`              | `4326`   | Output spatial reference. `4326` = WGS84 lat/lon — leave it.         |

## CSV-index-then-zip (GDELT-shape)

`format: "csv_index_then_zip"` is a specialty mode for publishers
that ship a small index page listing dated zip files (GDELT). It uses
`extra.index_link_pattern` (a regex) to pluck zip URLs out of the
index HTML. See `flows/gdelt_global/v1/spec.json` for the only
worked example today.

## When to NOT use api_caller

If the source is a Tableau-native connector (Snowflake, Postgres,
SQL Server, Excel, CSV file you'll point Tableau at directly), use
`type: "native_connector"` instead. The api_caller is for HTTP
publishers that don't have a native Tableau connector — public
open-data REST/JSON, ArcGIS feature layers, GraphQL gateways.

## Adding a new derived-column kind

The `json_derived_columns` dispatch lives at the top of
`_apply_json_schema_coercion` in
`skill/templates/api_caller.py.j2`. To add a new kind:

1. Add the `elif kind == "..."` branch with the transform logic.
2. Add it to the table above with a one-line description and
   required args.
3. Use it in a flow spec; commit the working pattern as a
   reference example under `flows/<name>/v1/`.

The bar for adding a new kind: **at least one real flow needs it,
and the same shape isn't already covered**. If two existing kinds
chain to give you what you want (e.g. `concat` + `days_between`),
prefer composition over a new kind.
