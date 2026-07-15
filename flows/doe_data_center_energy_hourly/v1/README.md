# doe_data_center_energy_hourly — v1

**Request:** DOE Data-Center Energy Hourly: RTO/ISO grid-operator hourly demand (`type=D`) across the four US regions where data centers are heaviest — PJM (Northern Virginia / Ashburn), ERCOT (Central Texas / San Antonio Loop), CAISO (Silicon Valley), MISO (Chicago/Ohio). One row per (respondent, hour). This dataset supports diurnal load-curve analysis, weekend vs. weekday load shape (a fingerprint for data-center dominance since DC load is flat while HVAC/lighting is peaky), and cross-RTO comparison of how DC growth is bending each region's load curve. Source: EIA Open Data v2 electricity/rto/region-data endpoint (grid-operator-reported demand, refreshed hourly with a ~24h lag).

## Sources

- **REST API** (`json`): https://api.eia.gov/v2/electricity/rto/region-data/data/?frequency=hourly&data[0]=value&facets[type][]=D&facets[respondent][]=PJM&facets[respondent][]=ERCO&facets[respondent][]=CISO&facets[respondent][]=MISO&sort[0][column]=period&sort[0][direction]=desc

## Transformations

- (none — raw passthrough)

## Outputs

- `DOE Data Center Energy Hourly - RTO Demand` (published data source on Tableau Server, project `DOE Data Center Energy`)

## Refresh cadence

`every_6_hours`

## Sample output

- `sample_output/DOE Data Center Energy Hourly - RTO Demand.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/doe_data_center_energy_hourly/v1/spec.json \
    --flow-name doe_data_center_energy_hourly
```

