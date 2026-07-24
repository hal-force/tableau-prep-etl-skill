# cms_nursing_home_providers — v1

**Request:** Pull CMS Nursing Home Provider Information from data.cms.gov (Provider Data API dataset 4pq5-n9py) — full national roster (~15k providers). One row per nursing home. Enrich with size_band (bed-count binning: micro <25 / small <50 / mid <150 / large <300 / mega >=300) and ownership_group (map_values on ownership_type -> for_profit / non_profit / government / other). Publish to 'Prep Agent / 24 - CMS Nursing Home Providers' on Tableau Server for state health-agency + LTC-quality analysts. Note: pivoted from NY Nursing Home bed census (data.cityofnewyork.us) after repeated DNS resolution failures against the Socrata FedRAMP cluster from within TabPy — CMS Provider Data API is Akamai-fronted and stable (mirrors the working Flow 06 pattern).

## Sources

- **REST API** (`json`): https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0

## Transformations

- **trend_analysis**: CMS Provider Trend

## Outputs

- `CMS Nursing Home Provider Detail` (published data source on Tableau Server, project `24 - CMS Nursing Home Providers`)
- `CMS Nursing Home Provider Stats` (published data source on Tableau Server, project `24 - CMS Nursing Home Providers`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/CMS Nursing Home Provider Detail.sample.csv`
- `sample_output/CMS Nursing Home Provider Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/cms_nursing_home_providers/v1/spec.json \
    --flow-name cms_nursing_home_providers
```

