# space_domain_convergence — v2

**Request:** Advanced-route deliverable: space-domain convergence view. Pull the active satellite TLE catalog and the CNEOS Sentry impact-risk catalog. Bucket TLEs into orbital regimes (LEO/MEO/GEO/HEO/cislunar) via TLE line2 mean-motion substring extraction. Publish two DSes to Tableau Cloud under Prep Agent. OpenSky US airspace activity is a dashboard-time join, not a build-time coupling.

## Sources

- **REST API** (`json`): https://tle.ivanstanojevic.me/api/tle/?page-size=100&page=1

## Transformations

- **trend_analysis**: TLE Convergence Trend

## Outputs

- `Space Convergence Satellite Detail` (published data source on Tableau Server, project `37 - Space Domain Convergence`)

## Refresh cadence

`daily`
Prior versions: `v1`

## Sample output

- `sample_output/Space Convergence Satellite Detail.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/space_domain_convergence/v2/spec.json \
    --flow-name space_domain_convergence
```

