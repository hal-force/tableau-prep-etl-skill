# sled_grant_clawback_risk — v2

**Request:** Advanced-route deliverable: SLED grant clawback risk for FY24. Pull FY24 (2023-10-01 through 2024-09-30) federal grants awarded to state/local/educational recipients from USASpending. Award types 02/03/04/05. Derive per-award clawback-risk signals: outlay stagnation ratio (Award Amount - Total Outlays) / Award Amount for awards >=180d past Start, unspent_dollars, recipient_name_count per prime_award_recipient_id. Publish two DSes to Tableau Cloud under Prep Agent. Fed Register signal join and FY25 renewal join are handled at dashboard time from existing DSes.

## Sources

- **REST API** (`json`): https://api.usaspending.gov/api/v2/search/spending_by_award/

## Transformations

- **trend_analysis**: SLED FY24 Trend

## Outputs

- `SLED Grants FY24 Detail` (published data source on Tableau Server, project `33 - SLED Grant Clawback Risk`)
- `SLED FY24 Sub-Agency Stats` (published data source on Tableau Server, project `33 - SLED Grant Clawback Risk`)

## Refresh cadence

`monthly`
Prior versions: `v1`

## Sample output

- `sample_output/SLED FY24 Sub-Agency Stats.hyper`
- `sample_output/SLED Grants FY24 Detail.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/sled_grant_clawback_risk/v2/spec.json \
    --flow-name sled_grant_clawback_risk
```

