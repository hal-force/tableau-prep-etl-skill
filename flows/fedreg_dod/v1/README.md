# fedreg_dod — v1

**Request:** Pull YTD 2026 Federal Register documents where the DoD is a listed agency. Flatten to one row per document with title, type, publication date, first agency, doc URL, days_since_published, and calendar features. Publish to 'Prep Agent / 14 - Federal Register DoD Documents' on Tableau Server for defense-policy analysts.

## Sources

- **REST API** (`json`): https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=defense-department&conditions%5Bpublication_date%5D%5Bgte%5D=2026-01-01&conditions%5Bpublication_date%5D%5Blte%5D=2026-07-14&per_page=100&page=1

## Transformations

- **trend_analysis**: FedReg DoD Trend

## Outputs

- `FR DoD Documents` (published data source on Tableau Server, project `14 - Federal Register DoD Documents`)
- `FR DoD Stats` (published data source on Tableau Server, project `14 - Federal Register DoD Documents`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/FR DoD Documents.hyper`
- `sample_output/FR DoD Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/fedreg_dod/v1/spec.json \
    --flow-name fedreg_dod
```

