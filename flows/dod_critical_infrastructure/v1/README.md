# dod_critical_infrastructure — v1

**Request:** Pull the HIFLD Military_Installation FeatureServer (public geoplatform.gov copy of the DoD Base Structure Report footprint — 744 US + overseas sites with polygon footprints, COMPONENT, JOINT_BASE, STATE_TERR/COUNTRY, and reported AREA). Enrich each site with a `replacement_likelihood_score` (and its inverse `criticality_score`) computed from acreage, joint-basing status, service component, and overseas/SOFA exposure. Publish to Tableau Cloud under the `Prep Agent` parent project.

## Sources

- **REST API** (`arcgis_features`): https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/Military_Installation/FeatureServer/0/query

## Transformations

- (raw passthrough — the ETL step is scoring, applied by `scoring.py` inside the container-executed driver `run_end_to_end.py`. Kept outside the .tfl transform graph so the demo can run without prep-cli on the host.)

## Scoring — replacement_likelihood_score

Weighted sum, clipped 0–100:

| Weight | Component | Meaning |
|-------:|-----------|---------|
| 40 | AREA (log-scaled, 1000 km² reference) | Bigger complexes are harder to replace. |
| 25 | JOINT_BASE flag (present ≠ "N/A") | Multi-service consolidations are sticky. |
| 20 | COMPONENT strategic weight | Navy / Air Force / Marines / Army > Guard / Reserve. |
| 15 | Overseas flag (COUNTRY ≠ "United States") | SOFA-country siting is politically expensive to reproduce. |

`replacement_likelihood_score = 100 − criticality_score`. Higher score = more replaceable.

Top-5 hardest to replace (July 2026 HIFLD snapshot):

1. Joint Base Lewis-McChord — 68.8
2. Naval Base Guam — 65.5
3. Joint Base Elmendorf-Richardson — 58.4
4. Joint Base San Antonio — 55.8
5. Joint Base McGuire-Dix-Lakehurst — 55.3

## Outputs

- `DoD Critical Infrastructure (Replacement Likelihood)` — published data source on Tableau Cloud, project `32 - DoD Critical Infrastructure` (child of `Prep Agent`). Column descriptions written via .tdsx round-trip.

## Refresh cadence

`monthly` — HIFLD updates rarely.

## Sample output

- `sample_output/DoD Critical Infrastructure (Replacement Likelihood).hyper`
- `sample_output/dod_critical_infrastructure.hyper`

Real output included because this flow's source is open-source / public.

## Reproduce

Inside the docker skill container (see `docker/README.md`):

```bash
# 1. Generate the .tfl
docker compose -f docker/docker-compose.yml -f docker/compose.local.yml \
    run --rm skill python3 -m skill.scripts.generate_flow \
        --spec runtime/specs/dod_critical_infrastructure.json \
        --run-dir /workspace/runtime/build/dod_critical_infrastructure

# 2. Fetch, score, write .hyper
docker compose -f docker/docker-compose.yml -f docker/compose.local.yml \
    run --rm skill python3 flows/dod_critical_infrastructure/v1/run_end_to_end.py

# 3. Publish (needs env-var creds; run from host after sourcing load_env.sh)
python3 -m skill.scripts.publish \
    flows/dod_critical_infrastructure/v1/spec.json \
    runtime/build/dod_critical_infrastructure/flow.tfl \
    --run-dir runtime/build/dod_critical_infrastructure
```
