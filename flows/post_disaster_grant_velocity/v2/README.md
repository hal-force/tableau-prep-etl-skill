# post_disaster_grant_velocity — v2

**Request:** Advanced-route deliverable: post-disaster grant velocity. Pull FEMA Disaster Declaration Summaries for the last 24 months (declarationDate > 2024-07-24) as the F1 anchor. Enrich with days_since_declaration, days_open. Publish two DSes to Tableau Cloud under Prep Agent. Grant-side joins to 'SLED Grants FY24 Detail' + 'USASpending SLED Grants' + 'Fed Outlays' happen at dashboard time — this is the 4-DS join demo.

## Sources

- **REST API** (`json`): https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?$filter=declarationDate%20gt%20%272024-07-24T00:00:00.000Z%27

## Transformations

- **trend_analysis**: Post Disaster Velocity Trend

## Outputs

- `Post Disaster Anchor Detail` (published data source on Tableau Server, project `39 - Post Disaster Grant Velocity`)
- `Post Disaster Trend Stats` (published data source on Tableau Server, project `39 - Post Disaster Grant Velocity`)

## Refresh cadence

`daily`
Prior versions: `v1`

## Sample output

- `sample_output/Post Disaster Anchor Detail.hyper`
- `sample_output/Post Disaster Trend Stats.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/post_disaster_grant_velocity/v2/spec.json \
    --flow-name post_disaster_grant_velocity
```

