# la_crime_2024 — v1

**Request:** Pull LAPD crime incidents from City of Los Angeles Open Data (data.lacity.org resource 2nrs-mtv8). Filter to 2024-onward for a manageable ~200k-row slice. One row per reported crime. Enrich with victim_age_band (numeric_bin on vict_age: unknown <1 / child <18 / young_adult <30 / adult <50 / senior >=50) and crime_class (map_values on part_1_2: 1=part_1_violent_property, 2=part_2_other). Publish to 'Prep Agent / 28 - LA Crime Incidents' on Tableau Server for LAPD public-safety analytics teams, city-council policy staff, and academic criminologists. data.lacity.org is Socrata-hosted, reliable.

## Sources

- **REST API** (`json`): https://data.lacity.org/resource/2nrs-mtv8.json?$where=date_occ%3E=%272024-01-01T00:00:00%27&$order=date_occ

## Transformations

- **trend_analysis**: LA Crime Trend

## Outputs

- `LA Crime Incidents` (published data source on Tableau Server, project `28 - LA Crime Incidents`)
- `LA Crime Stats` (published data source on Tableau Server, project `28 - LA Crime Incidents`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/LA Crime Incidents.sample.csv`
- `sample_output/LA Crime Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/la_crime_2024/v1/spec.json \
    --flow-name la_crime_2024
```

