# UK_EA_Flood_Monitoring — v1

**Request:** Pull the UK Environment Agency (Defra) real-time flood-monitoring 'measures' catalogue from environment.data.gov.uk — one row per (station x parameter x qualifier), ~5.6k rows nationwide across England. Each measure carries a nested latestReading with the most recent observed value + timestamp. We flatten latestReading.value / latestReading.dateTime via dotted_path and enrich with level_band (numeric_bin on reading value: <0 dry / 0-0.5 low / 0.5-1.5 normal / 1.5-3 elevated / 3+ high), parameter_class (map_values parameter: level=water_level, flow=river_flow, wind=wind, temperature=temperature, rainfall=rainfall, others=other), reading_freshness_days (days_since latestReading.dateTime), and stage_qualifier_group (map_values qualifier: Stage/Downstream Stage/Upstream Stage=stage, Tidal Level=tidal, Groundwater=groundwater, Rainfall=rainfall). Publish to 'Prep Agent / 33 - UK Environment Agency Flood Monitoring' on Tableau Server for Defra / EA / local resilience forum analysts. Keyless, Open Government Licence.

## Sources

- **REST API** (`json`): https://environment.data.gov.uk/flood-monitoring/id/measures?_limit=10000

## Transformations

- **trend_analysis**: EA Flood Measures Trend

## Outputs

- `UK EA Flood Measures Detail` (published data source on Tableau Server, project `33 - UK Environment Agency Flood Monitoring`)
- `UK EA Flood Measures Stats` (published data source on Tableau Server, project `33 - UK Environment Agency Flood Monitoring`)

## Refresh cadence

`hourly`

## Sample output

- `sample_output/UK EA Flood Measures Detail.sample.csv`
- `sample_output/UK EA Flood Measures Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/UK_EA_Flood_Monitoring/v1/spec.json \
    --flow-name UK_EA_Flood_Monitoring
```

