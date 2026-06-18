"""
Tableau Server INTERNAL data discovery via Metadata API.

Phase 0 of the skill: before any external source acquisition, scan the
connected Tableau site for published data sources that match the user's
request. The user may pick one - it becomes an `internal_published_ds`
source on the spec, sparing a re-acquisition of the upstream feed.

Public surface:
    is_configured()              -> bool        # cheap env-only check
    search_datasources(query, *) -> list[dict]  # ranked candidates
    inventory_datasource(luid)   -> dict        # full column list

Auth: PAT only via TABLEAU_SERVER_{URL,PAT_NAME,PAT_SECRET,SITE} env
vars. Reads at call time, used for the single signin handshake, never
persisted. Skill scripts never embed creds in rendered Python.

CLI:
    python3 -m skill.scripts.server_scan --check
    python3 -m skill.scripts.server_scan --search "USAFE workforce" --top-k 10
    python3 -m skill.scripts.server_scan --inventory <luid>
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

# Bootstrap tflb_lib import path
from skill.scripts.lib import _REPO_ROOT  # noqa: F401


REQUIRED_ENV = (
    "TABLEAU_SERVER_URL",
    "TABLEAU_SERVER_PAT_NAME",
    "TABLEAU_SERVER_PAT_SECRET",
)


def is_configured(env: Optional[dict] = None) -> bool:
    """True iff every required Tableau Server env var is non-empty.

    No network call. Used by run_loop to decide whether to attempt a
    scan or skip straight to external sources."""
    env = env or os.environ
    return all((env.get(k, "") or "").strip() for k in REQUIRED_ENV)


# === GraphQL queries ===

# Narrow query - broad introspection on big sites is slow and the
# Metadata API can time out at ~30s.
_LIST_DATASOURCES_GQL = """
query ListPublishedDatasources($first: Int, $after: String) {
  publishedDatasourcesConnection(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      luid
      name
      description
      projectName
      hasExtracts
      isCertified
      certificationNote
      tags { name }
      owner { username name }
      createdAt
      updatedAt
      extractLastUpdateTime
    }
  }
}
"""

# Per-DS column inventory. Pulls field-level descriptions + types so the
# planner / metadata writer knows what's already documented on the site.
_INVENTORY_GQL = """
query DatasourceInventory($luid: String!) {
  publishedDatasources(filter: { luid: $luid }) {
    luid
    name
    description
    projectName
    hasExtracts
    isCertified
    fields {
      __typename
      name
      description
      ... on ColumnField { dataType role aggregation }
      ... on CalculatedField { dataType role formula }
    }
  }
}
"""


@dataclass
class DatasourceCandidate:
    luid: str
    name: str
    project: str
    description: str = ""
    is_certified: bool = False
    has_extract: bool = False
    owner: str = ""
    last_refresh: str = ""
    tags: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ColumnInfo:
    name: str
    data_type: str = ""
    role: str = ""
    description: str = ""
    field_kind: str = ""
    formula: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# === Public scan operations ===

def _signin():
    """Sign in via tflb_lib.publishing.config_from_env. Returns the
    live Server. Caller is responsible for sign-out."""
    from tflb_lib import publishing
    cfg = publishing.config_from_env()
    return publishing.sign_in(cfg)


def _query(server, gql: str, variables: dict) -> dict:
    """Run a GraphQL query through TSC's metadata client."""
    from tableauserverclient import server as tsc_server  # noqa: F401
    raw = server.metadata.query(gql, variables=variables)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw or {}


_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "from", "and", "or", "with",
    "in", "on", "by", "data", "set", "datasets", "data set",
}


def _tokenize(s: str) -> set[str]:
    if not s:
        return set()
    toks = {t.lower() for t in _TOKEN_RE.findall(s)}
    return {t for t in toks if t not in _STOPWORDS and len(t) > 1}


def _score_ds(query_tokens: set[str], node: dict) -> float:
    """Token-overlap score with a small certified-DS boost.

    Empty query tokens fall back to 1.0 so the user still sees a list
    sorted by certification + recency."""
    if not query_tokens:
        return 1.0
    name_t = _tokenize(node.get("name") or "")
    desc_t = _tokenize(node.get("description") or "")
    proj_t = _tokenize(node.get("projectName") or "")
    tag_t = _tokenize(" ".join((t.get("name") or "") for t in (node.get("tags") or [])))

    score = 0.0
    score += 3.0 * len(query_tokens & name_t)
    score += 1.5 * len(query_tokens & desc_t)
    score += 1.0 * len(query_tokens & proj_t)
    score += 2.0 * len(query_tokens & tag_t)
    if node.get("isCertified"):
        score *= 1.15
    return round(score, 3)


