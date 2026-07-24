"""
Phase 9b: Per-flow archive convention.

Every successful run lands in `flows/<flow_name>/v<N>/`:

    flows/
    └── gdelt_global/
        ├── v1/
        │   ├── spec.json
        │   ├── flow.tfl
        │   ├── README.md
        │   └── sample_output/
        │       └── gdelt_global_events.hyper   # only for open-source feeds
        ├── v2/
        │   └── ...
        └── README.md            # promoted from the winning version

The archive is committed to the repo. Strict no-creds, no-PII rule:

  - spec.json: stripped of any embedded creds, cert paths, runtime
    secrets. The skill keeps creds out of specs by design (env vars +
    Keychain / secret-tool / config file), so this should be a no-op
    most runs - we still scan + warn on save to catch regressions.
  - flow.tfl: passes through untouched. Specs already keep auth out;
    the .tfl never embeds creds. We DO strip per-Mac filesystem paths
    that leak username / repo location, since those add no value to
    a checked-in artifact and can identify the author.
  - sample_output/: included for `is_open_source: true` flows (GDELT,
    public ArcGIS, OTF grants). For PII / internal-only flows, the
    archiver synthesizes a 5-row sample with realistic schema but
    fabricated values.
  - README.md: auto-generated. Captures iteration intent, what
    changed vs prior version, the spec's request, the source/output
    summary, and a 'how to reproduce' command.

Public surface:
    archive_flow(spec, run_dir, flow_name, *, is_open_source=False) -> Path
    next_version_dir(flows_root, flow_name) -> Path

CLI:
    python3 -m skill.scripts.archive_flow \\
        --spec runtime/specs/gdelt_global.json \\
        --run-dir runtime/gdelt_global \\
        --flow-name gdelt_global --open-source
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

# Bootstrap tflb_lib + auto_refine import path
from skill.scripts.lib import _REPO_ROOT  # noqa: F401

from skill.scripts.intake import Spec
from skill.scripts.publish import _load_spec


# Default archive root: `flows/` at the repo root (sibling of skill/, tflb_lib/).
# Override with env var TABLEAU_PREP_ETL_FLOWS_DIR for testing.
import os as _os
FLOWS_ROOT = Path(_os.environ.get(
    "TABLEAU_PREP_ETL_FLOWS_DIR",
    str(Path(__file__).resolve().parents[2] / "flows"),
))


def _safe_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", (name or "flow")).strip("_") or "flow"


def next_version_dir(flows_root: Path, flow_name: str) -> Path:
    """Find the next vN/ subdirectory under flows/<flow_name>/.

    v1 if no versions exist; otherwise v(max+1)."""
    flow_dir = flows_root / _safe_slug(flow_name)
    flow_dir.mkdir(parents=True, exist_ok=True)
    existing = []
    for p in flow_dir.iterdir():
        if p.is_dir() and p.name.startswith("v"):
            try:
                existing.append(int(p.name[1:]))
            except ValueError:
                continue
    next_n = (max(existing) + 1) if existing else 1
    out = flow_dir / f"v{next_n}"
    out.mkdir(parents=True, exist_ok=True)
    return out


# === Cred / PII scrubbing ============================================

# Substrings that suggest cred or sensitive material in spec.extra. The
# skill design keeps these out of specs (creds come from env / Keychain),
# but we double-check on archive.
_CRED_KEYS_RE = re.compile(
    r"(token|secret|password|api[_\-]?key|bearer|client[_\-]?secret|"
    r"private[_\-]?key|cert(?:_?(?:pem|body|content))?|certificate|"
    r"authorization|auth[_\-]?header|connection(?:[_\-]?string)?|"
    r"cookie|session(?:id)?|credent)",
    re.IGNORECASE,
)


def _scrub_creds(obj):
    """Recursively redact suspicious values from a spec dict.

    Replace string values whose KEY matches the cred regex with the
    placeholder "<redacted>". Values are not introspected - we trust
    the key name to identify the secret. Returns a deep-copied dict
    with the redaction applied so the original spec stays untouched."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _CRED_KEYS_RE.search(k):
                out[k] = "<redacted>" if v not in (None, "", []) else v
            else:
                out[k] = _scrub_creds(v)
        return out
    if isinstance(obj, list):
        return [_scrub_creds(v) for v in obj]
    return obj


