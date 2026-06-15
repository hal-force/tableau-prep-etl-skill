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
) -> tuple[str, dict]:
    """Build a SuperExtensibilityNode (Python Script step).

    The returned dict matches the shape Tableau Prep emits for Script
    nodes — outer SuperExtensibilityNode wrapping an inner
    ExtensibilityNode with setupParameters.scriptFilePath and
    executionParameters.scriptFunctionName.

    `next_node_ids` is the list of downstream node ids (Hyper writers,
    join nodes, etc) the script's output should feed.
    """
    inner_id = new_id()
    outer_id = new_id()
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
        "description": None,
        "beforeActionAnnotations": [],
        "afterActionAnnotations": [],
        "actionNode": {
            "nodeType": ".v2019_2_2.ExtensibilityNode",
            "name": name,
            "id": inner_id,
            "baseType": "transform",
            "nextNodes": [],
            "serialize": False,
            "description": None,
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
) -> tuple[str, dict]:
    """Build a SuperJoin step joining two upstream feeds on a single field."""
    inner_id = new_id()
    outer_id = new_id()
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
        "description": None,
        "beforeActionAnnotations": [],
        "afterActionAnnotations": [],
        "actionNode": {
            "nodeType": ".v1.SimpleJoin",
            "name": name,
            "id": inner_id,
            "baseType": "transform",
            "nextNodes": [],
            "serialize": False,
            "description": None,
            "conditions": [{
                "leftExpression": f"[{on_field}]",
                "rightExpression": f"[{on_field}]",
                "comparator": "==",
            }],
            "joinType": join_type,
        },
    }


def make_hyper_node(name: str, hyper_path: Path) -> tuple[str, dict]:
    """Build a WriteToHyper terminal output node."""
    nid = new_id()
    return nid, {
        "nodeType": ".v1.WriteToHyper",
        "name": name,
        "id": nid,
        "baseType": "output",
        "nextNodes": [],
        "serialize": False,
        "description": None,
        "hyperOutputFile": str(hyper_path),
        "tdsOutput": str(hyper_path.with_suffix(".tds")),
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
