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

import ast
import json
import os
import shutil
from pathlib import Path
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile

# Bootstrap tflb_lib
from skill.scripts.lib import _REPO_ROOT  # noqa: F401

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tflb_lib.nodes import (
    add_edge,
    make_change_column_type_node,
    make_change_semantic_role_node,
    make_hyper_node,
    make_join_node,
    make_published_datasource_node,
    make_script_node,
    new_id,
)
from tflb_lib.builder import read_flow, write_flow

from skill.scripts.intake import Spec
from skill.scripts.source_planner import NodePlan, Plan
from skill.scripts import connector_registry


# A .tfl is a ZIP whose load-bearing entries are `flow`, `displaySettings`,
# `maestroMetadata`, and `flowGraphThumbnail.svg`. The Maestro deserializer
# requires `maestroMetadata` to be a fully-formed JSON document naming the
# flow + displaySettings entries (otherwise it throws NullPointerException
# at ZipFile.getEntry(null) and Prep Builder reports the .tfl as corrupt).
#
# Synthesizing a valid maestroMetadata from scratch would mean
# reverse-engineering the Maestro document feature catalog. Instead we
# bundle a known-good empty seed (skill/templates/seeds/empty.tfl) that
# was produced by Tableau Prep Builder, and clone it on every run.
SEED_TFL = Path(__file__).resolve().parents[1] / "templates" / "seeds" / "empty.tfl"


def _render_templates(plan: Plan, scripts_dir: Path, templates_dir: Path,
                      sources: Optional[list] = None) -> None:
    """Render every script template referenced by the plan to scripts_dir.

    For source-side connectors, the connector registry supplies *defaults*
    learned from prior runs (timeouts, tested page sizes, etc.) that get
    merged underneath the current spec's `extra`. Rendering is always
    fresh because the rendered script bakes per-spec values (URL paths,
    where clauses, field lists) into module constants — copying a
    previous render would silently use the previous spec's values.
    """
    scripts_dir.mkdir(parents=True, exist_ok=True)
    # Hardening: StrictUndefined turns silent {{ undefined_var }} into
    # an error so a typo'd variable can't render to empty string and
    # ship a syntactically-valid-but-wrong script. autoescape=False is
    # explicit (HTML-style escaping in Python output would be wrong);
    # the safety isn't escaping but the post-render `ast.parse` below
    # combined with `tojson`-wrapped variables in templates.
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=False,
        undefined=StrictUndefined,
    )
    # `tojson` emits JSON literals (`true`/`false`/`null`) that are
    # invalid Python; rendered .py files were SyntaxError'ing on
    # `GRAPHQL = false`. `pyrepr` produces a `repr()` of the value, which
    # round-trips through ast.literal_eval and is always valid Python.
    env.filters["pyrepr"] = repr
    sources = sources or []

    # Map plan.transforms[i] → sources[transforms[i].branch]. Each
    # transform gets its own rendered file (api_caller_b0.py,
    # api_caller_b1.py, …). Without per-branch filenames, multi-source
    # flows clobber earlier branches' rendered scripts and every node
    # ends up pointing at the last-written file — Maestro then
    # complains the upstream column doesn't exist on the join's left
    # side because every branch reports the same (last) schema.
    for node in plan.transforms:
        if not node.template:
            continue
        branch_idx = node.branch
        src = sources[branch_idx] if 0 <= branch_idx < len(sources) else None
        cached = connector_registry.lookup(src) if src is not None else None
        if cached is not None and "extra" in node.template_vars:
            merged = dict(cached.defaults)
            merged.update(node.template_vars["extra"])  # spec wins
            node.template_vars["extra"] = merged
        try:
            tpl = env.get_template(node.template)
        except Exception as e:
            raise RuntimeError(f"failed to load template '{node.template}': {e}")
        rendered = tpl.render(**node.template_vars)
        _assert_valid_python(rendered, node.template)
        base_name = node.template.replace(".j2", "").replace("/", "_")
        if "." in base_name:
            stem, ext = base_name.rsplit(".", 1)
            out_name = f"{stem}_b{branch_idx}.{ext}"
        else:
            out_name = f"{base_name}_b{branch_idx}"
        out_path = scripts_dir / out_name
        out_path.write_text(rendered)
        if src is not None:
            if cached is not None:
                connector_registry.touch(src)
            else:
                connector_registry.store(
                    src, out_path, defaults=node.template_vars.get("extra", {}),
                )
        node.rendered_path = str(out_path.resolve())

    # QA + validator nodes are not cached
    for node in plan.qa_nodes:
        if not node.template:
            continue
        try:
            tpl = env.get_template(node.template)
        except Exception as e:
            raise RuntimeError(f"failed to load template '{node.template}': {e}")
        rendered = tpl.render(**node.template_vars)
        _assert_valid_python(rendered, node.template)
        out_name = node.template.replace(".j2", "").replace("/", "_")
        out_path = scripts_dir / out_name
        out_path.write_text(rendered)
        node.rendered_path = str(out_path.resolve())


