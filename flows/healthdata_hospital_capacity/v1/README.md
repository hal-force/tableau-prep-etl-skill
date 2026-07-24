# healthdata_hospital_capacity — v1

**Request:** Pull HHS COVID-19 Reported Patient Impact and Hospital Capacity by State (Timeseries) from healthdata.gov (dataset g62h-syeh, ~82k rows, daily state observations Jan-2020 through Apr-2024 when reporting ended). One row per state x date. Enrich with utilization_band (numeric_bin on inpatient_beds_utilization: low <0.5 / moderate <0.7 / high <0.85 / crisis >=0.85) and census_region (map_values state -> Northeast/Midwest/South/West/territory). Publish to 'Prep Agent / 25 - HHS Hospital Capacity Timeseries' on Tableau Server for state public-health analysts. healthdata.gov resolves to AWS (15.197.185.55 / 3.33.161.206), not the Socrata FedRAMP NLB — stable from TabPy subprocesses.

## Sources

- **REST API** (`json`): https://healthdata.gov/resource/g62h-syeh.json

## Transformations

- **trend_analysis**: HHS Hospital Capacity Trend

## Outputs

- `HHS Hospital Capacity Detail` (published data source on Tableau Server, project `25 - HHS Hospital Capacity Timeseries`)
- `HHS Hospital Capacity Stats` (published data source on Tableau Server, project `25 - HHS Hospital Capacity Timeseries`)

## Refresh cadence

`weekly`

## Sample output

- `sample_output/HHS Hospital Capacity Detail.sample.csv`
- `sample_output/HHS Hospital Capacity Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/healthdata_hospital_capacity/v1/spec.json \
    --flow-name healthdata_hospital_capacity
```

