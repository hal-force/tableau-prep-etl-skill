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
    IntakeIncomplete, Output, Source, Spec, Transformation, intake,
)
from skill.scripts.source_planner import plan_sources
from skill.scripts.generate_flow import generate_flow
from skill.scripts.synthesize_eval import synthesize_eval


def _spec_from_dict(spec_dict: dict, request: str = "") -> Spec:
    """Hydrate a Spec from a JSON dict (no-LLM mode)."""
    return Spec(
        request=spec_dict.get("request") or request,
        sources=[Source(**s) for s in spec_dict.get("sources", [])],
        transformations=[Transformation(**t) for t in spec_dict.get("transformations", [])],
        outputs=[Output(**o) for o in spec_dict.get("outputs", [])],
        qa_tier=spec_dict.get("qa_tier", "deterministic"),
        eval_strategy=spec_dict.get("eval_strategy", "sample_validation"),
        deployment=spec_dict.get("deployment", "local"),
        refresh_cadence=spec_dict.get("refresh_cadence", "once"),
        parameterize_query=bool(spec_dict.get("parameterize_query", False)),
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


def _run_prep_cli(tfl: Path, log_path: Path, timeout_s: int = 1800) -> int:
    """Invoke tableau-prep-cli, capturing stdout/stderr to log_path.
    Returns the CLI exit code."""
    cli = Path(TABLEAU_PREP_CLI)
    if not cli.exists():
        raise RuntimeError(f"tableau-prep-cli not found at {cli}")
    if not tfl.exists():
        raise RuntimeError(f"flow file not found: {tfl}")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as logf:
        logf.write(f"# tableau-prep-cli run at {time.ctime()}\n")
        logf.write(f"# CLI: {cli}\n")
        logf.write(f"# TFL: {tfl}\n\n")
        logf.flush()
        proc = subprocess.Popen(
            [str(cli), "-t", str(tfl)],
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        try:
            return proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            return -1


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


def run(request: str, run_dir: Optional[Path] = None,
        spec_path: Optional[Path] = None,
        skip_cli: bool = False,
        flow_name: Optional[str] = None) -> dict:
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
    run_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: intake (or load pre-built spec)
    if spec_path is not None:
        spec_dict = json.loads(Path(spec_path).read_text())
        spec = _spec_from_dict(spec_dict, request=request or spec_dict.get("request", ""))
        (run_dir / "spec.json").write_text(json.dumps(spec.to_dict(), indent=2))
    else:
        spec = intake(request, run_dir)

    # Phase 2: plan
    plan = plan_sources(spec, run_dir / "outputs")

    # Phase 3: generate flow
    tfl_path = generate_flow(spec, plan, run_dir)

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
            if not skip_cli:
                # Hard-fail by default. Caller can pass skip_cli=True to
                # collect the flow even when it fails (useful when iterating
                # with diagnostic output already in hand).
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
        return {
            "run_dir": str(run_dir),
            "tfl": str(tfl_path),
            "verify": verify_result,
            "skipped_cli": True,
            "spec": spec.to_dict(),
        }

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

    return {
        "run_dir": str(run_dir),
        "tfl": str(tfl_path),
        "report": str(report_path),
        "iterations": len(history),
        "final_mean": history[-1]["score"]["overall_mean"] if history else 0.0,
        "passed": history[-1]["score"]["overall_mean"] >= THRESHOLD if history else False,
    }


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
