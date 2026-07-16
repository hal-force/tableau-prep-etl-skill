"""
Source planner: turn a Spec into a list of NodePlan entries describing
which Tableau Prep nodes to emit.

Decision tree (per source.type):

  local_folder      → folder-listing input + per-file Script (using
                      a connector-class template if 'format' matches)
  native_connector  → native .v1.SqlConnection / .v1.LoadCsv / etc.
                      (no Python step needed)
  rest_api          → Python Script step rendered from
                      templates/api_caller.py.j2 (REST variant)
  graphql_api       → Python Script step rendered from
                      templates/api_caller.py.j2 (GraphQL variant)
  web_crawl         → Python Script step rendered from
                      templates/crawler.py.j2 + Prep parameter for
                      the query
  pki_endpoint      → Python Script step rendered from
                      templates/pki_connector.py.j2 (cert-auth)

The plan is purely descriptive — `generate_flow.py` is what actually
calls into `tflb_lib` to assemble the .tfl from this plan.

Public entry: `plan_sources(spec: Spec) -> Plan`
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from skill.scripts.intake import Spec, Source
from skill.scripts.cast_planner import (
    plan_casts_for_columns,
    plan_semantic_roles_for_columns,
)


@dataclass
class NodePlan:
    """One node we intend to emit in the .tfl."""
    role: str             # 'input' | 'script' | 'join' | 'output'
    name: str             # display name in Prep
    description: str = "" # human-readable purpose, surfaced as the Prep node's `description`
    template: str = ""    # Jinja template path (relative to templates/) for script nodes
    template_vars: dict = field(default_factory=dict)
    rendered_path: str = ""  # filled in by generate_flow after rendering
    function_name: str = ""  # entry function for script nodes
    connector_class: str = ""  # for native input nodes
    connector_attrs: dict = field(default_factory=dict)
    branch: int = 0       # which source branch this transform belongs to (0..N-1)
    # Join-only fields. Populated when role == 'join'.
    join_left: int = -1   # index into Plan.branch_tails of the left feed
    join_right: int = -1  # index into Plan.branch_tails of the right feed
    join_on: str = ""     # column name to join on (must exist in both branches)
    join_type: str = "inner"  # inner | leftOuter | rightOuter | fullOuter
    # Fan-out hook. When set, this transform node hangs off the same
    # upstream as another node ("the fork") instead of extending the
    # linear chain. `parent` names another transform's `name` (or
    # "input" + branch idx). Empty string = linear append (default).
    parent: str = ""


@dataclass
class Plan:
    """The full plan: source-side input nodes, transformation script nodes, output nodes.
    `inputs` and `transforms` are 1:1 indexed by source-branch position; `joins`
    is a list of join NodePlans referencing branch indices. `branch_tails` is
    populated by generate_flow after per-branch chains are emitted, mapping
    branch_index → tail node id (so joins can wire to the right upstream)."""
    inputs: list[NodePlan] = field(default_factory=list)
    transforms: list[NodePlan] = field(default_factory=list)
    joins: list[NodePlan] = field(default_factory=list)
    qa_nodes: list[NodePlan] = field(default_factory=list)
    outputs: list[NodePlan] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)  # Tableau Prep parameters block


def _plan_local_folder(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan]]:
    """Local-folder source → (input nodes, transform nodes)."""
    # The input is a tiny .xlsx with a single 'folder' column pointing at the
    # source path. We rewire it to a local file later in generate_flow.
    inp_name = src.name or f"Input {idx}"
    inp_desc = src.description or f"Local folder source: {src.path or '<path>'} ({src.format or 'auto'})"
    inp = NodePlan(role="input", name=inp_name, description=inp_desc,
                   connector_class="local_folder",
                   connector_attrs={"path": src.path, "format": src.format})

    # Transform: a Python step that walks the folder. Template depends on format.
    if src.format in ("pdf_portfolio", "pdf"):
        template = "connectors/pdf_walker.py.j2"
        walk_desc = f"Walks {src.path} extracting fields from each PDF; emits one row per document."
    elif src.format == "json":
        template = "connectors/json_walker.py.j2"
        walk_desc = f"Walks {src.path}, parsing each JSON file and yielding records."
    elif src.format == "csv":
        # CSV folders are best handled by the native CSV connector with
        # union, no Python step needed.
        return [inp], []
    else:
        template = "connectors/generic_folder_walker.py.j2"
        walk_desc = f"Generic folder walker over {src.path} ({src.format or 'auto'})."

    walk = NodePlan(role="script", name=f"{inp_name} Walker", description=walk_desc,
                    template=template,
                    template_vars={"folder_path": src.path, "format": src.format},
                    function_name="walk_folder")
    return [inp], [walk]


def _plan_native_connector(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan]]:
    """Native Tableau connector. No Python step; the .tfl input node carries
    the connector type + attrs."""
    fmt = src.format.lower()
    if fmt in ("excel", "xlsx", "xls"):
        cls = "excel-direct"
    elif fmt in ("csv", "tsv"):
        cls = "textscan"
    elif fmt == "snowflake":
        cls = "snowflake"
    elif fmt in ("postgres", "postgresql"):
        cls = "postgres"
    elif fmt == "mysql":
        cls = "mysql"
    elif fmt in ("mssql", "sqlserver"):
        cls = "sqlserver"
    else:
        cls = fmt or "unknown"

    inp_name = src.name or f"Input {idx}"
    inp_desc = src.description or f"Native {cls} connector ({src.url or '<no url>'})"
    inp = NodePlan(role="input", name=inp_name, description=inp_desc,
                   connector_class=cls,
                   connector_attrs={"url": src.url, "auth": src.auth, **src.extra})
    return [inp], []


def _plan_rest_api(src: Source, idx: int, *, graphql: bool = False) -> tuple[list[NodePlan], list[NodePlan]]:
    """REST or GraphQL API → trivial folder-listing input + Python step."""
    proto = "GraphQL" if graphql else "REST"
    short_url = src.url.split("?", 1)[0] if src.url else "<no url>"
    inp_name = src.name or f"Input {idx}"
    inp_desc = src.description or f"Trigger row for {proto} fetch from {short_url} ({src.format or 'json'})."
    inp = NodePlan(role="input", name=inp_name, description=inp_desc,
                   connector_class="local_xlsx_pointer",
                   connector_attrs={"hint": "skill rewires to a local trigger xlsx"})
    # ACLED uses email+key query-string auth (not Bearer), and the
    # response shape is specific enough that a dedicated template keeps
    # the generic api_caller from accumulating per-publisher special
    # cases. The template still hits the same NodePlan contract.
    if src.format == "acled_json":
        template = "acled_caller.py.j2"
    else:
        template = "api_caller.py.j2"
    api_name = f"{inp_name} Fetcher" if src.name else f"API Caller {idx}"
    api_desc = (
        f"Pulls {proto} data from {short_url}. Format: {src.format or 'json'}. "
        f"Walks pagination, flattens attributes/geometry, returns a dataframe "
        f"with {src.format} schema."
    )
    api = NodePlan(role="script", name=api_name, description=api_desc,
                   template=template,
                   template_vars={
                       "url": src.url,
                       "auth": src.auth,
                       "format": src.format,
                       "graphql": graphql,
                       "extra": src.extra,
                   },
                   function_name="call_api")
    return [inp], [api]


def _plan_web_crawl(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan], dict]:
    """Web crawl → Python step + Prep parameter for the query."""
    inp_name = src.name or f"Input {idx}"
    inp_desc = src.description or f"Trigger row for web crawl (engine: {src.extra.get('engine', 'crawl4ai')})."
    inp = NodePlan(role="input", name=inp_name, description=inp_desc,
                   connector_class="local_xlsx_pointer")
    crawl = NodePlan(role="script", name=f"{inp_name} Crawler" if src.name else f"Crawler {idx}",
                     description=f"Runs a {src.extra.get('engine', 'crawl4ai')} crawl driven by the '{src.extra.get('query_param_name', 'Query')}' Prep parameter; emits one row per fetched page.",
                     template="crawler.py.j2",
                     template_vars={
                         "engine": src.extra.get("engine", "crawl4ai"),
                         "query_param_name": src.extra.get("query_param_name", "Query"),
                         "max_results_per_run": src.extra.get("max_results_per_run", 50),
                         "domains_allowlist": src.extra.get("domains_allowlist", []),
                     },
                     function_name="crawl")
    parameters = {
        src.extra.get("query_param_name", "Query"): {
            "name": src.extra.get("query_param_name", "Query"),
            "displayName": "Crawl Query",
            "domain": {"type": "open"},
            "currentValue": src.extra.get("query_default", ""),
            "type": "string",
        },
    }
    return [inp], [crawl], parameters


def _plan_internal_published_ds(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan]]:
    """A source bound to an existing published data source on the
    Tableau Server.

    Two emission modes:

    1. **Local-CSV mode** (default when run_loop has downloaded the
       extract): emit a LoadCsv input pointing at the CSV that
       Phase 4a wrote. prep-cli runs locally with no auth - this is
       how MFA-bound Cloud sites stay iterable.

    2. **LoadSqlProxy mode** (fallback for backgrounder execution
       AND for sites without MFA): emit a `published_datasource`
       NodePlan that generate_flow renders as a `.v2019_3_1.LoadSqlProxy`
       node with a `.v1.SqlConnection` (class=sqlproxy). At publish
       time, run_loop swaps any LoadCsv inputs back to LoadSqlProxy
       so the backgrounder hits the live DS via the user's site session.

    Both modes preserve LUID/project/site/datasource_name in
    connector_attrs so the publish-time swap can route correctly."""
    extra = src.extra or {}
    inp_name = src.name or f"Input {idx}"

    # Mode 1: local CSV is the iterable mode for MFA-bound Cloud sites.
    csv_path = extra.get("_pds_local_csv_path", "")
    if csv_path:
        from pathlib import Path
        p = Path(csv_path)
        if p.exists():
            ds_name = extra.get("_pds_actual_ds_name") or src.name or ""
            project = extra.get("_pds_actual_project") or extra.get("project") or ""
            row_count = extra.get("_pds_row_count", 0)
            inp_desc = (src.description or "").strip() or (
                f"Local snapshot of published DS '{ds_name}' "
                f"({row_count} rows from project {project!r}) - "
                f"swapped to live LoadSqlProxy at publish time."
            )
            inp = NodePlan(
                role="input", name=inp_name, description=inp_desc,
                connector_class="local_csv",
                connector_attrs={
                    # _pds_* keys are the swap signal for Phase 10:
                    # any input whose connector_attrs carries them
                    # gets rewritten back to LoadSqlProxy at publish.
                    "_pds_csv_path": str(p),
                    "_pds_luid": extra.get("luid", ""),
                    "_pds_project": project,
                    "_pds_site": extra.get("site", ""),
                    "_pds_datasource_name": ds_name,
                    "_pds_column_subset": extra.get("column_subset", []),
                },
            )
            return [inp], []

    # Mode 2: LoadSqlProxy fallback. Used when Phase 4a download failed
    # OR when this skill runs on a non-MFA site where prep-cli could
    # auth directly (rare but valid).
    desc_parts: list[str] = [src.description or ""]
    if extra.get("luid"):
        desc_parts.append(f"luid={extra['luid']}")
    if extra.get("project"):
        desc_parts.append(f"project={extra['project']}")
    if extra.get("column_subset"):
        cols = ",".join(extra["column_subset"][:6])
        if len(extra["column_subset"]) > 6:
            cols += "..."
        desc_parts.append(f"columns={cols}")
    inp_desc = " - ".join(p for p in desc_parts if p) or (
        f"Internal published data source ({extra.get('luid', '<no luid>')}) on the connected Tableau site."
    )
    inp = NodePlan(
        role="input", name=inp_name, description=inp_desc,
        connector_class="published_datasource",
        connector_attrs={
            "luid": extra.get("luid", ""),
            "project": extra.get("project", ""),
            "site": extra.get("site", ""),
            "column_subset": extra.get("column_subset", []),
            "auth": "server_session",
        },
    )
    return [inp], []


def _plan_pki_endpoint(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan]]:
    """PKI cert-auth endpoint → Python step from pki_connector template."""
    inp_name = src.name or f"Input {idx}"
    inp_desc = src.description or f"Trigger row for PKI-authenticated fetch from {src.url or '<no url>'}."
    inp = NodePlan(role="input", name=inp_name, description=inp_desc,
                   connector_class="local_xlsx_pointer")
    pki = NodePlan(role="script", name=f"{inp_name} Caller" if src.name else f"PKI Caller {idx}",
                   description=f"Calls {src.url or '<no url>'} with client cert auth (cert env: {src.extra.get('cert_path_env', 'CLIENT_CERT_PATH')}); returns response rows.",
                   template="pki_connector.py.j2",
                   template_vars={
                       "url": src.url,
                       "format": src.format,
                       "cert_path_env": src.extra.get("cert_path_env", "CLIENT_CERT_PATH"),
                       "cert_key_env": src.extra.get("cert_key_env", "CLIENT_KEY_PATH"),
                       "extra": src.extra,
                   },
                   function_name="call_pki_endpoint")
    return [inp], [pki]


def _is_arcgis_date_col(name: str) -> bool:
    """True iff `name` looks like an ArcGIS date/datetime/time column,
    using word-boundary semantics (so `ActiveFireCandidate` does NOT
    qualify even though it ends in 'date'). Mirrors api_caller's
    word-boundary date detection."""
    if not name:
        return False
    lf = name.lower()
    for suf in ("datetime", "date", "time", "_dt"):
        if not lf.endswith(suf):
            continue
        if suf.startswith("_"):
            return True
        idx = len(lf) - len(suf)
        if idx == 0:
            return True
        if lf[idx - 1] == "_":
            return True
        if idx < len(name) and name[idx].isupper():
            return True
    return False


def _declared_schema_for_source(src: Source) -> dict[str, str]:
    """Best-effort {col: declared_type} for the upstream schema produced
    by this source's fetcher. Mirrors what api_caller's
    `get_output_schema()` (and the GDELT/CSV equivalents) actually
    return so we can suppress redundant casts. Lowercased type strings
    (string/int/decimal/date/datetime/bool)."""
    schema: dict[str, str] = {}
    extra = src.extra or {}
    if src.format == "arcgis_features":
        fields = extra.get("arcgis_out_fields") or ""
        field_types = extra.get("arcgis_field_types") or {}
        if fields and fields != "*":
            for f in [x.strip() for x in fields.split(",") if x.strip()]:
                # api_caller's logic: explicit field_types override > name suffix > default string.
                if f in field_types:
                    schema[f] = field_types[f].lower()
                    continue
                lf = f.lower()
                # api_caller declares date columns as prep_string()
                # (Maestro rejects ISO strings declared as prep_datetime).
                # Word-boundary check via `_is_arcgis_date_col` keeps
                # `ActiveFireCandidate` out of this branch.
                if _is_arcgis_date_col(f):
                    schema[f] = "string"
                elif any(k in lf for k in ("acres", "size", "percent", "lat", "lon")):
                    schema[f] = "decimal"
                elif lf in ("objectid",):
                    schema[f] = "int"
                else:
                    schema[f] = "string"
        if extra.get("arcgis_return_geometry", True):
            if extra.get("arcgis_geometry_kind", "point") == "polyline":
                for c in ("start_lon", "start_lat", "end_lon", "end_lat"):
                    schema.setdefault(c, "decimal")
            else:
                schema.setdefault("longitude", "decimal")
                schema.setdefault("latitude", "decimal")
    elif src.format in ("csv", "csv_zip"):
        for col, decl in (extra.get("csv_schema") or {}).items():
            schema[col] = (decl or "string").lower()
    elif src.format in ("json", "jsonl", "ndjson", "xml"):
        for col, decl in (extra.get("json_schema") or {}).items():
            schema[col] = (decl or "string").lower()
    elif src.format == "csv_index_then_zip":
        # GDELT v1 schema reused from _input_schema_from_sources.
        gdelt_int = {
            "GLOBALEVENTID", "SQLDATE", "MonthYear", "Year", "IsRootEvent",
            "EventCode", "EventBaseCode", "EventRootCode", "QuadClass",
            "NumMentions", "NumSources", "NumArticles", "DATEADDED",
            "Actor1Geo_Type", "Actor2Geo_Type", "ActionGeo_Type",
        }
        gdelt_decimal = {
            "FractionDate", "GoldsteinScale", "AvgTone",
            "Actor1Geo_Lat", "Actor1Geo_Long",
            "Actor2Geo_Lat", "Actor2Geo_Long",
            "ActionGeo_Lat", "ActionGeo_Long",
        }
        for c in gdelt_int:
            schema[c] = "int"
        for c in gdelt_decimal:
            schema[c] = "decimal"
    return schema


def _columns_for_source(src: Source) -> list[str]:
    """Best-effort list of column names emitted by `src`. Used by the
    cast/semantic-role planner so heuristics can fire on each column.
    Returns the union of declared-schema columns plus any user
    overrides (so a cast can be forced on a derived column too)."""
    cols: list[str] = []
    seen: set[str] = set()

    def add(c: str) -> None:
        if c and c not in seen:
            cols.append(c)
            seen.add(c)

    for c in _declared_schema_for_source(src).keys():
        add(c)
    extra = src.extra or {}
    for c in (extra.get("casts") or {}).keys():
        add(c)
    for c in (extra.get("semantic_roles") or {}).keys():
        add(c)
    return cols


def _plan_casts_and_roles(src: Source, branch_idx: int) -> list[NodePlan]:
    """Emit cast + semantic-role NodePlans for `src`'s columns.

    Casts come first (so downstream nodes see typed columns), then
    semantic roles (which Tableau attaches to the typed columns).
    Both insert linearly into the branch chain — `parent=""` means
    `generate_flow` extends the linear tail. They land between the
    source's fetcher transform and any analytics transforms
    (trend_analysis, graph_analysis) that the spec adds later, so
    those analytics see properly-typed inputs.

    Suppresses casts that would be no-ops: if the upstream fetcher
    already declares a column with the same type (e.g. api_caller's
    `get_output_schema()` returns `latitude: prep_decimal()` for a
    point-geometry ArcGIS feed), an explicit ChangeColumnType node
    wraps the column in another type-check round-trip that Maestro
    sometimes rejects with 'a decimal type is required for [latitude]'
    when TabPy's gzipped JSON serialization round-trips the column.
    User-supplied overrides under `extra.casts` always win, even when
    redundant — they may be a deliberate user request to surface the
    cast as an explicit Prep step.
    """
    extra = src.extra or {}
    # Escape hatch: when a source's column-name heuristics fire wrong
    # (e.g. GDELT's `SQLDATE` looks like a date suffix but the data is
    # `YYYYMMDD` strings Prep can't auto-parse), the spec can opt out
    # entirely with `extra._skip_auto_casts: true`. Explicit overrides
    # under extra.casts still apply.
    if extra.get("_skip_auto_casts"):
        return []
    cast_overrides = extra.get("casts") or {}
    role_overrides = extra.get("semantic_roles") or {}
    cols = _columns_for_source(src)
    declared = _declared_schema_for_source(src)
    casts = plan_casts_for_columns(cols, cast_overrides)
    roles = plan_semantic_roles_for_columns(cols, role_overrides)

    nodes: list[NodePlan] = []
    for col, typ in casts.items():
        if col not in cast_overrides and declared.get(col, "").lower() == typ.lower():
            continue
        nodes.append(NodePlan(
            role="cast",
            name=f"Change {col} to {typ.title()}",
            description=f"Casts {col!r} to Tableau type {typ!r} so downstream steps and the Hyper extract carry the correct dtype.",
            connector_attrs={"cast_column": col, "cast_type": typ},
            branch=branch_idx,
        ))
    for col, (role_id, role_name) in roles.items():
        nodes.append(NodePlan(
            role="semantic_role",
            name=f"Change {col} to {role_name}",
            description=f"Tags {col!r} with semantic role {role_name!r} so Tableau renders the geographic / URL pill icon and supports map drill-up.",
            connector_attrs={
                "role_column": col,
                "role_id": role_id,
                "role_name": role_name,
            },
            branch=branch_idx,
        ))
    return nodes


def _plan_outputs(spec: Spec, outputs_dir: Path) -> list[NodePlan]:
    plans: list[NodePlan] = []
    for o in spec.outputs:
        desc = o.description or _default_output_description(o.kind, o.name)
        # `kind` and `source` flow through connector_attrs so generate_flow
        # can fan multiple outputs off the right upstream node and pick the
        # right writer node type. `source` names a transform node by its
        # plan name (e.g. "Crime Trend Analyzer (Stats)"); empty = the
        # linear chain's final tail (single-output default).
        attrs: dict = {"kind": o.kind, "source": o.source or "", "project": o.project or ""}
        if o.kind == "hyper":
            attrs["hyper_path"] = str(outputs_dir / o.name)
        elif o.kind == "csv":
            attrs["csv_path"] = str(outputs_dir / o.name)
        elif o.kind == "published_data_source":
            # The skill's publish step handles server upload of the .tfl;
            # the .tfl itself emits a WritePublishedDataSource node so
            # backgrounder writes the result to the named project.
            attrs["published"] = True
        else:
            attrs["unknown_kind"] = o.kind
        plans.append(NodePlan(role="output", name=o.name, description=desc,
                              connector_attrs=attrs))
    return plans


def _default_output_description(kind: str, name: str) -> str:
    if kind == "hyper":
        return f"Writes the final dataframe to {name}.hyper for Tableau extracts."
    if kind == "csv":
        return f"Writes the final dataframe to {name}.csv."
    if kind == "published_data_source":
        return (
            f"Publishes the result as a Tableau Server data source named {name}. "
            "Tableau backgrounder writes the extract into the project configured "
            "on the .tfl during scheduled runs."
        )
    return f"Output: {name}"


def _input_schema_from_sources(spec: Spec) -> dict:
    """Best-effort upstream schema so QA nodes can pass-through input cols.
    Returns {field_name: declared_type}. Empty dict means 'unknown'."""
    schema: dict = {}
    for src in spec.sources:
        extra = src.extra or {}
        if src.format == "arcgis_features":
            fields = extra.get("arcgis_out_fields") or "*"
            if fields == "*":
                continue
            field_types = extra.get("arcgis_field_types") or {}
            for f in [x.strip() for x in fields.split(",") if x.strip()]:
                if f in field_types:
                    schema[f] = field_types[f]
                    continue
                lf = f.lower()
                # Mirror api_caller's get_output_schema arcgis branch -
                # date columns are emitted as ISO strings. Word-boundary
                # check keeps `ActiveFireCandidate` out of this branch.
                if _is_arcgis_date_col(f):
                    schema[f] = "string"
                elif any(k in lf for k in ("acres", "size", "percent", "lat", "lon")):
                    schema[f] = "decimal"
                elif lf in ("objectid",):
                    schema[f] = "int"
                else:
                    schema[f] = "string"
            if extra.get("arcgis_return_geometry", True):
                if extra.get("arcgis_geometry_kind", "point") == "polyline":
                    schema.setdefault("start_lon", "decimal")
                    schema.setdefault("start_lat", "decimal")
                    schema.setdefault("end_lon", "decimal")
                    schema.setdefault("end_lat", "decimal")
                else:
                    schema.setdefault("longitude", "decimal")
                    schema.setdefault("latitude", "decimal")
        elif src.format == "csv_index_then_zip":
            # GDELT v1 schema (the only csv_index_then_zip source we wire today)
            gdelt_int = {
                "GLOBALEVENTID", "SQLDATE", "MonthYear", "Year", "IsRootEvent",
                "EventCode", "EventBaseCode", "EventRootCode", "QuadClass",
                "NumMentions", "NumSources", "NumArticles", "DATEADDED",
                "Actor1Geo_Type", "Actor2Geo_Type", "ActionGeo_Type",
            }
            gdelt_decimal = {
                "FractionDate", "GoldsteinScale", "AvgTone",
                "Actor1Geo_Lat", "Actor1Geo_Long",
                "Actor2Geo_Lat", "Actor2Geo_Long",
                "ActionGeo_Lat", "ActionGeo_Long",
            }
            gdelt_cols = [
                "GLOBALEVENTID", "SQLDATE", "MonthYear", "Year", "FractionDate",
                "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
                "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
                "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
                "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
                "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
                "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
                "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode",
                "QuadClass", "GoldsteinScale", "NumMentions", "NumSources",
                "NumArticles", "AvgTone", "Actor1Geo_Type", "Actor1Geo_FullName",
                "Actor1Geo_CountryCode", "Actor1Geo_ADM1Code", "Actor1Geo_Lat",
                "Actor1Geo_Long", "Actor1Geo_FeatureID",
                "Actor2Geo_Type", "Actor2Geo_FullName", "Actor2Geo_CountryCode",
                "Actor2Geo_ADM1Code", "Actor2Geo_Lat", "Actor2Geo_Long", "Actor2Geo_FeatureID",
                "ActionGeo_Type", "ActionGeo_FullName", "ActionGeo_CountryCode",
                "ActionGeo_ADM1Code", "ActionGeo_Lat", "ActionGeo_Long", "ActionGeo_FeatureID",
                "DATEADDED", "SOURCEURL",
            ]
            for c in gdelt_cols:
                if c in gdelt_int:
                    schema[c] = "int"
                elif c in gdelt_decimal:
                    schema[c] = "decimal"
                else:
                    schema[c] = "string"
        elif src.format in ("csv", "csv_zip"):
            # Plain CSV sources declare their post-rename schema in extra.csv_schema.
            # Validator + downstream nodes need this so column-passthrough
            # works after joins. Last-write-wins on column-name collisions
            # is fine because join keys overlap intentionally (left/right
            # carry the same column name).
            for col, decl in (extra.get("csv_schema") or {}).items():
                schema[col] = decl
        elif src.format in ("json", "jsonl", "ndjson", "xml"):
            # Plain JSON/XML sources declare schema in extra.json_schema —
            # symmetric with csv_schema. Required when downstream
            # script nodes need to know upstream column types.
            for col, decl in (extra.get("json_schema") or {}).items():
                schema[col] = decl
    return schema


def _input_schema_after_casts(spec: Spec) -> dict:
    """Like `_input_schema_from_sources` but reflects the type each
    column will have AFTER the planner's cast nodes run.

    Cast nodes between the fetcher and analytics transforms convert
    e.g. ISO 8601 string columns into datetime - the upstream-only
    schema view returns those as `string`, which then thrashes against
    the cast in any downstream script's `get_output_schema()`. Apply
    the same `plan_casts_for_columns` rules + cast_overrides here so
    `INPUT_SCHEMA` in the rendered scripts matches what's actually on
    the wire when Maestro hands them rows."""
    base = _input_schema_from_sources(spec)
    for src in spec.sources:
        extra = src.extra or {}
        if extra.get("_skip_auto_casts"):
            continue
        cast_overrides = extra.get("casts") or {}
        # Use the same name list `_plan_casts_and_roles` uses.
        cols = _columns_for_source(src)
        try:
            casts = plan_casts_for_columns(cols, cast_overrides)
        except Exception:
            casts = {}
        for col, typ in casts.items():
            base[col] = typ
    return base


def _plan_qa(spec: Spec) -> list[NodePlan]:
    """Add QA nodes per the spec's qa_tier."""
    if spec.qa_tier == "none":
        return []
    nodes: list[NodePlan] = []
    input_schema = _input_schema_from_sources(spec)
    if spec.qa_tier in ("deterministic", "llm"):
        nodes.append(NodePlan(role="script", name="Validator",
                              description="Deterministic per-row validator. Adds validation_score, n_rules_passed/failed, validation_issues, needs_review. Passes input columns through.",
                              template="validator.py.j2",
                              template_vars={
                                  "transformations": [t.kind for t in spec.transformations],
                                  "input_schema": input_schema,
                              },
                              function_name="validate"))
    if spec.qa_tier == "llm":
        nodes.append(NodePlan(role="script", name="QA Reviewer",
                              description="LLM-backed reviewer. Reads each canonical record and flags issues, severity, and recommended actions.",
                              template="qa_reviewer.py.j2",
                              template_vars={"domain": spec.request[:200]},
                              function_name="review_canonical"))
        nodes.append(NodePlan(role="script", name="Statistical Analyst",
                              description="Computes per-field z-scores and group-level anomalies across the run for downstream attention lists.",
                              template="statistical_analyst.py.j2",
                              template_vars={"transformations": [t.kind for t in spec.transformations]},
                              function_name="analyze_corpus"))
    return nodes


