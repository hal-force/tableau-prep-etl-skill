# doe_data_center_energy_monthly — v1

**Request:** DOE Data-Center Energy Monthly: state-level electricity consumption at monthly cadence, focused on the commercial sector (EIA sectorid=COM) which encompasses data-center load. Two composed EIA v2 sources: (1) retail-sales COM sector by state × month — sales (MWh) and average price — the canonical demand-side signal that the DOE tracks for commercial-sector electrification; (2) state-electricity-profiles/source-disposition — annual state totals for net-generation and supply, tying commercial demand to the supply-side story that drives siting decisions (PJM/ERCOT gas-and-nuclear vs. CAISO renewables). Region focus: 50 US states + DC. The narrative the dataset supports: Virginia's commercial-sector growth curve vs. rest-of-country (Loudoun-County data-center concentration), and how the state's supply mix constrains DC growth. All rows carry `region_type='state'` so downstream Tableau vizzes can filter by state, group by census region, or compare against national aggregates.

## Sources

- **REST API** (`json`): https://api.eia.gov/v2/electricity/retail-sales/data/?frequency=monthly&data[0]=sales&data[1]=price&facets[sectorid][]=COM&sort[0][column]=period&sort[0][direction]=desc
- **REST API** (`json`): https://api.eia.gov/v2/electricity/state-electricity-profiles/source-disposition/data/?frequency=annual&data[0]=total-net-generation&data[1]=total-supply&data[2]=direct-use&sort[0][column]=period&sort[0][direction]=desc

## Transformations

- (none — raw passthrough)

## Outputs

- `DOE Data Center Energy Monthly - Retail Sales` (published data source on Tableau Server, project `DOE Data Center Energy`)
- `DOE Data Center Energy Annual - Supply Disposition` (published data source on Tableau Server, project `DOE Data Center Energy`)

## Refresh cadence

`weekly`

## Sample output

- `sample_output/DOE Data Center Energy Annual - Supply Disposition.hyper`
- `sample_output/DOE Data Center Energy Monthly - Retail Sales.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/doe_data_center_energy_monthly/v1/spec.json \
    --flow-name doe_data_center_energy_monthly
```