def _to_candidate(node: dict, score: float) -> DatasourceCandidate:
    owner = node.get("owner") or {}
    tags = [t.get("name") for t in (node.get("tags") or []) if t.get("name")]
    return DatasourceCandidate(
        luid=node.get("luid") or "",
        name=node.get("name") or "",
        project=node.get("projectName") or "",
        description=node.get("description") or "",
        is_certified=bool(node.get("isCertified")),
        has_extract=bool(node.get("hasExtracts")),
        owner=owner.get("name") or owner.get("username") or "",
        last_refresh=node.get("extractLastUpdateTime") or node.get("updatedAt") or "",
        tags=tags,
        score=score,
    )


def _list_all_datasources(server, page_size: int = 100) -> list[dict]:
    nodes: list[dict] = []
    after: Optional[str] = None
    while True:
        result = _query(server, _LIST_DATASOURCES_GQL,
                        {"first": page_size, "after": after})
        if "errors" in result:
            err = result["errors"][0] if result["errors"] else {}
            msg = err.get("message", "Metadata API error")
            raise RuntimeError(f"Metadata API: {msg}")
        data = (result.get("data") or {}).get("publishedDatasourcesConnection") or {}
        nodes.extend(data.get("nodes") or [])
        page = data.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    return nodes


def search_datasources(query: str, top_k: int = 10,
                       page_size: int = 100) -> list[dict]:
    """Return up to `top_k` published datasources ranked by relevance.

    Score = token overlap on (name x3, tags x2, desc x1.5, project x1) +
    1.15 multiplier for certified DSs. Empty query returns the
    top_k most-recent / most-certified DSs.
    """
    if not is_configured():
        raise RuntimeError(
            "Tableau Server scan requires TABLEAU_SERVER_URL, "
            "TABLEAU_SERVER_PAT_NAME, TABLEAU_SERVER_PAT_SECRET env vars. "
            "See SKILL.md or `python3 -m skill.scripts.server_creds --suggest`."
        )
    server = _signin()
    try:
        nodes = _list_all_datasources(server, page_size=page_size)
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass

    qtokens = _tokenize(query or "")
    scored = [(_score_ds(qtokens, n), n) for n in nodes]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_to_candidate(n, s).to_dict() for s, n in scored[:top_k]]


def inventory_datasource(luid: str) -> dict:
    """Pull full field/column inventory for one DS."""
    if not is_configured():
        raise RuntimeError(
            "Tableau Server inventory requires TABLEAU_SERVER_* env vars."
        )
    server = _signin()
    try:
        result = _query(server, _INVENTORY_GQL, {"luid": luid})
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass
    if "errors" in result:
        err = result["errors"][0] if result["errors"] else {}
        raise RuntimeError(f"Metadata API: {err.get('message', 'unknown error')}")
    items = ((result.get("data") or {}).get("publishedDatasources")) or []
    if not items:
        return {"luid": luid, "found": False}
    ds = items[0]
    cols: list[ColumnInfo] = []
    for f in ds.get("fields") or []:
        kind = f.get("__typename") or ""
        cols.append(ColumnInfo(
            name=f.get("name") or "",
            data_type=f.get("dataType") or "",
            role=f.get("role") or "",
            description=f.get("description") or "",
            field_kind=kind,
            formula=f.get("formula") or "",
        ))
    return {
        "luid": ds.get("luid") or luid,
        "name": ds.get("name") or "",
        "project": ds.get("projectName") or "",
        "description": ds.get("description") or "",
        "is_certified": bool(ds.get("isCertified")),
        "has_extract": bool(ds.get("hasExtracts")),
        "columns": [c.to_dict() for c in cols],
    }


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Tableau Server INTERNAL data scan.")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--check", action="store_true",
                     help="Print whether TABLEAU_SERVER_* env vars are present, then exit.")
    grp.add_argument("--search", metavar="QUERY",
                     help="Score and return ranked candidates for the query.")
    grp.add_argument("--inventory", metavar="LUID",
                     help="Pull full column inventory for one DS.")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args(argv)

    if args.check:
        out = {
            "configured": is_configured(),
            "present": [k for k in REQUIRED_ENV if (os.environ.get(k, "") or "").strip()],
            "missing": [k for k in REQUIRED_ENV if not (os.environ.get(k, "") or "").strip()],
        }
        print(json.dumps(out, indent=2))
        return 0 if out["configured"] else 2

    if args.search is not None:
        try:
            candidates = search_datasources(args.search, top_k=args.top_k)
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
            return 3
        print(json.dumps(candidates, indent=2))
        return 0

    if args.inventory:
        try:
            inv = inventory_datasource(args.inventory)
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
            return 3
        print(json.dumps(inv, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
