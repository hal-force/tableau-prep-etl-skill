# Example: Ontario Trillium Foundation grants (multi-source CSV join)

User request:

> Create a flow that grabs the Ontario Trillium Foundation grants
> dataset along with the catchment-area concordance files for cities
> and census divisions, then weaves them together so each grant carries
> its OTF catchment area and census division.

This is the canonical **multi-source join** example: three independent
public CSVs combined in Tableau Prep (not in Python) so an analyst can
swap encodings, change a join key, or repoint a URL without touching
Python.

## What this exercises

- Multi-source DAG (3 inputs → 2 joins → 1 output)
- Heterogeneous CSV encodings (UTF-8-BOM grants + Latin-1 concordances)
- Bilingual column headers (`Recipient Org:City:Org du bénéficiaires:Ville`)
  cleaned via `csv_rename_map` so join keys reduce to plain
  `city` / `catchment_id`
- Native Prep `.v2018_2_3.SuperJoin` nodes wired with
  `nextNamespace: "Left"` / `"Right"` and Maestro's canonical
  `JoinType` enum (`left`, not `leftOuter`)
- Per-source `csv_schema` so the validator's `INPUT_SCHEMA` is populated
  and downstream Hyper output keeps every upstream column

## Spec

`runtime/specs/otf_grants.json` (excerpted):

```json
{
  "sources": [
    {
      "type": "rest_api",
      "url": "https://otf.ca/sites/default/files/OTF-Grants_since2000.csv",
      "format": "csv",
      "extra": {
        "csv_encoding": "utf-8-sig",
        "csv_rename_map": {
          "Identifier:Identificateur": "grant_id",
          "Recipient Org:City:Org du bénéficiaires:Ville": "city",
          "Amount Awarded:Montant décerné": "amount_awarded"
        },
        "csv_usecols": ["grant_id", "city", "amount_awarded", "..."],
        "csv_schema": {"grant_id": "string", "city": "string",
                       "amount_awarded": "decimal"}
      }
    },
    {
      "type": "rest_api",
      "url": "https://otf.ca/sites/default/files/otf_catchment_area-cities_concordance_file.csv",
      "format": "csv",
      "extra": {
        "csv_encoding": "latin-1",
        "csv_rename_map": {
          "City:Ville": "city",
          "Catchment area:Région": "catchment_area",
          "Catchment ID:Numéro de région": "catchment_id"
        },
        "csv_schema": {"city": "string", "catchment_area": "string",
                       "catchment_id": "int"}
      }
    },
    {
      "type": "rest_api",
      "url": "https://otf.ca/sites/default/files/otf_catchment_area-census_division_concordance_file.csv",
      "format": "csv",
      "extra": {
        "csv_encoding": "latin-1",
        "csv_rename_map": {
          "Catchment area:Région": "catchment_area_census",
          "Census Division: Division de recensement": "census_division",
          "Catchment ID:Numéro de région": "catchment_id"
        },
        "csv_schema": {"catchment_area_census": "string",
                       "census_division": "string", "catchment_id": "int"}
      }
    }
  ],
  "transformations": [
    {"kind": "join", "args": {"name": "Grants + Cities",
                              "left_branch": 0, "right_branch": 1,
                              "on": "city", "join_type": "leftOuter"}},
    {"kind": "join", "args": {"name": "+ Census Division",
                              "left_branch": 0, "right_branch": 2,
                              "on": "catchment_id", "join_type": "leftOuter"}}
  ],
  "outputs": [{"kind": "hyper", "name": "otf_grants_enriched"}],
  "qa_tier": "deterministic",
  "refresh_cadence": "on_demand"
}
```

## Strategy chosen by `source_planner.py`

- **Source acquisition**: each source renders its own
  `api_caller_b<i>.py` (one per branch) — without the `_b<i>` suffix,
  later branches clobber earlier ones and Maestro reports
  `InvalidLeftConditionColumnMsg: Missing field: <col>` because every
  branch's `get_output_schema` returns the same (last) schema.
- **Joins** translate to two `.v2018_2_3.SuperJoin` nodes. The planner
  normalizes `leftOuter` to Maestro's enum `left` (the JVM enum
  rejects SQL synonyms with a `JoinAccessors.getJoinType` NPE).
- **Validator** receives a populated `INPUT_SCHEMA` derived from each
  source's `csv_schema`, so `pd.concat([df, val_df], axis=1)` keeps
  every upstream column in the Hyper output.

## DAG (after generation)

```
[Input 1: grants]    → API Caller_b0   ↘
                                        SuperJoin "Grants + Cities" (on city)  ↘
[Input 2: cities]    → API Caller_b1   ↗                                        SuperJoin "+ Census Division" (on catchment_id) → Validator → WriteToHyper
                                                                               ↗
[Input 3: census]    → API Caller_b2   ──────────────────────────────────────────
```

Each input is a tiny per-branch trigger.xlsx with a single `folder`
column; the API Caller ignores the input dataframe and pulls from the
configured URL.

## Run

```bash
python3 -m skill.scripts.run_loop \
  --spec runtime/specs/otf_grants.json \
  --flow-name otf_grants \
  --skip-cli  # omit to run the bounded refinement loop
```

## Verification (last working run)

- 3 source CSVs fetched (grants ~29 MB UTF-8-BOM; cities + census
  Latin-1)
- `flow.tfl` deserializes cleanly: `tableau-prep-cli -t flow.tfl`
  exits 0 ("Finished running the flow successfully")
- Output: `outputs/otf_grants_enriched.hyper`
  - 26 columns (16 grant fields + catchment/census joins + 6 validator
    cols) × 89,548 rows
  - 32,835 grants × ~2.7 census-division fan-out per catchment_id
  - 97% city-join coverage; 97% catchment/census coverage

## Gotchas codified from this run

Codified gotchas (multi-source / join traps):

1. `JoinType` enum strings must be `inner|left|right|full|notInner|leftOnly|rightOnly` — NOT `leftOuter`/`rightOuter`/`fullOuter`. The planner aliases the SQL forms automatically.
2. Edges *into* a `SuperJoin` need `nextNamespace: "Left"` / `"Right"`. Edges *out* of a join stay `Default`.
3. Multi-source flows must render per-branch script filenames (`api_caller_b0.py`, `api_caller_b1.py`, …). One file per branch is mandatory.
4. The validator's `INPUT_SCHEMA` template var must be populated from each source's declared schema, otherwise the Hyper output drops every input column.
