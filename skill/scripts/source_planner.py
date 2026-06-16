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


@dataclass
class NodePlan:
    """One node we intend to emit in the .tfl."""
    role: str             # 'input' | 'script' | 'join' | 'output'
    name: str             # display name in Prep
    template: str = ""    # Jinja template path (relative to templates/) for script nodes
    template_vars: dict = field(default_factory=dict)
    rendered_path: str = ""  # filled in by generate_flow after rendering
    function_name: str = ""  # entry function for script nodes
    connector_class: str = ""  # for native input nodes
    connector_attrs: dict = field(default_factory=dict)


@dataclass
class Plan:
    """The full plan: source-side input nodes, transformation script nodes, output nodes."""
    inputs: list[NodePlan] = field(default_factory=list)
    transforms: list[NodePlan] = field(default_factory=list)
    qa_nodes: list[NodePlan] = field(default_factory=list)
    outputs: list[NodePlan] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)  # Tableau Prep parameters block


def _plan_local_folder(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan]]:
    """Local-folder source → (input nodes, transform nodes)."""
    # The input is a tiny .xlsx with a single 'folder' column pointing at the
    # source path. We rewire it to a local file later in generate_flow.
    inp = NodePlan(role="input", name=f"Input {idx}",
                   connector_class="local_folder",
                   connector_attrs={"path": src.path, "format": src.format})

    # Transform: a Python step that walks the folder. Template depends on format.
    if src.format in ("pdf_portfolio", "pdf"):
        template = "connectors/pdf_walker.py.j2"
    elif src.format == "json":
        template = "connectors/json_walker.py.j2"
    elif src.format == "csv":
        # CSV folders are best handled by the native CSV connector with
        # union, no Python step needed.
        return [inp], []
    else:
        template = "connectors/generic_folder_walker.py.j2"

    walk = NodePlan(role="script", name=f"Source {idx} Walker",
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

    inp = NodePlan(role="input", name=f"Input {idx}",
                   connector_class=cls,
                   connector_attrs={"url": src.url, "auth": src.auth, **src.extra})
    return [inp], []


def _plan_rest_api(src: Source, idx: int, *, graphql: bool = False) -> tuple[list[NodePlan], list[NodePlan]]:
    """REST or GraphQL API → trivial folder-listing input + Python step."""
    inp = NodePlan(role="input", name=f"Input {idx}",
                   connector_class="local_xlsx_pointer",
                   connector_attrs={"hint": "skill rewires to a local trigger xlsx"})
    template = "api_caller.py.j2"
    api = NodePlan(role="script", name=f"API Caller {idx}",
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
    inp = NodePlan(role="input", name=f"Input {idx}",
                   connector_class="local_xlsx_pointer")
    crawl = NodePlan(role="script", name=f"Crawler {idx}",
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


def _plan_pki_endpoint(src: Source, idx: int) -> tuple[list[NodePlan], list[NodePlan]]:
    """PKI cert-auth endpoint → Python step from pki_connector template."""
    inp = NodePlan(role="input", name=f"Input {idx}",
                   connector_class="local_xlsx_pointer")
    pki = NodePlan(role="script", name=f"PKI Caller {idx}",
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


def _plan_outputs(spec: Spec, outputs_dir: Path) -> list[NodePlan]:
    plans: list[NodePlan] = []
    for o in spec.outputs:
        if o.kind == "hyper":
            plans.append(NodePlan(role="output", name=o.name,
                                  connector_attrs={"hyper_path": str(outputs_dir / o.name)}))
        elif o.kind == "csv":
            plans.append(NodePlan(role="output", name=o.name,
                                  connector_attrs={"csv_path": str(outputs_dir / o.name)}))
        elif o.kind == "published_data_source":
            # v2: needs Tableau Server publishing
            plans.append(NodePlan(role="output", name=o.name,
                                  connector_attrs={"published": True, "deferred": "v2"}))
        else:
            plans.append(NodePlan(role="output", name=o.name,
                                  connector_attrs={"unknown_kind": o.kind}))
    return plans


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
            for f in [x.strip() for x in fields.split(",") if x.strip()]:
                lf = f.lower()
                if lf.endswith(("date", "datetime", "time")):
                    schema[f] = "string"
                elif any(k in lf for k in ("acres", "size", "percent", "lat", "lon")):
                    schema[f] = "decimal"
                elif lf in ("objectid",):
                    schema[f] = "int"
                else:
                    schema[f] = "string"
            if extra.get("arcgis_return_geometry", True):
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
    return schema


def _plan_qa(spec: Spec) -> list[NodePlan]:
    """Add QA nodes per the spec's qa_tier."""
    if spec.qa_tier == "none":
        return []
    nodes: list[NodePlan] = []
    input_schema = _input_schema_from_sources(spec)
    if spec.qa_tier in ("deterministic", "llm"):
        nodes.append(NodePlan(role="script", name="Validator",
                              template="validator.py.j2",
                              template_vars={
                                  "transformations": [t.kind for t in spec.transformations],
                                  "input_schema": input_schema,
                              },
                              function_name="validate"))
    if spec.qa_tier == "llm":
        nodes.append(NodePlan(role="script", name="QA Reviewer",
                              template="qa_reviewer.py.j2",
                              template_vars={"domain": spec.request[:200]},
                              function_name="review_canonical"))
        nodes.append(NodePlan(role="script", name="Statistical Analyst",
                              template="statistical_analyst.py.j2",
                              template_vars={"transformations": [t.kind for t in spec.transformations]},
                              function_name="analyze_corpus"))
    return nodes


def plan_sources(spec: Spec, outputs_dir: Optional[Path] = None) -> Plan:
    """Top-level: turn a Spec into a Plan. `outputs_dir` defaults to ./outputs."""
    outputs_dir = outputs_dir or Path("./outputs")
    plan = Plan()

    for i, src in enumerate(spec.sources, start=1):
        if src.type == "local_folder":
            ins, trs = _plan_local_folder(src, i)
            plan.inputs.extend(ins)
            plan.transforms.extend(trs)
        elif src.type == "native_connector":
            ins, trs = _plan_native_connector(src, i)
            plan.inputs.extend(ins)
            plan.transforms.extend(trs)
        elif src.type == "rest_api":
            ins, trs = _plan_rest_api(src, i, graphql=False)
            plan.inputs.extend(ins)
            plan.transforms.extend(trs)
        elif src.type == "graphql_api":
            ins, trs = _plan_rest_api(src, i, graphql=True)
            plan.inputs.extend(ins)
            plan.transforms.extend(trs)
        elif src.type == "web_crawl":
            ins, trs, params = _plan_web_crawl(src, i)
            plan.inputs.extend(ins)
            plan.transforms.extend(trs)
            plan.parameters.update(params)
        elif src.type == "pki_endpoint":
            ins, trs = _plan_pki_endpoint(src, i)
            plan.inputs.extend(ins)
            plan.transforms.extend(trs)
        else:
            raise ValueError(f"unsupported source type: {src.type}")

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
