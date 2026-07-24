# UK_Parliament_Written_Questions — v1

**Request:** Pull UK Parliament written questions from the questions-statements-api.parliament.uk /api/writtenquestions/questions endpoint for the last 90 days across all answering bodies. Each question row includes the tabled/answer dates, department (answeringBodyName), asking member (askingMemberId), topic heading, question text, and answer text. Flatten the nested `results[].value` shape with dotted_path derived columns. Enrich with answer_latency_days (days_between dateTabled and dateAnswered — signals departmental responsiveness), department_group (map_values on answeringBodyName: Defence/Home Office/Health/Education/Treasury/etc.), and answer_status (map_values on isWithdrawn/dateAnswered presence). Publish to 'Prep Agent / 34 - UK Parliament Written Questions' on Tableau Server for Cabinet Office / Parliament analysts. OGL v3, no API key required.

## Sources

- **REST API** (`json`): https://questions-statements-api.parliament.uk/api/writtenquestions/questions?take=1000&tabledWhenFrom=2026-05-01

## Transformations

- **trend_analysis**: Parliament Written Questions Trend

## Outputs

- `UK Parliament Written Questions Detail` (published data source on Tableau Server, project `34 - UK Parliament Written Questions`)
- `UK Parliament Written Questions Stats` (published data source on Tableau Server, project `34 - UK Parliament Written Questions`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/UK Parliament Written Questions Detail.sample.csv`
- `sample_output/UK Parliament Written Questions Stats.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/UK_Parliament_Written_Questions/v1/spec.json \
    --flow-name UK_Parliament_Written_Questions
```

