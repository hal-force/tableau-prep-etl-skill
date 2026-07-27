# nursing_home_collapse_risk — v2

**Request:** Advanced-route deliverable: nursing-home quality-collapse early warning. Pull CMS Nursing Home Health Deficiencies (r5ix-sfxw, 12mo since 2025-07-24). Enrich with days_since_survey, days_to_correction. Compute per-provider F1/F2/F3 signals in trend_analysis rollup. Publish two DSes on Cloud under Prep Agent. F4 hospital-spillover and F5 PBJ staffing are declared as scope decisions (F4 pulled from existing HealthData Hospital Capacity DS at dashboard-time; F5 is RED gap).

## Sources

- **REST API** (`json`): https://data.cms.gov/provider-data/api/1/datastore/query/r5ix-sfxw/0?conditions%5B0%5D%5Bproperty%5D=survey_date&conditions%5B0%5D%5Bvalue%5D=2025-07-24&conditions%5B0%5D%5Boperator%5D=%3E

## Transformations

- **trend_analysis**: Nursing Home Collapse Trend

## Outputs

- `Nursing Home Deficiency Detail` (published data source on Tableau Server, project `34 - Nursing Home Collapse Risk`)
- `Nursing Home Deficiency Stats` (published data source on Tableau Server, project `34 - Nursing Home Collapse Risk`)

## Refresh cadence

`monthly`
Prior versions: `v1`

## Sample output

- `sample_output/Nursing Home Deficiency Detail.hyper`
- `sample_output/Nursing Home Deficiency Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/nursing_home_collapse_risk/v2/spec.json \
    --flow-name nursing_home_collapse_risk
```

