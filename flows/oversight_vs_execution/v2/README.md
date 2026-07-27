# oversight_vs_execution — v2

**Request:** Advanced-route deliverable: oversight vs execution — GRACEFUL DEGRADE on Congressional-interest RED. Pull 18mo of Federal Register documents ACROSS all executive-branch agencies (not just DoD) as the oversight-signal proxy. Publish two DSes to Tableau Cloud under Prep Agent. Execution-side joins to DoD Contracts + USASpending SLED Grants happen at dashboard time.

## Sources

- **REST API** (`json`): https://www.federalregister.gov/api/v1/documents.json?conditions%5Bpublication_date%5D%5Bgte%5D=2025-01-24&conditions%5Bpublication_date%5D%5Blte%5D=2026-07-24

## Transformations

- **trend_analysis**: Oversight Execution Trend

## Outputs

- `Oversight vs Execution Detail` (published data source on Tableau Server, project `40 - Oversight vs Execution`)
- `Oversight vs Execution Stats` (published data source on Tableau Server, project `40 - Oversight vs Execution`)

## Refresh cadence

`daily`
Prior versions: `v1`

## Sample output

- `sample_output/Oversight vs Execution Detail.hyper`
- `sample_output/Oversight vs Execution Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/oversight_vs_execution/v2/spec.json \
    --flow-name oversight_vs_execution
```

