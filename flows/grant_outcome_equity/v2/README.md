# grant_outcome_equity — v2

**Request:** Advanced-route deliverable: grant-outcome equity. Pull CDC PLACES county-level health-outcomes (2023) as a NEED proxy. Publish a PLACES-focused DS keyed on county+measure that operators can pivot in Tableau. State-level FY24 SLED grant totals come from the existing flow #3 output at dashboard-time. This is the CANONICAL pass-3 proxy-substitution demo: real grant outcomes aren't available, so we substitute health-outcome burden as a need proxy.

## Sources

- **REST API** (`json`): https://chronicdata.cdc.gov/resource/swc5-untb.json?$where=year%3D%272023%27+AND+categoryid%3D%27HLTHOUT%27&$order=locationid&$select=year,stateabbr,statedesc,locationname,category,measure,data_value,totalpopulation,locationid,categoryid,measureid,short_question_text

## Transformations

- (none — raw passthrough)

## Outputs

- `PLACES Health Outcome Burden Detail` (published data source on Tableau Server, project `38 - Grant Outcome Equity`)

## Refresh cadence

`monthly`
Prior versions: `v1`

## Sample output

- `sample_output/PLACES Health Outcome Burden Detail.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/grant_outcome_equity/v2/spec.json \
    --flow-name grant_outcome_equity
```

