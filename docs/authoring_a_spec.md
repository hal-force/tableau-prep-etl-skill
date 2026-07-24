# Authoring a spec from scratch (no LLM gateway needed)

Most users start by copying the closest archived spec and editing.
The full path with no LLM gateway / no `/tableau-prep-etl` invocation:

```sh
# 1. Pick the closest archive (see docs/worked_examples.md). Trend by
#    date? Copy fed_outlays. POST + body? Copy fed_workforce. ZIP CSV?
#    Copy college_scorecard. Live snapshot? Copy opensky_us.
cp flows/fed_outlays/v1/spec.json runtime/specs/my_flow.json

# 2. Edit it. Required edits per section:
#
#    sources[0]:
#      url           - the publisher's endpoint
#      extra.json_schema (or csv_schema) - declare every column you'll keep
#      extra.json_records_path - dotted path if records aren't at top level
#      extra._skip_auto_casts: true - safest default; the cast planner has
#                                     edge cases on CamelCase column names
#
#    transformations[]:
#      kind: "trend_analysis" - YoY/rolling/anomaly per dimension. Need a
#                               date_col on the source.
#      kind: "graph_analysis" - networkx centralities + spring layout.
#                               Need source_id_col + target_id_col on edges.
#      kind: "eoc_fire_metrics" - WFIGS/NIFC fire-incident enrichment.
#      kind: "join"           - multi-source flows; index sources by branch.
#      kind: "pii_redaction"  - mask PII per category, plus audit table.
#      []                      - empty: just publish raw + derived columns.
#
#    outputs[]:
#      One published_data_source entry per terminal node. trend_analysis
#      and pii_redaction emit two siblings (Features+Stats / Redact+Audit) -
#      both need an output with `source: "<NodeName>"` to land in Hyper.
#
#    server_publish:
#      project + parent_project (both name strings). The publish step
#      auto-creates the child under the named parent if --auto-create-project
#      is passed.

# 3. Verify locally (no server work):
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan --skip-cli   # generate scripts only
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan              # generate + verify with prep-cli

# 4. Publish to server (will auto-create parent/child project if missing):
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan --publish --auto-create-project
# If publish fails with "project not found" right after auto-create
# (cache lag), rerun without --auto-create-project:
python3 -m skill.scripts.run_loop \
    --spec runtime/specs/my_flow.json \
    --flow-name my_flow --skip-scan --publish

# 5. Archive the working version once it lands cleanly:
RD=$(ls -t runtime/my_flow/ | head -1)
python3 -m skill.scripts.archive_flow \
    --spec runtime/specs/my_flow.json \
    --run-dir runtime/my_flow/$RD \
    --flow-name my_flow --open-source     # --open-source: copies real Hyper sample
```

Reference for the `extra.*` knobs honored by api_caller (every JSON
pagination shape, every derived column kind):
**`skill/reference/api_caller_knobs.md`**.
