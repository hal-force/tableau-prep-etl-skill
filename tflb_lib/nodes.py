"""
Node-construction primitives for .tfl flow JSON.

Each helper returns `(node_id, node_dict)`. Callers wire nodes together
by passing IDs into `next_node_ids` or by mutating an existing node's
`nextNodes` via `add_edge()`. None of these functions know anything
about specific scripts, schemas, or domains — they're shape factories.
"""
from __future__ import annotations

import uuid
from pathlib import Path


def new_id() -> str:
    """Fresh UUID string for any node/connection identifier."""
    return str(uuid.uuid4())


def make_script_node(
    name: str,
    script_path: Path,
    function_name: str,
    next_node_ids: list[str],
    description: str | None = None,
) -> tuple[str, dict]:
    """Build a SuperExtensibilityNode (Python Script step).

    The returned dict matches the shape Tableau Prep emits for Script
    nodes — outer SuperExtensibilityNode wrapping an inner
    ExtensibilityNode with setupParameters.scriptFilePath and
    executionParameters.scriptFunctionName.

    `next_node_ids` is the list of downstream node ids (Hyper writers,
    join nodes, etc) the script's output should feed.

    `description` populates the node's `description` field, which
    Tableau Prep Builder surfaces in the canvas as the node's
    "Description" property. Pass a short sentence explaining the
    node's purpose so the flow is self-documenting on open.
    """
    inner_id = new_id()
    outer_id = new_id()
    desc = description or None
    return outer_id, {
        "nodeType": ".v2019_2_2.SuperExtensibilityNode",
        "name": name,
        "id": outer_id,
        "baseType": "superNode",
        "nextNodes": [
            {"namespace": "Default", "nextNodeId": nid, "nextNamespace": "Default"}
            for nid in next_node_ids
        ],
        "serialize": False,
        "description": desc,
        "beforeActionAnnotations": [],
        "afterActionAnnotations": [],
        "actionNode": {
            "nodeType": ".v2019_2_2.ExtensibilityNode",
            "name": name,
            "id": inner_id,
            "baseType": "transform",
            "nextNodes": [],
            "serialize": False,
            "description": desc,
            "setupParameters": {"scriptFilePath": str(script_path)},
            "executionParameters": {"scriptFunctionName": function_name},
            "externalServiceType": "pythonSupport",
        },
    }


def make_join_node(
    name: str,
    next_node_ids: list[str],
    on_field: str = "id",
    join_type: str = "inner",
    description: str | None = None,
) -> tuple[str, dict]:
    """Build a SuperJoin step joining two upstream feeds on a single field."""
    inner_id = new_id()
    outer_id = new_id()
    desc = description or None
    return outer_id, {
        "nodeType": ".v2018_2_3.SuperJoin",
        "name": name,
        "id": outer_id,
        "baseType": "superNode",
        "nextNodes": [
            {"namespace": "Default", "nextNodeId": nid, "nextNamespace": "Default"}
            for nid in next_node_ids
        ],
        "serialize": False,
        "description": desc,
        "beforeActionAnnotations": [],
        "afterActionAnnotations": [],
        "actionNode": {
            "nodeType": ".v1.SimpleJoin",
            "name": name,
            "id": inner_id,
            "baseType": "transform",
            "nextNodes": [],
            "serialize": False,
            "description": desc,
            "conditions": [{
                "leftExpression": f"[{on_field}]",
                "rightExpression": f"[{on_field}]",
                "comparator": "==",
            }],
            "joinType": join_type,
        },
    }


def make_hyper_node(name: str, hyper_path: Path, description: str | None = None) -> tuple[str, dict]:
    """Build a WriteToHyper terminal output node.

    Maestro validates `hyperOutputFile` ends in `.hyper`; ensure the
    extension regardless of what the caller passed.
    """
    nid = new_id()
    if hyper_path.suffix.lower() != ".hyper":
        hyper_path = hyper_path.with_suffix(".hyper")
    return nid, {
        "nodeType": ".v1.WriteToHyper",
        "name": name,
        "id": nid,
        "baseType": "output",
        "nextNodes": [],
        "serialize": False,
        "description": description or None,
        "hyperOutputFile": str(hyper_path),
        "tdsOutput": str(hyper_path.with_suffix(".tds")),
    }


