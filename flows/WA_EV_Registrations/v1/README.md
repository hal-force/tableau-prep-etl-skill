# WA EV Registrations — v1

**Request:** Pull Washington State electric-vehicle registrations from data.wa.gov (Socrata resource f6w7-q2d2, WA Dept of Licensing). ~290k rows. One row per registered EV. Enrich with range_band (numeric_bin on electric_range: unknown <1 / short <100 / medium <200 / long <300 / ultra_long >=300) and ev_class (map_values on ev_type: 'Battery Electric Vehicle (BEV)'=bev, 'Plug-in Hybrid Electric Vehicle (PHEV)'=phev, others=other). Publish to 'Prep Agent / 30 - WA EV Registrations' on Tableau Server for WA Department of Ecology, Dept of Commerce EV-incentive teams, and utility planners at PSE/Seattle City Light. data.wa.gov is Socrata-hosted, reliable.

## Sources

- **REST API** (`json`): https://data.wa.gov/resource/f6w7-q2d2.json?$order=dol_vehicle_id&$select=vin_1_10,county,city,state,zip_code,model_year,make,model,ev_type,cafv_type,electric_range,legislative_district,dol_vehicle_id,electric_utility,_2020_census_tract

## Transformations

- (none — raw passthrough)

## Outputs

- `WA EV Registrations` (published data source on Tableau Server, project `30 - WA EV Registrations`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/WA EV Registrations.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/WA_EV_Registrations/v1/spec.json \
    --flow-name WA_EV_Registrations
```

