# fed_register_actions — v1

**Request:** Pull all Federal Register documents (Rule, Proposed Rule, Notice, Presidential Document) from federalregister.gov for the last 18 months. Treat each document as a regulatory 'case'. Enrich with primary agency name flattened from the agencies list, document type, days_since_publication, plus trend analysis by agency_primary so case-management analysts can see rule-making volume + lag per agency. Publish to 'Prep Agent / 04 - Federal Register Actions' on Tableau Server.

## Sources

- **REST API** (`json`): https://www.federalregister.gov/api/v1/documents.json?conditions%5Bpublication_date%5D%5Bgte%5D=2025-01-01

## Transformations

- **trend_analysis**: Reg Action Trend

## Outputs

- `Federal Register Detail` (published data source on Tableau Server, project `04 - Federal Register Actions`)
- `Federal Register Stats` (published data source on Tableau Server, project `04 - Federal Register Actions`)

## Refresh cadence

`weekly`

## Sample output

- `sample_output/Federal Register Detail.hyper`
- `sample_output/Federal Register Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/fed_register_actions/v1/spec.json \
    --flow-name fed_register_actions
```