def make_published_datasource_node(
    name: str,
    project_name: str,
    datasource_name: str | None = None,
    description: str | None = None,
    project_luid: str = "",
    server_url: str = "",
    datasource_description: str = "",
) -> tuple[str, dict]:
    """Build a .v1.PublishExtract terminal output node.

    Shape verified against a Tableau Prep-emitted flow (Interos
    `tier_orgs_to_parts_joins.tfl`):
      projectName, projectLuid, datasourceName, datasourceDescription,
      serverUrl. `projectLuid` is the load-bearing routing field on
      Cloud — Maestro will fail the run task if the LUID is empty AND
      `projectName` is ambiguous. Skill callers pass project_luid from
      the publish step's `find_project()` result.

    `serverUrl` is informational on the .tfl; the actual destination
    is determined by the site the flow is published into. Pass it for
    parity with hand-authored flows.
    """
    nid = new_id()
    return nid, {
        "nodeType": ".v1.PublishExtract",
        "name": name,
        "id": nid,
        "baseType": "output",
        "nextNodes": [],
        "serialize": False,
        "description": description or None,
        "projectName": project_name,
        "projectLuid": project_luid,
        "datasourceName": datasource_name or name,
        "datasourceDescription": datasource_description,
        "serverUrl": server_url,
    }


def make_change_column_type_node(
    column_name: str,
    type_str: str,
    next_node_ids: list[str] | None = None,
    description: str | None = None,
) -> tuple[str, dict]:
    """Build a `.v1.ChangeColumnType` standalone transform node.

    Coerces `column_name` to `type_str` (Maestro's accepted values:
    `string`, `date`, `datetime`, `int`, `decimal`, `bool`).

    Shape verified against `Interos/Flows/network_analysis_interos.tfl`
    (column-type cast nested in a `.v1.Container.loomContainer`) and
    `Analyst Notebook/Flows/Collection/APIs/get_flight_data.tfl`
    (cast as an `afterActionAnnotations.annotationNode`). Both nest
    the same shape; emitting it as a top-level transform node in
    `flow.nodes` works as well — Maestro reads the `nodeType` and
    `fields` regardless of where the node sits in the graph, as long
    as `nextNodes` wires it correctly.

    `calc` is left as `null` for plain casts. For string→date
    coercions Tableau Prep will add a `DATEPARSE` calc; we leave
    that to the user since the format string varies per source.
    """
    nid = new_id()
    type_str_lower = type_str.lower().strip()
    return nid, {
        "nodeType": ".v1.ChangeColumnType",
        "fields": {column_name: {"type": type_str_lower, "calc": None}},
        "name": f"Change {column_name} to {type_str_lower.title()} 1",
        "id": nid,
        "baseType": "transform",
        "nextNodes": [
            {"namespace": "Default", "nextNodeId": n, "nextNamespace": "Default"}
            for n in (next_node_ids or [])
        ],
        "serialize": False,
        "description": description or None,
    }


def make_change_semantic_role_node(
    column_name: str,
    role_id: str,
    role_name: str,
    next_node_ids: list[str] | None = None,
    description: str | None = None,
) -> tuple[str, dict]:
    """Build a `.v2018_2_3.ChangeSemanticRole` standalone transform node.

    Tags `column_name` with a Tableau semantic role (e.g. geo/state,
    geo/postal_code, resource/url) so the resulting Hyper extract /
    published data source surfaces the correct role icon in Tableau.

    Common role IDs:
      - `global/geo/state` (state/province)
      - `global/geo/city`
      - `global/geo/country`
      - `global/geo/postal_code`
      - `global/resource/url`

    Shape verified against `Interos/Flows/org_table.tfl` (which uses
    the bare 2-key form `{id, name}`) and
    `Document Processing/invoice_processing.tfl` (which uses the
    5-key extended form with `serverUrl`/`siteName`/`detailsUrl` =
    null). The 5-key form is forward-compatible — Maestro accepts
    either; we emit the extended form for parity with current Prep
    Builder output.
    """
    nid = new_id()
    return nid, {
        "nodeType": ".v2018_2_3.ChangeSemanticRole",
        "columnName": column_name,
        "semanticRole": {
            "id": role_id,
            "name": role_name,
            "serverUrl": None,
            "siteName": None,
            "detailsUrl": None,
        },
        "name": f"change {column_name} to {role_name} 1",
        "id": nid,
        "baseType": "transform",
        "nextNodes": [
            {"namespace": "Default", "nextNodeId": n, "nextNamespace": "Default"}
            for n in (next_node_ids or [])
        ],
        "serialize": False,
        "description": description or None,
    }


def add_edge(node: dict, next_id: str, namespace: str = "Default") -> None:
    """Append an outgoing edge from `node` to `next_id`.

    `namespace` controls the Tableau Prep namespace; default 'Default'
    matches the convention Prep emits for single-output script nodes.
    For joins that need distinct left/right inputs, pass distinct
    namespace strings.
    """
    node.setdefault("nextNodes", []).append({
        "namespace": "Default",
        "nextNodeId": next_id,
        "nextNamespace": namespace,
    })
