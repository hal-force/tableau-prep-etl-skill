# bls_laus_states — v1

**Request:** Pull monthly state-level unemployment rates (BLS Local Area Unemployment Statistics, series LASST<FIPS>0000000000003) for the 25 most populous states + DC from 2022-2026. Enrich with a rate_band (very_low/low/moderate/elevated/high thresholds on the seasonally-adjusted unemployment rate) plus a state FIPS -> state code lookup. Publish to 'Prep Agent / 21 - BLS LAUS State Unemployment' on Tableau Server for SLED workforce and economic-development analysts.

## Sources

- **REST API** (`json`): https://api.bls.gov/publicAPI/v2/timeseries/data/

## Transformations

- **trend_analysis**: Unemployment Trend

## Outputs

- `LAUS State Detail` (published data source on Tableau Server, project `21 - BLS LAUS State Unemployment`)
- `LAUS State Stats` (published data source on Tableau Server, project `21 - BLS LAUS State Unemployment`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/LAUS State Detail.sample.csv`
- `sample_output/LAUS State Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/bls_laus_states/v1/spec.json \
    --flow-name bls_laus_states
```

