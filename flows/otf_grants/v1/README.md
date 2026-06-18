# otf_grants — v1

**Request:** Pull all three Ontario Trillium Foundation open datasets (the master grants list since 2000, the catchment-area-to-cities concordance, and the catchment-area-to-census-division concordance), join them on city and catchment ID, and publish the enriched grants table to the 'Grants' project on Tableau Server.

## Sources

- **REST API** (`csv`): https://otf.ca/sites/default/files/OTF-Grants_since2000.csv
- **REST API** (`csv`): https://otf.ca/sites/default/files/otf_catchment_area-cities_concordance_file.csv
- **REST API** (`csv`): https://otf.ca/sites/default/files/otf_catchment_area-census_division_concordance_file.csv

## Transformations

- **join**: Left-outer join the OTF grants ledger to the cities concordance on Recipient City to add the catchment area and catchment ID for every grant.
- **join**: Left-outer join the city-enriched grants to the census-division concordance on Catchment ID so each grant carries the Statistics Canada census division name.

## Outputs

- `OTF Grants Enriched` (published data source on Tableau Server, project `Grants`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/OTF Grants Enriched.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/otf_grants/v1/spec.json \
    --flow-name otf_grants
```

