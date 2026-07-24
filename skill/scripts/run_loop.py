"""
End-to-end orchestrator for the tableau-prep-etl skill.

Pipeline:
  1. intake(request) → spec.json
  2. plan_sources(spec) → Plan
  3. generate_flow(spec, plan, run_dir) → flow.tfl
  4. synthesize_eval(spec, run_dir) → EvalRig
  5. Bounded refinement loop (default MAX_ITERATIONS=3):
     a. Run flow.tfl via tableau-prep-cli
     b. Read output Hyper(s)
     c. Score against GT (if any)
     d. If overall_mean < THRESHOLD and iters < MAX_ITERATIONS:
        - Ask LLM to propose a v+1 of the worst-performing script
        - Re-render the template, swap the script path, re-run
     e. If overall_mean >= THRESHOLD or iters exhausted: stop
  6. Emit final report.md (attention list + suggestions + anomalies)

Public entry: `run(request: str, run_dir: Optional[Path] = None) -> dict`
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from skill.scripts.lib import _REPO_ROOT  # noqa: F401

from skill.scripts.intake import (
    IntakeIncomplete, Output, ServerPublish, Source, Spec, Transformation, intake,
)
from skill.scripts.source_planner import plan_sources
from skill.scripts.generate_flow import generate_flow
from skill.scripts.synthesize_eval import synthesize_eval
from skill.scripts.spec_validation import (
    SpecValidationError,
    safe_output_dict,
    safe_source_dict,
    safe_transform_dict,
    validate_spec_strict,
)
from skill.scripts import host_trust


def _spec_from_dict(spec_dict: dict, request: str = "") -> Spec:
    """Hydrate a Spec from a JSON dict (no-LLM mode).

    The archive load path was previously trusting `flows/<flow>/v*/spec.json`
    verbatim — meaning an edited archive could ship a `file://` URL or
    `../../etc/foo` output name straight to code rendering. Both this
    function and intake.intake() now run through `validate_spec_strict`
    + the host-approval gate before any rendering.
    """
    validate_spec_strict(spec_dict)

    # Host-approval gate — same as intake.intake. Internal hosts /
    # previously-approved hosts pass without prompting; unknown hosts
    # surface to the operator (or hard-fail under TPE_HOST_APPROVAL=
    # deny-unknown for unattended runs).
    host_trust.ensure_hosts_approved(host_trust.extract_hosts(spec_dict))

    sp = spec_dict.get("server_publish")
    server_publish = ServerPublish(**sp) if isinstance(sp, dict) else None
    return Spec(
        request=spec_dict.get("request") or request,
        sources=[Source(**safe_source_dict(s)) for s in spec_dict.get("sources", [])],
        transformations=[
            Transformation(**safe_transform_dict(t))
            for t in spec_dict.get("transformations", [])
        ],
        outputs=[Output(**safe_output_dict(o)) for o in spec_dict.get("outputs", [])],
        qa_tier=spec_dict.get("qa_tier", "deterministic"),
        eval_strategy=spec_dict.get("eval_strategy", "sample_validation"),
        deployment=spec_dict.get("deployment", "local"),
        refresh_cadence=spec_dict.get("refresh_cadence", "once"),
        parameterize_query=bool(spec_dict.get("parameterize_query", False)),
        server_publish=server_publish,
        confidence=float(spec_dict.get("confidence", 1.0)),
        open_questions=list(spec_dict.get("open_questions", [])),
    )


MAX_ITERATIONS = int(os.environ.get("MAX_REFINEMENT_ITERATIONS", "3"))
THRESHOLD = float(os.environ.get("REFINEMENT_THRESHOLD", "0.85"))
TABLEAU_PREP_CLI = os.environ.get(
    "TABLEAU_PREP_CLI",
    "/Applications/Tableau Prep Builder (Apple silicon) 2026.1.app"
    "/Contents/scripts/tableau-prep-cli",
)


def _new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _safe_tfl_basename(flow_name: Optional[str]) -> str:
    """Filesystem-safe basename for the .tfl artifact. Falls back to
    'flow' when no flow_name is set (preserves the legacy default for
    direct callers of generate_flow)."""
    if not flow_name:
        return "flow"
    import re
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", flow_name).strip("._-")
    return cleaned or "flow"


def _run_prep_cli(tfl: Path, log_path: Path, timeout_s: int = 1800) -> int:
    """Invoke tableau-prep-cli, capturing stdout/stderr to log_path.
    Returns the CLI exit code.

    When the .tfl contains any `class: sqlproxy` connection (i.e. the
    flow reads from a Tableau Server published DS), we synthesize a
    temporary credentials.json with the user/pass from
    TABLEAU_SERVER_USERNAME / _PASSWORD and pass it via -c. The temp
    file is chmod 600 and deleted after the CLI exits regardless of
    success.

    Tableau Prep CLI v2026.1 doesn't accept PATs in this file - product
    gap. PATs remain primary auth for publish/scan/metadata."""
    cli = Path(TABLEAU_PREP_CLI)
    if not cli.exists():
        raise RuntimeError(f"tableau-prep-cli not found at {cli}")
    if not tfl.exists():
        raise RuntimeError(f"flow file not found: {tfl}")

    creds_path: Optional[Path] = None
    creds_synth_result: Optional[dict] = None
    try:
        from skill.scripts.server_creds import synthesize_cli_credentials_json
        tmp_creds = log_path.parent / "_cli_credentials.json"
        creds_synth_result = synthesize_cli_credentials_json(tfl, tmp_creds)
        if creds_synth_result.get("status") == "ok":
            creds_path = Path(creds_synth_result["path"])
            # The synthesized file contains plaintext server PAT/password
            # by necessity (Tableau Prep CLI's contract). chmod 600 the
            # moment it exists so umask defaults can't leave it readable
            # to other users on shared workstations.
            try:
                os.chmod(creds_path, 0o600)
            except OSError:
                pass
    except Exception as e:
        creds_synth_result = {"status": "error", "type": type(e).__name__,
                              "message": str(e)}

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as logf:
        logf.write(f"# tableau-prep-cli run at {time.ctime()}\n")
        logf.write(f"# CLI: {cli}\n")
        logf.write(f"# TFL: {tfl}\n")
        if creds_synth_result:
            # Don't log the path if it's not used; never log credentials.
            status = creds_synth_result.get("status")
            if status == "ok":
                logf.write(f"# credentials.json: synthesized for "
                           f"{creds_synth_result.get('connection_count', 0)} sqlproxy connection(s)\n")
            elif status == "skipped":
                logf.write(f"# credentials.json: skipped ({creds_synth_result.get('reason', '')[:120]})\n")
            else:
                logf.write(f"# credentials.json: error ({creds_synth_result.get('message', '')[:120]})\n")
        logf.write("\n")
        logf.flush()
        argv = [str(cli), "-t", str(tfl)]
        if creds_path is not None:
            argv.extend(["-c", str(creds_path)])
        proc = subprocess.Popen(argv, stdout=logf, stderr=subprocess.STDOUT)
        try:
            rc = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = -1

    # Always remove the synthesized creds file - it contains plaintext
    # password by necessity (Tableau Prep CLI requires it). Failures
    # used to be swallowed silently, which masked NFS permission bugs
    # and leaked the file. Log + re-attempt rather than pass.
    if creds_path is not None and creds_path.exists():
        try:
            creds_path.unlink()
        except Exception as e:
            try:
                with log_path.open("a") as logf:
                    logf.write(
                        f"# WARN: failed to delete {creds_path}: {type(e).__name__}: {e}\n"
                    )
            except Exception:
                pass
    return rc


def _read_hyper(hyper_path: Path) -> list[dict]:
    """Read a Hyper file via tableauhyperapi. Returns list of row dicts."""
    if not hyper_path.exists():
        return []
    try:
        from tableauhyperapi import HyperProcess, Telemetry, Connection
    except ImportError:
        return []
    rows: list[dict] = []
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(endpoint=hp.endpoint, database=hyper_path) as conn:
            schemas = [s.name.unescaped for s in conn.catalog.get_schema_names()]
            chosen = "Extract" if "Extract" in schemas else (schemas[0] if schemas else None)
            if chosen is None:
                return []
            tables = conn.catalog.get_table_names(chosen)
            if not tables:
                return []
            t = tables[0]
            cols = [c.name.unescaped for c in conn.catalog.get_table_definition(t).columns]
            with conn.execute_query(f'SELECT * FROM {t}') as cur:
                for row in cur:
                    rows.append(dict(zip(cols, row)))
    return rows


def _score_against_gt(rig_gt_dir: Path, output_rows: list[dict]) -> dict:
    """Field-level scoring of output rows against GT records on disk.
    Returns aggregate dict: {overall_mean, per_field, n_scored}."""
    if not rig_gt_dir.exists():
        return {"overall_mean": 0.0, "per_field": {}, "n_scored": 0, "reason": "no GT dir"}

    gt_files = sorted(rig_gt_dir.glob("*.json"))
    if not gt_files:
        return {"overall_mean": 0.0, "per_field": {}, "n_scored": 0, "reason": "no GT records"}

    sys.path.insert(0, str(_REPO_ROOT / "auto_refine") if (_REPO_ROOT / "auto_refine").exists() else str(_REPO_ROOT))
    try:
        from auto_refine.eval.scorer.score import score_one, ScorerConfig, aggregate
    except ImportError:
        return {"overall_mean": 0.0, "per_field": {}, "n_scored": 0, "reason": "scorer unavailable"}

    # Build a config from the union of fields in GT records
    all_fields: set[str] = set()
    gt_by_id: dict[str, dict] = {}
    for p in gt_files:
        rec = json.loads(p.read_text())
        rid = rec.get("id") or rec.get("portfolio_id") or p.stem
        gt_by_id[rid] = rec.get("fields") or {}
        all_fields.update(gt_by_id[rid].keys())

    cfg = ScorerConfig(fields=sorted(all_fields))

    out_by_id = {}
    for r in output_rows:
        rid = r.get("id") or r.get("portfolio_id") or r.get("invoice_id") or r.get("filename")
        if rid:
            out_by_id[str(rid)] = r

    scores = {}
    for rid, gt_fields in gt_by_id.items():
        actual = out_by_id.get(rid, {})
        ps = score_one(gt_fields, actual, config=cfg)
        ps.portfolio_id = rid
        scores[rid] = ps

    agg = aggregate(scores)
    return {
        "overall_mean": agg["overall_mean"],
        "per_field": agg["field_accuracy"],
        "n_scored": agg["portfolios_scored"],
    }


def _emit_report(run_dir: Path, history: list[dict], spec_dict: dict, tfl_path: Path) -> Path:
    """Write final report.md to run_dir."""
    report = run_dir / "report.md"
    final_iter = history[-1] if history else {}
    final_score = final_iter.get("score", {}).get("overall_mean", 0.0)
    final_status = "PASS" if final_score >= THRESHOLD else "BELOW THRESHOLD"

    lines = [
        f"# tableau-prep-etl run report",
        "",
        f"**Status**: {final_status}",
        f"**Overall mean accuracy**: {final_score:.3f}",
        f"**Threshold**: {THRESHOLD:.3f}",
        f"**Iterations**: {len(history)}",
        f"**Flow**: `{tfl_path}`",
        "",
        "## Spec",
        "",
        "```json",
        json.dumps(spec_dict, indent=2)[:2000],
        "```",
        "",
        "## Iteration history",
        "",
        "| # | mean | n_scored | rc | notes |",
        "|---|---|---|---|---|",
    ]
    for i, it in enumerate(history, start=1):
        s = it.get("score", {})
        lines.append(
            f"| {i} | {s.get('overall_mean', 0.0):.3f} | "
            f"{s.get('n_scored', 0)} | {it.get('rc', '?')} | "
            f"{it.get('notes', '')} |"
        )

    if final_iter.get("score", {}).get("per_field"):
        lines += ["", "## Per-field accuracy (final iteration)", "",
                  "| field | accuracy |", "|---|---|"]
        per_field = final_iter["score"]["per_field"]
        for f, s in sorted(per_field.items(), key=lambda kv: kv[1]):
            lines.append(f"| `{f}` | {s:.3f} |")

    lines += [
        "",
        "## Outputs",
        "",
        f"- `{run_dir}/outputs/`",
        "",
        "## Next steps",
        "",
        f"- Open `{tfl_path}` in Tableau Prep Builder to inspect / iterate.",
        f"- Or run again headless: `tableau-prep-cli -t {tfl_path}`",
        f"- v2 publishing: see `skill/reference/server_publishing.md`",
    ]
    report.write_text("\n".join(lines))
    return report


def _maybe_scan_internal(spec: Spec, run_dir: Path, top_k: int = 10) -> dict:
    """Phase 1b. Scan the connected Tableau site for INTERNAL published
    data sources matching `spec.request`. Returns a dict the orchestrator
    can surface to the user via AskUserQuestion.

    Mirrors `_maybe_publish` semantics: never silently rewrites the spec.
    Emits candidates and bounces back as needs_user_decision so the
    orchestrator can ask. The user either:
      (a) reruns with --skip-scan to fall through to external sources, or
      (b) edits spec.json to add an internal_published_ds source and reruns.
    """
    try:
        from skill.scripts.server_scan import is_configured, search_datasources
        from skill.scripts.server_creds import discover
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "message": str(e)}
    if not is_configured():
        # Try Keychain / secret-tool / file fallbacks before giving up.
        creds = discover()
        if creds.status != "configured":
            return {"status": "skipped",
                    "reason": "TABLEAU_SERVER_* env vars not set",
                    "credentials": creds.to_dict()}
    try:
        candidates = search_datasources(spec.request, top_k=top_k)
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "message": str(e)}

    out_path = run_dir / "internal_scan.json"
    out_path.write_text(json.dumps({
        "request": spec.request,
        "candidates": candidates,
    }, indent=2))
    return {
        "status": "needs_user_decision" if candidates else "no_matches",
        "scan_path": str(out_path),
        "candidates": candidates,
        "request": spec.request,
    }


def _maybe_write_metadata(spec: Spec, publish_result: dict, run_dir: Path,
                          review: bool = False) -> dict:
    """Phase 7b. For each published_data_source output, generate (and
    optionally apply) DS + column descriptions. Runs after `_maybe_publish`
    so the LUIDs are known.

    `publish_result` is the `result["publish"]` dict; we use it to
    extract LUIDs when present. When publish failed or the output is
    local-only, we still emit the proposal as an audit trail."""
    pd_outputs = [o for o in spec.outputs if o.kind == "published_data_source"]
    if not pd_outputs:
        return {"status": "skipped", "reason": "no published_data_source outputs"}
    try:
        from skill.scripts.metadata_writer import write_for_output
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "message": str(e)}

    # The flow-publish step doesn't carry DS LUIDs (the backgrounder
    # creates the DS at run-time). For Cloud-friendly flows that write
    # the local Hyper as a DS, the LUID is discovered by name in the
    # target project. Fall back to publish_result["datasources"] when
    # available (older shape).
    luids_by_name = {}
    for ds in (publish_result or {}).get("datasources", []) or []:
        if ds.get("name") and ds.get("luid"):
            luids_by_name[ds["name"]] = ds["luid"]
    if not luids_by_name:
        try:
            from tflb_lib import publishing as _pub
            cfg = _pub.config_from_env()
            srv = _pub.sign_in(cfg)
            try:
                project_name = (publish_result or {}).get("project_name") or (
                    spec.server_publish.project if spec.server_publish else ""
                )
                # Resolve the target project's LUID once so we can
                # disambiguate same-named DSes that legitimately exist
                # in sibling projects under different parents (Cloud
                # nested-project layouts, e.g. the Prep Agent demo
                # collection's `01 - Federal Outlays` child project
                # under the `Prep Agent` parent).
                parent_want = ""
                if spec.server_publish:
                    parent_want = (spec.server_publish.parent_project or "").strip()
                target_project_id = ""
                try:
                    from skill.scripts.publish import list_site_projects
                    projects = list_site_projects()
                    parent_id_filter = ""
                    if parent_want:
                        parent_match = next(
                            (p for p in projects
                             if p["id"] == parent_want or p["name"] == parent_want),
                            None,
                        )
                        if parent_match:
                            parent_id_filter = parent_match["id"]
                    for p in projects:
                        if p["name"] != project_name:
                            continue
                        if parent_id_filter and p.get("parent_id") != parent_id_filter:
                            continue
                        target_project_id = p["id"]
                        break
                except Exception:
                    pass

                import tableauserverclient as TSC
                req = TSC.RequestOptions()
                for o in pd_outputs:
                    req.filter.clear_filters()
                    req.filter.add(TSC.Filter(
                        "name", TSC.RequestOptions.Operator.Equals, o.name))
                    if project_name:
                        req.filter.add(TSC.Filter(
                            "projectName", TSC.RequestOptions.Operator.Equals,
                            project_name))
                    for ds in TSC.Pager(srv.datasources, req):
                        # If we resolved a parent-scoped project LUID,
                        # require the DS sit inside it. Skips
                        # same-named DSes living under a different
                        # parent's identically-named child project.
                        if target_project_id and ds.project_id != target_project_id:
                            continue
                        luids_by_name[o.name] = ds.id
                        break
            finally:
                try:
                    srv.auth.sign_out()
                except Exception:
                    pass
        except Exception as e:
            # The bare-except here used to mask 401s on the LUID lookup,
            # which surfaced downstream as "no LUID found, skipping
            # metadata write" — making PAT expiry look like a benign
            # absence of data. Log the real reason so the operator can
            # tell auth from absence. Only TSC's auth/server response
            # exceptions reach this branch; anything else is a bug.
            try:
                import tableauserverclient as TSC
                _auth_classes: tuple = tuple(
                    cls for cls in (
                        getattr(TSC, "ServerResponseError", None),
                        getattr(TSC, "NotSignedInError", None),
                    ) if cls is not None
                )
            except Exception:
                _auth_classes = ()
            if _auth_classes and isinstance(e, _auth_classes):
                # Auth failures must NOT silently degrade — they almost
                # always mean the PAT rotated and downstream metadata
                # writes will hit the same wall. Re-raise so the caller
                # surfaces it on the run summary.
                raise
            # Anything else (network blip, transient TSC parsing error)
            # falls back to the empty-LUID path with a logged note.
            try:
                (run_dir / "metadata_luid_lookup_warning.txt").write_text(
                    f"LUID lookup non-fatal error: {type(e).__name__}: {e}\n"
                )
            except Exception:
                pass

    # Build {column_name: declared_type} from the planned upstream
    # schema so the .tds-roundtrip path can declare datatypes for
    # columns that aren't already in the published .tds. This is a
    # best-effort map - empty when sources don't expose a schema and
    # the writer falls back to `string` for unknowns. Includes
    # transformation-added columns (trend_features / eoc_fire_metrics).
    try:
        from skill.scripts.source_planner import _input_schema_after_casts
        column_types = dict(_input_schema_after_casts(spec))
    except Exception:
        column_types = {}
    # Hard-coded type hints for the canonical transformation-added
    # columns. These match what the templates declare in their
    # `get_output_schema()` updates. Future templates can register
    # their derived columns here as they're added.
    _TRANSFORM_COLUMN_TYPES = {
        # trend_features
        "year": "int", "month": "int", "quarter": "int",
        "year_month": "string", "iso_week": "int",
        "day_of_week_num": "int", "day_of_week_name": "string",
        "is_weekend": "bool", "hour_of_day": "int", "hour_bucket": "string",
        # eoc_fire_metrics
        "days_since_discovery": "decimal", "hours_since_modified": "decimal",
        "staleness_band": "string", "acres_per_day": "decimal",
        "growth_band": "string", "size_class": "string",
        "containment_band": "string", "is_active": "bool",
        "region_key": "string", "incident_summary": "string",
        # embassy_threat_join
        "post_name": "string", "post_country": "string",
        "post_classification": "string", "post_lat": "decimal",
        "post_lon": "decimal", "event_id": "int", "event_date": "string",
        "event_root_code": "string", "event_root_name": "string",
        "event_lat": "decimal", "event_lon": "decimal",
        "distance_miles": "decimal", "severity_score": "int",
        "proximity_score": "int", "recency_score": "int",
        "us_actor_flag": "int", "composite_score": "int",
        "goldstein_scale": "decimal", "num_mentions": "int",
        "source_url": "string", "actor1_country": "string",
        "actor2_country": "string",
        # embassy_risk_summary
        "events_in_window": "int", "max_severity_score": "int",
        "mass_violence_count": "int", "assault_count": "int",
        "fight_count": "int", "threaten_count": "int",
        "protest_count": "int", "coerce_count": "int",
        "weighted_threat_score": "decimal", "risk_band": "string",
        "top_event_type": "string", "last_event_date": "string",
        # ew_fusion
        "emitter_class": "string", "primary_emitter": "string",
        "rf_band": "string", "centre_freq_ghz": "decimal",
        "pri_us": "decimal", "pw_us": "decimal", "erp_dbw": "decimal",
        "mode": "string", "range_nm": "decimal",
        "bearing_deg": "decimal", "aspect_deg": "decimal",
        "rx_dbm": "decimal", "threat_band": "string",
        "fusion_confidence": "decimal", "own_ship_label": "string",
    }
    column_types.update(_TRANSFORM_COLUMN_TYPES)

    per_output: list[dict] = []
    for o in pd_outputs:
        luid = luids_by_name.get(o.name, "")
        # Prefer the actual produced Hyper schema over the upstream
        # input schema — when a transform reshapes the data (joins, new
        # derived columns), the input schema is stale and the LLM ends
        # up describing source columns that aren't in the published DS.
        cols = []
        per_out_types = dict(column_types)
        try:
            from tableauhyperapi import (
                Connection as _HConn, HyperProcess as _HProc,
                Telemetry as _HTel,
            )
            hyper_path = run_dir / "outputs" / f"{o.name}.hyper"
            if hyper_path.exists():
                with _HProc(telemetry=_HTel.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as _hp:
                    with _HConn(endpoint=_hp.endpoint,
                                database=str(hyper_path)) as _conn:
                        # Tableau-produced .hyper has both 'public'
                        # (empty) and 'Extract' schemas; pick the first
                        # schema that actually contains a table.
                        for sch in _conn.catalog.get_schema_names():
                            tables = list(_conn.catalog.get_table_names(sch))
                            if not tables:
                                continue
                            td = _conn.catalog.get_table_definition(tables[0])
                            for c in td.columns:
                                cols.append(c.name.unescaped)
                            break
        except Exception:
            cols = []
        if not cols:
            cols = list(column_types.keys())
        try:
            res = write_for_output(spec, o.name, luid, cols, [], run_dir,
                                   review=review,
                                   column_types=per_out_types)
            per_output.append(res)
        except Exception as e:
            per_output.append({
                "status": "error", "output_name": o.name,
                "type": type(e).__name__, "message": str(e),
            })
    return {
        "status": "needs_user_decision" if review and per_output else "ok",
        "outputs": per_output,
    }


def run(request: str, run_dir: Optional[Path] = None,
        spec_path: Optional[Path] = None,
        skip_cli: bool = False,
        flow_name: Optional[str] = None,
        publish: bool = False,
        auto_create_project: bool = False,
        skip_scan: bool = False,
        review_metadata: bool = False) -> dict:
    """Top-level entry. Returns a dict summary of the run.

    `spec_path` activates no-LLM mode: a pre-built spec.json is loaded
    instead of calling the LLM gateway. Useful when the user has no
    gateway configured or wants to drive the skill from a hand-edited
    spec.

    `skip_cli` skips the bounded prep-cli refinement loop and just
    returns after generating the flow + scripts. Useful for structural
    smoke tests on machines without TabPy / tableau-prep-cli.

    `flow_name` groups runs under `runtime/<flow_name>/<run_id>/` so
    repeated runs of the same flow stay co-located. Inferred from
    `spec_path` filename when not given.
    """
    if run_dir is None:
        if flow_name is None and spec_path is not None:
            flow_name = Path(spec_path).stem
        parent = Path("./runtime") / flow_name if flow_name else Path("./runtime")
        run_dir = parent / _new_run_id()
    run_dir = Path(run_dir).resolve()
    # 0o700: per-run scratch holds spec.json, hyper extracts, and the
    # transient _cli_credentials.json — keep readable only to the
    # operator who launched the run.
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Phase 1: intake (or load pre-built spec)
    if spec_path is not None:
        spec_dict = json.loads(Path(spec_path).read_text())
        spec = _spec_from_dict(spec_dict, request=request or spec_dict.get("request", ""))
        (run_dir / "spec.json").write_text(json.dumps(spec.to_dict(), indent=2))
    else:
        spec = intake(request, run_dir)

    # Phase 1a: credentials gate. If the spec implies any server work
    # (internal_published_ds source, published_data_source output, or
    # --publish), discover Tableau Server creds before going any further.
    # Discovery walks env -> macOS Keychain -> Linux secret-tool -> local
    # config file. When nothing turns up, we bounce back as
    # needs_user_decision with platform-tailored secure-storage
    # suggestions so the orchestrator can guide the user without ever
    # having to handle secrets in the conversation transcript.
    spec_dict_for_check = spec.to_dict()
    needs_creds = False
    try:
        from skill.scripts.server_creds import discover, secrets_in_spec
        needs_creds = secrets_in_spec(spec_dict_for_check) or publish
    except Exception:
        needs_creds = False
    if needs_creds:
        creds = discover()
        if creds.status != "configured":
            return {
                "run_dir": str(run_dir),
                "spec": spec_dict_for_check,
                "credentials": creds.to_dict(),
                "passed": False,
            }

    # Phase 1b: INTERNAL data scan. Before any external source acquisition,
    # check the connected Tableau site for a published DS that already
    # answers the user's request. Re-using a certified DS already on the
    # site is almost always preferable to re-acquiring the upstream feed.
    #
    # Behavior matches the publish picker: never silently rewrites the
    # spec. Emits candidates and bounces back as needs_user_decision so
    # the orchestrator can prompt via AskUserQuestion. The user then:
    #   (a) reruns with --skip-scan to fall through to external sources, or
    #   (b) edits spec.json to add an internal_published_ds source and reruns.
    has_internal = any(s.type == "internal_published_ds" for s in spec.sources)
    if not skip_scan and not has_internal:
        scan_result = _maybe_scan_internal(spec, run_dir)
        # Only block when the scan succeeded with candidates the user
        # should review. "skipped" / "no_matches" / "error" all fall
        # through silently - the user shouldn't need a Tableau site to
        # run this skill.
        if scan_result.get("status") == "needs_user_decision":
            return {
                "run_dir": str(run_dir),
                "spec": spec.to_dict(),
                "internal_scan": scan_result,
                "passed": False,
            }
        if scan_result.get("status") not in (None, "skipped"):
            (run_dir / "internal_scan_result.json").write_text(
                json.dumps(scan_result, indent=2)
            )

    # Phase 4a: PAT-authed download of any internal_published_ds source.
    # Tableau Cloud sites that enforce MFA on every login block prep-cli
    # (its credentials.json schema only accepts username/password — no
    # PAT, no MFA factor). To iterate locally on such sites, download
    # the published DS as a Hyper extract via REST (PAT-authed, no MFA),
    # convert to CSV, and let the planner emit a local-CSV input. At
    # publish time we swap the input back to LoadSqlProxy so the
    # backgrounder uses the user's site session against the live DS.
    download_results: list[dict] = []
    if has_internal:
        try:
            from skill.scripts.extract_downloader import download_published_ds
        except Exception as e:
            return {
                "run_dir": str(run_dir),
                "spec": spec.to_dict(),
                "extract_download": {
                    "status": "error", "type": type(e).__name__, "message": str(e),
                },
                "passed": False,
            }
        inputs_dir = run_dir / "inputs"
        for src in spec.sources:
            if src.type != "internal_published_ds":
                continue
            luid = (src.extra or {}).get("luid", "")
            if not luid:
                continue
            res = download_published_ds(luid, inputs_dir, friendly_name=src.name)
            download_results.append(res.to_dict())
            if res.status == "ok":
                # Mutate the spec source in place so the planner sees a
                # local-CSV input. Preserve the original LUID + project +
                # site + datasource_name in extra so Phase 10 can swap
                # the input shape back to LoadSqlProxy at publish time.
                src.extra = dict(src.extra or {})
                src.extra["_pds_local_csv_path"] = res.csv_path
                src.extra["_pds_local_hyper_path"] = res.hyper_path
                src.extra["_pds_actual_ds_name"] = res.ds_name
                src.extra["_pds_actual_project"] = res.project
                src.extra["_pds_row_count"] = res.row_count
            else:
                # Surface the failure to the orchestrator. Falls back to
                # LoadSqlProxy shape if the download fails - prep-cli will
                # then fail at sign-in (MFA wall) but the .tfl is still
                # publishable, so the publish path remains a valid escape.
                pass
        if download_results:
            (run_dir / "extract_download.json").write_text(
                json.dumps(download_results, indent=2)
            )

    # Phase 2: plan
    plan = plan_sources(spec, run_dir / "outputs")

    # Phase 3: generate flow.
    # local_iteration=True swaps every `published_data_source` output to
    # a local `WriteToHyper` so the flow can run + verify entirely
    # locally with no server auth. Phase 10 swaps it back at publish time.
    # Trigger when EITHER a published-DS source has been downloaded OR
    # the spec has any published_data_source output (which the verify
    # step would otherwise fail on with "not signed in to any Tableau
    # server"). Flows with only local outputs skip this entirely.
    has_downloaded_pds = any(
        (s.extra or {}).get("_pds_local_csv_path") for s in spec.sources
    )
    has_pds_output = any(o.kind == "published_data_source" for o in spec.outputs)
    tfl_basename = _safe_tfl_basename(flow_name)
    tfl_path = generate_flow(spec, plan, run_dir,
                             local_iteration=has_downloaded_pds or has_pds_output,
                             tfl_basename=tfl_basename)

    # Phase 3b: verify the .tfl actually deserializes + runs in tableau-prep-cli.
    # This is the load-bearing test — earlier we shipped flows that passed
    # structural ZIP validation but blew up Maestro's deserializer. CLI is
    # the only ground truth.
    verify_log = run_dir / "logs" / "verify.log"
    verify_log.parent.mkdir(parents=True, exist_ok=True)
    cli_path = Path(TABLEAU_PREP_CLI)
    if not cli_path.exists():
        verify_result = {"status": "skipped", "reason": f"prep-cli not at {cli_path}"}
    else:
        rc = _run_prep_cli(tfl_path, verify_log)
        verify_result = {"status": "pass" if rc == 0 else "fail", "rc": rc,
                          "log": str(verify_log)}
        if rc != 0:
            tail = verify_log.read_text()[-4000:] if verify_log.exists() else ""
            verify_result["log_tail"] = tail

            # Heuristic: TabPy auth failures via prep-cli on local Macs
            # are an environmental issue (CLI doesn't read pythonSupport.json
            # the way the docs say it should in v2026.1). When the failure
            # is purely TabPy auth on a flow that has script nodes, downgrade
            # to a soft-warn instead of hard-fail so server-bound flows can
            # still publish - the server's Analytics Extension config is
            # independent of this Mac's local TabPy auth path.
            tabpy_auth_failure = (
                "BasicAuthConfiguration.getPassword()" in tail
                or "request to TabPy" in tail
            )
            has_script_nodes = any(
                t.kind in ("trend_analysis", "graph_analysis", "pii_redaction",
                          "qa_review", "stats_review", "validate",
                          "eoc_fire_metrics", "ew_fusion",
                          "embassy_threat_join", "embassy_risk_summary")
                or "script" in (t.kind or "").lower()
                for t in spec.transformations
            )
            if tabpy_auth_failure and has_script_nodes:
                verify_result["status"] = "warn"
                verify_result["reason"] = (
                    "prep-cli local TabPy auth failed (known environmental issue; "
                    "v2026.1 CLI doesn't read pythonSupport.json the way docs claim). "
                    "Flow is structurally valid - script-node execution will run server-side "
                    "via the site's Analytics Extension config when published."
                )
            elif not skip_cli:
                # Hard-fail by default for non-TabPy errors. Caller can pass
                # skip_cli=True to collect the flow even when it fails.
                return {
                    "run_dir": str(run_dir),
                    "tfl": str(tfl_path),
                    "verify": verify_result,
                    "spec": spec.to_dict(),
                    "passed": False,
                }

    # Phase 4: synthesize the evaluation rig
    rig = synthesize_eval(spec, run_dir)

    if skip_cli:
        result = {
            "run_dir": str(run_dir),
            "tfl": str(tfl_path),
            "verify": verify_result,
            "skipped_cli": True,
            "spec": spec.to_dict(),
        }
        if publish:
            result["publish"] = _maybe_publish(spec, tfl_path, run_dir,
                                            auto_create_project=auto_create_project)
            # Phase 7b: metadata writer. Only runs after a successful publish.
            if result["publish"].get("status") == "ok":
                result["metadata"] = _maybe_write_metadata(
                    spec, result["publish"], run_dir, review=review_metadata,
                )
        return result

    # Phase 5: bounded refinement loop
    history: list[dict] = []
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    for iteration in range(1, MAX_ITERATIONS + 1):
        log_path = log_dir / f"iter_{iteration:02d}.log"
        rc = _run_prep_cli(tfl_path, log_path)

        # Find primary output Hyper (first one in plan)
        primary_hyper: Optional[Path] = None
        for o in plan.outputs:
            attrs = o.connector_attrs or {}
            hp = attrs.get("hyper_path")
            if hp:
                primary_hyper = Path(hp)
                break

        rows = _read_hyper(primary_hyper) if primary_hyper else []
        score = _score_against_gt(rig.gt_dir, rows) if rows else {
            "overall_mean": 0.0, "per_field": {}, "n_scored": 0, "reason": "no output"
        }
        notes = []
        if rc != 0:
            notes.append(f"prep-cli rc={rc} — see {log_path.name}")
        if not rows:
            notes.append("no output rows")

        history.append({
            "iteration": iteration,
            "rc": rc,
            "score": score,
            "notes": "; ".join(notes),
        })

        # Stop if we hit threshold or it's the last iteration
        if score["overall_mean"] >= THRESHOLD:
            break
        if iteration == MAX_ITERATIONS:
            break

        # v1: refinement is a no-op (just re-run). v2 will ask the LLM
        # to propose a script-template variant for the worst-performing
        # field and swap it in via tflb_lib.rewrite_script_paths.

    # Phase 6: report
    report_path = _emit_report(run_dir, history, spec.to_dict(), tfl_path)

    result: dict = {
        "run_dir": str(run_dir),
        "tfl": str(tfl_path),
        "report": str(report_path),
        "iterations": len(history),
        "final_mean": history[-1]["score"]["overall_mean"] if history else 0.0,
        "passed": history[-1]["score"]["overall_mean"] >= THRESHOLD if history else False,
    }

    # Phase 7 (optional): publish + schedule on Tableau Server / Cloud.
    # Only fires when caller passed --publish AND the spec has a
    # server_publish block. Failures don't roll back the local build —
    # the .tfl is still on disk and the report is already written.
    if publish:
        result["publish"] = _maybe_publish(spec, tfl_path, run_dir,
                                            auto_create_project=auto_create_project)
        # Phase 7a-bis: Cloud-friendly Hyper upload. Cloud backgrounder
        # cannot execute script nodes; the .tfl was published for code-
        # review/schedule visibility but its backgrounder run will fail.
        # Upload the local Hyper extracts produced by prep-cli's verify
        # run as published data sources so analysts have something to
        # connect to immediately. Server (on-prem) sites can run the
        # flow on their own backgrounder; this step is a Cloud-only
        # convenience.
        if result["publish"].get("status") == "ok" and result["publish"].get("is_cloud"):
            result["pds_uploads"] = _upload_hypers_as_published_datasources(
                spec, run_dir, result["publish"],
            )
        # Phase 7b: metadata writer. Only runs after a successful publish.
        # Inject the DS LUIDs from `pds_uploads` into the publish_result
        # so the writer can apply column descriptions without doing its
        # own server-side name lookup (faster + avoids race with Cloud
        # search-index latency right after a fresh upload).
        if result["publish"].get("status") == "ok":
            _enriched_pub = dict(result["publish"])
            _ds_luids = []
            for r in (result.get("pds_uploads", {}) or {}).get("results", []) or []:
                if r.get("status") == "ok" and r.get("luid") and r.get("name"):
                    _ds_luids.append({"name": r["name"], "luid": r["luid"]})
            if _ds_luids:
                _enriched_pub["datasources"] = _ds_luids
            result["metadata"] = _maybe_write_metadata(
                spec, _enriched_pub, run_dir, review=review_metadata,
            )

    return result


def _upload_hypers_as_published_datasources(
    spec, run_dir: Path, publish_result: dict,
) -> dict:
    """Upload local Hyper files (produced by prep-cli's verify run)
    as published data sources. Used for Cloud sites where the
    backgrounder cannot execute the .tfl's script nodes — the analyst-
    facing data has to land on the server somehow.

    Maps each spec.outputs[] of kind == 'published_data_source' to its
    on-disk Hyper at runtime/<flow>/<run>/outputs/<name>.hyper, then
    publishes via TSC into the same project the .tfl landed in. LUIDs
    are preserved on overwrite so downstream dashboards keep working.
    """
    from tflb_lib import publishing
    out: list[dict] = []
    pd_outputs = [o for o in spec.outputs if o.kind == "published_data_source"]
    if not pd_outputs:
        return {"status": "skipped", "reason": "no published_data_source outputs"}
    project_id = publish_result.get("project_id") or ""
    project_name = publish_result.get("project_name") or ""
    if not project_id:
        return {"status": "skipped", "reason": "no project_id in publish_result"}
    outputs_dir = run_dir / "outputs"
    cfg = publishing.config_from_env()
    server = publishing.sign_in(cfg)
    try:
        for o in pd_outputs:
            hyper = outputs_dir / f"{o.name}.hyper"
            if not hyper.exists():
                out.append({
                    "status": "skipped",
                    "output_name": o.name,
                    "reason": f"no Hyper at {hyper}",
                })
                continue
            try:
                ds = publishing.publish_hyper_as_datasource(
                    server,
                    str(hyper),
                    project_id=project_id,
                    datasource_name=o.name,
                    description=o.description or "",
                    overwrite=True,
                )
                out.append({
                    "status": "ok",
                    "output_name": o.name,
                    "luid": ds.id,
                    "name": ds.name,
                    "project_id": project_id,
                    "project_name": project_name,
                    "hyper_size_bytes": hyper.stat().st_size,
                })
            except Exception as e:
                out.append({
                    "status": "error",
                    "output_name": o.name,
                    "type": type(e).__name__,
                    "message": str(e),
                })
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass
    return {
        "status": "ok",
        "project_id": project_id,
        "project_name": project_name,
        "results": out,
    }


def _patch_publish_extract_routing(tfl_path: Path, project_luid: str,
                                   server_url: str,
                                   project_name: str = "") -> None:
    """Prepare the .tfl for publish:

    1. Swap any local-iteration `WriteToHyper` nodes carrying
       `_pds_target_*` markers back into `.v1.PublishExtract` nodes
       (the inverse of generate_flow's `local_iteration=True` substitution).
    2. Set projectLuid + serverUrl on every `.v1.PublishExtract` node so
       backgrounder can route writes to the resolved project.
    """
    import zipfile
    with zipfile.ZipFile(tfl_path) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    flow = json.loads(members["flow"].decode("utf-8"))
    changed = False
    for nid, n in flow.get("nodes", {}).items():
        nt = n.get("nodeType")
        # Step 1: swap-back. Any WriteToHyper carrying _pds_target_*
        # markers was inserted by generate_flow under local_iteration=True
        # to make the flow runnable locally; restore the published_data_source
        # shape before we hand the .tfl to publish_run.
        if nt == ".v1.WriteToHyper" and n.get("_pds_target_datasource_name"):
            target_proj = n.pop("_pds_target_project", "") or project_name
            target_ds = n.pop("_pds_target_datasource_name", "") or n.get("name", "")
            target_desc = n.pop("_pds_target_description", "") or n.get("description") or ""
            n.pop("hyperOutputFile", None)
            n.pop("tdsOutput", None)
            n["nodeType"] = ".v1.PublishExtract"
            n["projectName"] = target_proj
            n["projectLuid"] = project_luid
            n["datasourceName"] = target_ds
            n["datasourceDescription"] = target_desc
            n["serverUrl"] = server_url
            changed = True
            continue
        if nt == ".v1.PublishExtract":
            if project_luid and not n.get("projectLuid"):
                n["projectLuid"] = project_luid
                changed = True
            if server_url and not n.get("serverUrl"):
                n["serverUrl"] = server_url
                changed = True
    if not changed:
        return
    members["flow"] = json.dumps(flow, indent=2).encode("utf-8")
    tmp = tfl_path.with_suffix(".tfl.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    tmp.replace(tfl_path)


def _maybe_publish(spec: Spec, tfl_path: Path, run_dir: Path,
                   auto_create_project: bool = False) -> dict:
    """Run the publish + schedule step. Failures are reported in the
    result dict; the local build is preserved either way.

    Project picker contract: before attempting upload, this fetches the
    site project list. If `spec.server_publish.project` doesn't match
    an existing project, returns
        {"status": "needs_user_decision",
         "want": "<configured name>",
         "candidates": [{"id", "name", "description"}, ...],
         "near_matches": [...],   # case-insensitive substring matches
         "tfl": <tfl path>}
    so the caller (Claude / the orchestrator shell) can prompt the user
    via AskUserQuestion: pick an existing project, type a different
    name, or opt into create-new. The picker NEVER auto-uploads to a
    project the user didn't explicitly approve — local build stays
    intact and re-publish is a single retry away.

    Pass `auto_create_project=True` (e.g. CI / batch mode) to
    pre-authorize creating a project with the spec's configured name
    when no match exists; without it, missing projects always bounce
    back as needs_user_decision.
    """
    if spec.server_publish is None:
        return {"status": "skipped",
                "reason": "no server_publish block in spec"}
    try:
        from skill.scripts.publish import (
            publish_run, list_site_projects, create_site_project,
        )
        from dataclasses import asdict

        want = spec.server_publish.project or ""
        parent_want = (spec.server_publish.parent_project or "").strip()
        projects = list_site_projects()
        # When a parent is specified, scope the existence/disambiguation
        # check to children of that parent. Same name can appear under
        # multiple parents on a busy site.
        parent_id_filter = ""
        if parent_want:
            parent_match = next(
                (p for p in projects
                 if p["id"] == parent_want or p["name"] == parent_want),
                None,
            )
            if not parent_match:
                return {
                    "status": "error",
                    "type": "ParentProjectNotFound",
                    "message": (
                        f"parent_project {parent_want!r} not found on this site. "
                        "Create it first or correct the spec."
                    ),
                }
            parent_id_filter = parent_match["id"]
        scoped = [p for p in projects
                  if not parent_id_filter or p.get("parent_id") == parent_id_filter]
        names = {p["name"]: p for p in scoped}
        if want and want not in names:
            wl = want.lower()
            near = [p for p in scoped if wl and wl in (p["name"] or "").lower()]
            if not auto_create_project:
                return {
                    "status": "needs_user_decision",
                    "reason": (
                        f"Project {want!r} doesn't exist on this site"
                        + (f" under parent {parent_want!r}" if parent_want else "")
                        + ". Pick an existing project, type a different "
                        "name, or rerun with --auto-create-project to "
                        "create it."
                    ),
                    "want": want,
                    "parent_want": parent_want,
                    "candidates": scoped,
                    "near_matches": near,
                    "tfl": str(tfl_path),
                }
            new = create_site_project(
                want,
                description=f"Auto-created by tableau-prep-etl skill for {spec.server_publish.flow_name or Path(tfl_path).stem!r}.",
                parent_name_or_id=parent_want,
            )
            spec.server_publish.project = new["name"]
            # Re-fetch so the LUID-patch below sees the freshly-created project.
            projects = list_site_projects()
            scoped = [p for p in projects
                      if not parent_id_filter or p.get("parent_id") == parent_id_filter]
            names = {p["name"]: p for p in scoped}

        # Patch any .v1.PublishExtract nodes in the .tfl with the
        # resolved project LUID + serverUrl. Without this, backgrounder
        # rejects the run task with "project not found" because the
        # LUID is the load-bearing routing field on Cloud (project
        # names are non-unique site-wide).
        target = names.get(spec.server_publish.project) or {}
        proj_luid = target.get("id") or ""
        from tflb_lib.publishing import config_from_env
        try:
            cfg = config_from_env()
            server_url = cfg.url or ""
        except Exception:
            server_url = ""
        if proj_luid:
            _patch_publish_extract_routing(tfl_path, proj_luid, server_url,
                                            project_name=spec.server_publish.project)

        pr = publish_run(spec, tfl_path, run_dir=run_dir)
        return {"status": "ok", **asdict(pr)}
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "message": str(e)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("request", nargs="?", default="",
                    help="ETL request (natural language). Optional when --spec is given.")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--spec", default=None,
                    help="Path to a pre-built spec.json. Skips the LLM intake step.")
    ap.add_argument("--skip-cli", action="store_true",
                    help="Skip the tableau-prep-cli refinement loop. Generate .tfl + scripts only.")
    ap.add_argument("--flow-name", default=None,
                    help="Group runs under runtime/<flow_name>/. Defaults to the spec filename stem.")
    ap.add_argument("--publish", action="store_true",
                    help="After build, publish the .tfl to Tableau Server/Cloud and "
                         "schedule it per spec.server_publish. Requires "
                         "TABLEAU_SERVER_{URL,PAT_NAME,PAT_SECRET,SITE} env vars. "
                         "Default is local-only — server upload only happens when "
                         "this flag is explicitly passed.")
    ap.add_argument("--auto-create-project", action="store_true",
                    help="Pre-authorize creating the spec.server_publish.project "
                         "if it doesn't exist on the site. Without this, missing "
                         "projects bounce back as needs_user_decision so the user "
                         "can pick from existing projects or approve creation.")
    ap.add_argument("--skip-scan", action="store_true",
                    help="Bypass the Phase 1b INTERNAL data scan and fall through "
                         "straight to external source acquisition. Use when the spec "
                         "already specifies the source you want.")
    ap.add_argument("--review-metadata", action="store_true",
                    help="Stop the Phase 11 metadata writer after generating proposal "
                         "JSON; surface to the user before applying. Default is "
                         "auto-apply. Proposal is always saved as audit trail either way.")
    args = ap.parse_args()
    if not args.request and not args.spec:
        ap.error("must provide either a request string or --spec path/to/spec.json")
    try:
        result = run(
            args.request,
            run_dir=Path(args.run_dir) if args.run_dir else None,
            spec_path=Path(args.spec) if args.spec else None,
            skip_cli=args.skip_cli,
            flow_name=args.flow_name,
            publish=args.publish,
            auto_create_project=args.auto_create_project,
            skip_scan=args.skip_scan,
            review_metadata=args.review_metadata,
        )
        print(json.dumps(result, indent=2))
    except IntakeIncomplete as e:
        print(f"INTAKE INCOMPLETE: {e}", file=sys.stderr)
        for q in e.questions:
            print(f"  - {q}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
