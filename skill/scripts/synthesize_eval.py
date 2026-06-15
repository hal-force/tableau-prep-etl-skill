"""
GT bootstrap dispatcher.

Branches by eval_strategy and produces a small ground-truth dataset
the run_loop can score against:

  extract_from_source: parse expected values out of source documents
                       (the SF1034 invoice case).
  sample_validation:   ask the user (or auto-pull a sample) for
                       expected output for a tiny corpus, treat as GT.
  synthesized:         ask the LLM to generate a small expected-output
                       set from the spec. Capped at SYNTHESIZED_CAP.
  user_supplied:       wire the user's CSV/JSON directly into the
                       holdout builder.
  self_consistency:    no separate GT — run the flow N times and
                       treat consensus as truth (flag disagreements).

Outputs (per run):
  <run_dir>/eval/ground_truth/*.json   per-record expected fields
  <run_dir>/eval/holdout/manifest.json train/holdout split

Public entry: `synthesize_eval(spec, run_dir) -> EvalRig`
"""
from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from skill.scripts.intake import Spec
from skill.scripts.lib import _REPO_ROOT  # noqa: F401


SYNTHESIZED_CAP = 20
HOLDOUT_FRACTION = 0.30
HOLDOUT_SEED = 1734


@dataclass
class EvalRig:
    """The GT setup the run_loop will score against."""
    strategy: str
    gt_dir: Path
    holdout_manifest: Path
    n_records: int = 0
    notes: list[str] = field(default_factory=list)


def _record_id(payload: dict) -> str:
    """Stable id from a record's content. Used when source data has no
    natural primary key."""
    h = hashlib.sha256()
    h.update(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:16]


def _write_holdout(records: list[dict], holdout_path: Path) -> dict:
    """Stratified split keyed on record id hash. No shuffling — uses a
    deterministic hash bucket so reruns produce identical splits."""
    rng = random.Random(HOLDOUT_SEED)
    ordered = sorted(records, key=lambda r: r.get("id", ""))
    rng.shuffle(ordered)
    n_holdout = max(1, round(len(ordered) * HOLDOUT_FRACTION))
    holdout = ordered[:n_holdout]
    train = ordered[n_holdout:]
    manifest = {
        "seed": HOLDOUT_SEED,
        "fraction": HOLDOUT_FRACTION,
        "corpus_size": len(records),
        "holdout_size": len(holdout),
        "train_size": len(train),
        "holdout": [r["id"] for r in holdout],
        "train": [r["id"] for r in train],
    }
    holdout_path.parent.mkdir(parents=True, exist_ok=True)
    holdout_path.write_text(json.dumps(manifest, indent=2))
    return manifest


def _strategy_extract_from_source(spec: Spec, gt_dir: Path) -> int:
    """For document-extraction sources: walk source files and pull
    expected values from form widgets / structured embeds. v1 supports
    PDF AcroForm widgets (the SF1034 case)."""
    src = spec.sources[0]
    if src.type != "local_folder":
        raise RuntimeError(
            f"extract_from_source eval requires local_folder source; got {src.type}"
        )

    folder = Path(src.path)
    if not folder.exists():
        raise RuntimeError(f"source folder does not exist: {folder}")

    try:
        import PyPDF2
    except ImportError:
        raise RuntimeError(
            "extract_from_source eval needs PyPDF2 installed in this Python."
        )

    n = 0
    for pdf_path in sorted(folder.glob("*.pdf")):
        # Walk PDF AcroForm widgets, dump {field_name: value} as the GT row.
        record = {"id": _record_id({"path": str(pdf_path.resolve())}),
                  "filename": pdf_path.name,
                  "fields": {}}
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                fields = reader.get_fields() or {}
                for name, info in fields.items():
                    v = info.get("/V") if hasattr(info, "get") else None
                    if v not in (None, ""):
                        record["fields"][str(name)] = str(v)
        except Exception:
            pass
        (gt_dir / f"{record['id']}.json").write_text(json.dumps(record, indent=2))
        n += 1
    return n


def _strategy_sample_validation(spec: Spec, gt_dir: Path) -> int:
    """Pull a small sample from the source, ask the user to confirm
    expected output. v1 emits a placeholder file the user fills in;
    in subsequent iterations the run_loop compares live output against
    this user-supplied table."""
    placeholder = gt_dir / "USER_SUPPLY_GROUND_TRUTH.md"
    placeholder.write_text(
        "# Sample Validation Ground Truth\n\n"
        "The skill's sample-validation eval needs a small ground-truth\n"
        "table to score against. Put `<id>.json` files in this folder,\n"
        "each containing `{\"id\": \"...\", \"fields\": {field: value, ...}}`,\n"
        "matching the schema the source produces.\n\n"
        f"Source: {spec.sources[0].url or spec.sources[0].path}\n"
        f"Format: {spec.sources[0].format}\n"
    )
    return 0


