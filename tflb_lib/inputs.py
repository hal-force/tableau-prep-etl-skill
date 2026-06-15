"""
Input-connection rewiring helpers.

Tableau Prep flows authored in Builder typically reference cloud-backed
inputs (Google Drive Excel, Snowflake, S3 …) that need OAuth or other
credentials. For headless `tableau-prep-cli` runs we want to swap those
inputs for local files. This module knows how to rewrite a flow's
connection block in place.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def rewire_input_to_local_excel(
    flow: dict,
    xlsx_path: Path,
    input_node_name: str = "Directory List",
    sheet: str = "Sheet1$",
    field_name: str = "folder",
) -> Optional[dict]:
    """Repoint the flow's first connection at a local .xlsx file.

    Reuses the existing connection ID so the input node's `connectionId`
    reference stays valid. Only the connection's attributes change.

    Returns swap details, or None if the flow has no connections to rewire.
    Raises RuntimeError if the named input node isn't present.
    """
    nodes = flow["nodes"]
    input_node = next(
        (n for n in nodes.values() if n.get("name") == input_node_name),
        None,
    )
    if input_node is None:
        raise RuntimeError(
            f"could not find input node named '{input_node_name}' to rewire"
        )

    connections = flow.get("connections") or {}
    if not connections:
        return None
    base_conn_id = next(iter(connections.keys()))
    base_conn = connections[base_conn_id]

    base_conn["connectionType"] = ".v1.SqlConnection"
    base_conn["name"] = "local_input"
    base_conn["isPackaged"] = False
    base_conn["connectionAttributes"] = {
        "filename": str(xlsx_path),
        "directory": str(xlsx_path.parent),
        "class": "excel-direct",
        "validate": "no",
        "is-single-table-union": "yes",
        "interpretationMode": "0",
    }

    input_node["nodeType"] = ".v1.LoadSql"
    input_node["relation"] = {"type": "table", "table": f"[{sheet}]"}
    input_node["fields"] = [{
        "name": field_name,
        "type": "string",
        "collation": "LEN_RCA_S2",
        "caption": "",
        "ordinal": 0,
        "isGenerated": False,
    }]

    return {
        "input_node_id": input_node["id"],
        "xlsx_path": str(xlsx_path),
        "connection_id": base_conn_id,
    }
