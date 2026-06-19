"""One-shot backfill driver for the Prep Agent demo collection.

Reads each archived spec.json, calls the existing
`run_loop._maybe_write_metadata` with an empty publish_result so the
parent-aware LUID lookup fires, and reports per-output status. Does
NOT re-run any flows or re-publish .tfls — only the .tds-roundtrip
apply path runs.

Usage:
    python3 scripts/backfill_metadata.py [--only flow_name1,flow_name2]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from skill.scripts.lib import _REPO_ROOT  # noqa: F401
from skill.scripts.run_loop import _maybe_write_metadata, _spec_from_dict


PREP_AGENT_FLOWS = [
    "fed_outlays",
    "fed_workforce",
    "cisa_kev",
    "fed_register_actions",
    "fema_disasters",
    "cms_deficiencies",
    "college_scorecard",
    "opensky_us",
    "epa_aqs_ozone",
    "usaspending_contracts",
]


# Known LUIDs from PREP_AGENT_REPORT.md. The .tds-roundtrip apply path
# is keyed on LUID, so we hand them in directly to skip the (occasionally
# 401-flaky) env-side lookup. Same source of truth the report uses.
KNOWN_LUIDS: dict[str, dict[str, str]] = {
    "fed_outlays": {
        "Federal Outlays Detail": "db010c2b-40e8-48e1-8bf1-415fdf60385f",
        "Federal Outlays Stats":  "0c876948-f3db-465f-9d66-d3168e4d0441",
    },
    "fed_workforce": {
        "Federal Workforce Detail": "f539f9a6-6632-4981-9473-34eee1d731fd",
        "Federal Workforce Stats":  "c5026e8d-4c16-41b2-9039-0493c803c257",
    },
    "cisa_kev": {
        "CISA KEV Detail": "237e69ea-a62c-41d2-b4dc-6f879e8e10a3",
        "CISA KEV Stats":  "fe00cf10-fa12-4117-b930-3b494d4eaef9",
    },
    "fed_register_actions": {
        "Federal Register Detail": "4afdaf55-c468-4cd9-b5c2-a0c579b752c2",
        "Federal Register Stats":  "9c729a30-5418-4d3f-b4fb-98d892a6c57d",
    },
    "fema_disasters": {
        "FEMA Disaster Detail": "de26b181-727f-4fd1-bc45-324863e8e275",
        "FEMA Disaster Stats":  "7e6f2268-222a-4bd7-8ef2-ea1e2abdd7bc",
    },
    "cms_deficiencies": {
        "CMS Deficiency Detail": "774213e6-b851-40c5-a715-98911aa3fd74",
        "CMS Deficiency Stats":  "9deb5efb-9e76-4250-ac92-526a63f5e376",
    },
    "college_scorecard": {
        "College Scorecard Outcomes": "0da80e0a-c750-4c17-b278-5ee9c0850e1f",
    },
    "opensky_us": {
        "OpenSky US Live States": "7b09f4ac-3dda-485b-a9d9-b178674acc14",
    },
    "epa_aqs_ozone": {
        "EPA Ozone Detail": "e839b508-91fe-400a-a4f6-e195b8ce91c3",
        "EPA Ozone Stats":  "a5de5682-61a8-4f97-b223-f767ac26586f",
    },
    "usaspending_contracts": {
        "Federal Award Detail": "05578bb7-b94c-48b9-8361-84332fd3d051",
        "Federal Award Stats":  "806d1b55-d951-4fe8-92bb-e1ade0b489d1",
    },
}


def backfill_one(flow_name: str) -> dict:
    spec_path = Path("flows") / flow_name / "v1" / "spec.json"
    if not spec_path.exists():
        return {"flow": flow_name, "status": "error",
                "reason": f"no spec at {spec_path}"}

    spec_dict = json.loads(spec_path.read_text())
    spec = _spec_from_dict(spec_dict, request=spec_dict.get("request", ""))

    run_dir = Path("runtime") / flow_name / f"backfill-{int(time.time())}"
    run_dir.mkdir(parents=True, exist_ok=True)

    luids = KNOWN_LUIDS.get(flow_name, {})
    publish_result = {
        "project_name": (spec.server_publish.project
                          if spec.server_publish else ""),
        "datasources": [
            {"name": n, "luid": luid} for n, luid in luids.items()
        ],
    }
    res = _maybe_write_metadata(spec, publish_result, run_dir, review=False)
    return {"flow": flow_name, "run_dir": str(run_dir), **res}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="",
                    help="Comma-separated list of flow names; default = all 10")
    args = ap.parse_args()

    flows = (
        [f.strip() for f in args.only.split(",") if f.strip()]
        if args.only else PREP_AGENT_FLOWS
    )
    print(f"Backfilling metadata for {len(flows)} flow(s): {', '.join(flows)}",
          file=sys.stderr)

    results = []
    for fn in flows:
        print(f"\n=== {fn} ===", file=sys.stderr)
        try:
            r = backfill_one(fn)
        except Exception as e:
            r = {"flow": fn, "status": "error",
                 "type": type(e).__name__, "message": str(e)}
        results.append(r)
        # One-line per-output summary so failures stand out at a glance.
        for o in (r.get("outputs") or []):
            print(f"  - {o.get('output_name','?')}: status={o.get('status','?')} "
                  f"luid={o.get('luid','')} "
                  f"applied={(o.get('applied') or {}).get('status','?')}",
                  file=sys.stderr)

    print("\n=== summary ===", file=sys.stderr)
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
