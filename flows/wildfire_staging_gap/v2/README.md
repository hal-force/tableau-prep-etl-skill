# wildfire_staging_gap — v2

**Request:** Advanced-route deliverable: wildfire staging-resource gap. Pull active US wildfire incidents from NIFC/WFIGS (ActiveFireCandidate=1). Enrich with EOC metrics (size class, growth rate, days-since-discovery). Surface F2 assigned-resource fields (TotalIncidentPersonnel, EstimatedCostToDate, IncidentComplexityLevel) explicitly so gap ratios are one-hop in Tableau. Publish two DSes to Tableau Cloud under Prep Agent. Grid-spillover join to US Grid Network is a dashboard-time step, not a build-time join.

## Sources

- **REST API** (`arcgis_features`): https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query

## Transformations

- **eoc_fire_metrics**: EOC Fire Metrics
- **trend_analysis**: Staging Gap Trend

## Outputs

- `Wildfire Staging Gap Detail` (published data source on Tableau Server, project `35 - Wildfire Staging Gap`)
- `Wildfire Staging Gap Stats` (published data source on Tableau Server, project `35 - Wildfire Staging Gap`)

## Refresh cadence

`hourly`
Prior versions: `v1`

## Sample output

- `sample_output/Wildfire Staging Gap Detail.hyper`
- `sample_output/Wildfire Staging Gap Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/wildfire_staging_gap/v2/spec.json \
    --flow-name wildfire_staging_gap
```

