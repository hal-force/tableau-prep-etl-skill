# fema_disasters — v1

**Request:** Pull FEMA Disaster Declaration Summaries from OpenFEMA OData v2 since 2022-01-01, treat each declaration as a public-safety incident case, enrich with days_since_declaration, days_open (declarationDate to disasterCloseoutDate), incidentType-by-state hot-spot trend analysis, and publish to 'Prep Agent / 05 - FEMA Disaster Cases' on Tableau Server for emergency-management analysts.

## Sources

- **REST API** (`json`): https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?$filter=declarationDate%20gt%20%272022-01-01T00:00:00.000Z%27

## Transformations

- **trend_analysis**: Disaster Trend

## Outputs

- `FEMA Disaster Detail` (published data source on Tableau Server, project `05 - FEMA Disaster Cases`)
- `FEMA Disaster Stats` (published data source on Tableau Server, project `05 - FEMA Disaster Cases`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/FEMA Disaster Detail.hyper`
- `sample_output/FEMA Disaster Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/fema_disasters/v1/spec.json \
    --flow-name fema_disasters
```

