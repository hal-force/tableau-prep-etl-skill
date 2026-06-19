# opensky_us — v1

**Request:** Pull a live snapshot of all aircraft state vectors over the contiguous United States (lat 24-49.5, lon -125 to -66) from the OpenSky Network public API. Each row = one aircraft instance with position, velocity, heading, altitude, ground/airborne state. Publish to 'Prep Agent / 08 - Live US Air Traffic' on Tableau Server for transportation analysts to monitor airspace utilization in real time.

## Sources

- **REST API** (`json`): https://opensky-network.org/api/states/all?lamin=24&lamax=49.5&lomin=-125&lomax=-66

## Transformations

- (none — raw passthrough)

## Outputs

- `OpenSky US Live States` (published data source on Tableau Server, project `08 - Live US Air Traffic`)

## Refresh cadence

`hourly`

## Sample output

- `sample_output/OpenSky US Live States.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/opensky_us/v1/spec.json \
    --flow-name opensky_us
```

