# UK_Police_London_Crime — v1

**Request:** Pull UK street-level crime records from the Home Office's data.police.uk open data API for a Central London polygon (Westminster / City of London / Southwark), previous complete calendar month. One row per crime. The API returns nested location (latitude/longitude/street.name) and outcome_status (category/date); we flatten those with dotted_path derived columns. Enrich with crime_severity_band (map_values on category: violent-crime/robbery/possession-of-weapons->high, burglary/drugs/vehicle-crime/theft-from-the-person->medium, other -> low), outcome_stage (map_values on outcome_status.category: awaiting/court/complete/no-action) and neighborhood_area (map_values on location.street.name prefix -> Westminster / City / Southwark / Other). Publish to 'Prep Agent / 32 - UK Police Street Crime (London)' on Tableau Server for UK MoJ / Home Office / GLA analysts. data.police.uk is a keyless, rate-friendly open-data API (Home Office).

## Sources

- **REST API** (`json`): https://data.police.uk/api/crimes-street/all-crime?poly=51.485,-0.130:51.485,-0.070:51.525,-0.070:51.525,-0.130&date=2026-05

## Transformations

- **trend_analysis**: UK Police London Crime Trend

## Outputs

- `UK Police London Crime Detail` (published data source on Tableau Server, project `32 - UK Police Street Crime (London)`)
- `UK Police London Crime Stats` (published data source on Tableau Server, project `32 - UK Police Street Crime (London)`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/UK Police London Crime Detail.sample.csv`
- `sample_output/UK Police London Crime Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/UK_Police_London_Crime/v1/spec.json \
    --flow-name UK_Police_London_Crime
```

