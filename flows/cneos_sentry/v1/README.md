# cneos_sentry — v1

**Request:** Pull NASA JPL CNEOS Sentry impact-risk catalog (~2160 asteroids on the risk list, with cumulative Palermo scale and impact probability). Enrich each row with palermo_band and days_since_last_obs. Publish to 'Prep Agent / 20 - NASA CNEOS Sentry Impact Risks' on Tableau Server for planetary-defense + space-domain-awareness analysts.

## Sources

- **REST API** (`json`): https://ssd-api.jpl.nasa.gov/sentry.api

## Transformations

- **trend_analysis**: Sentry Trend

## Outputs

- `CNEOS Sentry Detail` (published data source on Tableau Server, project `20 - NASA CNEOS Sentry Impact Risks`)
- `CNEOS Sentry Stats` (published data source on Tableau Server, project `20 - NASA CNEOS Sentry Impact Risks`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/CNEOS Sentry Detail.sample.csv`
- `sample_output/CNEOS Sentry Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/cneos_sentry/v1/spec.json \
    --flow-name cneos_sentry
```

