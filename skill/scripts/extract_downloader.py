"""
Phase 4a: PAT-authed download of a Tableau Server published data
source as a local Hyper extract.

Why this exists: Tableau Cloud sites that enforce MFA on every login
block `tableau-prep-cli` from authenticating (the CLI's
credentials.json schema only accepts username/password — no PAT, no
MFA factor). To iterate flows locally against published-DS data on
such sites, we use the REST API (which DOES accept PATs) to download
the DS as a .tdsx, extract the embedded .hyper, and feed THAT into
prep-cli as a local file source.

At publish time, run_loop swaps the input back to the LoadSqlProxy
shape so Tableau Server's backgrounder runs against the live DS via
the user's site session - no MFA loop, no plaintext password.

Public surface:
    download_published_ds(luid, dest_dir) -> dict

CLI:
    python3 -m skill.scripts.extract_downloader \\
        --luid <luid> --dest-dir runtime/<run>/inputs
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Bootstrap tflb_lib import path
from skill.scripts.lib import _REPO_ROOT  # noqa: F401


@dataclass
class DownloadResult:
    status: str          # "ok" | "skipped" | "error"
    luid: str = ""
    ds_name: str = ""
    project: str = ""
    hyper_path: str = ""
    csv_path: str = ""
    tdsx_path: str = ""
    row_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status, "luid": self.luid, "ds_name": self.ds_name,
            "project": self.project, "hyper_path": self.hyper_path,
            "csv_path": self.csv_path, "tdsx_path": self.tdsx_path,
            "row_count": self.row_count, "reason": self.reason,
        }


def _safe_name(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", (name or "ds")).strip("_") or "ds"


def _signin():
    from tflb_lib import publishing
    cfg = publishing.config_from_env()
    return publishing.sign_in(cfg)


def _hyper_to_csv(hyper_path: Path, csv_path: Path) -> tuple[Optional[Path], int]:
    """Convert a downloaded Hyper extract to CSV so prep-cli can read
    it via the existing LoadCsv shape.

    Why CSV and not Hyper-as-input: Tableau Prep's `.v1.HyperLoad` /
    similar local-Hyper-input shapes require a Builder-saved seed to
    reverse-engineer correctly. The existing `LoadCsv` shape is
    well-trodden in this skill and works headlessly. CSV write happens
    locally with no PII / network exposure.

    Returns (csv_path or None, row_count).
    """
    try:
        from tableauhyperapi import HyperProcess, Connection, Telemetry
    except ImportError:
        return None, 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(endpoint=hp.endpoint, database=str(hyper_path)) as conn:
            # Find the data table. Tableau extracts always live under
            # schema "Extract" with table "Extract" by convention; some
            # older formats use "Public.Extract" or named differently.
            tables = []
            for schema in conn.catalog.get_schema_names():
                for tbl in conn.catalog.get_table_names(schema):
                    tables.append(tbl)
            if not tables:
                return None, 0
            tbl = tables[0]  # extracts have exactly one table

            cols = [c.name.unescaped for c in conn.catalog.get_table_definition(tbl).columns]
            import csv as _csv
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = _csv.writer(f)
                writer.writerow(cols)
                # SQL-quote table name properly via the table type's API
                with conn.execute_query(f"SELECT * FROM {tbl}") as rows:
                    for row in rows:
                        # Hyper returns native Python types; convert to strings
                        # consistent with what Prep's CSV reader expects.
                        writer.writerow([
                            "" if v is None else str(v) for v in row
                        ])
                        row_count += 1
    return csv_path, row_count


def _extract_hyper_from_tdsx(tdsx: Path, dest_hyper: Path) -> Optional[Path]:
    """Pull the .hyper out of a .tdsx (which is a zip).

    Tableau bundles structure: data/<name>.hyper (sometimes
    Data/Federated/.../<name>.hyper for federated extracts).
    """
    with zipfile.ZipFile(tdsx) as z:
        hyper_members = [n for n in z.namelist() if n.lower().endswith(".hyper")]
        if not hyper_members:
            return None
        # Largest .hyper is the actual extract; others are usually empty
        # placeholders for future revisions.
        hyper_members.sort(key=lambda n: z.getinfo(n).file_size, reverse=True)
        member = hyper_members[0]
        dest_hyper.parent.mkdir(parents=True, exist_ok=True)
        with z.open(member) as src, dest_hyper.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return dest_hyper


def download_published_ds(luid: str, dest_dir: Path,
                          friendly_name: str = "") -> DownloadResult:
    """Download a published DS as a Hyper extract via PAT.

    Uses TSC's `server.datasources.download(luid)` which calls the
    REST API (PAT-authed, MFA-bypassed). Returns the local .hyper
    path + metadata. The downloaded .tdsx is preserved alongside in
    case the caller wants the .tds connection metadata.

    `friendly_name` is the spec's source.name; if empty, the function
    fetches the actual DS name via TSC's `get_by_id`.
    """
    if not luid:
        return DownloadResult(status="error", reason="luid required")

    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    server = _signin()
    try:
        item = server.datasources.get_by_id(luid)
        ds_name = item.name or friendly_name or luid
        project = item.project_name or ""
        slug = _safe_name(ds_name)
        tdsx_path = dest_dir / f"{slug}.tdsx"
        hyper_path = dest_dir / f"{slug}.hyper"

        # TSC's download() returns the path it wrote to. include_extract=True
        # is the default; we set it explicitly so future versions can't break us.
        result_path = server.datasources.download(
            luid, filepath=str(tdsx_path), include_extract=True,
        )
        result_path = Path(result_path)
        if not result_path.exists():
            return DownloadResult(
                status="error", luid=luid, ds_name=ds_name, project=project,
                reason=f"TSC download returned a path that doesn't exist: {result_path}",
            )

        # If TSC chose a different filename (it sometimes adds .tdsx suffix
        # automatically), normalize to our slug.
        if result_path != tdsx_path:
            result_path.replace(tdsx_path)

        extracted = _extract_hyper_from_tdsx(tdsx_path, hyper_path)
        if extracted is None:
            return DownloadResult(
                status="error", luid=luid, ds_name=ds_name, project=project,
                tdsx_path=str(tdsx_path),
                reason=("no .hyper found in downloaded .tdsx - DS may be a "
                        "live connection (not extracted) or empty"),
            )

        # Hyper -> CSV so prep-cli can read it locally without trying
        # to authenticate to a server. CSV is the path of least
        # resistance for headless prep-cli + MFA-bound Cloud sites.
        csv_path = dest_dir / f"{slug}.csv"
        csv_result, row_count = _hyper_to_csv(hyper_path, csv_path)
    finally:
        try:
            server.auth.sign_out()
        except Exception:
            pass

    return DownloadResult(
        status="ok",
        luid=luid,
        ds_name=ds_name,
        project=project,
        hyper_path=str(hyper_path),
        csv_path=str(csv_result) if csv_result else "",
        tdsx_path=str(tdsx_path),
        row_count=row_count,
    )


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Phase 4a download helper: PAT-authed published-DS "
                    "extract download for MFA-bound sites.",
    )
    ap.add_argument("--luid", required=True)
    ap.add_argument("--dest-dir", required=True)
    ap.add_argument("--friendly-name", default="")
    args = ap.parse_args(argv)

    result = download_published_ds(args.luid, Path(args.dest_dir),
                                   friendly_name=args.friendly_name)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
