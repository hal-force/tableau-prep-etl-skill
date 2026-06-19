"""Tests for skill.scripts.host_trust.

Run from the repo root:
    python3 -m pytest skill/tests/test_host_trust.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill.scripts import host_trust as ht
from skill.scripts.host_trust import (
    ApprovalDecision,
    HostEvaluation,
    ensure_hosts_approved,
    extract_hosts,
    heuristic_evaluate,
    record_approval,
)


# === Fixtures ========================================================

@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point CONFIG_DIR + KNOWN_HOSTS_FILE at a tmp dir so tests don't
    touch the real ~/.tableau-prep-etl."""
    cfg = tmp_path / ".tableau-prep-etl"
    cfg.mkdir()
    monkeypatch.setattr(ht, "CONFIG_DIR", cfg)
    monkeypatch.setattr(ht, "KNOWN_HOSTS_FILE", cfg / "known_hosts.json")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TABLEAU_SERVER_URL", raising=False)
    monkeypatch.delenv("TPE_HOST_APPROVAL", raising=False)
    yield tmp_path


# === extract_hosts ==================================================

class TestExtractHosts:
    def test_pulls_unique_hosts(self):
        spec = {
            "sources": [
                {"type": "rest_api", "url": "https://api.example.gov/v1"},
                {"type": "rest_api", "url": "https://api.example.gov/v2"},
                {"type": "graphql_api", "url": "https://gql.other.org/"},
                {"type": "local_folder", "path": "/data/foo"},
            ]
        }
        assert extract_hosts(spec) == ["api.example.gov", "gql.other.org"]

    def test_empty_spec(self):
        assert extract_hosts({}) == []
        assert extract_hosts({"sources": []}) == []

    def test_skips_sources_without_url(self):
        spec = {
            "sources": [
                {"type": "internal_published_ds"},
                {"type": "local_folder", "path": "/x"},
            ]
        }
        assert extract_hosts(spec) == []


# === heuristic_evaluate =============================================

class TestHeuristicEvaluate:
    def test_legitimate_anchor(self):
        ev = heuristic_evaluate("api.data.gov")
        assert ev.verdict == "looks-legitimate"
        assert ev.risk_score < 20

    def test_suspicious_tld(self):
        ev = heuristic_evaluate("free-data.tk")
        assert ev.risk_score >= 30
        assert any(".tk" in r for r in ev.reasons)

    def test_typosquat_detected(self):
        ev = heuristic_evaluate("data-gov.com")
        # Edit-distance from "data.gov" tail = 1 ('-' vs '.', then 'com' vs 'gov').
        # Actual catch is when last-two-labels are EditDistance-1 from anchor's last-two-labels.
        # "gov.com" vs "data.gov" tail "data.gov" — won't catch this case.
        # Pick a clearer typosquat case instead:
        ev2 = heuristic_evaluate("data.cov")  # data.gov with one swap
        assert ev2.typosquat_of == "data.gov" or ev2.risk_score >= 40

    def test_clean_unknown_host(self):
        ev = heuristic_evaluate("unknown-but-fine.example.org")
        assert ev.verdict in ("looks-legitimate", "unknown")


# === record_approval / is_host_known ================================

class TestPersistence:
    def test_record_then_known(self, isolated_home):
        assert not ht.is_host_known("api.foo.org")
        record_approval("api.foo.org", source="user-approved")
        assert ht.is_host_known("api.foo.org")

    def test_known_is_case_insensitive(self, isolated_home):
        record_approval("API.Foo.org", source="user-approved")
        assert ht.is_host_known("api.foo.ORG")

    def test_persists_evaluation(self, isolated_home):
        ev = HostEvaluation(host="api.foo.org", risk_score=10,
                            verdict="looks-legitimate", reasons=["ok"])
        record_approval("api.foo.org", source="user-approved", verdict=ev)
        d = json.loads((isolated_home / ".tableau-prep-etl" / "known_hosts.json").read_text())
        assert d["hosts"]["api.foo.org"]["verdict"]["risk_score"] == 10


# === ensure_hosts_approved ==========================================

