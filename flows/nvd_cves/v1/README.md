# nvd_cves — v1

**Request:** Pull the last 30 days of CVEs from the NIST NVD REST v2 API (published 2026-06-15 through 2026-07-14). Flatten each vulnerability's id, publication date, description, CVSS v3.1 base score + severity, primary CWE, and enrich with cvss_band (Critical/High/Medium/Low), days_since_published, and trend analysis by cvss_band + severity. Publish to 'Prep Agent / 12 - NIST NVD Vulnerabilities' on Tableau Server for vulnerability management analysts.

## Sources

- **REST API** (`json`): https://services.nvd.nist.gov/rest/json/cves/2.0?pubStartDate=2026-06-15T00:00:00.000&pubEndDate=2026-07-14T23:59:59.999

## Transformations

- **trend_analysis**: NVD Trend

## Outputs

- `NVD Vulnerability Detail` (published data source on Tableau Server, project `12 - NIST NVD Vulnerabilities`)
- `NVD Vulnerability Stats` (published data source on Tableau Server, project `12 - NIST NVD Vulnerabilities`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/NVD Vulnerability Detail.hyper`
- `sample_output/NVD Vulnerability Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/nvd_cves/v1/spec.json \
    --flow-name nvd_cves
```

