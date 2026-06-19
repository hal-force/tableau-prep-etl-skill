# usaspending_contracts — v1

**Request:** Pull federal contract awards (award type A/B/C/D = definitive contracts and BPA/IDV variants) from USAspending.gov for the first half of 2025, enrich with NAICS code+description flattening, days_active = end_date - start_date, and trend analysis by Awarding Agency + NAICS code. Publish to 'Prep Agent / 10 - Federal Contract Awards' on Tableau Server for procurement analysts.

## Sources

- **REST API** (`json`): https://api.usaspending.gov/api/v2/search/spending_by_award/

## Transformations

- **trend_analysis**: Award Trend

## Outputs

- `Federal Award Detail` (published data source on Tableau Server, project `10 - Federal Contract Awards`)
- `Federal Award Stats` (published data source on Tableau Server, project `10 - Federal Contract Awards`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/Federal Award Detail.hyper`
- `sample_output/Federal Award Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/usaspending_contracts/v1/spec.json \
    --flow-name usaspending_contracts
```

