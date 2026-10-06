# Example: synthetic multi-view scenario (one trigger → N extracts)

User request (two real instances):

> Create a Tableau Prep flow that addresses these eight required
> visualization views (operational picture, kill-web, effectiveness, …).

> Create Prep flows for an MTF "Net Assessment": cross-reference physical
> beds against credentialed, cleared, available staff and model how a
> deployment tasking or surge changes staffed-bed capacity.

Both are RFI/demo requests where **no real source is reachable** (classified
or PHI systems of record) and the deliverable is the *data layer* for a set of
dashboard views. The pattern: a deterministic synthetic scenario module, and a
flow that fans one trigger out to one script node + one Hyper output per view.

## What this exercises

- No-source flows: a one-row Excel trigger that only exists to fire the flow
- Fan-out topology: N independent `script → hyper` branches off one anchor
- A **shared Python module** imported by every script node (one scenario,
  N projections), so the extracts are mutually consistent
- A cross-extract coherence gate, beyond the per-Hyper QA gate

## Shape

```
Trigger (trigger.xlsx, 1 row)
  ├─ View 1 script ─→ 01 View 1.hyper
  ├─ View 2 script ─→ 02 View 2.hyper
  └─ …            ─→ …
```

Each `view_<x>.py` exposes `build_<x>(df)` (the node entry point — it ignores
the trigger row) and `get_output_schema()`. Each imports one shared
`scenario_core.py` that builds the whole scenario from a fixed seed; the view
modules only *project* it (filter, flatten, pick columns). Never let two view
modules generate overlapping facts independently — they will drift apart.

## Building the .tfl

Start from a small seed flow that has an Excel input (here
`flows/cisa_kev/v2/cisa_kev.tfl`), shrink it to just that input, and attach
the branches:

```python
from tflb_lib.builder import build
from tflb_lib.topology import add_branch, prune_to_keep_set

INPUT_ID = "017ccb43-97be-4bda-b6a5-f292540ff5ad"   # cisa_kev Excel input
CONN_ID  = "ff5c040b-e00f-49c3-8da7-33606fc6da2d"

def mutate(flow):
    prune_to_keep_set(flow, {"CISA KEV Catalog"})   # also drops edges to removed nodes
    trig = flow["nodes"][INPUT_ID]
    trig["name"] = "Scenario Trigger"
    attrs = flow["connections"][CONN_ID]["connectionAttributes"]
    attrs["filename"] = str(TRIGGER_XLSX)
    attrs["directory"] = str(HERE)
    for script, fn, node_name, out_base in BRANCHES:
        add_branch(flow, "Scenario Trigger", [
            {"kind": "script", "name": node_name,
             "script_path": HERE / script, "function_name": fn},
            {"kind": "hyper", "name": out_base,
             "hyper_path": OUT_DIR / (out_base + ".hyper")},
        ])

build(SRC_TFL, DST_TFL, [("views", mutate)])
```

Notes:

- `add_branch` **appends** to the anchor's `nextNodes`, so N calls on the same
  anchor give N parallel branches. It is name-idempotent: if the first step's
  name already exists, that branch is skipped — so node names must be unique.
- The trigger's column must match the seed input's declared field. For
  `cisa_kev` that is **`folder`**:
  `pd.DataFrame({"folder": ["SCENARIO-001"]}).to_excel(TRIGGER_XLSX, index=False)`.
  Keep the name so the file matches the input node's declared field list.
- `.tfl` is a ZIP — use `tflb_lib.builder.read_flow()` to inspect one, not
  `json.load` (see `../tfl_format.md`).

## Importing the shared module from a script node

TabPy runs the node's source text, so the flow directory is not on `sys.path`
and `__file__` may not be defined. Guard it with a hardcoded fallback:

```python
import os, sys
_FLOW_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() \
    else "/abs/path/to/flow_dir"
if _FLOW_DIR not in sys.path:
    sys.path.insert(0, _FLOW_DIR)
import scenario_core as SC  # noqa: E402
```

The same file then runs unchanged standalone (`python3 view_x.py`) and under
TabPy. The fallback path pins the flow to that directory; moving the flow
means rebuilding with the new path. See `../tabpy_setup.md` → "Shared modules
across script nodes" and "`get_output_schema()` must return a DataFrame".

## QA: check the extracts against each other

The per-Hyper gate (schema, nulls, distinct bounds) can't catch two extracts
that disagree. Add a local harness (`run_local.py`) that calls every
`build_<x>()`, writes each Hyper, and asserts cross-view invariants, e.g.:

- the leakers in the Effectiveness view == the failure points in the Kill-Web
- every RED cell in the Net Assessment raises a CRITICAL alert, and vice versa
- the per-cell staff counts in the Net Assessment == the aggregation of the
  reconciled roster extract
- a known worked example reproduces exactly (e.g. "−5 ICU nurses at 1:2 →
  −10 staffed beds")

Run the harness first (fast, no Tableau), then `tableau-prep-cli -t <flow>.tfl`
to prove the nodes also run under TabPy, then read the Tableau-produced
Hypers back and re-check the headline numbers.

## Scoping: say what Prep won't do

These requests usually include asks that belong to the layer above Prep.
State them up front (see `SKILL.md` → "It is not the right tool for"):
real-time/event-driven refresh, an interactive what-if (Prep bakes a fixed
set of named scenarios), alert *delivery* (Prep computes the breach flag),
and the dashboards themselves. Label all data `UNCLASSIFIED//SYNTHETIC` (or
your org's equivalent) in every row, and never commit the generated `.hyper`
files (see `../workflow_and_decision_gates.md`).
