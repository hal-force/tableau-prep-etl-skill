# centcom_supplier_risk — v2

**Request:** Advanced-route deliverable: CENTCOM supplier concentration risk. Pull DoD contract awards from USASpending.gov filtered to CENTCOM-adjacent place-of-performance countries (BH/IQ/JO/KW/OM/QA/SA/SY/YE/AF/EG/IR/LB/IL/KZ/KG/TJ/TM/UZ/PK), rolling 12-month window (2025-07-24 through 2026-07-24). Enrich with NAICS flattening, days_of_performance, open_window_flag, and per-prime trend / concentration / schedule-slip indicators. Publish two DSes on Tableau Cloud under Prep Agent parent. CENTCOM-adjacency is a proxy via place-of-performance country codes; USASpending does not carry combatant-command tags.

## Sources

- **REST API** (`json`): https://api.usaspending.gov/api/v2/search/spending_by_award/

## Transformations

- **trend_analysis**: CENTCOM Supplier Trend

## Outputs

- `CENTCOM Supplier Awards Detail` (published data source on Tableau Server, project `32 - CENTCOM Supplier Risk`)
- `CENTCOM Supplier Risk Stats` (published data source on Tableau Server, project `32 - CENTCOM Supplier Risk`)

## Refresh cadence

`monthly`
Prior versions: `v1`

## Sample output

- `sample_output/CENTCOM Supplier Awards Detail.hyper`
- `sample_output/CENTCOM Supplier Risk Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/centcom_supplier_risk/v2/spec.json \
    --flow-name centcom_supplier_risk
```

