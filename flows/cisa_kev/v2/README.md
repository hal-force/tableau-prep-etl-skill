# cisa_kev — v2

**Request:** Pull the CISA Known Exploited Vulnerabilities (KEV) catalog and enrich with days-since-added, days-to-due (SLA), and cwe_first columns for federal-agency vulnerability management. Publish to 'Prep Agent / 13 - CISA Known Exploited Vulnerabilities' on Tableau Server.

## Sources

- **REST API** (`json`): https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json

## Transformations

- **trend_analysis**: KEV Trend

## Outputs

- `CISA KEV Detail` (published data source on Tableau Server, project `13 - CISA Known Exploited Vulnerabilities`)
- `CISA KEV Stats` (published data source on Tableau Server, project `13 - CISA Known Exploited Vulnerabilities`)

## Refresh cadence

`daily`
Prior versions: `v1`

## Sample output

- `sample_output/CISA KEV Detail.hyper`
- `sample_output/CISA KEV Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/cisa_kev/v2/spec.json \
    --flow-name cisa_kev
```