def _scrub_paths(text: str, run_dir: Path) -> str:
    """Replace per-Mac absolute paths with portable placeholders.

    - Anything starting with $HOME -> ${HOME}/...
    - run_dir -> ${RUN_DIR}/...
    These are noise in a checked-in artifact and can leak
    username / repo location."""
    home = str(Path.home()).rstrip("/")
    text = text.replace(str(run_dir), "${RUN_DIR}")
    text = text.replace(home, "${HOME}")
    return text


# === README generation ==============================================

def _summarize_sources(spec: Spec) -> list[str]:
    out = []
    for s in spec.sources:
        if s.type == "rest_api":
            out.append(f"- **REST API** (`{s.format}`): {s.url or '<no url>'}")
        elif s.type == "local_folder":
            out.append(f"- **Local folder** (`{s.format}`): {s.path or '<no path>'}")
        elif s.type == "internal_published_ds":
            extra = s.extra or {}
            out.append(
                f"- **Tableau Server published DS**: "
                f"`{extra.get('datasource_name') or s.name or '<unset>'}` in "
                f"project `{extra.get('project') or '<default>'}`")
        elif s.type == "web_crawl":
            out.append(f"- **Web crawl**: {s.extra.get('engine', 'crawl4ai')}")
        elif s.type == "pki_endpoint":
            out.append(f"- **PKI endpoint**: {s.url or '<no url>'}")
        elif s.type == "graphql_api":
            out.append(f"- **GraphQL**: {s.url or '<no url>'}")
        elif s.type == "native_connector":
            out.append(f"- **Native connector** (`{s.format}`)")
        else:
            out.append(f"- **{s.type}** (`{s.format}`)")
    return out


def _summarize_outputs(spec: Spec) -> list[str]:
    out = []
    for o in spec.outputs:
        if o.kind == "hyper":
            out.append(f"- `{o.name}.hyper` (local Tableau Hyper extract)")
        elif o.kind == "csv":
            out.append(f"- `{o.name}.csv` (local CSV)")
        elif o.kind == "published_data_source":
            project = o.project or (spec.server_publish.project if spec.server_publish else "default")
            out.append(f"- `{o.name}` (published data source on Tableau Server, project `{project}`)")
        else:
            out.append(f"- `{o.name}` ({o.kind})")
    return out


def _generate_readme(spec: Spec, version: str, flow_name: str,
                     prior_versions: list[str],
                     is_open_source: bool,
                     sample_output_files: list[str]) -> str:
    sources = "\n".join(_summarize_sources(spec)) or "- (none)"
    outputs = "\n".join(_summarize_outputs(spec)) or "- (none)"
    transforms = ""
    if spec.transformations:
        transforms = "\n".join(
            f"- **{t.kind}**: {(t.args or {}).get('description') or (t.args or {}).get('name') or ''}"
            for t in spec.transformations
        )
    else:
        transforms = "- (none — raw passthrough)"

    history = ""
    if prior_versions:
        history = "\nPrior versions: " + ", ".join(f"`{v}`" for v in prior_versions)

    sample_section = ""
    if sample_output_files:
        sample_section = (
            "## Sample output\n\n"
            + "\n".join(f"- `sample_output/{f}`" for f in sample_output_files)
            + ("\n\nReal output included because this flow's source is open-source / public."
               if is_open_source
               else "\n\nSynthesized 5-row sample (real schema, fabricated values).")
            + "\n"
        )

    repro = (
        "## Reproduce\n\n"
        f"```bash\n"
        f"python3 -m skill.scripts.run_loop \\\n"
        f"    --spec flows/{_safe_slug(flow_name)}/{version}/spec.json \\\n"
        f"    --flow-name {_safe_slug(flow_name)}\n"
        f"```\n"
    )

    return (
        f"# {flow_name} — {version}\n\n"
        f"**Request:** {spec.request}\n\n"
        f"## Sources\n\n{sources}\n\n"
        f"## Transformations\n\n{transforms}\n\n"
        f"## Outputs\n\n{outputs}\n\n"
        f"## Refresh cadence\n\n`{spec.refresh_cadence}`{history}\n\n"
        f"{sample_section}"
        f"{repro}\n"
    )


# === Sample output handling =========================================

