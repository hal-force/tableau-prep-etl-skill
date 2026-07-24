"""
Golden-file tests for `source_planner.plan_sources`.

Locks in the planner's output shape for representative synthetic specs.
The planner is the load-bearing bridge between the LLM-supplied JSON
and the .tfl assembler, so any silent change to node ordering, template
selection, or role assignment shows up here first.

When intentional planner changes are made, regenerate the golden files
by running:

    UPDATE_GOLDENS=1 pytest skill/tests/test_planner_golden.py

Then diff the resulting `.golden.json` files and check them into git.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from skill.scripts.intake import Output, Source, Spec, Transformation
from skill.scripts.source_planner import plan_sources


GOLDENS_DIR = Path(__file__).parent / "goldens"


def _plan_to_dict(plan) -> dict:
    """Serialize a Plan into a stable, diff-friendly dict.

    Fields that are non-deterministic across runs (absolute paths in
    template_vars, tmp-dir suffixes) are stripped so the golden stays
    stable on any host."""

    def _clean_node(n) -> dict:
        d = asdict(n)
        d.pop("rendered_path", None)
        tvars = d.get("template_vars") or {}
        # OUTPUTS_DIR resolves to an absolute path on the runner — strip.
        for k in list(tvars.keys()):
            if k.upper().endswith("_DIR"):
                tvars.pop(k, None)
        return d

    return {
        "inputs":     [_clean_node(n) for n in plan.inputs],
        "transforms": [_clean_node(n) for n in plan.transforms],
        "joins":      [_clean_node(n) for n in plan.joins],
        "qa_nodes":   [_clean_node(n) for n in plan.qa_nodes],
        "outputs":    [_clean_node(n) for n in plan.outputs],
        "parameters": plan.parameters,
    }


def _compare_or_update(name: str, plan_dict: dict) -> None:
    golden = GOLDENS_DIR / f"{name}.golden.json"
    if os.environ.get("UPDATE_GOLDENS") == "1":
        GOLDENS_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps(plan_dict, indent=2, sort_keys=True) + "\n")
        return
    assert golden.exists(), (
        f"missing golden {golden}. Regenerate with "
        "UPDATE_GOLDENS=1 pytest skill/tests/test_planner_golden.py"
    )
    expected = json.loads(golden.read_text())
    assert plan_dict == expected, (
        f"planner output drifted from golden {golden}. Diff the two and, "
        "if the change is intentional, regenerate with UPDATE_GOLDENS=1."
    )


# ---------------------------------------------------------------------
# Golden specs — kept small and hand-written so a reviewer can eyeball
# the resulting .golden.json file.
# ---------------------------------------------------------------------

def _rest_api_spec() -> Spec:
    return Spec(
        request="Pull unemployment rates by state from BLS.",
        sources=[Source(
            type="rest_api",
            name="bls_laus",
            description="BLS LAUS state unemployment.",
            url="https://api.bls.gov/publicAPI/v2/timeseries/data/",
            format="json",
            auth="none",
            extra={
                "verify_ssl": True,
                "timeout_s": 60,
                "json_http_method": "GET",
                "json_records_path": "Results.series",
            },
        )],
        outputs=[Output(
            kind="hyper",
            name="unemployment_by_state",
        )],
        qa_tier="deterministic",
        eval_strategy="sample_validation",
        deployment="local",
        refresh_cadence="monthly",
    )


def _local_folder_spec() -> Spec:
    return Spec(
        request="Extract data from a folder of PDF filings.",
        sources=[Source(
            type="local_folder",
            path="/tmp/filings",
            format="pdf_portfolio",
        )],
        outputs=[Output(kind="hyper", name="filings")],
        qa_tier="deterministic",
        eval_strategy="extract_from_source",
        deployment="local",
        refresh_cadence="once",
    )


def _two_source_join_spec() -> Spec:
    return Spec(
        request="Join incidents with lookup table.",
        sources=[
            Source(type="rest_api", name="incidents",
                   url="https://example.gov/api/incidents",
                   format="json", auth="none"),
            Source(type="rest_api", name="lookup",
                   url="https://example.gov/api/lookup",
                   format="json", auth="none"),
        ],
        transformations=[
            Transformation(kind="join", args={
                "left_branch": 0,
                "right_branch": 1,
                "on": "state_fips",
                "join_type": "left",
                "name": "join_lookup",
            }),
        ],
        outputs=[Output(kind="hyper", name="incidents_enriched")],
        qa_tier="deterministic",
        eval_strategy="sample_validation",
        deployment="local",
        refresh_cadence="daily",
    )


CASES = [
    ("rest_api_single",    _rest_api_spec),
    ("local_folder_pdfs",  _local_folder_spec),
    ("two_source_join",    _two_source_join_spec),
]


@pytest.mark.parametrize("name,factory", CASES, ids=[c[0] for c in CASES])
def test_planner_golden(name: str, factory) -> None:
    plan = plan_sources(factory(), outputs_dir=Path("./outputs"))
    _compare_or_update(name, _plan_to_dict(plan))
