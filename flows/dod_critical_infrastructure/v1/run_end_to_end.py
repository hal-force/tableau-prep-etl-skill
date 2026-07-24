"""End-to-end driver for the DoD critical-infrastructure demo.

Runs entirely inside the docker skill container:

  1. Invokes the rendered api_caller_b0.call_api() against the live
     HIFLD Military_Installation FeatureServer (paginates all 744
     records).
  2. Applies scoring.score_frame() to compute criticality_score and
     replacement_likelihood_score for each site.
  3. Writes a .hyper extract via tableauhyperapi to
     runtime/build/dod_critical_infrastructure/outputs/.

No Tableau Prep CLI involvement — the api_caller runs as ordinary
Python inside the container. This is the "structural verification"
flavour of the run_loop test that doesn't require the macOS-only
Prep CLI binary.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
from tableauhyperapi import (
    Connection,
    CreateMode,
    HyperProcess,
    Inserter,
    NULLABLE,
    NOT_NULLABLE,
    SqlType,
    TableDefinition,
    TableName,
    Telemetry,
)

HERE = Path(__file__).parent
SCRIPTS = HERE / "scripts"
OUT_DIR = HERE / "outputs"
OUT_DIR.mkdir(exist_ok=True)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    api = _load("api_caller_b0", SCRIPTS / "api_caller_b0.py")
    scoring = _load("scoring", HERE / "scoring.py")

    print("[1/3] Fetching HIFLD Military_Installation records...")
    trigger = pd.DataFrame({"folder": ["_"]})
    raw = api.call_api(trigger)
    print(f"      pulled {len(raw)} rows, columns: {list(raw.columns)}")

    print("[2/3] Scoring replacement_likelihood...")
    scored = scoring.score_frame(raw)
    print(f"      scored {len(scored)} rows")
    print("      criticality distribution:")
    print(scored["criticality_score"].describe().round(2).to_string())
    print()
    print("      top-10 by criticality (hardest to replace):")
    top = scored.nlargest(10, "criticality_score")[
        ["SITE_NAME", "COMPONENT", "JOINT_BASE", "COUNTRY", "AREA",
         "criticality_score", "replacement_likelihood_score"]
    ]
    print(top.to_string(index=False))

    print()
    print(f"[3/3] Writing .hyper -> {OUT_DIR}/dod_critical_infrastructure.hyper")
    hyper_path = OUT_DIR / "dod_critical_infrastructure.hyper"
    _write_hyper(scored, hyper_path)
    print(f"      wrote {hyper_path.stat().st_size:,} bytes")

    csv_path = OUT_DIR / "dod_scored_sample.csv"
    scored.to_csv(csv_path, index=False)
    print(f"      wrote CSV sample -> {csv_path}")

    return 0


_COL_TYPE_MAP = {
    "OBJECTID": (SqlType.big_int(), NULLABLE),
    "SITE_NAME": (SqlType.text(), NULLABLE),
    "COMPONENT": (SqlType.text(), NULLABLE),
    "JOINT_BASE": (SqlType.text(), NULLABLE),
    "STATE_TERR": (SqlType.text(), NULLABLE),
    "COUNTRY": (SqlType.text(), NULLABLE),
    "OPER_STAT": (SqlType.text(), NULLABLE),
    "AREA": (SqlType.double(), NULLABLE),
    "IS_FIRRMA": (SqlType.text(), NULLABLE),
    "criticality_score": (SqlType.double(), NOT_NULLABLE),
    "replacement_likelihood_score": (SqlType.double(), NOT_NULLABLE),
}


def _write_hyper(df: pd.DataFrame, path: Path) -> None:
    if path.exists():
        path.unlink()
    columns = [
        TableDefinition.Column(col, *_COL_TYPE_MAP[col])
        for col in _COL_TYPE_MAP if col in df.columns
    ]
    tdef = TableDefinition(TableName("Extract", "Extract"), columns=columns)

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(hp.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(tdef)
            with Inserter(conn, tdef) as ins:
                col_specs = [(str(c.name).strip('"'), c.type) for c in tdef.columns]
                big_int_t = SqlType.big_int()
                double_t = SqlType.double()
                rows = []
                for _, r in df.iterrows():
                    row = []
                    for name, ty in col_specs:
                        v = r[name]
                        if pd.isna(v):
                            row.append(None)
                        elif ty == big_int_t:
                            row.append(int(v))
                        elif ty == double_t:
                            row.append(float(v))
                        else:
                            row.append(str(v))
                    rows.append(row)
                ins.add_rows(rows)
                ins.execute()


if __name__ == "__main__":
    raise SystemExit(main())
