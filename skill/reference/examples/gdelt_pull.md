# Example: GDELT online pull

User request:

> Pull the latest GDELT events for the United States and load them into a
> Tableau Hyper extract. Refresh daily.

## Spec produced by `intake.py`

```json
{
  "sources": [{
    "type": "rest_api",
    "url": "http://data.gdeltproject.org/events/index.html",
    "format": "csv_index_then_zip",
    "auth": "none",
    "refresh_cadence": "daily"
  }],
  "transformations": [
    {"kind": "filter", "field": "ActionGeo_CountryCode", "value": "US"},
    {"kind": "select_columns", "fields": [
      "GLOBALEVENTID", "SQLDATE", "Actor1Name", "Actor2Name",
      "EventCode", "GoldsteinScale", "ActionGeo_FullName"
    ]}
  ],
  "outputs": [{"kind": "hyper", "name": "gdelt_us_events.hyper"}],
  "qa_tier": "deterministic",
  "eval_strategy": "sample_validation",
  "deployment": "local"
}
```

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

- `refresh_cadence: daily` is captured in `spec.json` but v1 doesn't
  schedule it. v2 will wire this to Tableau Conductor.
- No PKI, no OAuth, no rate-limit risk — clean case.
- The api_caller template handles ZIP unpacking and retry-on-failure.
