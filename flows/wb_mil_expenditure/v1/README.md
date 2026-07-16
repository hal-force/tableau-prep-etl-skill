# wb_mil_expenditure — v1

**Request:** Pull World Bank military expenditure (% of GDP) indicator MS.MIL.XPND.GD.ZS for all countries, 2010-2024. Enrich each row with a spend_band (very_low / low / moderate / elevated / high) and years_since_observation for recency. Publish to 'Prep Agent / 19 - World Bank Military Expenditure' on Tableau Server for defense-economics + arms-industry analysts.

## Sources

- **REST API** (`json`): https://api.worldbank.org/v2/country/all/indicator/MS.MIL.XPND.GD.ZS?format=json&date=2010:2024

## Transformations

- **trend_analysis**: MilExp Trend

## Outputs

- `WB Military Expenditure Detail` (published data source on Tableau Server, project `19 - World Bank Military Expenditure`)
- `WB Military Expenditure Stats` (published data source on Tableau Server, project `19 - World Bank Military Expenditure`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/WB Military Expenditure Detail.sample.csv`
- `sample_output/WB Military Expenditure Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/wb_mil_expenditure/v1/spec.json \
    --flow-name wb_mil_expenditure
```