def plan_sources(spec: Spec, outputs_dir: Optional[Path] = None) -> Plan:
    """Top-level: turn a Spec into a Plan. `outputs_dir` defaults to ./outputs."""
    outputs_dir = outputs_dir or Path("./outputs")
    plan = Plan()

    for i, src in enumerate(spec.sources, start=1):
        branch_idx = i - 1
        if src.type == "local_folder":
            ins, trs = _plan_local_folder(src, i)
        elif src.type == "native_connector":
            ins, trs = _plan_native_connector(src, i)
        elif src.type == "rest_api":
            ins, trs = _plan_rest_api(src, i, graphql=False)
        elif src.type == "graphql_api":
            ins, trs = _plan_rest_api(src, i, graphql=True)
        elif src.type == "web_crawl":
            ins, trs, params = _plan_web_crawl(src, i)
            plan.parameters.update(params)
        elif src.type == "pki_endpoint":
            ins, trs = _plan_pki_endpoint(src, i)
        elif src.type == "internal_published_ds":
            ins, trs = _plan_internal_published_ds(src, i)
        else:
            raise ValueError(f"unsupported source type: {src.type}")
        for n in ins:
            n.branch = branch_idx
        for n in trs:
            n.branch = branch_idx
        plan.inputs.extend(ins)
        plan.transforms.extend(trs)
        # Cast + semantic-role nodes come right after the source's
        # fetcher transforms and before analytics (trend, graph) so
        # downstream computations see properly-typed columns. Linear
        # append (parent="") chains them onto the source's tail.
        plan.transforms.extend(_plan_casts_and_roles(src, branch_idx))

    # Join transformations. Each `kind == "join"` entry references two
    # source branches and a join column. The .tfl will materialize one
    # SuperJoin node per join; the post-join tail (qa, output) hangs off
    # the last join.
    #
    # Maestro's `JoinType` enum accepts: inner, left, right, full,
    # notInner, leftOnly, rightOnly. We normalize common SQL/dbt
    # synonyms (leftOuter, rightOuter, fullOuter) to the enum names
    # the deserializer expects, otherwise SimpleJoinCompiler NPEs at
    # JoinAccessors.getJoinType.
    JOIN_TYPE_ALIASES = {
        "leftouter": "left", "left_outer": "left", "left outer": "left",
        "rightouter": "right", "right_outer": "right", "right outer": "right",
        "fullouter": "full", "full_outer": "full", "full outer": "full",
        "outer": "full",
    }
    for j, tr in enumerate(spec.transformations):
        if tr.kind != "join":
            continue
        args = tr.args or {}
        raw_type = (args.get("join_type") or "inner").strip()
        join_type = JOIN_TYPE_ALIASES.get(raw_type.lower(), raw_type)
        join_name = args.get("name", f"Join {j + 1}")
        plan.joins.append(NodePlan(
            role="join",
            name=join_name,
            description=args.get("description") or f"{join_type} join of branch {args.get('left_branch', 0)} and branch {args.get('right_branch', 1)} on '{args.get('on', '')}'.",
            join_left=int(args.get("left_branch", 0)),
            join_right=int(args.get("right_branch", 1)),
            join_on=args.get("on", ""),
            join_type=join_type,
        ))

    # Graph analysis transformations. Emit a graph_analyzer script
    # appended to the named branch (default branch 0). The script
    # consumes an edge dataframe and emits an endpoint-row table with
    # geographic + force-directed layout coords + standard centralities.
    # Schema declared via `input_schema` so prior columns flow through.
    # Note: build the POST-cast schema. Cast nodes between the fetcher
    # and analytics transforms convert e.g. ISO 8601 string columns
    # into datetime; downstream scripts must declare those columns as
    # datetime in `get_output_schema()` to match what Maestro sees, or
    # Maestro fails the run with 'a datetime type is required for [X]'.
    input_schema = _input_schema_after_casts(spec)
    for j, tr in enumerate(spec.transformations):
        if tr.kind != "graph_analysis":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        ga_name = args.get("name", "Graph Analyzer")
        ga_desc = args.get("description") or (
            f"Builds a NetworkX graph from edges keyed by "
            f"{args.get('source_id_col', 'SUB_1')} → {args.get('target_id_col', 'SUB_2')}. "
            f"Computes Fruchterman-Reingold layout (geographic seed) plus degree, "
            f"betweenness, eigenvector, pagerank, and closeness centrality. Emits "
            f"two rows per edge (one per endpoint) for line rendering in Tableau."
        )
        node = NodePlan(
            role="script",
            name=ga_name,
            description=ga_desc,
            template="graph_analyzer.py.j2",
            template_vars={
                "source_id_col": args.get("source_id_col", "SUB_1"),
                "target_id_col": args.get("target_id_col", "SUB_2"),
                "layout_iterations": int(args.get("layout_iterations", 50)),
                "layout_scale": float(args.get("layout_scale", 10.0)),
                "layout_seed_from_geography": bool(args.get("layout_seed_from_geography", True)),
                "closeness_full_threshold": int(args.get("closeness_full_threshold", 1000)),
                "input_schema": input_schema,
            },
            function_name="analyze_graph",
            branch=branch_idx,
        )
        plan.transforms.append(node)

    # Trend analysis transformations. Now a fork:
    #   trend_features → row-level temporal features only (small extract)
    #   trend_stats    → long-form stats table (one row per
    #                    dim×value×year×month) joinable back from Tableau
    # Both nodes consume the same upstream input branch so the stats
    # don't pay row-multiplied storage costs.
    for j, tr in enumerate(spec.transformations):
        if tr.kind != "trend_analysis":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        base_name = args.get("name", "Trend Analyzer")
        dims = args.get("dimensions") or []
        date_col = args.get("date_col", "occ_date")
        time_col = args.get("time_col", "")
        rolling = int(args.get("rolling_window_days", 30))
        anomaly_z = float(args.get("anomaly_z", 2.0))

        feat_name = f"{base_name} (Features)"
        feat_desc = args.get("features_description") or (
            f"Adds per-row temporal features (year/month/quarter/dow/iso_week/"
            f"hour_of_day/hour_bucket) parsed from {date_col!r}"
            + (f" and {time_col!r}" if time_col else "")
            + ". Pure pass-through: no per-dimension stats are joined "
              "to the row, keeping the detail extract lean."
        )
        plan.transforms.append(NodePlan(
            role="script",
            name=feat_name,
            description=feat_desc,
            template="trend_features.py.j2",
            template_vars={
                "date_col": date_col,
                "time_col": time_col,
                "input_schema": input_schema,
            },
            function_name="add_features",
            branch=branch_idx,
        ))

        stats_name = f"{base_name} (Stats)"
        stats_desc = args.get("stats_description") or (
            f"Long-form trend statistics: one row per (dimension, value, year, month) "
            f"across {dims}. Joinable from Tableau on (dimension, value, year, month). "
            f"Includes monthly_count, yoy_change/yoy_pct, {rolling}-day rolling_count, "
            f"baseline_mean/std, zscore, lifetime_count/rank/pct_of_total, and "
            f"is_anomaly (|z| >= {anomaly_z})."
        )
        # Fan off the SAME upstream as Features so Stats consumes the
        # same raw event rows. For an API source the upstream is the
        # Fetcher (not the trigger Input), so a @sibling: parent is
        # required — `@input` would land Stats on the trigger row,
        # which carries no events. The linear chain (and therefore the
        # detail output) stays anchored on Features so the row-level
        # extract isn't collapsed to one row per (dim, value, ym).
        plan.transforms.append(NodePlan(
            role="script",
            name=stats_name,
            description=stats_desc,
            template="trend_stats.py.j2",
            template_vars={
                "date_col": date_col,
                "dimensions": dims,
                "rolling_window_days": rolling,
                "anomaly_z": anomaly_z,
            },
            function_name="build_stats",
            branch=branch_idx,
            parent=f"@sibling:{feat_name}",
        ))

    # EOC fire-incident enrichment. Single-row script; consumes the
    # branch tail (so it composes naturally after trend_features when
    # both are configured) and adds analyst-facing derived columns
    # (size_class, growth_band, containment_band, days_since_discovery,
    # region_key, incident_summary). Sized for ArcGIS/WFIGS-shape feeds
    # but works on any incident table by mapping the column names.
    for tr in spec.transformations:
        if tr.kind != "eoc_fire_metrics":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        base_name = args.get("name", "EOC Fire Metrics")
        eoc_desc = args.get("description") or (
            "Adds EOC analyst-facing derived metrics: days-since-discovery, "
            "staleness, daily growth (acres/day), NWCG size class, "
            "containment band, is_active flag, region_key (state/county) "
            "and a tooltip-ready incident_summary string."
        )
        plan.transforms.append(NodePlan(
            role="script",
            name=base_name,
            description=eoc_desc,
            template="eoc_fire_metrics.py.j2",
            template_vars={
                "size_col":          args.get("size_col", "IncidentSize"),
                "discovery_col":     args.get("discovery_col", "FireDiscoveryDateTime"),
                "modified_col":      args.get("modified_col", "ModifiedOnDateTime_dt"),
                "containment_col":   args.get("containment_col", "PercentContained"),
                "containment_dt_col":args.get("containment_dt_col", "ContainmentDateTime"),
                "state_col":         args.get("state_col", "POOState"),
                "county_col":        args.get("county_col", "POOCounty"),
                "agency_col":        args.get("agency_col", "POOJurisdictionalAgency"),
                "cause_col":         args.get("cause_col", "FireCauseGeneral"),
                "name_col":          args.get("name_col", "IncidentName"),
                "type_col":          args.get("type_col", "IncidentTypeCategory"),
                "fire_out_col":      args.get("fire_out_col", "FireOutDateTime"),
                "reference_now":     args.get("reference_now", ""),
                "input_schema":      input_schema,
            },
            function_name="add_metrics",
            branch=branch_idx,
        ))

    # PII / PAI redaction transformations. Like trend_analysis, this
    # forks into two siblings consuming the same upstream:
    #   pii_redactor → row-preserving clean output (one row in, one row out
    #                  with PII masked in place + 3 diagnostic columns)
    #   pii_audit    → long-form audit table (one row per detection,
    #                  with sha256 of the original — never the original)
    # The redactor anchors the linear chain so the clean records flow to
    # the default Hyper output; the auditor hangs off as a sibling so
    # the per-detection table can be wired to its own output.
    for j, tr in enumerate(spec.transformations):
        if tr.kind != "pii_redaction":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        base_name = args.get("name", "PII Redactor")
        enabled = args.get("enabled_categories") or [
            "direct", "financial", "geographic", "health",
        ]
        redaction_token = args.get("redaction_token", "[REDACTED]")
        hash_token_prefix = args.get("hash_token_prefix", "PII_")
        record_id_col = args.get("record_id_col", "record_id")
        red_desc = args.get("redactor_description") or (
            f"Detects and masks PII/PAI across categories {enabled}. "
            f"Returns the same rows with sensitive cells redacted in place "
            f"plus diagnostic columns: pii_categories_detected, "
            f"pii_fields_redacted, pii_severity (none|low|medium|high)."
        )
        red_name = f"{base_name} (Redact)"
        plan.transforms.append(NodePlan(
            role="script",
            name=red_name,
            description=red_desc,
            template="pii_redactor.py.j2",
            template_vars={
                "enabled_categories": enabled,
                "redaction_token": redaction_token,
                "hash_token_prefix": hash_token_prefix,
                "input_schema": input_schema,
            },
            function_name="redact",
            branch=branch_idx,
        ))

        audit_desc = args.get("audit_description") or (
            f"Long-form PII detection audit. One row per (record_id, field) "
            f"detection with category, detector, sha256 of the original "
            f"value (never the original itself), and the masked replacement. "
            f"Used for redaction QA / compliance review."
        )
        audit_name = f"{base_name} (Audit)"
        plan.transforms.append(NodePlan(
            role="script",
            name=audit_name,
            description=audit_desc,
            template="pii_audit.py.j2",
            template_vars={
                "enabled_categories": enabled,
                "redaction_token": redaction_token,
                "hash_token_prefix": hash_token_prefix,
                "record_id_col": record_id_col,
            },
            function_name="audit",
            branch=branch_idx,
            parent=f"@sibling:{red_name}",
        ))

    # Embassy threat join. Single-input script that consumes the GDELT
    # feed dataframe, filters to threat-class CAMEO root codes within
    # the configured lookback window, and emits one row per (US post,
    # event) pair within haversine radius. Sibling `embassy_risk_summary`
    # consumes this node's output to produce the per-post roll-up.
    for tr in spec.transformations:
        if tr.kind != "embassy_threat_join":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        join_name = args.get("name", "Embassy Threat Join")
        join_desc = args.get("description") or (
            f"Spatial-joins GDELT events to a curated US diplomatic-post roster. "
            f"Filters to CAMEO root codes {args.get('cameo_root_codes')} within "
            f"the past {args.get('lookback_days', 90)} days; haversine radius "
            f"{args.get('radius_miles', 50)}mi. Emits one row per (post, event) "
            f"pair with severity / proximity / recency / US-actor scoring."
        )
        plan.transforms.append(NodePlan(
            role="script",
            name=join_name,
            description=join_desc,
            template="embassy_threat_join.py.j2",
            template_vars={
                "radius_miles":         int(args.get("radius_miles", 50)),
                "lookback_days":        int(args.get("lookback_days", 90)),
                "cameo_root_codes":     args.get("cameo_root_codes", ["13", "14", "17", "18", "19", "20"]),
                "lat_col":              args.get("lat_col", "ActionGeo_Lat"),
                "lon_col":              args.get("lon_col", "ActionGeo_Long"),
                "date_col":             args.get("date_col", "SQLDATE"),
                "event_root_col":       args.get("event_root_col", "EventRootCode"),
                "event_code_col":       args.get("event_code_col", "EventCode"),
                "goldstein_col":        args.get("goldstein_col", "GoldsteinScale"),
                "actor1_country_col":   args.get("actor1_country_col", "Actor1CountryCode"),
                "actor2_country_col":   args.get("actor2_country_col", "Actor2CountryCode"),
                "actor1_name_col":      args.get("actor1_name_col", "Actor1Name"),
                "actor2_name_col":      args.get("actor2_name_col", "Actor2Name"),
                "action_geo_full_col":  args.get("action_geo_full_col", "ActionGeo_FullName"),
                "num_mentions_col":     args.get("num_mentions_col", "NumMentions"),
                "source_url_col":       args.get("source_url_col", "SOURCEURL"),
                "input_schema":         input_schema,
            },
            function_name="join_threats",
            branch=branch_idx,
        ))

    # Embassy ACLED join. Single-input script that consumes the ACLED
    # API response, filters to events within the lookback window, and
    # emits one row per (US post, event) pair within haversine radius.
    # Unlike embassy_threat_join, no severity/risk scoring is applied —
    # the consumer pattern is LLM-grounded analysis in Tableau using
    # the analyst-written `notes` field, where pre-aggregation would
    # conceal the qualitative signal that matters most.
    for tr in spec.transformations:
        if tr.kind != "embassy_acled_join":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        join_name = args.get("name", "Embassy ACLED Join")
        join_desc = args.get("description") or (
            f"Spatial-joins ACLED events to a curated US diplomatic-post roster. "
            f"Window: past {args.get('lookback_days', 90)} days; "
            f"haversine radius {args.get('radius_miles', 100)}mi. "
            f"Emits one row per (post, event) pair with distance_miles + days_ago. "
            f"All ACLED fields (event_type, sub_event_type, actors, fatalities, "
            f"source, notes) pass through verbatim for analyst grounding."
        )
        plan.transforms.append(NodePlan(
            role="script",
            name=join_name,
            description=join_desc,
            template="embassy_acled_join.py.j2",
            template_vars={
                "radius_miles":  int(args.get("radius_miles", 100)),
                "lookback_days": int(args.get("lookback_days", 90)),
                "lat_col":       args.get("lat_col", "latitude"),
                "lon_col":       args.get("lon_col", "longitude"),
                "date_col":      args.get("date_col", "event_date"),
                "input_schema":  input_schema,
            },
            function_name="join_acled_events",
            branch=branch_idx,
        ))

    # Embassy risk summary. Sibling of embassy_threat_join. Consumes the
    # event-pair dataframe and aggregates to one row per US post with
    # weighted threat score and risk_band. Posts with zero events in
    # the window still appear in the output (LOW band).
    for tr in spec.transformations:
        if tr.kind != "embassy_risk_summary":
            continue
        args = tr.args or {}
        branch_idx = int(args.get("branch", 0))
        sum_name = args.get("name", "Embassy Risk Summary")
        sum_desc = args.get("description") or (
            f"Per-post weighted-threat-score roll-up of the Embassy Threat "
            f"Join's event pairs over a {args.get('window_days', 7)}-day window. "
            "Emits one row per post with risk_band (CRITICAL / HIGH / ELEVATED "
            "/ GUARDED / LOW) plus per-class event counts."
        )
        # Linear child of the join: summary consumes the join's output
        # (post×event pairs), not raw GDELT. The event-level output
        # routes to the join via `output.source = "Embassy Threat Join"`;
        # the summary output uses the linear tail (this node) by default.
        plan.transforms.append(NodePlan(
            role="script",
            name=sum_name,
            description=sum_desc,
            template="embassy_risk_summary.py.j2",
            template_vars={
                "window_days": int(args.get("window_days", 7)),
            },
            function_name="summarize",
            branch=branch_idx,
        ))

    plan.qa_nodes = _plan_qa(spec)
    plan.outputs = _plan_outputs(spec, outputs_dir)
    return plan


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="Path to spec.json")
    ap.add_argument("--outputs-dir", default="./outputs")
    args = ap.parse_args()
    spec_dict = json.loads(Path(args.spec).read_text())
    spec = Spec(
        request=spec_dict["request"],
        sources=[Source(**s) for s in spec_dict["sources"]],
        transformations=[],  # not needed for planner
        outputs=[],
        qa_tier=spec_dict["qa_tier"],
        eval_strategy=spec_dict["eval_strategy"],
        deployment=spec_dict.get("deployment", "local"),
        refresh_cadence=spec_dict.get("refresh_cadence", "once"),
        parameterize_query=bool(spec_dict.get("parameterize_query", False)),
        confidence=spec_dict.get("confidence", 1.0),
    )
    # Re-hydrate full spec
    from skill.scripts.intake import Transformation, Output
    spec.transformations = [Transformation(**t) for t in spec_dict["transformations"]]
    spec.outputs = [Output(**o) for o in spec_dict["outputs"]]
    plan = plan_sources(spec, Path(args.outputs_dir))
    print(json.dumps({
        "inputs": [n.__dict__ for n in plan.inputs],
        "transforms": [n.__dict__ for n in plan.transforms],
        "qa_nodes": [n.__dict__ for n in plan.qa_nodes],
        "outputs": [n.__dict__ for n in plan.outputs],
        "parameters": plan.parameters,
    }, indent=2))
