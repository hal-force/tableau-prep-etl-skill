# usgs_earthquakes — v1

**Request:** Pull the last month of significant earthquakes from the USGS GeoJSON summary feed. Flatten each event to mag, place, event_time (ISO from epoch ms), alert, tsunami flag, magType, lon/lat/depth, and a felt-count enrichment. Publish to 'Prep Agent / 15 - USGS Significant Earthquakes' on Tableau Server for global-events / DoD site-risk analysts.

## Sources

- **REST API** (`json`): https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson

## Transformations

- **trend_analysis**: Quake Trend

## Outputs

- `USGS Quake Detail` (published data source on Tableau Server, project `15 - USGS Significant Earthquakes`)
- `USGS Quake Stats` (published data source on Tableau Server, project `15 - USGS Significant Earthquakes`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/USGS Quake Detail.hyper`
- `sample_output/USGS Quake Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/usgs_earthquakes/v1/spec.json \
    --flow-name usgs_earthquakes
```

