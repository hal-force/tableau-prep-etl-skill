# cisa_kev — v1

**Request:** Pull the CISA Known Exploited Vulnerabilities (KEV) catalog from cisa.gov, enrich with exploit window (days from added-to-due-date), normalized CWE list, ransomware-campaign flag, and run trend analysis by vendorProject. Publish to a 'Prep Agent / 03 - CISA KEV' project on Tableau Server for cyber analysts to track newly catalogued exploits and SLA pressure across vendors.

## Sources

- **REST API** (`json`): https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json

## Transformations

- **trend_analysis**: KEV Trend

## Outputs

- `CISA KEV Detail` (published data source on Tableau Server, project `03 - CISA KEV`)
- `CISA KEV Stats` (published data source on Tableau Server, project `03 - CISA KEV`)

## Refresh cadence

`weekly`

## Sample output

- `sample_output/CISA KEV Detail.hyper`
- `sample_output/CISA KEV Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/cisa_kev/v1/spec.json \
    --flow-name cisa_kev
```

