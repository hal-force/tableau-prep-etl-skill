"""Unit tests for run_loop pure helpers.

Live orchestration (`run()`) needs TabPy + Prep CLI + a real spec so it
lives in verification, not unit tests. But the helpers around it —
run-id shape, tfl basename sanitization, spec-dict hydration — are
straight functions that we can pin down cheaply.
"""
from __future__ import annotations

import re

import pytest

from skill.scripts import run_loop as rl
from skill.scripts.intake import ServerPublish, Spec


@pytest.fixture(autouse=True)
def _trust_all_hosts(monkeypatch):
    """Bypass host-approval prompt for tests. Real runs still gate."""
    monkeypatch.setenv("TPE_HOST_APPROVAL", "trust-all")


def test_new_run_id_shape_and_uniqueness():
    a = rl._new_run_id()
    b = rl._new_run_id()
    assert re.match(r"^\d{8}-\d{6}-[0-9a-f]{6}$", a), a
    assert a != b, "each call must yield a distinct id"


def test_safe_tfl_basename_sanitization():
    assert rl._safe_tfl_basename(None) == "flow"
    assert rl._safe_tfl_basename("") == "flow"
    assert rl._safe_tfl_basename("Simple Name") == "Simple_Name"
    assert rl._safe_tfl_basename("path/../etc") == "path_.._etc"
    assert rl._safe_tfl_basename("...___") == "flow"
    assert rl._safe_tfl_basename("Embassy Threat Monitor v2") == "Embassy_Threat_Monitor_v2"


def test_spec_from_dict_round_trip_minimal():
    d = {
        "request": "hello",
        "sources": [
            {"type": "rest_api", "name": "S", "url": "https://example.com/api",
             "format": "json", "auth": "none", "extra": {}},
        ],
        "transformations": [],
        "outputs": [{"kind": "hyper", "name": "out"}],
        "qa_tier": "deterministic",
        "eval_strategy": "sample_validation",
        "refresh_cadence": "once",
    }
    spec = rl._spec_from_dict(d)
    assert isinstance(spec, Spec)
    assert spec.request == "hello"
    assert len(spec.sources) == 1
    assert spec.sources[0].type == "rest_api"
    assert spec.outputs[0].name == "out"
    assert spec.server_publish is None


def test_spec_from_dict_hydrates_server_publish():
    d = {
        "request": "x",
        "sources": [{"type": "rest_api", "url": "https://example.com/api",
                     "format": "json", "auth": "none", "extra": {}}],
        "transformations": [],
        "outputs": [{"kind": "hyper", "name": "out"}],
        "qa_tier": "deterministic",
        "eval_strategy": "sample_validation",
        "refresh_cadence": "hourly",
        "server_publish": {
            "project": "P", "cadence": "hourly", "hour_utc": 6, "minute_utc": 15,
        },
    }
    spec = rl._spec_from_dict(d)
    assert isinstance(spec.server_publish, ServerPublish)
    assert spec.server_publish.cadence == "hourly"
    assert spec.server_publish.hour_utc == 6
    assert spec.server_publish.minute_utc == 15