def _assert_valid_python(rendered: str, template_name: str) -> None:
    """Raise RuntimeError if `rendered` is not parseable Python.

    Cheap last-line-of-defense against an injection that survived the
    spec validators and Jinja's `tojson` wrapping. If a quote breaks
    out of `API_URL = {{ url | tojson }}`, the resulting code won't
    parse — fail before writing the .py file rather than at import
    inside TabPy.
    """
    try:
        ast.parse(rendered)
    except SyntaxError as e:
        # Surface a small excerpt around the offending line so the
        # operator can see what survived rendering.
        lines = rendered.splitlines()
        ln = max(1, (e.lineno or 1))
        lo, hi = max(0, ln - 3), min(len(lines), ln + 2)
        excerpt = "\n".join(f"{i+1:4d}: {lines[i]}" for i in range(lo, hi))
        raise RuntimeError(
            f"rendered template '{template_name}' is not valid Python "
            f"(SyntaxError at line {ln}: {e.msg}). Excerpt:\n{excerpt}"
        )


_PROXY_TYPE_TO_PREP = {
    "string": "string",
    "varchar": "string",
    "text": "string",
    "integer": "integer",
    "int": "integer",
    "long": "integer",
    "bigint": "integer",
    "real": "real",
    "float": "real",
    "double": "real",
    "decimal": "real",
    "date": "date",
    "datetime": "datetime",
    "timestamp": "datetime",
    "boolean": "bool",
    "bool": "bool",
}

_DEFAULT_STRING_COLLATION = "LEN_RUS_S2"


def _published_ds_meta_from_inventory(luid: str) -> tuple[list[dict], str, str]:
    """Best-effort fetch of (fields, datasource_name, project_name) from
    the Metadata API for a published DS so the LoadSqlProxy node can
    declare its schema + name up-front. Maestro requires both at
    deserialize time, and `datasourceName` must match what's on the
    site exactly (it's the resolution key for the proxy connection).

    Falls back to ([], "", "") when:
      - server_scan can't be imported (running from a different repo layout)
      - TABLEAU_SERVER_* env vars aren't set
      - the Metadata API is unreachable / rejects the query

    Caller code accepts an empty list as a degraded but still serializable
    flow - Maestro may reject at run time, but the .tfl writes successfully
    and the user sees a clear error from prep-cli rather than a Python
    exception."""
    if not luid:
        return [], "", ""
    try:
        from skill.scripts.server_scan import inventory_datasource, is_configured
    except Exception:
        return [], "", ""
    if not is_configured():
        return [], "", ""
    try:
        inv = inventory_datasource(luid)
    except Exception:
        return [], "", ""
    cols = inv.get("columns") or []
    out: list[dict] = []
    for i, c in enumerate(cols):
        # Skip calculated fields - they're computed downstream from the
        # published DS itself; Maestro requires them in the source DS,
        # not in the consuming flow's input node.
        if c.get("field_kind") == "CalculatedField":
            continue
        raw_type = (c.get("data_type") or "string").lower()
        prep_type = _PROXY_TYPE_TO_PREP.get(raw_type, "string")
        collation = _DEFAULT_STRING_COLLATION if prep_type == "string" else None
        out.append({
            "name": c.get("name") or "",
            "type": prep_type,
            "collation": collation,
            "caption": "",
            "ordinal": i,
            "isGenerated": False,
        })
    return out, inv.get("name") or "", inv.get("project") or ""


