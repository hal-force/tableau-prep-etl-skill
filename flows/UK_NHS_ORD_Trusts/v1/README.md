# UK_NHS_ORD_Trusts — v1

**Request:** Pull the NHS Organisation Reference Data (ORD) directory of active NHS Trusts from directory.spineservices.nhs.uk (Spine ORD 2-0-0), PrimaryRoleId=RO197 (NHS TRUST). One row per trust (~247 rows). Each record includes Name, OrgId (trust code), Status, OrgRecordClass, PostCode, LastChangeDate, PrimaryRoleDescription. Enrich with postcode_district (substring of PostCode up to the space), postcode_area (substring: first 2 chars — 'BA', 'SW', 'M', etc.), org_id_prefix (substring: first 3 chars of OrgId — 'R1A', 'RXK', etc.), record_freshness_days (days_since LastChangeDate), and region_group (map_values on postcode_area to England regions: NE/NW/YH/EM/WM/EE/L/SE/SW/None). Publish to 'Prep Agent / 35 - UK NHS Organisation Reference Data' on Tableau Server for NHS England / DHSC / regional ICB analysts. Keyless, OGL v3, no API key required.

## Sources

- **REST API** (`json`): https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations?Status=Active&PrimaryRoleId=RO197&Limit=1000

## Transformations

- **trend_analysis**: NHS Trusts Trend

## Outputs

- `UK NHS Trusts Detail` (published data source on Tableau Server, project `35 - UK NHS Organisation Reference Data`)
- `UK NHS Trusts Stats` (published data source on Tableau Server, project `35 - UK NHS Organisation Reference Data`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/UK NHS Trusts Detail.sample.csv`
- `sample_output/UK NHS Trusts Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/UK_NHS_ORD_Trusts/v1/spec.json \
    --flow-name UK_NHS_ORD_Trusts
```

