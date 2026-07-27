# federal_kev_exposure — v2

**Request:** Advanced-route deliverable: federal KEV exposure ranking. Pull the CISA Known Exploited Vulnerabilities catalog and enrich for FCEB agencies with SLA pressure (days_to_due, exploit_sla_days), ransomware flag, and CWE class. This is the CANONICAL RED-path demo: per-agency CVE inventory is not publicly available and is declared as gap in the DS description. Publish two DSes to Tableau Cloud under Prep Agent. Fed Workforce (BLS CES) join is a dashboard-time capacity proxy.

## Sources

- **REST API** (`json`): https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json

## Transformations

- **trend_analysis**: Federal KEV Exposure Trend

## Outputs

- `Federal KEV Exposure Detail` (published data source on Tableau Server, project `36 - Federal KEV Exposure`)
- `Federal KEV Exposure Stats` (published data source on Tableau Server, project `36 - Federal KEV Exposure`)

## Refresh cadence

`weekly`
Prior versions: `v1`

## Sample output

- `sample_output/Federal KEV Exposure Detail.hyper`
- `sample_output/Federal KEV Exposure Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/federal_kev_exposure/v2/spec.json \
    --flow-name federal_kev_exposure
```