def _make_published_ds_input_node(plan_input: NodePlan,
                                  conn_id: str) -> tuple[str, dict]:
    """Build the .v2019_3_1.LoadSqlProxy input node bound to a published
    data source on the connected Tableau Server. Shape reverse-engineered
    from `user_examples/USAFE_server_pull_example.tfl` saved by Tableau
    Prep Builder."""
    nid = new_id()
    attrs = plan_input.connector_attrs or {}
    luid = attrs.get("luid", "")
    project = attrs.get("project", "")
    # datasourceName must EXACTLY match what's on the site - it's how
    # Tableau Server identifies the DS for the proxy connection. Pull
    # from the Metadata API inventory (authoritative) when we have
    # creds; fall back to the spec's source.name (a user-facing label
    # that often won't match the actual DS) only if the API is
    # unreachable.
    fields, server_ds_name, server_proj_name = _published_ds_meta_from_inventory(luid)
    ds_name = (
        attrs.get("datasource_name")
        or server_ds_name
        or plan_input.name
        or ""
    )
    project = project or server_proj_name or ""
    # dbname is the datasourceName with spaces removed (Maestro convention
    # observed in Builder-saved seed flows).
    db_name = attrs.get("dbname") or ds_name.replace(" ", "")

    return nid, {
        "nodeType": ".v2019_3_1.LoadSqlProxy",
        "name": plan_input.name,
        "id": nid,
        "baseType": "input",
        "nextNodes": [],
        "serialize": False,
        "description": plan_input.description or None,
        "connectionId": conn_id,
        "connectionAttributes": {
            "dbname": db_name,
            "projectName": project,
            "datasourceName": ds_name,
        },
        "fields": fields,
        "actions": [],
        "debugModeRowLimit": 393216,
        "originalDataTypes": {},
        "randomSampling": None,
        "updateTimestamp": None,
        "restrictedFields": {},
        "userRenamedFields": {},
        "selectedFields": None,
        "samplingType": None,
        "groupByFields": None,
        "filters": [],
        "relation": {"type": "table", "table": "[sqlproxy]"},
    }


def _make_sqlproxy_connection(conn_id: str, server_url: str,
                              site_url_name: str,
                              friendly_name: str = "") -> dict:
    """Build the .v1.SqlConnection block for a sqlproxy (Tableau Server
    published DS) connection. Shape from the Builder-saved seed flow.

    The auth itself is resolved by the backgrounder (or by Prep Builder
    when running locally) using the user's site session - no creds in
    the .tfl."""
    name = friendly_name or f"{server_url} ({site_url_name or 'default'})"
    return {
        "connectionType": ".v1.SqlConnection",
        "id": conn_id,
        "name": name,
        "isPackaged": False,
        "connectionAttributes": {
            "server": server_url,
            "port": "443",
            "query-category": "Data",
            "siteUrlName": site_url_name or "",
            "channel": "https",
            "class": "sqlproxy",
            "directory": "/dataserver",
            "odbc-native-protocol": "yes",
        },
    }


def _make_local_csv_input_node(plan_input: NodePlan,
                               conn_id: str) -> tuple[str, dict]:
    """Build a LoadCsv input node pointing at a local CSV. Used when
    run_loop's Phase 4a downloaded a published DS as CSV (MFA-bound
    Cloud sites). Mirrors the LoadCsv shape Tableau Prep Builder
    produces for File > Connect to CSV.

    The connection block is created by the caller and points at the
    CSV's directory + filename, class=textscan."""
    nid = new_id()
    attrs = plan_input.connector_attrs or {}
    csv_path = attrs.get("_pds_csv_path", "")
    desc = plan_input.description or None
    return nid, {
        "nodeType": ".v1.LoadCsv",
        "name": plan_input.name,
        "id": nid,
        "baseType": "input",
        "nextNodes": [],
        "serialize": False,
        "description": desc,
        "connectionId": conn_id,
        # _pds_* attrs are preserved here so Phase 10 (publish-time
        # rewrite in run_loop) can detect them and swap this node
        # back to LoadSqlProxy without losing the routing info.
        "connectionAttributes": {
            "_pds_luid": attrs.get("_pds_luid", ""),
            "_pds_project": attrs.get("_pds_project", ""),
            "_pds_site": attrs.get("_pds_site", ""),
            "_pds_datasource_name": attrs.get("_pds_datasource_name", ""),
        },
        "fields": [],
        "actions": [],
        "debugModeRowLimit": 393216,
        "originalDataTypes": {},
        "randomSampling": None,
        "updateTimestamp": None,
        "restrictedFields": {},
        "userRenamedFields": {},
        "selectedFields": None,
        "samplingType": None,
        "groupByFields": None,
        "filters": [],
        "relation": {"type": "table", "table": str(Path(csv_path).name)},
    }


