# propublica_ny_nonprofits — v1

**Request:** Pull New York State nonprofit organizations from ProPublica Nonprofit Explorer (IRS Form 990-derived data). ~10k orgs (API caps at 10k results per search). One row per nonprofit. Enrich with ntee_family (map_values on ntee_code first character -> Arts_Culture / Education / Environment / Animals / Health / Human_Services / International / Public_Benefit / Religion / Other) and subsection_class (map_values on subseccd IRS 501(c) subsection: 3=public_charity, 4=civic_league, 5=labor, 6=business_league, 7=social, others=other). Publish to 'Prep Agent / 26 - NY Nonprofit Directory' on Tableau Server for state AG offices, community-planning agencies, and grantmakers vetting local nonprofits. ProPublica is Cloudflare-fronted at projects.propublica.org, reliable and no auth required.

## Sources

- **REST API** (`json`): https://projects.propublica.org/nonprofits/api/v2/search.json?q=&state%5Bid%5D=NY

## Transformations

- (none — raw passthrough)

## Outputs

- `NY Nonprofit Directory` (published data source on Tableau Server, project `26 - NY Nonprofit Directory`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/NY Nonprofit Directory.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/propublica_ny_nonprofits/v1/spec.json \
    --flow-name propublica_ny_nonprofits
```

