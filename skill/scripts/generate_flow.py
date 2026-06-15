"""
Generate a working .tfl file from a Plan + Spec.

Steps:
  1. Render every Jinja template in the plan to a .py file under
     <run_dir>/scripts/.
  2. Build a fresh .tfl from a minimal seed template, mutating it via
     tflb_lib primitives:
       - one input node (folder-listing xlsx for non-native sources;
         direct connector for native ones)
       - one Python Script node per transform / qa_node
       - one WriteToHyper output node per output
       - edges wiring everything in series

This v1 builds linear flows. More complex DAGs (multi-source joins,
fan-out validators) come in a later iteration.

Public entry: `generate_flow(spec, plan, run_dir) -> Path`
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile

# Bootstrap tflb_lib
from skill.scripts.lib import _REPO_ROOT  # noqa: F401

from jinja2 import Environment, FileSystemLoader

from tflb_lib.nodes import (
    add_edge,
    make_hyper_node,
    make_script_node,
    new_id,
)
from tflb_lib.builder import write_flow

from skill.scripts.intake import Spec
from skill.scripts.source_planner import NodePlan, Plan


# Minimal seed flow JSON. The .tfl ZIP must have a `flow` member.
# `displaySettings` and `maestroMetadata` would normally come from
# Tableau Prep Builder; for skill-generated flows we emit empty ones
# (Builder regenerates layout when the file is opened).
SEED_FLOW: dict = {
    "parameters": {"parameters": {}},
    "initialNodes": [],
    "nodes": {},
    "connections": {},
    "dataConnections": {},
    "connectionIds": [],
    "dataConnectionIds": [],
    "nodeProperties": [],
    "extensibility": {},
    "selection": {},
    "majorVersion": 2026,
    "minorVersion": 1,
    "documentId": "",
    "obfuscatorId": "",
}

SEED_DISPLAY_SETTINGS = {"viewport": {"x": 0, "y": 0, "scale": 1.0}, "nodes": {}}
SEED_MAESTRO_METADATA = {"version": "skill-generated", "skill": "tableau-prep-etl"}


def _render_templates(plan: Plan, scripts_dir: Path, templates_dir: Path) -> None:
    """Render every script template referenced by the plan to scripts_dir."""
    scripts_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(templates_dir))

    for node in (*plan.transforms, *plan.qa_nodes):
        if not node.template:
            continue
        try:
            tpl = env.get_template(node.template)
        except Exception as e:
            raise RuntimeError(f"failed to load template '{node.template}': {e}")
        rendered = tpl.render(**node.template_vars)
        script_name = node.template.replace(".j2", "").replace("/", "_")
        out_path = scripts_dir / script_name
        out_path.write_text(rendered)
        node.rendered_path = str(out_path.resolve())


def _make_input_node(plan_input: NodePlan, trigger_xlsx: Path) -> tuple[str, dict]:
    """Build an input node. For non-native sources we always use the
    folder-listing xlsx as a 'trigger' input that the downstream Script
    node ignores in favor of the configured URL/folder/etc."""
    nid = new_id()
    if plan_input.connector_class in ("local_folder", "local_xlsx_pointer"):
        return nid, {
            "nodeType": ".v1.LoadSql",
            "name": plan_input.name,
            "id": nid,
            "baseType": "input",
            "nextNodes": [],
            "serialize": False,
            "description": None,
            "connectionId": "",  # filled by skill in build()
            "connectionAttributes": {},
            "fields": [{
                "name": "folder", "type": "string", "collation": "LEN_RCA_S2",
                "caption": "", "ordinal": 0, "isGenerated": False,
            }],
            "actions": [],
            "debugModeRowLimit": 393216,
            "originalDataTypes": {},
            "randomSampling": None,
            "updateTimestamp": 0,
            "restrictedFields": {},
            "userRenamedFields": {},
            "selectedFields": None,
            "samplingType": None,
            "groupByFields": None,
            "filters": [],
            "relation": {"type": "table", "table": "[Sheet1$]"},
        }
    # Native connector: shape is similar but with the connector class set
    # appropriately. For v1 we still emit the LoadSql shape — actually
    # generating a working Snowflake/CSV connector requires the user's
    # auth info, which is out of scope for v1's minimum-viable .tfl.
    return nid, {
        "nodeType": ".v1.LoadSql",
        "name": plan_input.name,
        "id": nid,
        "baseType": "input",
        "nextNodes": [],
        "serialize": False,
        "description": f"native_connector hint: {plan_input.connector_class}",
        "connectionId": "",
        "connectionAttributes": plan_input.connector_attrs or {},
        "fields": [],
        "relation": {"type": "table", "table": ""},
    }


def _make_trigger_xlsx(run_dir: Path, folder_path: str = "") -> Path:
    """Emit a tiny .xlsx with a single 'folder' column the input node points at."""
    try:
        from openpyxl import Workbook
    except ImportError:
        # Fallback: empty placeholder. The skill will warn the user.
        p = run_dir / "trigger.xlsx"
        p.write_bytes(b"")
        return p
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["folder"])
    ws.append([folder_path])
    p = run_dir / "trigger.xlsx"
    wb.save(p)
    return p


def generate_flow(spec: Spec, plan: Plan, run_dir: Path,
                  templates_dir: Optional[Path] = None) -> Path:
    """Generate a working .tfl. Returns the path to the produced file."""
    if templates_dir is None:
        templates_dir = Path(__file__).resolve().parents[1] / "templates"

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir = run_dir / "scripts"
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Render all script templates
    _render_templates(plan, scripts_dir, templates_dir)

    # 2. Build flow JSON
    flow = json.loads(json.dumps(SEED_FLOW))  # deep copy

    # 2a. Input
    if not plan.inputs:
        raise RuntimeError("plan has no input nodes")
    src0 = spec.sources[0] if spec.sources else None
    folder_hint = (src0.path if src0 else "") or ""
    trigger_xlsx = _make_trigger_xlsx(run_dir, folder_hint)
    conn_id = new_id()
    flow["connections"][conn_id] = {
        "connectionType": ".v1.SqlConnection",
        "id": conn_id,
        "name": "skill_input",
        "isPackaged": False,
        "connectionAttributes": {
            "filename": str(trigger_xlsx),
            "directory": str(trigger_xlsx.parent),
            "class": "excel-direct",
            "validate": "no",
            "is-single-table-union": "yes",
            "interpretationMode": "0",
        },
    }
    flow["connectionIds"] = [conn_id]
    inp_id, inp_node = _make_input_node(plan.inputs[0], trigger_xlsx)
    inp_node["connectionId"] = conn_id
    flow["nodes"][inp_id] = inp_node
    flow["initialNodes"] = [inp_id]

    prev_id = inp_id

    # 2b. Transforms (linear chain)
    for node in plan.transforms:
        sid, snode = make_script_node(
            node.name, Path(node.rendered_path), node.function_name, next_node_ids=[],
        )
        flow["nodes"][sid] = snode
        add_edge(flow["nodes"][prev_id], sid)
        prev_id = sid

    # 2c. QA nodes (linear after transforms)
    for node in plan.qa_nodes:
        sid, snode = make_script_node(
            node.name, Path(node.rendered_path), node.function_name, next_node_ids=[],
        )
        flow["nodes"][sid] = snode
        add_edge(flow["nodes"][prev_id], sid)
        prev_id = sid

    # 2d. Outputs (each Hyper writer hangs off the last transform/qa node)
    for o in plan.outputs:
        attrs = o.connector_attrs or {}
        hp = attrs.get("hyper_path") or attrs.get("csv_path") or str(outputs_dir / o.name)
        hid, hnode = make_hyper_node(o.name, Path(hp))
        flow["nodes"][hid] = hnode
        add_edge(flow["nodes"][prev_id], hid)

    # 2e. Parameters (web crawl exposes a query param)
    if plan.parameters:
        flow["parameters"]["parameters"] = plan.parameters

    # 3. Write the .tfl
    tfl_path = run_dir / "flow.tfl"
    members = {
        "displaySettings": json.dumps(SEED_DISPLAY_SETTINGS, indent=2).encode("utf-8"),
        "maestroMetadata": json.dumps(SEED_MAESTRO_METADATA, indent=2).encode("utf-8"),
    }
    write_flow(flow, members, tfl_path)
    return tfl_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="Path to spec.json")
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    from skill.scripts.intake import Source, Transformation, Output
    spec_dict = json.loads(Path(args.spec).read_text())
    spec = Spec(
        request=spec_dict["request"],
        sources=[Source(**s) for s in spec_dict["sources"]],
        transformations=[Transformation(**t) for t in spec_dict["transformations"]],
        outputs=[Output(**o) for o in spec_dict["outputs"]],
        qa_tier=spec_dict["qa_tier"],
        eval_strategy=spec_dict["eval_strategy"],
        deployment=spec_dict.get("deployment", "local"),
    )
    from skill.scripts.source_planner import plan_sources
    plan = plan_sources(spec, Path(args.run_dir) / "outputs")
    out = generate_flow(spec, plan, Path(args.run_dir))
    print(f"flow.tfl: {out}")
