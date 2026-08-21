# MOD_JEWOSC_EW_Fusion_v4 — v1

**Request:** MOD JEWOSC EW intercept -> mission-data fusion (v4, native joins). A fuzzy parametric MATCH node assigns each ELINT/ES intercept cut a library emitter_id (modelling; nearest-neighbour can't be an equality join), then three reference sources — an emitter threat library, an Electronic Order of Battle laydown rollup, and platform mission-data-file coverage — are FUSED onto the matched intercepts with native Prep SuperJoins on emitter_id. Surfaces matched/ambiguous/unknown emitters, reprogramming triggers, library-vs-measured parametrics, EOB affiliation, and platform coverage gaps. Baltic scenario. All data synthetic/notional for a JEWOSC evaluation demo.

## Sources

- **local_csv** (`csv`)
- **local_csv** (`csv`)
- **local_csv** (`csv`)
- **local_csv** (`csv`)

## Transformations

- **ew_intercept_match**: EW Intercept Match
- **join**: Fuse the emitter threat-library record onto each matched intercept on emitter_id (NATO name, system type, lethality, weapon, library parametrics).
- **join**: Fuse the Electronic Order of Battle rollup on emitter_id (known-site count, affiliation, confirmed/active).
- **join**: Fuse platform mission-data-file coverage on emitter_id (coverage gap count + which platforms are blind to this emitter).

## Outputs

- `MOD JEWOSC EW Fusion v4` (published data source on Tableau Server, project `31 - MOD JEWOSC EW Fusion Demo`)

## Refresh cadence

`hourly`

## Sample output

- `sample_output/MOD JEWOSC EW Fusion v4.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/MOD_JEWOSC_EW_Fusion_v4/v1/spec.json \
    --flow-name MOD_JEWOSC_EW_Fusion_v4
```

