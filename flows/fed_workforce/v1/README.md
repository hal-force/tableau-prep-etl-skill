# fed_workforce — v1

**Request:** Pull monthly federal employment counts from the U.S. Bureau of Labor Statistics Public Data API (CES Federal employment series across the major federal branches: total federal, executive postal, total non-postal civilian, DOD civilian, military), 2018-2025. Enrich with year-over-year change, 12-month rolling averages, z-score anomalies, and lifetime ranks. Publish to a 'Prep Agent / 02 - Federal Workforce' project on Tableau Server for HR analysts to track federal headcount trends.

## Sources

- **REST API** (`json`): https://api.bls.gov/publicAPI/v2/timeseries/data/

## Transformations

- **trend_analysis**: Workforce Trend

## Outputs

- `Federal Workforce Detail` (published data source on Tableau Server, project `02 - Federal Workforce`)
- `Federal Workforce Stats` (published data source on Tableau Server, project `02 - Federal Workforce`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/Federal Workforce Detail.hyper`
- `sample_output/Federal Workforce Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/fed_workforce/v1/spec.json \
    --flow-name fed_workforce
```