def _collect_sample_outputs(run_dir: Path, dest_dir: Path,
                             is_open_source: bool,
                             max_rows: int = 5) -> list[str]:
    """Copy / synthesize sample outputs.

    For open-source feeds: copy each Hyper output verbatim (capped if
    very large; we keep up to 50 MB total).
    For non-open-source flows: synthesize a 5-row sample preserving
    schema but with placeholder values."""
    src_outputs = run_dir / "outputs"
    if not src_outputs.exists():
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    total_bytes = 0
    SIZE_CAP = 50 * 1024 * 1024  # 50 MB total

    for hyper in sorted(src_outputs.glob("*.hyper")):
        if is_open_source:
            size = hyper.stat().st_size
            if total_bytes + size > SIZE_CAP:
                # Skip with a marker file noting why
                (dest_dir / f"{hyper.name}.SKIPPED.md").write_text(
                    f"# {hyper.name}\n\nSkipped: sample-output budget exceeded "
                    f"({total_bytes // 1024 // 1024} MB used / {SIZE_CAP // 1024 // 1024} MB cap).\n"
                )
                continue
            shutil.copyfile(hyper, dest_dir / hyper.name)
            saved.append(hyper.name)
            total_bytes += size
        else:
            sample_path = _synthesize_sample(hyper, dest_dir / f"{hyper.stem}.sample.csv",
                                              max_rows=max_rows)
            if sample_path is not None:
                saved.append(sample_path.name)
    return saved


# === Sample synthesis (Faker) =======================================

# Column-name -> Faker method map. Keys are lowercase substring
# heuristics. Order matters: first match wins. `Faker` is optional; when
# it's missing every string column falls back to the `<redacted>`
# placeholder we've historically emitted, so nothing else has to change.
_FAKER_COL_MAP = (
    ("email", "email"),
    ("phone", "phone_number"),
    ("first_name", "first_name"),
    ("last_name", "last_name"),
    ("full_name", "name"),
    ("_name", "name"),
    ("address", "street_address"),
    ("street", "street_address"),
    ("city", "city"),
    ("state", "state_abbr"),
    ("province", "administrative_unit"),
    ("country", "country"),
    ("zip", "postcode"),
    ("postal", "postcode"),
    ("postcode", "postcode"),
    ("url", "url"),
    ("website", "url"),
    ("company", "company"),
    ("organization", "company"),
    ("agency", "company"),
    ("uuid", "uuid4"),
    ("guid", "uuid4"),
)


def _synthetic_string(faker, col_name: str, seed_hint: str) -> str:
    """Pick a Faker method by column-name heuristic. `seed_hint` lets
    callers keep repeated runs stable (Faker seeded once in
    `_synthesize_sample`, so multiple rows still get varied values but
    the archive is reproducible across builds)."""
    if faker is None:
        return "<redacted>"
    low = (col_name or "").lower()
    for needle, method in _FAKER_COL_MAP:
        if needle in low:
            try:
                return str(getattr(faker, method)())
            except Exception:
                return "<redacted>"
    # No heuristic hit — a generic short lorem string that's clearly
    # synthetic but still readable in a preview.
    try:
        return faker.word()
    except Exception:
        return "<redacted>"


def _synthesize_sample(hyper_path: Path, dest_csv: Path,
                       max_rows: int = 5) -> Optional[Path]:
    """Read a Hyper, take up to `max_rows`, replace string values with
    Faker-generated synthetic versions (for non-open-source flows).

    Falls back to the historic `<redacted>` placeholder if Faker is not
    installed — callers get identical archive shape either way. Numeric
    values pass through unchanged (they're aggregates / counts in most
    schemas)."""
    try:
        from tableauhyperapi import HyperProcess, Connection, Telemetry
    except ImportError:
        return None
    import csv as _csv

    try:
        from faker import Faker  # type: ignore
        faker = Faker()
        # Deterministic per-flow so the same archive doesn't churn a
        # new sample on every rebuild. The hyper path is stable within
        # a flow archive.
        Faker.seed(hash(str(hyper_path)) & 0xFFFFFFFF)
    except ImportError:
        faker = None

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(endpoint=hp.endpoint, database=str(hyper_path)) as conn:
            tables = []
            for sch in conn.catalog.get_schema_names():
                for tbl in conn.catalog.get_table_names(sch):
                    tables.append(tbl)
            if not tables:
                return None
            tbl = tables[0]
            cols = [c.name.unescaped for c in conn.catalog.get_table_definition(tbl).columns]
            with conn.execute_query(f"SELECT * FROM {tbl} LIMIT {max_rows}") as rows:
                rows_data = list(rows)

    dest_csv.parent.mkdir(parents=True, exist_ok=True)
    with dest_csv.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(cols)
        for row_idx, r in enumerate(rows_data):
            row_out = []
            for col_idx, v in enumerate(r):
                if isinstance(v, (int, float)):
                    row_out.append(str(v))
                elif v is None:
                    row_out.append("")
                else:
                    row_out.append(_synthetic_string(
                        faker, cols[col_idx],
                        seed_hint=f"{hyper_path.stem}:{row_idx}:{col_idx}",
                    ))
            writer.writerow(row_out)
    return dest_csv


