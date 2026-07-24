# UK_TfL_AccidentStats_2019 — v1

**Request:** Pull Transport for London AccidentStats for 2019 (the last complete published year from TfL Unified API), api.tfl.gov.uk/AccidentStats/2019 — ~51k road-traffic accidents across Greater London. Each row includes lat/lon, location string, ISO datetime, severity (Fatal/Serious/Slight), borough, casualties list and vehicles list. Enrich with casualty_count and vehicle_count via list_length, severity_band via map_values (Fatal=critical/Serious=high/Slight=low), primary_vehicle via list_first_field on vehicles, primary_casualty_mode via list_first_field on casualties, hour_of_day extracted from the ISO date via substring, and time_of_day_bucket via map_values on hour_of_day (00-05=night, 06-09=morning_peak, 10-15=daytime, 16-19=evening_peak, 20-23=evening). Publish to 'Prep Agent / 36 - UK TfL Accident Statistics 2019' on Tableau Server for TfL / MoT / DfT / MPS analysts. Keyless, OGL v3.

## Sources

- **REST API** (`json`): https://api.tfl.gov.uk/AccidentStats/2019

## Transformations

- **trend_analysis**: TfL Accidents Trend

## Outputs

- `UK TfL Accidents Detail` (published data source on Tableau Server, project `36 - UK TfL Accident Statistics 2019`)
- `UK TfL Accidents Stats` (published data source on Tableau Server, project `36 - UK TfL Accident Statistics 2019`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/UK TfL Accidents Detail.sample.csv`
- `sample_output/UK TfL Accidents Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/UK_TfL_AccidentStats_2019/v1/spec.json \
    --flow-name UK_TfL_AccidentStats_2019
```

