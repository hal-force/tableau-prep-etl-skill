# usaspending_sled_grants — v1

**Request:** Pull federal grants awarded to state, local, and education recipients from USASpending.gov (POST /api/v2/search/spending_by_award/), filtered to award_type_codes 02/03/04/05 (Block Grant, Formula Grant, Project Grant, Cooperative Agreement) and recipient_type_names in [State Government, County Government, City or Township Government, Special District Government, Independent School District, State Controlled Institution of Higher Education, Public/State Controlled Institution of Higher Education]. Fiscal year 2025-2026 (start 2024-10-01). Paginate via body 'page' with 100 per page, cap at 30 pages / 3000 rows. Enrich with amount_band (small<$100K / mid<$1M / large<$10M / mega>=$10M), award_kind (grant vs coop_agreement). Publish to 'Prep Agent / 22 - Federal Grants to SLED' on Tableau Server for state and local budget analysts tracking incoming federal funds.

## Sources

- **REST API** (`json`): https://api.usaspending.gov/api/v2/search/spending_by_award/

## Transformations

- **trend_analysis**: SLED Grants Trend

## Outputs

- `SLED Grants Detail` (published data source on Tableau Server, project `22 - Federal Grants to SLED`)
- `SLED Grants Stats` (published data source on Tableau Server, project `22 - Federal Grants to SLED`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/SLED Grants Detail.sample.csv`
- `sample_output/SLED Grants Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/usaspending_sled_grants/v1/spec.json \
    --flow-name usaspending_sled_grants
```

