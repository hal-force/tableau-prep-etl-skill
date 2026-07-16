# gdelt_centcom — v1

**Request:** Pull the latest GDELT global events feed, filter to CENTCOM AOR countries (IR, IQ, SY, YE, AF, SA, QA, KW, BH, OM, AE, JO, LB, EG, PK, TJ, TM, UZ, KG, KZ), and enrich with a Goldstein-scale conflict-cooperation band. Publish to 'Prep Agent / 17 - GDELT CENTCOM AOR Events' on Tableau Server for regional-intelligence analysts.

## Sources

- **REST API** (`csv_index_then_zip`): http://data.gdeltproject.org/events/index.html

## Transformations

- (none — raw passthrough)

## Outputs

- `GDELT CENTCOM Events` (published data source on Tableau Server, project `17 - GDELT CENTCOM AOR Events`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/GDELT CENTCOM Events.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/gdelt_centcom/v1/spec.json \
    --flow-name gdelt_centcom
```