def _make_local_csv_connection(conn_id: str, csv_path: Path) -> dict:
    """Build a `.v1.SqlConnection` (class=textscan) for a local CSV.
    Mirrors what Tableau Prep Builder produces when you File > Connect
    to a CSV file."""
    return {
        "connectionType": ".v1.SqlConnection",
        "id": conn_id,
        "name": csv_path.name,
        "isPackaged": False,
        "connectionAttributes": {
            "filename": str(csv_path),
            "directory": str(csv_path.parent),
            "class": "textscan",
            "validate": "no",
            "is-single-table-union": "yes",
            "interpretationMode": "0",
        },
    }


def _make_input_node(plan_input: NodePlan, trigger_xlsx: Path) -> tuple[str, dict]:
    """Build an input node. For non-native sources we always use the
    folder-listing xlsx as a 'trigger' input that the downstream Script
    node ignores in favor of the configured URL/folder/etc."""
    nid = new_id()
    desc = plan_input.description or None
    if plan_input.connector_class in ("local_folder", "local_xlsx_pointer"):
        return nid, {
            "nodeType": ".v1.LoadSql",
            "name": plan_input.name,
            "id": nid,
            "baseType": "input",
            "nextNodes": [],
            "serialize": False,
            "description": desc,
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
        "description": desc or f"native_connector hint: {plan_input.connector_class}",
        "connectionId": "",
        "connectionAttributes": plan_input.connector_attrs or {},
        "fields": [],
        "relation": {"type": "table", "table": ""},
    }


def _make_trigger_xlsx(run_dir: Path, folder_path: str = "",
                       filename: str = "trigger.xlsx") -> Path:
    """Emit a tiny .xlsx with a single 'folder' column the input node points at.
    `filename` lets multi-source flows give each branch a unique trigger file
    (Prep tracks each source by its `connectionAttributes.filename`).

    IMPORTANT: row 2 must be a non-empty string. When the row cell is None,
    Maestro emits zero rows from the LoadSql input node, the downstream
    Script node never receives a trigger DataFrame, and the entire flow
    fails with cryptic schema errors (TabPy `BasicAuthConfiguration` /
    `getPassword` errors are misleading - they fire because the script
    node's `get_output_schema()` is the only thing that runs and it's
    invoked without any input rows). For rest_api / web_crawl / pki
    sources where there's no folder path, fall back to a sentinel
    placeholder so the row exists and the script gets called."""
    try:
        from openpyxl import Workbook
    except ImportError:
        p = run_dir / filename
        p.write_bytes(b"")
        return p
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["folder"])
    ws.append([folder_path or "TRIGGER"])
    p = run_dir / filename
    wb.save(p)
    return p


