# fec_candidate_totals — v1

**Request:** Pull US federal candidate (House/Senate/President) fundraising totals for the 2024 cycle from the FEC's api.open.fec.gov /v1/candidates/totals endpoint. ~5,323 candidates. One row per candidate-cycle. Enrich with receipts_band (numeric_bin on receipts: micro <10k / small <100k / mid <1M / large <5M / mega >=5M) and party_class (map_values on party: DEM=democratic, REP=republican, LIB=libertarian, GRE=green, IND=independent, others=other). Publish to 'Prep Agent / 27 - FEC Candidate Totals' on Tableau Server for state boards of elections and civic-transparency organizations. Uses DEMO_KEY or user-supplied API_DATA_GOV_KEY.

## Sources

- **REST API** (`json`): https://api.open.fec.gov/v1/candidates/totals/?election_year=2024&api_key=DEMO_KEY

## Transformations

- **trend_analysis**: FEC Candidate Totals Trend

## Outputs

- `FEC Candidate Totals` (published data source on Tableau Server, project `27 - FEC Candidate Totals`)
- `FEC Candidate Totals Stats` (published data source on Tableau Server, project `27 - FEC Candidate Totals`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/FEC Candidate Totals Stats.sample.csv`
- `sample_output/FEC Candidate Totals.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/fec_candidate_totals/v1/spec.json \
    --flow-name fec_candidate_totals
```

