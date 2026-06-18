# us_wildfires_eoc — v1

**Request:** Pull active US wildfire incidents from the NIFC/WFIGS authoritative incident-locations feed, enrich each row with EOC analyst-facing metrics (days-since-discovery, staleness, daily growth rate, NWCG size class, containment band, region key, tooltip-ready incident summary) plus calendar-axis temporal features, and publish the enriched data source to the Weather & Disaster Response project on Tableau Server for emergency operations dashboards.

## Sources

- **REST API** (`arcgis_features`): https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query

## Transformations

- **eoc_fire_metrics**: EOC Fire Metrics
- **trend_analysis**: Discovery Trend

## Outputs

- `US Wildfires (EOC Enriched)` (published data source on Tableau Server, project `Weather & Disaster Response`)

## Refresh cadence

`hourly`

## Sample output

- `sample_output/US Wildfires (EOC Enriched).hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/us_wildfires_eoc/v1/spec.json \
    --flow-name us_wildfires_eoc
```

