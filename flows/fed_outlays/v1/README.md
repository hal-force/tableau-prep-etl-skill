# fed_outlays — v1

**Request:** Pull top-level monthly federal outlay totals from the Treasury Fiscal Data Monthly Treasury Statement (Table 5) for calendar years 2018-2025, run trend analysis with year-over-year change, rolling baselines and z-score anomalies, and publish to a 'Prep Agent / 01 - Federal Outlays' project on Tableau Server for finance analysts to track spending trends across the federal classification hierarchy.

## Sources

- **REST API** (`json`): https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_5?filter=record_calendar_year:gte:2018,record_calendar_year:lte:2025,sequence_level_nbr:eq:1

## Transformations

- **trend_analysis**: Outlay Trend

## Outputs

- `Federal Outlays Detail` (published data source on Tableau Server, project `01 - Federal Outlays`)
- `Federal Outlays Stats` (published data source on Tableau Server, project `01 - Federal Outlays`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/Federal Outlays Detail.hyper`
- `sample_output/Federal Outlays Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/fed_outlays/v1/spec.json \
    --flow-name fed_outlays
```

