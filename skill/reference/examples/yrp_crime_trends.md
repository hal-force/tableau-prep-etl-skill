# Example: York Regional Police crime occurrences with per-row trend stats

User request:

> Get crime data from York Regional Police in Ontario. Then add
> statistical analysis a crime analyst would use to understand trends.

This is the canonical **incident enrichment** example: a single
ArcGIS FeatureServer source with point geometry, enriched in a single
Python step with the temporal + per-dimension stats analysts pivot off
constantly. Stats are joined back at the row level so one Hyper
extract powers both detail tables and trend dashboards in Tableau —
no desktop-side blends or relationships required.

## What this exercises

- Single-source ArcGIS REST FeatureServer with `point` geometry
  (lat/lon flattened by api_caller's `_fetch_arcgis_features`)
- All-string `arcgis_field_types` to opt out of the planner's
  field-name heuristic — YRP's `time_est` ("HH:MM") and
  `case_status` ("Closed") would otherwise mis-bucket via the
  `*time*` and similar substring rules
- A new `trend_analysis` transformation kind (template:
  `templates/trend_analyzer.py.j2`) that emits 1 row per input row
  enriched with:
  - **Temporal features** — `year`, `month`, `quarter`,
    `year_month` (YYYY-MM), `iso_week`, `day_of_week_num`,
    `day_of_week_name`, `is_weekend`, `hour_of_day` (parsed from
    `time_est`), `hour_bucket` (Morning/Afternoon/Evening/Night)
  - **Per-dimension stats**, computed for every dimension in
    `args.dimensions`:
    - `{D}_monthly_count` — count of rows with same D in the row's
      (year, month) bucket. The hot-/cold-spot signal.
    - `{D}_yoy_change` and `{D}_yoy_pct` — current-month count
      minus prior-year same-month, capped to ±10× to keep Tableau
      auto-axes sane.
    - `{D}_rolling_count` — trailing-N-day count with same D
      (default 30 days). Smooths daily noise.
    - `{D}_baseline_mean`, `{D}_baseline_std` — mean/std of monthly
      counts for that D over the entire dataset.
    - `{D}_zscore` — `(monthly_count - baseline_mean)/std`. Flags
      "unusually high/low for this D this month."
    - `{D}_lifetime_count`, `{D}_lifetime_rank`, `{D}_pct_of_total`
      — volume context.
  - `is_anomaly` — True when any dimension's `|zscore|` exceeds
    `args.anomaly_z` (default 2.0). Powers a one-click "what's
    unusual" dashboard filter.

## Why per-row enrichment vs. a separate stats table

Crime-analytics dashboards almost always slice/filter by the same
dimensions used to compute the stats. Joining at extract time keeps
every viz one-click filterable without the user re-creating a blend
or relationship. Row-size cost is negligible for typical incident
volumes (<1M rows): YRP's 177k occurrences × 76 columns landed at
17 MB after the trend step.

## Spec

`runtime/specs/yrp_crime.json` (excerpted):

```json
{
  "sources": [
    {
      "type": "rest_api",
      "name": "YRP Community Safety Occurrences",
      "description": "Pulls York Regional Police occurrence records from the YRP ArcGIS open-data FeatureServer.",
      "url": "https://services8.arcgis.com/lYI034SQcOoxRCR7/arcgis/rest/services/Occurrence_2016_to_2019/FeatureServer/0/query",
      "format": "arcgis_features",
      "extra": {
        "arcgis_where": "1=1",
        "arcgis_out_fields": "UniqueIdentifier,case_type_pubtrans,LocationCode,district,municipality,Special_grouping,Shooting,hate_crime,case_status,occ_type,rep_date,time_est,occ_date",
        "arcgis_page_size": 2000,
        "arcgis_return_geometry": true,
        "arcgis_geometry_kind": "point",
        "arcgis_out_sr": 4326,
        "arcgis_field_types": {
          "UniqueIdentifier": "string", "case_type_pubtrans": "string",
          "LocationCode": "string", "district": "string",
          "municipality": "string", "Special_grouping": "string",
          "Shooting": "string", "hate_crime": "string",
          "case_status": "string", "occ_type": "string",
          "rep_date": "string", "time_est": "string", "occ_date": "string"
        }
      }
    }
  ],
  "transformations": [
    {
      "kind": "trend_analysis",
      "args": {
        "name": "Crime Trend Analyzer",
        "branch": 0,
        "date_col": "occ_date",
        "time_col": "time_est",
        "dimensions": ["municipality", "occ_type", "district",
                       "case_status", "case_type_pubtrans"],
        "rolling_window_days": 30,
        "anomaly_z": 2.0
      }
    }
  ],
  "outputs": [{"kind": "hyper", "name": "yrp_crime_occurrences"}]
}
```

## Note on the YRP layer name

The FeatureServer endpoint is named `Occurrence_2016_to_2019` but the
layer's view-definition restricts it to
`occ_date BETWEEN 2021-01-01 AND 2025-01-01`. This is upstream's
quirk — don't rename the URL. There's a sibling endpoint
`Occurrence` with view-def `occ_date > 2025-01-01` for year-to-date
data; combine the two via a multi-source spec if you want the full
historical + current series.

## DAG

```
[Input 1: trigger]  →  API Caller (ArcGIS fetcher)  →  Crime Trend Analyzer  →  WriteToHyper
```

## Run

```bash
python3 -m skill.scripts.run_loop \
  --spec runtime/specs/yrp_crime.json \
  --flow-name yrp_crime
```

## Verification (last working run)

- 177,542 occurrences fetched (2021-01-01 → 2025-01-01)
- 76 output columns (15 source + 10 temporal + 50 per-dim stats + `is_anomaly`)
- Spot-checks against the underlying monthly series:
  - `Theft Under $5000` 2024-05: monthly_count=968, prior-year (2023-05) was 1208,
    so `yoy_change=-240`, `yoy_pct=-19.87%` — matches.
  - Top z-score anomalies surface real signals: residential B&E spike
    in Nov-Dec 2023, weapons-violations spike in May 2022, Cannabis
    Act tail in early 2021.
- 5,748 anomalous rows (3.2% of total) — consistent with the
  z >= 2.0 threshold.

## Gotchas codified from this run

See [`feedback-trend-enrichment-gotchas`](../../../../../../../Users/jgillmore/.claude/projects/-Users-jgillmore-claude-projects/memory/feedback_trend_enrichment_gotchas.md)
for:

1. **Inverted YoY lookup keys.** Building an intermediate dict with
   `{(v, y - 1, m): c}` and then querying with `(v, y, m)` reads
   *next year's* count as the prior-year baseline. Look up the cube
   directly: `cube.get((v, year - 1, month), 0)`.
2. **Spot-check shifted-window features against the underlying
   monthly series, every time.** Schema validation passes on subtly
   wrong numbers; only SQL spot-checks catch them.
3. **Cap percentage changes** at ±10× to prevent div-by-zero
   blowups from flattening Tableau auto-axes.
4. **Rolling counts: sort once per dimension, walk with two
   pointers** — naive nested-loop is O(N²) and dies on 100k+ rows.
