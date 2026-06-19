# epa_aqs_ozone — v1

**Request:** Pull EPA Air Quality System (AQS) ozone (parameter 44201) hourly sample measurements for California for January 2024, enrich with sample-time-of-day features and trend analysis by site_number + county. Publish to 'Prep Agent / 09 - EPA Air Quality' on Tableau Server for environmental analysts.

## Sources

- **REST API** (`json`): https://aqs.epa.gov/data/api/sampleData/byState?email=test@aqs.api&key=test&param=44201&bdate=20240115&edate=20240117&state=06

## Transformations

- **trend_analysis**: Ozone Trend

## Outputs

- `EPA Ozone Detail` (published data source on Tableau Server, project `09 - EPA Air Quality`)
- `EPA Ozone Stats` (published data source on Tableau Server, project `09 - EPA Air Quality`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/EPA Ozone Detail.hyper`
- `sample_output/EPA Ozone Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/epa_aqs_ozone/v1/spec.json \
    --flow-name epa_aqs_ozone
```

