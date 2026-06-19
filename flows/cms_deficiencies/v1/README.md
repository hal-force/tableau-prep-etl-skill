# cms_deficiencies — v1

**Request:** Pull CMS Nursing Home Health Inspection Deficiencies (Provider Data) since 2025-12-01, treat each citation as a public-health-surveillance event, enrich with days_since_survey, days_to_correction, and trend analysis by state + deficiency_category. Publish to 'Prep Agent / 06 - CMS Nursing Home Surveillance' on Tableau Server for public-health analysts.

## Sources

- **REST API** (`json`): https://data.cms.gov/provider-data/api/1/datastore/query/r5ix-sfxw/0?conditions%5B0%5D%5Bproperty%5D=survey_date&conditions%5B0%5D%5Bvalue%5D=2025-12-01&conditions%5B0%5D%5Boperator%5D=%3E

## Transformations

- **trend_analysis**: Deficiency Trend

## Outputs

- `CMS Deficiency Detail` (published data source on Tableau Server, project `06 - CMS Nursing Home Surveillance`)
- `CMS Deficiency Stats` (published data source on Tableau Server, project `06 - CMS Nursing Home Surveillance`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/CMS Deficiency Detail.hyper`
- `sample_output/CMS Deficiency Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/cms_deficiencies/v1/spec.json \
    --flow-name cms_deficiencies
```

