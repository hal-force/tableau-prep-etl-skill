# boston_311_requests — v1

**Request:** Pull City of Boston 311 service requests from data.boston.gov's CKAN datastore (resource 1a0b420d-99f1-4887-9851-990b2a5a6e17, calendar-year 2026). Cap at 20,000 rows via CKAN datastore_search offset pagination (limit=5000). Enrich with status_band (open/closed/other) and dept_group (PWD / Streets / ISD / Parks / Police / Neighborhood Svcs / Other) using map_values. Publish to 'Prep Agent / 23 - Boston 311 Service Requests' on Tableau Server for city operations analysts. Note: pivoted from Chicago 311 (data.cityofchicago.org) after repeated DNS resolution failures against the Socrata FedRAMP cluster from within TabPy — Boston hosts on Cloudflare and is stable.

## Sources

- **REST API** (`json`): https://data.boston.gov/api/3/action/datastore_search?resource_id=1a0b420d-99f1-4887-9851-990b2a5a6e17

## Transformations

- **trend_analysis**: Boston 311 Trend

## Outputs

- `Boston 311 Detail` (published data source on Tableau Server, project `23 - Boston 311 Service Requests`)
- `Boston 311 Stats` (published data source on Tableau Server, project `23 - Boston 311 Service Requests`)

## Refresh cadence

`weekly`

## Sample output

- `sample_output/Boston 311 Detail.sample.csv`
- `sample_output/Boston 311 Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/boston_311_requests/v1/spec.json \
    --flow-name boston_311_requests
```

