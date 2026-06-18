# gdelt_global — v1

**Request:** Pull the latest GDELT global events feed and load into a local Hyper extract for Tableau analysis. One row per event, geocoded by lat/lon with country, event-root code (CAMEO), Goldstein scale, and source URL. No country filter - keep events worldwide so we can map global activity by location.

## Sources

- **REST API** (`csv_index_then_zip`): http://data.gdeltproject.org/events/index.html

## Transformations

- (none — raw passthrough)

## Outputs

- `gdelt_global_events.hyper` (local Tableau Hyper extract)

## Refresh cadence

`daily`

## Sample output

- `sample_output/gdelt_global_events.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/gdelt_global/v1/spec.json \
    --flow-name gdelt_global
```

