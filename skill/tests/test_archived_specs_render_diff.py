"""
Render-diff harness across every archived spec in `flows/*/v*/spec.json`.

Purpose: unblock template-body refactors (e.g. extracting shared HTTP
helpers from api_caller / acled_caller / pki_connector / qa_reviewer
into a common include) by making it cheap to prove a change is
render-neutral for every real production spec.

How it works:

- Walk every `flows/*/v*/spec.json` in the repo.
- Hydrate each into a Spec via `run_loop._spec_from_dict` (same code
  path production takes when reading an archive, so schema drift shows
  up here first).
- Plan sources for it, then render every referenced script template to
  a per-spec temp scripts_dir.
- SHA-256 the rendered file bytes and collect a `{spec_name: {script_name: hash}}`
  dict, plus a top-level hash of every template file the harness saw.

The test does one of two things depending on `UPDATE_RENDER_HASHES`:

- Not set: compare against `goldens/rendered_scripts_hashes.json`.
  A drift is a hard failure. Diff-friendly output points at which
  spec + which script hash changed.

- Set to `1`: rewrite the goldens file. Commit the new file only after
  eyeballing that every changed hash matches an intended change.

Refactor workflow (the P2.12 use case):

    # 1. Snapshot current renders (once, after this test lands).
    UPDATE_RENDER_HASHES=1 pytest skill/tests/test_archived_specs_render_diff.py

    # 2. Do the template refactor (extract helpers to templates/lib/http.py.j2).

    # 3. Verify: no test failures = byte-identical renders for every spec.
    pytest skill/tests/test_archived_specs_render_diff.py

Hermetic guarantees:

- `TPE_HOST_APPROVAL=trust-all` bypasses the interactive host-approval
  gate that `_spec_from_dict` runs on load.
- `TABLEAU_PREP_ETL_CONNECTOR_CACHE` points at a tmp dir so the
  connector-registry merge is deterministic — no leakage of the
  developer's ~/.tableau-prep-etl cache defaults.
- outputs_dir passed to plan_sources is fixed to a synthetic string so
  the `hyper_path`/`csv_path` in plan_outputs is deterministic. These
  never reach the rendered scripts (they land in the .tfl only), but
  the fixed value keeps intent explicit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

import pytest

from skill.scripts import connector_registry
from skill.scripts.generate_flow import _render_templates
from skill.scripts.run_loop import _spec_from_dict
from skill.scripts.source_planner import plan_sources


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FLOWS_DIR = _REPO_ROOT / "flows"
_TEMPLATES_DIR = _REPO_ROOT / "skill" / "templates"
_GOLDEN_PATH = Path(__file__).parent / "goldens" / "rendered_scripts_hashes.json"


def _iter_archived_specs() -> Iterable[Path]:
    """Every `flows/<flow>/v<N>/spec.json` on disk, sorted."""
    if not _FLOWS_DIR.exists():
        return []
    return sorted(_FLOWS_DIR.glob("*/v*/spec.json"))


def _spec_id(spec_path: Path) -> str:
    """Stable identifier `<flow-name>/<version>` from the spec path."""
    return f"{spec_path.parent.parent.name}/{spec_path.parent.name}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_templates() -> dict[str, str]:
    """SHA-256 every .j2 file under templates/. If any template body
    changes the top-level hash dict changes, which makes the source of
    a render drift trivially bisectable."""
    out: dict[str, str] = {}
    for p in sorted(_TEMPLATES_DIR.rglob("*.j2")):
        rel = str(p.relative_to(_TEMPLATES_DIR))
        out[rel] = _sha256(p.read_bytes())
    return out


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch, tmp_path):
    """Isolate every render from developer state."""
    monkeypatch.setenv("TPE_HOST_APPROVAL", "trust-all")
    cache = tmp_path / "connector-cache"
    monkeypatch.setenv("TABLEAU_PREP_ETL_CONNECTOR_CACHE", str(cache))
    # connector_registry caches CONNECTORS_DIR at import time; rebind
    # via monkeypatch so this run sees the tmp dir.
    monkeypatch.setattr(connector_registry, "CONNECTORS_DIR", cache)
    monkeypatch.setattr(connector_registry, "INDEX_FILE", cache / "index.json")


def _render_spec_hashes(spec_path: Path, scripts_dir: Path) -> dict[str, str]:
    """Load one archived spec, plan + render, return {script_name: sha256}.

    Failure modes are turned into per-spec pytest.fail(...) — a bad
    archive should surface the file that's wrong, not stop the whole
    sweep."""
    spec_dict = json.loads(spec_path.read_text())
    spec = _spec_from_dict(spec_dict, request=spec_dict.get("request", ""))
    plan = plan_sources(spec, outputs_dir=Path("/tmp/render-diff-outputs"))
    _render_templates(plan, scripts_dir, _TEMPLATES_DIR, sources=spec.sources)

    hashes: dict[str, str] = {}
    for p in sorted(scripts_dir.iterdir()):
        if not p.is_file():
            continue
        hashes[p.name] = _sha256(p.read_bytes())
    return hashes


def _collect_all_hashes(tmp_root: Path) -> dict:
    specs = list(_iter_archived_specs())
    per_spec: dict[str, dict[str, str]] = {}
    for sp in specs:
        sid = _spec_id(sp)
        scripts_dir = tmp_root / sid.replace("/", "__") / "scripts"
        try:
            per_spec[sid] = _render_spec_hashes(sp, scripts_dir)
        except Exception as e:
            # Preserve the spec that failed and re-raise with context.
            raise AssertionError(
                f"render failed for archived spec {sid} ({sp}): "
                f"{type(e).__name__}: {e}"
            ) from e
    return {
        "templates": _hash_templates(),
        "specs": per_spec,
    }


def test_archived_specs_render_matches_golden(tmp_path):
    """Byte-for-byte render check across every `flows/*/v*/spec.json`.

    A failing assertion means one of:
      1. A template body changed and rendered output for at least one
         archived spec changed with it. Intended template refactors
         must rerun with UPDATE_RENDER_HASHES=1 to bless the new
         outputs.
      2. An archived spec is malformed (schema drift). The AssertionError
         re-raised from _collect_all_hashes points at the offending file.
    """
    if not list(_iter_archived_specs()):
        pytest.skip("no archived flows/*/v*/spec.json found")

    current = _collect_all_hashes(tmp_path)

    if os.environ.get("UPDATE_RENDER_HASHES") == "1":
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n"
        )
        return

    if not _GOLDEN_PATH.exists():
        pytest.skip(
            f"no golden at {_GOLDEN_PATH}. Bless with "
            "UPDATE_RENDER_HASHES=1 pytest skill/tests/test_archived_specs_render_diff.py"
        )

    expected = json.loads(_GOLDEN_PATH.read_text())

    # Report per-spec drift so a refactor diff is readable, not a
    # 200-line dict dump.
    drifted: list[str] = []
    for sid, cur_hashes in current["specs"].items():
        exp_hashes = expected["specs"].get(sid)
        if exp_hashes is None:
            drifted.append(f"  + new spec (no golden entry): {sid}")
            continue
        for name, h in cur_hashes.items():
            eh = exp_hashes.get(name)
            if eh is None:
                drifted.append(f"  + new script {sid} :: {name}")
            elif eh != h:
                drifted.append(f"  ~ changed  {sid} :: {name}  ({eh[:12]} → {h[:12]})")
        for name in exp_hashes:
            if name not in cur_hashes:
                drifted.append(f"  - removed  {sid} :: {name}")
    for sid in expected["specs"]:
        if sid not in current["specs"]:
            drifted.append(f"  - removed spec: {sid}")

    tmpl_drift = []
    for name, h in current["templates"].items():
        eh = expected["templates"].get(name)
        if eh is None:
            tmpl_drift.append(f"  + new template {name}")
        elif eh != h:
            tmpl_drift.append(f"  ~ changed template {name}  ({eh[:12]} → {h[:12]})")
    for name in expected["templates"]:
        if name not in current["templates"]:
            tmpl_drift.append(f"  - removed template {name}")

    if drifted or tmpl_drift:
        raise AssertionError(
            "render-diff harness detected drift from goldens.\n"
            "Template changes:\n" + ("\n".join(tmpl_drift) or "  (none)") + "\n"
            "Rendered-script changes:\n" + ("\n".join(drifted) or "  (none)") + "\n\n"
            "If every change is intentional, rebless with:\n"
            "  UPDATE_RENDER_HASHES=1 pytest skill/tests/test_archived_specs_render_diff.py"
        )