def generate_flow(spec: Spec, plan: Plan, run_dir: Path,
                  templates_dir: Optional[Path] = None,
                  local_iteration: bool = False,
                  tfl_basename: str = "flow") -> Path:
    """Generate a working .tfl. Returns the path to the produced file.

    `local_iteration=True` swaps every `published_data_source` output
    to a local WriteToHyper. Used by run_loop's pre-publish iteration
    loop on MFA-bound Cloud sites where prep-cli can't auth to push
    extracts to the server. Phase 10 (publish-time rewrite) flips them
    back to `PublishExtract` before upload.

    `tfl_basename` controls the on-disk filename (`<basename>.tfl`).
    Run_loop passes the resolved `flow_name` so artifacts are
    self-describing (e.g. `fed_outlays.tfl`)."""
    if templates_dir is None:
        templates_dir = Path(__file__).resolve().parents[1] / "templates"

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir = run_dir / "scripts"
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Render all script templates (with connector registry consultation)
    _render_templates(plan, scripts_dir, templates_dir, sources=spec.sources)

    # 2. Clone the bundled empty seed and mutate its `flow` member.
    if not SEED_TFL.exists():
        raise RuntimeError(
            f"seed .tfl not found at {SEED_TFL}. "
            "Run skill/templates/seeds/build_seed.py to regenerate it."
        )
    flow, members = read_flow(SEED_TFL)

    # 2a. Per-source-branch input nodes + per-branch transform chains.
    # For multi-source flows we emit one trigger.xlsx per branch (in its own
    # directory) with its own connection entry. Each branch then runs its
    # rendered transform chain. After all branches are wired, joins consume
    # branch tails to merge data.
    if not plan.inputs:
        raise RuntimeError("plan has no input nodes")

    flow["connectionIds"] = []
    initial_nodes: list[str] = []
    branch_tails: list[str] = []  # branch_index → current tail node id
    branch_input_ids: list[str] = []  # branch_index → input node id (for fan-out)
    transform_ids_by_name: dict[str, str] = {}  # transform.name → emitted node id
    transform_upstream_by_name: dict[str, str] = {}  # transform.name → its upstream node id

    for branch_idx, plan_input in enumerate(plan.inputs):
        # Per-branch trigger.xlsx in its own subdirectory so multiple Excel
        # sources don't collide on filename or interpretationMode caching.
        branch_dir = run_dir / f"branch_{branch_idx}"
        branch_dir.mkdir(parents=True, exist_ok=True)
        src = spec.sources[branch_idx] if branch_idx < len(spec.sources) else None

        is_published_ds = plan_input.connector_class == "published_datasource"
        is_local_csv = plan_input.connector_class == "local_csv"

        conn_id = new_id()
        if is_published_ds:
            attrs = plan_input.connector_attrs or {}
            site_url = attrs.get("site") or os.environ.get("TABLEAU_SERVER_SITE", "")
            server_url = (
                attrs.get("server_url")
                or os.environ.get("TABLEAU_SERVER_URL", "")
                or ""
            ).rstrip("/")
            flow["connections"][conn_id] = _make_sqlproxy_connection(
                conn_id, server_url, site_url,
            )
            inp_id, inp_node = _make_published_ds_input_node(plan_input, conn_id)
        elif is_local_csv:
            attrs = plan_input.connector_attrs or {}
            csv_path = Path(attrs.get("_pds_csv_path", ""))
            flow["connections"][conn_id] = _make_local_csv_connection(
                conn_id, csv_path,
            )
            inp_id, inp_node = _make_local_csv_input_node(plan_input, conn_id)
        else:
            folder_hint = (src.path if src else "") or ""
            trigger_xlsx = _make_trigger_xlsx(branch_dir, folder_hint, "trigger.xlsx")
            flow["connections"][conn_id] = {
                "connectionType": ".v1.SqlConnection",
                "id": conn_id,
                "name": f"skill_input_{branch_idx}",
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
            inp_id, inp_node = _make_input_node(plan_input, trigger_xlsx)
            inp_node["connectionId"] = conn_id
        flow["connectionIds"].append(conn_id)
        # Respect the plan's name (which honors src.name from the spec);
        # only fall back to "Input N" when the planner didn't supply one.
        if not plan_input.name:
            inp_node["name"] = f"Input {branch_idx + 1}"
        flow["nodes"][inp_id] = inp_node
        initial_nodes.append(inp_id)
        branch_input_ids.append(inp_id)

        # Transforms within a branch can either extend the linear chain
        # (default) or fan off the branch input ("@input") or off a
        # previously-emitted transform (by `name`). The linear-chain
        # tail (`prev_id`) advances ONLY when the transform appended
        # to it; fan-off transforms don't move the chain head, so a
        # subsequent linear transform still hangs off the previous
        # linear node and the detail extract stays lean.
        prev_id = inp_id
        for tnode in plan.transforms:
            if tnode.branch != branch_idx:
                continue
            # Branch on transform role: cast / semantic_role nodes are
            # native Maestro transform nodes (no Python script); script
            # nodes wrap a rendered .py via SuperExtensibilityNode.
            if tnode.role == "cast":
                col = tnode.connector_attrs.get("cast_column", "")
                typ = tnode.connector_attrs.get("cast_type", "string")
                sid, snode = make_change_column_type_node(
                    col, typ, next_node_ids=[],
                    description=tnode.description or None,
                )
            elif tnode.role == "semantic_role":
                col = tnode.connector_attrs.get("role_column", "")
                rid = tnode.connector_attrs.get("role_id", "")
                rname = tnode.connector_attrs.get("role_name", "")
                sid, snode = make_change_semantic_role_node(
                    col, rid, rname, next_node_ids=[],
                    description=tnode.description or None,
                )
            else:
                sid, snode = make_script_node(
                    tnode.name, Path(tnode.rendered_path), tnode.function_name,
                    next_node_ids=[], description=tnode.description or None,
                )
            flow["nodes"][sid] = snode
            # parent forms:
            #   ""           → linear append (advance prev_id)
            #   "@input"     → fork off this branch's input node
            #   "@sibling:N" → share upstream with previously-emitted
            #                  transform N (fan from same upstream)
            #   "<name>"     → hang directly off transform <name>
            if tnode.parent == "@input":
                upstream_id = inp_id
            elif tnode.parent.startswith("@sibling:"):
                sib = tnode.parent.split(":", 1)[1]
                upstream_id = transform_upstream_by_name.get(sib, prev_id)
            elif tnode.parent and tnode.parent in transform_ids_by_name:
                upstream_id = transform_ids_by_name[tnode.parent]
            else:
                upstream_id = prev_id
                prev_id = sid
            add_edge(flow["nodes"][upstream_id], sid)
            transform_ids_by_name[tnode.name] = sid
            transform_upstream_by_name[tnode.name] = upstream_id
        branch_tails.append(prev_id)

    flow["initialNodes"] = initial_nodes

    # 2b. Joins. Each join feeds from two branch tails. The join's id
    # becomes the new tail of `join_left` so chained joins accumulate
    # (left=branch0, right=branch1) → join1; (left=join1, right=branch2) → join2…
    # Spec authors express this by setting `left_branch=0` for every join
    # after the first (since branch 0's tail is the previous join's id).
    for j in plan.joins:
        if j.join_left < 0 or j.join_left >= len(branch_tails):
            raise RuntimeError(f"join '{j.name}': left_branch={j.join_left} out of range")
        if j.join_right < 0 or j.join_right >= len(branch_tails):
            raise RuntimeError(f"join '{j.name}': right_branch={j.join_right} out of range")
        if not j.join_on:
            raise RuntimeError(f"join '{j.name}': missing 'on' field")
        jid, jnode = make_join_node(j.name, next_node_ids=[],
                                    on_field=j.join_on, join_type=j.join_type,
                                    description=j.description or None)
        flow["nodes"][jid] = jnode
        # Wire both upstream branch tails into the join. Maestro's
        # SimpleJoinCompiler reads `nextNamespace` to identify the Left
        # vs Right input stream; both must be present or it NPEs in
        # JoinAccessors.getJoinType.
        add_edge(flow["nodes"][branch_tails[j.join_left]], jid, namespace="Left")
        add_edge(flow["nodes"][branch_tails[j.join_right]], jid, namespace="Right")
        branch_tails[j.join_left] = jid

    # The post-join tail is whatever branch the spec's last join landed on.
    # If there were no joins, fall back to branch 0 (single-source flow).
    final_tail = branch_tails[plan.joins[-1].join_left] if plan.joins else branch_tails[0]

    # Source-name → branch-tail lookup so outputs can route to a source
    # branch by name (e.g. `output.source = "<spec.sources[i].name>"`).
    # When that branch was the left side of a join, its entry already
    # points to the join id (line above advances branch_tails[join_left]
    # to the join), so source-named outputs on a joined branch resolve
    # to the join tail — correct. Un-joined sibling branches keep their
    # original tail and route to it.
    source_tails_by_name: dict[str, str] = {}
    for i, src in enumerate(spec.sources):
        if i < len(branch_tails) and src.name:
            source_tails_by_name[src.name] = branch_tails[i]

    # 2c. QA nodes (linear after the final join)
    for node in plan.qa_nodes:
        sid, snode = make_script_node(
            node.name, Path(node.rendered_path), node.function_name, next_node_ids=[],
            description=node.description or None,
        )
        flow["nodes"][sid] = snode
        add_edge(flow["nodes"][final_tail], sid)
        final_tail = sid

    # 2d. Outputs hang off the resolved upstream:
    #   - if `source` names a previously-emitted transform, fan off it
    #     (lets a stats table sibling-fan off a stats node while the
    #     detail output continues from the linear tail)
    #   - otherwise, hang off the final tail (single-output linear default)
    # Output kind controls writer-node type:
    #   hyper / csv → WriteToHyper
    #   published_data_source → WritePublishedDataSource (server-bound)
    pub_cfg = spec.server_publish
    default_project = (pub_cfg.project if pub_cfg else "") or "default"
    for o in plan.outputs:
        attrs = o.connector_attrs or {}
        kind = attrs.get("kind", "hyper")
        source_name = attrs.get("source", "") or ""
        if source_name:
            upstream_id = (
                transform_ids_by_name.get(source_name)
                or source_tails_by_name.get(source_name)
                or final_tail
            )
        else:
            upstream_id = final_tail
        if kind == "published_data_source" and not local_iteration:
            project_name = attrs.get("project") or default_project
            oid, onode = make_published_datasource_node(
                o.name, project_name=project_name, datasource_name=o.name,
                description=o.description or None,
            )
        elif kind == "published_data_source" and local_iteration:
            # Local-iteration substitution: write to a Hyper on disk
            # instead of pushing to the server. The original published
            # DS routing (project, datasource_name) is preserved on the
            # node so Phase 10 can rewrite back to PublishExtract.
            hp = str(outputs_dir / f"{o.name}.hyper")
            oid, onode = make_hyper_node(o.name, Path(hp),
                                         description=o.description or None)
            onode["_pds_target_project"] = attrs.get("project") or default_project
            onode["_pds_target_datasource_name"] = o.name
            onode["_pds_target_description"] = o.description or ""
        else:
            hp = attrs.get("hyper_path") or attrs.get("csv_path") or str(outputs_dir / o.name)
            oid, onode = make_hyper_node(o.name, Path(hp), description=o.description or None)
        flow["nodes"][oid] = onode
        add_edge(flow["nodes"][upstream_id], oid)

    # 2e. Parameters (web crawl exposes a query param)
    if plan.parameters:
        flow["parameters"]["parameters"] = plan.parameters

    # 3. Write the .tfl. We preserve maestroMetadata + flowGraphThumbnail.svg
    # from the seed (they're required for deserialization); the layout map in
    # displaySettings is reset because our nodes have new IDs the seed doesn't
    # know about. Tableau Prep Builder lays out unknown nodes automatically
    # when the file is first opened.
    tfl_path = run_dir / f"{tfl_basename}.tfl"
    if "displaySettings" in members:
        try:
            ds = json.loads(members["displaySettings"].decode("utf-8"))
            ds["nodes"] = {}
            members["displaySettings"] = json.dumps(ds, indent=2).encode("utf-8")
        except Exception:
            pass
    write_flow(flow, members, tfl_path)
    return tfl_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="Path to spec.json")
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    from skill.scripts.intake import Source, Transformation, Output, ServerPublish
    spec_dict = json.loads(Path(args.spec).read_text())
    sp_dict = spec_dict.get("server_publish")
    spec = Spec(
        request=spec_dict["request"],
        sources=[Source(**s) for s in spec_dict["sources"]],
        transformations=[Transformation(**t) for t in spec_dict["transformations"]],
        outputs=[Output(**o) for o in spec_dict["outputs"]],
        qa_tier=spec_dict["qa_tier"],
        eval_strategy=spec_dict["eval_strategy"],
        deployment=spec_dict.get("deployment", "local"),
        refresh_cadence=spec_dict.get("refresh_cadence", "once"),
        parameterize_query=bool(spec_dict.get("parameterize_query", False)),
        server_publish=ServerPublish(**sp_dict) if sp_dict else None,
    )
    from skill.scripts.source_planner import plan_sources
    plan = plan_sources(spec, Path(args.run_dir) / "outputs")
    out = generate_flow(spec, plan, Path(args.run_dir))
    print(f"flow.tfl: {out}")
