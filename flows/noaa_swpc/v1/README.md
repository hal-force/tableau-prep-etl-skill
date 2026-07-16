# noaa_swpc — v1

**Request:** Pull the last 30 days of NOAA Space Weather Prediction Center alerts (K-index warnings, solar flare notifications, geomagnetic storm alerts, radio blackout warnings). Include product_id, issue_datetime, and message. Enrich with alert_class (Warning/Watch/Alert/Summary), space_weather_scale (G/S/R prefix from product_id), and days_since_issued. Publish to 'Prep Agent / 18 - NOAA Space Weather Alerts' on Tableau Server for space-domain-awareness + SATCOM continuity analysts.

## Sources

- **REST API** (`json`): https://services.swpc.noaa.gov/products/alerts.json

## Transformations

- **trend_analysis**: SWPC Trend

## Outputs

- `SWPC Alerts Detail` (published data source on Tableau Server, project `18 - NOAA Space Weather Alerts`)
- `SWPC Alerts Stats` (published data source on Tableau Server, project `18 - NOAA Space Weather Alerts`)

## Refresh cadence

`hourly`

## Sample output

- `sample_output/SWPC Alerts Detail.hyper`
- `sample_output/SWPC Alerts Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/noaa_swpc/v1/spec.json \
    --flow-name noaa_swpc
```