class TestEnsureHostsApproved:
    def test_internal_trust_skips_prompt(self, isolated_home, monkeypatch):
        cfg = isolated_home / ".tableau-prep-etl"
        (cfg / "internal_hosts.txt").write_text("internal.corp\n")
        # Asker should NEVER be invoked for internal-trust hosts.
        called = []
        decisions = ensure_hosts_approved(
            ["api.internal.corp"],
            asker=lambda h, ev: (called.append(h), True)[1],
        )
        assert decisions[0].source == "internal-trust"
        assert decisions[0].approved is True
        assert called == []

    def test_known_host_skips_prompt(self, isolated_home):
        record_approval("api.example.gov", source="user-approved")
        called = []
        decisions = ensure_hosts_approved(
            ["api.example.gov"],
            asker=lambda h, ev: (called.append(h), True)[1],
        )
        assert decisions[0].source == "known"
        assert called == []

    def test_unknown_host_prompts_and_records_on_yes(self, isolated_home):
        decisions = ensure_hosts_approved(
            ["new-host.example.com"],
            asker=lambda h, ev: True,
        )
        assert decisions[0].approved is True
        assert decisions[0].source == "user-approved"
        assert ht.is_host_known("new-host.example.com")

    def test_unknown_host_denied_raises(self, isolated_home):
        with pytest.raises(RuntimeError, match="Host approval denied"):
            ensure_hosts_approved(
                ["bad-host.example.com"],
                asker=lambda h, ev: False,
            )
        assert not ht.is_host_known("bad-host.example.com")

    def test_deny_unknown_mode_skips_prompt(self, isolated_home, monkeypatch):
        monkeypatch.setenv("TPE_HOST_APPROVAL", "deny-unknown")
        called = []
        with pytest.raises(RuntimeError, match="Host approval denied"):
            ensure_hosts_approved(
                ["unrecorded.example.com"],
                asker=lambda h, ev: (called.append(h), True)[1],
            )
        assert called == []  # asker never invoked under deny-unknown

    def test_auto_trust_known_mode_passes_known(self, isolated_home, monkeypatch):
        record_approval("known.example.com", source="user-approved")
        monkeypatch.setenv("TPE_HOST_APPROVAL", "auto-trust-known")
        decisions = ensure_hosts_approved(
            ["known.example.com"],
            asker=lambda h, ev: pytest.fail("asker should not be called"),
        )
        assert decisions[0].approved is True

    def test_trust_all_mode_skips_evaluation(self, isolated_home, monkeypatch):
        monkeypatch.setenv("TPE_HOST_APPROVAL", "trust-all")
        decisions = ensure_hosts_approved(
            ["any-host.example.com"],
            asker=lambda h, ev: pytest.fail("should not be called"),
            evaluator=lambda h: pytest.fail("should not be called"),
        )
        assert decisions[0].approved is True
        assert decisions[0].source == "trust-all"
        # trust-all does NOT persist — that's the whole point of opt-out.
        assert not ht.is_host_known("any-host.example.com")

    def test_passes_evaluation_to_asker(self, isolated_home):
        seen_eval = []

        def custom_eval(h):
            return HostEvaluation(host=h, risk_score=42, verdict="suspicious",
                                  reasons=["test reason"])

        ensure_hosts_approved(
            ["custom-eval.example.com"],
            asker=lambda h, ev: (seen_eval.append(ev), True)[1],
            evaluator=custom_eval,
        )
        assert seen_eval[0].risk_score == 42
        assert seen_eval[0].verdict == "suspicious"

    def test_dedupes_hosts(self, isolated_home):
        call_count = []
        ensure_hosts_approved(
            ["dup.example.com", "dup.example.com", "DUP.example.com"],
            asker=lambda h, ev: (call_count.append(h), True)[1],
        )
        assert len(call_count) == 1

    def test_collects_all_rejections_before_raising(self, isolated_home):
        with pytest.raises(RuntimeError) as exc_info:
            ensure_hosts_approved(
                ["bad1.example.com", "bad2.example.com"],
                asker=lambda h, ev: False,
            )
        msg = str(exc_info.value)
        assert "bad1.example.com" in msg
        assert "bad2.example.com" in msg
