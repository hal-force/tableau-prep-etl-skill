# dod_critical_infrastructure — v2

**Request:** Pull the HIFLD Military_Installation FeatureServer (public geoplatform.gov copy of the DoD Base Structure Report footprint — 744 US + overseas sites with polygon footprints, COMPONENT, JOINT_BASE, STATE_TERR/COUNTRY, and reported AREA in acres). Enrich each site with a replacement_likelihood_score computed from its acreage, joint-basing status, service component, and overseas/SOFA exposure. Output a local Hyper extract for analyst use; not published to Server (local-only demo run).

## Sources

- **REST API** (`arcgis_features`): https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/Military_Installation/FeatureServer/0/query

## Transformations

- (none — raw passthrough)

## Outputs

- `DoD Critical Infrastructure (Replacement Likelihood)` (published data source on Tableau Server, project `32 - DoD Critical Infrastructure`)

## Refresh cadence

`monthly`
Prior versions: `v1`

## Sample output

- `sample_output/DoD Critical Infrastructure (Replacement Likelihood).hyper`
- `sample_output/dod_critical_infrastructure.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/dod_critical_infrastructure/v2/spec.json \
    --flow-name dod_critical_infrastructure
```

