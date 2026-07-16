# dod_contracts — v1

**Request:** Pull DoD contract awards (agency 'Department of Defense', top-tier) from USAspending.gov for the current fiscal year (2025-10-01 through today, 2026-07-14), enrich with NAICS flattening, days_of_performance, and trend analysis by Awarding Sub Agency + Recipient. Publish to 'Prep Agent / 11 - DoD Contract Awards' on Tableau Server for defense procurement analysts.

## Sources

- **REST API** (`json`): https://api.usaspending.gov/api/v2/search/spending_by_award/

## Transformations

- **trend_analysis**: DoD Award Trend

## Outputs

- `DoD Award Detail` (published data source on Tableau Server, project `11 - DoD Contract Awards`)
- `DoD Award Stats` (published data source on Tableau Server, project `11 - DoD Contract Awards`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/DoD Award Detail.hyper`
- `sample_output/DoD Award Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/dod_contracts/v1/spec.json \
    --flow-name dod_contracts
```

