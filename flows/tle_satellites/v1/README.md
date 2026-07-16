# tle_satellites — v1

**Request:** Pull TLE elements for active satellites via the tle.ivanstanojevic.me API (Space-Track mirror). Extract satelliteId, name, epoch date, and TLE lines. Enrich with days_since_epoch and derive orbital classification-hint character from TLE line1. Publish to 'Prep Agent / 16 - Active Satellite TLE Catalog' on Tableau Server for space-domain-awareness analysts.

## Sources

- **REST API** (`json`): https://tle.ivanstanojevic.me/api/tle/?page-size=100&page=1

## Transformations

- **trend_analysis**: TLE Trend

## Outputs

- `TLE Catalog Detail` (published data source on Tableau Server, project `16 - Active Satellite TLE Catalog`)
- `TLE Catalog Stats` (published data source on Tableau Server, project `16 - Active Satellite TLE Catalog`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/TLE Catalog Detail.hyper`
- `sample_output/TLE Catalog Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/tle_satellites/v1/spec.json \
    --flow-name tle_satellites
```