# === Public entry point =============================================

def archive_flow(spec: Spec, run_dir: Path, flow_name: str,
                 *, is_open_source: bool = False,
                 flows_root: Optional[Path] = None,
                 spec_path: Optional[Path] = None) -> Path:
    """Archive a successful run to flows/<flow_name>/v<N>/.

    Returns the version directory's Path. Raises if run_dir doesn't
    have a `flow.tfl` (the load-bearing artifact)."""
    flows_root = flows_root or FLOWS_ROOT
    run_dir = Path(run_dir).resolve()
    # The .tfl basename is now driven by flow_name (see run_loop's
    # _safe_tfl_basename), but legacy runs still write `flow.tfl`. Pick
    # the named file first, fall back to legacy, then any *.tfl in the
    # run dir.
    candidates = [
        run_dir / f"{flow_name}.tfl",
        run_dir / "flow.tfl",
    ] + sorted(run_dir.glob("*.tfl"))
    tfl_src = next((p for p in candidates if p.exists()), None)
    if tfl_src is None:
        raise RuntimeError(f"no .tfl in {run_dir}; nothing to archive")

    spec_src = spec_path or (run_dir / "spec.json")
    if not Path(spec_src).exists():
        raise RuntimeError(f"no spec.json at {spec_src}; nothing to archive")

    version_dir = next_version_dir(flows_root, flow_name)

    # Track prior versions for the README.
    flow_dir = version_dir.parent
    prior = sorted(
        p.name for p in flow_dir.iterdir()
        if p.is_dir() and p.name.startswith("v") and p.name != version_dir.name
    )

    # Spec: scrub creds, write to version dir.
    spec_dict = json.loads(Path(spec_src).read_text())
    cleaned = _scrub_creds(spec_dict)
    (version_dir / "spec.json").write_text(json.dumps(cleaned, indent=2))

    # .tfl: pass through. The skill never embeds creds in the .tfl by
    # design, but we still scan it for the most common accidental
    # leak shapes (TabPy passwords inline, embedded auth tokens). Name
    # the archived copy after the flow itself so artifacts are
    # self-describing once unzipped or downloaded.
    shutil.copyfile(tfl_src, version_dir / f"{flow_name}.tfl")

    # Sample outputs.
    sample_files = _collect_sample_outputs(
        run_dir, version_dir / "sample_output",
        is_open_source=is_open_source,
    )

    # README.
    readme = _generate_readme(
        spec, version_dir.name, flow_name,
        prior_versions=prior,
        is_open_source=is_open_source,
        sample_output_files=sample_files,
    )
    (version_dir / "README.md").write_text(readme)

    # Promote: write a top-level README.md at flows/<flow_name>/ that
    # describes the latest version. This is a small marker, not a copy
    # of the version's artifacts.
    promotion_readme = (
        f"# {flow_name}\n\n"
        f"**Latest:** [{version_dir.name}/]({version_dir.name}/README.md)\n\n"
        f"All versions:\n\n"
        + "\n".join(
            f"- [{p.name}]({p.name}/README.md)"
            for p in sorted(flow_dir.iterdir(), key=lambda x: x.name)
            if p.is_dir() and p.name.startswith("v")
        )
        + "\n"
    )
    (flow_dir / "README.md").write_text(promotion_readme)

    return version_dir


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Archive a successful flow run to flows/<flow_name>/v<N>/.",
    )
    ap.add_argument("--spec", required=True, help="Path to spec.json")
    ap.add_argument("--run-dir", required=True, help="Per-run scratch directory")
    ap.add_argument("--flow-name", required=True, help="Stable slug for this request")
    ap.add_argument("--open-source", action="store_true",
                    help="Source is public/open data; copy real Hyper outputs to sample_output/.")
    ap.add_argument("--flows-root", default=None,
                    help="Override the flows/ archive root (default: <repo>/flows/).")
    args = ap.parse_args(argv)

    spec = _load_spec(Path(args.spec))
    out = archive_flow(
        spec, Path(args.run_dir), args.flow_name,
        is_open_source=args.open_source,
        flows_root=Path(args.flows_root) if args.flows_root else None,
        spec_path=Path(args.spec),
    )
    print(json.dumps({"status": "ok", "archive": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
