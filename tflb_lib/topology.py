"""
Graph mutation helpers for .tfl flow JSON.

Higher-level than `nodes.py`: these functions operate on the whole flow
graph — pruning subgraphs, repointing script paths, attaching branches.
They remain domain-agnostic; concrete flows specify which nodes to
affect by name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from tflb_lib.nodes import add_edge, make_hyper_node, make_script_node


def prune_nodes_by_name(flow: dict, names: Iterable[str]) -> list[str]:
    """Remove every node whose `name` matches `names` and clean up dangling edges.

    Returns the list of removed node ids.
    """
    nodes = flow["nodes"]
    target_names = set(names)
    prune_ids = {nid for nid, n in nodes.items() if n.get("name") in target_names}
    for nid in prune_ids:
        del nodes[nid]
    for n in nodes.values():
        n["nextNodes"] = [
            e for e in n.get("nextNodes", [])
            if e.get("nextNodeId") not in prune_ids
        ]
    flow["initialNodes"] = [
        nid for nid in flow.get("initialNodes", [])
        if nid not in prune_ids
    ]
    return list(prune_ids)


def prune_to_keep_set(flow: dict, keep_names: Iterable[str]) -> list[str]:
    """Keep only nodes whose `name` is in `keep_names`. Drop all others.

    Returns the list of removed node ids.
    """
    nodes = flow["nodes"]
    target = set(keep_names)
    keep_ids = {nid for nid, n in nodes.items() if n.get("name") in target}
    removed = [nid for nid in nodes if nid not in keep_ids]
    for nid in removed:
        del nodes[nid]
    for n in nodes.values():
        n["nextNodes"] = [
            e for e in n.get("nextNodes", [])
            if e.get("nextNodeId") in keep_ids
        ]
    flow["initialNodes"] = [
        nid for nid in flow.get("initialNodes", [])
        if nid in keep_ids
    ]
    return removed


def rewrite_script_paths(
    flow: dict,
    slot_resolver: Callable[[str], Optional[str]],
    active_paths: dict[str, Path],
) -> list[dict]:
    """Walk every Script node and swap its scriptFilePath per the active map.

    `slot_resolver(current_path)` returns the slot name (or None) for a
    given existing scriptFilePath. `active_paths[slot]` is the new
    file path to install.

    Returns a list of change records: {node_id, node_name, slot, from, to}.
    """
    changes: list[dict] = []
    nodes = flow.get("nodes", {})
    for node_id, node in nodes.items():
        if "Extensibility" not in node.get("nodeType", ""):
            continue
        action = node.get("actionNode") or {}
        setup = action.get("setupParameters") or {}
        old = setup.get("scriptFilePath")
        if not old:
            continue
        slot = slot_resolver(old)
        if slot is None:
            continue
        new_path = active_paths.get(slot)
        if new_path is None:
            continue
        new_str = str(new_path)
        if new_str == old:
            continue
        setup["scriptFilePath"] = new_str
        action["setupParameters"] = setup
        node["actionNode"] = action
        changes.append({
            "node_id": node_id,
            "node_name": node.get("name"),
            "slot": slot,
            "from": old,
            "to": new_str,
        })
    return changes


def add_branch(
    flow: dict,
    anchor_name: str,
    chain: list[dict],
) -> list[dict]:
    """Attach a chain of script nodes (and one or more terminal Hyper writers)
    downstream of an existing anchor node identified by name.

    `chain` is a list of step dicts. Each dict is either:
      {"kind": "script", "name": ..., "script_path": Path,
       "function_name": ..., "fan_out": [...]}
    or:
      {"kind": "hyper", "name": ..., "hyper_path": Path}

    `fan_out` (optional, on script steps) is a list of further chain
    dicts that branch off this step in addition to the linear chain.
    The linear chain proceeds through the chain list in order; each
    step's primary output connects to the next step.

    Idempotent on the per-name level: if any node with the same name
    already exists in the flow, the entire branch is skipped.

    Returns the list of created node summaries (empty if skipped).
    """
    nodes = flow["nodes"]
    by_name = {n.get("name"): nid for nid, n in nodes.items()}

    # Idempotency: if the FIRST step's name is already wired, skip the whole branch.
    if chain and chain[0]["name"] in by_name:
        return []

    if anchor_name not in by_name:
        return []
    anchor_id = by_name[anchor_name]

    new_nodes: dict[str, dict] = {}

    def _add_step(step: dict) -> tuple[str, dict]:
        if step["kind"] == "script":
            sub_ids: list[str] = []
            # Build linear next first (filled in by caller). Plus any fan_out terminals.
            for terminal in step.get("fan_out") or []:
                tid, tnode = _add_step(terminal)
                sub_ids.append(tid)
            return None, sub_ids  # placeholder; caller composes
        elif step["kind"] == "hyper":
            hid, hnode = make_hyper_node(step["name"], step["hyper_path"])
            new_nodes[hid] = hnode
            return hid, hnode
        else:
            raise ValueError(f"unknown step kind: {step['kind']}")

    # Walk the chain right-to-left so each step knows its downstream id.
    next_ids_for_step: list[list[str]] = [[] for _ in chain]
    # Resolve all fan-out terminals up front (they're always hyper writers
    # in this convention).
    for i, step in enumerate(chain):
        if step["kind"] != "script":
            continue
        for fan in step.get("fan_out") or []:
            if fan["kind"] != "hyper":
                raise ValueError("fan_out items must be hyper writers")
            hid, hnode = make_hyper_node(fan["name"], fan["hyper_path"])
            new_nodes[hid] = hnode
            next_ids_for_step[i].append(hid)

    # Now build the chain right-to-left so each script knows its primary downstream.
    last_id: Optional[str] = None
    created_in_order: list[tuple[str, dict]] = []
    for i in range(len(chain) - 1, -1, -1):
        step = chain[i]
        downstream = list(next_ids_for_step[i])
        if last_id is not None:
            downstream.insert(0, last_id)
        if step["kind"] == "script":
            sid, snode = make_script_node(
                step["name"],
                step["script_path"],
                step["function_name"],
                next_node_ids=downstream,
            )
            new_nodes[sid] = snode
            created_in_order.insert(0, (sid, snode))
            last_id = sid
        elif step["kind"] == "hyper":
            hid, hnode = make_hyper_node(step["name"], step["hyper_path"])
            new_nodes[hid] = hnode
            created_in_order.insert(0, (hid, hnode))
            last_id = hid

    if last_id is None:
        return []

    add_edge(nodes[anchor_id], created_in_order[0][0])
    nodes.update(new_nodes)
    return [
        {"node_name": n["name"], "node_id": nid, "kind": n["nodeType"]}
        for nid, n in new_nodes.items()
    ]
