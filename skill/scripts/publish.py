"""
Publish a built .tfl to Tableau Server / Cloud and schedule its refresh.

Reads auth + URL/site from env vars (never from disk). Reads project +
cadence from the spec's `server_publish` block.

Public entry: `publish_run(spec, tfl_path) -> PublishResult`.

Usage from run_loop:
    --publish              run publish step after a successful build
    --publish-only         skip the build, publish an existing .tfl

Standalone CLI:
    python3 -m skill.scripts.publish <spec.json> <flow.tfl>
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from skill.scripts.lib import _REPO_ROOT  # noqa: F401
from tflb_lib import publishing
from skill.scripts.intake import ServerPublish, Spec


def _scheduled_spec(sp: ServerPublish) -> publishing.ScheduleSpec:
    return publishing.ScheduleSpec(
        cadence=sp.cadence,
        hour=sp.hour_utc,
        minute=sp.minute_utc,
        weekday=sp.weekday,
        day_of_month=sp.day_of_month,
        name_hint=sp.schedule_name_hint or None,
        balance_tolerance_hours=sp.balance_tolerance_hours,
    )


def publish_run(spec: Spec, tfl_path: Path,
                run_dir: Optional[Path] = None) -> publishing.PublishResult:
    """Sign in, publish the .tfl, schedule it. Returns the publish
    result; caller is responsible for printing/persisting."""
    if spec.server_publish is None:
        raise RuntimeError(
            "Spec has no `server_publish` block. Either set deployment="
            "'tableau_server' and a server_publish dict in spec.json, or "
            "drop --publish from the run."
        )
    sp = spec.server_publish
    cfg = publishing.config_from_env()

    server = publishing.sign_in(cfg)
    try:
        project = publishing.find_project(server, sp.project)
        flow_name = sp.flow_name or Path(tfl_path).stem
        flow = publishing.publish_flow(
            server, str(tfl_path), project.id,
            flow_name=flow_name, overwrite=sp.overwrite,
        )
        result = publishing.create_or_assign_schedule(
            server, flow, project.name, _scheduled_spec(sp),
        )
        warnings = _check_runtime_portability(tfl_path)
        if run_dir is not None:
            payload = asdict(result)
            if warnings:
                payload["warnings"] = warnings
            (run_dir / "publish.json").write_text(
                json.dumps(payload, indent=2, default=str)
            )
        return result
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass


def _check_runtime_portability(tfl_path: Path) -> list[str]:
    """Inspect the .tfl for inputs/scripts/outputs that won't resolve on
    Tableau Cloud's backgrounder. Returns a list of human-readable
    warnings — empty if the flow is fully portable.

    Cloud's backgrounder runs in a sandbox that:
      - cannot reach local file paths (LoadExcel/LoadCsv pointing at
        /Users/... or /tmp/...)
      - has no TabPy unless Tableau Bridge is configured to a remote
        host the site can reach
      - cannot write Hyper outputs to local disk paths — outputs must
        be `published_data_source` to land somewhere queryable
    """
    import zipfile, json as _json
    out: list[str] = []
    try:
        with zipfile.ZipFile(tfl_path) as zf:
            with zf.open("flow") as fh:
                doc = _json.load(fh)
    except Exception as e:
        return [f"Could not inspect .tfl for portability: {e}"]

    nodes = doc.get("nodes", {})
    for nid, n in nodes.items():
        nt = n.get("nodeType", "")
        if nt == ".v1.WriteToHyper":
            p = n.get("hyperOutputFile") or ""
            if p.startswith("/") or "\\" in p:
                out.append(
                    f"Output node {n.get('name', nid)!r} writes to a local "
                    f"path ({p}) — Cloud backgrounder cannot reach it. "
                    "Switch this output to a published_data_source kind, "
                    "or run the flow locally only."
                )
        if nt == ".v2019_2_2.SuperExtensibilityNode":
            params = (n.get("actionNode") or {}).get("setupParameters") or {}
            sp_path = params.get("scriptFilePath") or ""
            if sp_path.startswith("/") or "\\" in sp_path:
                out.append(
                    f"Script node {n.get('name', nid)!r} references a local "
                    f"Python script ({sp_path}) — Cloud's TabPy bridge cannot "
                    "load it. Either disable the schedule and run locally, "
                    "or host the script on a TabPy server reachable from Cloud."
                )
        if nt in (".v1.LoadExcel", ".v1.LoadCsv"):
            p = n.get("inputFilePath") or ""
            if p.startswith("/") or "\\" in p:
                out.append(
                    f"Input node {n.get('name', nid)!r} reads a local file "
                    f"({p}) — Cloud backgrounder cannot reach it without "
                    "Tableau Bridge."
                )
    return out


def _load_spec(spec_path: Path) -> Spec:
    """Hydrate Spec from JSON with proper ServerPublish nesting.
    Mirrors run_loop._spec_from_dict — keeps publish.py runnable on
    its own without importing run_loop."""
    from skill.scripts.intake import Output, Source, Transformation
    d = json.loads(spec_path.read_text())
    sp = d.get("server_publish")
    server_publish = ServerPublish(**sp) if isinstance(sp, dict) else None
    return Spec(
        request=d.get("request", ""),
        sources=[Source(**s) for s in d.get("sources", [])],
        transformations=[Transformation(**t) for t in d.get("transformations", [])],
        outputs=[Output(**o) for o in d.get("outputs", [])],
        qa_tier=d.get("qa_tier", "deterministic"),
        eval_strategy=d.get("eval_strategy", "sample_validation"),
        deployment=d.get("deployment", "local"),
        refresh_cadence=d.get("refresh_cadence", "once"),
        parameterize_query=bool(d.get("parameterize_query", False)),
        server_publish=server_publish,
        confidence=float(d.get("confidence", 1.0)),
        open_questions=list(d.get("open_questions", [])),
    )


def list_site_projects() -> list[dict]:
    """Sign in and return a JSON-friendly list of projects on the site.

    Used by the orchestrator's publish picker to surface candidates to
    the user via AskUserQuestion before any upload is attempted. Output
    shape: [{"id": ..., "name": ..., "description": ...}, ...] sorted
    by name (case-insensitive).
    """
    cfg = publishing.config_from_env()
    server = publishing.sign_in(cfg)
    try:
        projects = publishing.list_projects(server)
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass
    out = [
        {"id": p.id, "name": p.name, "description": p.description or ""}
        for p in projects
    ]
    out.sort(key=lambda p: (p["name"] or "").lower())
    return out


def create_site_project(name: str, description: str = "") -> dict:
    """Sign in and create a top-level project. Returns the new project's
    id+name. Used by the publish picker when the user opts to land the
    flow in a fresh bucket rather than picking an existing one."""
    cfg = publishing.config_from_env()
    server = publishing.sign_in(cfg)
    try:
        proj = publishing.create_project(server, name, description=description)
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass
    return {"id": proj.id, "name": proj.name, "description": proj.description or ""}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", help="Path to spec.json (must include server_publish block).")
    ap.add_argument("tfl", nargs="?", help="Path to the built .tfl to publish.")
    ap.add_argument("--run-dir", default=None,
                    help="Where to write publish.json record. Defaults to .tfl's parent.")
    ap.add_argument("--list-projects", action="store_true",
                    help="Sign in and print site projects as JSON, then exit.")
    ap.add_argument("--create-project", default=None,
                    help="Create a project with this name and exit (use with --create-project-description).")
    ap.add_argument("--create-project-description", default="",
                    help="Description for the project being created.")
    args = ap.parse_args()
    if args.list_projects:
        print(json.dumps(list_site_projects(), indent=2))
        sys.exit(0)
    if args.create_project:
        print(json.dumps(create_site_project(args.create_project,
                                             args.create_project_description), indent=2))
        sys.exit(0)
    if not args.spec or not args.tfl:
        ap.error("spec and tfl are required unless --list-projects/--create-project is used")
    spec = _load_spec(Path(args.spec))
    tfl = Path(args.tfl)
    run_dir = Path(args.run_dir) if args.run_dir else tfl.parent
    result = publish_run(spec, tfl, run_dir=run_dir)
    print(json.dumps(asdict(result), indent=2, default=str))
