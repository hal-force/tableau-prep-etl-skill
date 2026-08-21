# Example: GDELT online pull

User request:

> Pull the latest GDELT events for the United States and load them into a
> Tableau Hyper extract. Refresh daily.

## Spec produced by `intake.py`

```json
{
  "sources": [{
    "type": "rest_api",
    "name": "GDELT Events",
    "url": "http://data.gdeltproject.org/events/index.html",
    "format": "csv_index_then_zip",
    "auth": "none",
    "extra": {
      "country_filter": "US",
      "verify_ssl": true,
      "max_retries": 3
    }
  }],
  "transformations": [],
  "outputs": [{"kind": "hyper", "name": "gdelt_us_events"}],
  "qa_tier": "deterministic",
  "eval_strategy": "sample_validation",
  "deployment": "local",
  "refresh_cadence": "daily"
}
```

> **Schema note.** Source-acquisition options live under `extra` (not
> as top-level source keys), `refresh_cadence` is a **top-level** spec
> field, and `transformations` entries must be `{"kind": ..., "args": ...}`
> using a dispatched kind — arbitrary `filter` / `select_columns`
> transforms are not implemented and would fail validation. GDELT's
> US filter is done at acquisition time via `extra.country_filter`;
> the `csv_index_then_zip` format emits GDELT v1's fixed column schema.
> To keep a subset of columns, publish all and hide the rest in the
> `.tds`, or select downstream in Tableau.

## Strategy chosen by `source_planner.py`

- **Source acquisition**: `templates/api_caller.py.j2` rendered with
  the GDELT-specific URL pattern + ZIP unpacking logic. The Python
  step downloads the latest CSV ZIP, filters to US, returns a
  DataFrame.
- **Eval strategy**: `sample_validation`. The skill pulls a small
  sample on the first run, asks the user to confirm the schema +
  representative rows look right, then locks that as the holdout.
- **QA tier**: `deterministic`. Adds a validator (rules: GLOBALEVENTID
  is unique, SQLDATE is parseable, GoldsteinScale ∈ [-10, 10]). No LLM
  QA needed for a structured-CSV source.

## Notes

- `refresh_cadence: daily` is captured in `spec.json`; on `--publish`
  it maps to the closest Tableau schedule (see
  `../server_publishing.md` for the cadence mapping).
- No PKI, no OAuth, no rate-limit risk — clean case.
- The api_caller template handles ZIP unpacking and retry-on-failure.
