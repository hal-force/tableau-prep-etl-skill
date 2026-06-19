# college_scorecard — v1

**Request:** Pull the College Scorecard 'Most Recent Cohorts (Institution-Level)' bulk CSV from the U.S. Department of Education public download bucket, slice to the 23 columns relevant for a comparison demo (cost, completion, debt, earnings, admission rate, geography), and publish to 'Prep Agent / 07 - College Outcomes' on Tableau Server for education analysts.

## Sources

- **REST API** (`csv_zip`): https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Institution_06102026.zip

## Transformations

- (none — raw passthrough)

## Outputs

- `College Scorecard Outcomes` (published data source on Tableau Server, project `07 - College Outcomes`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/College Scorecard Outcomes.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/college_scorecard/v1/spec.json \
    --flow-name college_scorecard
```

