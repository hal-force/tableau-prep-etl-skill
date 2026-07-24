# CDC PLACES County Health 2023 — v1

**Request:** Pull CDC PLACES county-level health metrics from chronicdata.cdc.gov (Socrata resource swc5-untb) for the most recent complete year (2023). ~198k rows: one row per (US county x health measure). PLACES provides ~40 chronic disease + prevention indicators for all 3,143 US counties, sourced from BRFSS. Enrich with measure_class (map_values on categoryid: HLTHOUT=health_outcomes, PREVENT=prevention, HLTHSTAT=health_status, RISKBEH=risk_behaviors, DISABILT=disability, SOCLNEEDS=social_needs), value_band (numeric_bin on data_value: <10 low / 10-20 moderate / 20-30 elevated / 30+ high) and pop_band (numeric_bin on totalpopulation: <25k tiny / 25-100k small / 100-500k mid / 500k+ large). Publish to 'Prep Agent / 29 - CDC PLACES County Health' on Tableau Server for state/local public-health analysts benchmarking their counties against peers. chronicdata.cdc.gov is Socrata-hosted (same FedRAMP tenant as data.cdc.gov).

## Sources

- **REST API** (`json`): https://chronicdata.cdc.gov/resource/swc5-untb.json?$where=year=%272023%27&$order=locationid&$select=year,stateabbr,statedesc,locationname,datasource,category,measure,data_value_unit,data_value_type,data_value,low_confidence_limit,high_confidence_limit,totalpopulation,totalpop18plus,locationid,categoryid,measureid,datavaluetypeid,short_question_text

## Transformations

- (none — raw passthrough)

## Outputs

- `CDC PLACES County Health 2023` (published data source on Tableau Server, project `29 - CDC PLACES County Health`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/CDC PLACES County Health 2023.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/CDC_PLACES_County_Health_2023/v1/spec.json \
    --flow-name CDC_PLACES_County_Health_2023
```