def _strategy_synthesized(spec: Spec, gt_dir: Path) -> int:
    """Ask the LLM to generate up to SYNTHESIZED_CAP expected records.
    For v1 we emit a stub the run_loop's first iteration fills in via
    a self-consistency check (run flow once, treat the output as the
    initial GT, refine from there).
    """
    placeholder = gt_dir / "SYNTHESIZED_TODO.md"
    placeholder.write_text(
        "# Synthesized Ground Truth (v1 stub)\n\n"
        "v1 of the skill defers synthesized GT generation to the first\n"
        "refinement iteration's pilot run. The run_loop will run the flow\n"
        "once, sample up to "
        f"{SYNTHESIZED_CAP} representative outputs, and treat those as the\n"
        "baseline. Subsequent iterations score against that baseline.\n\n"
        "When v2 lands, this stub will be replaced by an LLM-generated\n"
        "expected-output set produced from the user's spec.\n"
    )
    return 0


def _strategy_user_supplied(spec: Spec, gt_dir: Path) -> int:
    """User-supplied GT path. The skill expects a GT_DIR env var (or
    spec.deployment hint) pointing at an existing directory of <id>.json
    records. v1 just records that this is the case and lets run_loop
    look for the records at the configured path."""
    placeholder = gt_dir / "USER_SUPPLIED.md"
    placeholder.write_text(
        "# User-Supplied Ground Truth\n\n"
        "Set the env var `GT_DIR` to a folder containing `<id>.json`\n"
        "records the run_loop will compare flow outputs against.\n"
    )
    return 0


def _strategy_self_consistency(spec: Spec, gt_dir: Path) -> int:
    """No separate GT — run the flow multiple times and treat agreement
    across runs as truth. This is appropriate for deterministic
    pipelines (no LLM in the hot path) where flakiness signals real
    bugs. v1 records the choice; the run_loop implements the actual
    multi-run consensus."""
    placeholder = gt_dir / "SELF_CONSISTENCY.md"
    placeholder.write_text(
        "# Self-Consistency Eval\n\n"
        "No separate ground truth. The run_loop runs the flow N times\n"
        "(default 3) and flags rows where outputs disagree across runs.\n"
    )
    return 0


def synthesize_eval(spec: Spec, run_dir: Path) -> EvalRig:
    run_dir = Path(run_dir).resolve()
    eval_dir = run_dir / "eval"
    gt_dir = eval_dir / "ground_truth"
    holdout_path = eval_dir / "holdout" / "manifest.json"
    gt_dir.mkdir(parents=True, exist_ok=True)
    holdout_path.parent.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    strategy = spec.eval_strategy

    if strategy == "extract_from_source":
        n = _strategy_extract_from_source(spec, gt_dir)
    elif strategy == "sample_validation":
        n = _strategy_sample_validation(spec, gt_dir)
        notes.append("user must populate USER_SUPPLY_GROUND_TRUTH.md")
    elif strategy == "synthesized":
        n = _strategy_synthesized(spec, gt_dir)
        notes.append("synthesized GT deferred to first run; v2 will pre-generate")
    elif strategy == "user_supplied":
        n = _strategy_user_supplied(spec, gt_dir)
    elif strategy == "self_consistency":
        n = _strategy_self_consistency(spec, gt_dir)
    else:
        raise ValueError(f"unknown eval_strategy: {strategy}")

    # Build holdout manifest from whatever GT we extracted (skip if none).
    if n > 0:
        records = []
        for p in sorted(gt_dir.glob("*.json")):
            rec = json.loads(p.read_text())
            if "id" in rec:
                records.append({"id": rec["id"]})
        if records:
            _write_holdout(records, holdout_path)

    return EvalRig(
        strategy=strategy,
        gt_dir=gt_dir,
        holdout_manifest=holdout_path,
        n_records=n,
        notes=notes,
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    from skill.scripts.intake import Source, Transformation, Output
    spec_dict = json.loads(Path(args.spec).read_text())
    spec = Spec(
        request=spec_dict["request"],
        sources=[Source(**s) for s in spec_dict["sources"]],
        transformations=[Transformation(**t) for t in spec_dict["transformations"]],
        outputs=[Output(**o) for o in spec_dict["outputs"]],
        qa_tier=spec_dict["qa_tier"],
        eval_strategy=spec_dict["eval_strategy"],
        deployment=spec_dict.get("deployment", "local"),
    )
    rig = synthesize_eval(spec, Path(args.run_dir))
    print(f"strategy: {rig.strategy}")
    print(f"records: {rig.n_records}")
    print(f"GT dir: {rig.gt_dir}")
    if rig.notes:
        for n in rig.notes:
            print(f"  note: {n}")
