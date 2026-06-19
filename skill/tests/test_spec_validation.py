"""Tests for skill.scripts.spec_validation.

Run from the repo root:
    python3 -m pytest skill/tests/test_spec_validation.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from skill.scripts.spec_validation import (
    SpecValidationError,
    safe_output_dict,
    safe_source_dict,
    validate_extra,
    validate_output_name,
    validate_regex,
    validate_relative_path,
    validate_spec,
    validate_spec_strict,
    validate_url,
)


# === validate_url ====================================================

class TestValidateUrl:
    def test_accepts_https(self):
        assert validate_url("https://api.example.com/data.json") == "https://api.example.com/data.json"

    def test_accepts_http(self):
        assert validate_url("http://api.example.com/data.json") == "http://api.example.com/data.json"

    def test_rejects_file_scheme(self):
        with pytest.raises(SpecValidationError, match="scheme 'file' not in allowlist"):
            validate_url("file:///etc/passwd")

    def test_rejects_gopher_scheme(self):
        with pytest.raises(SpecValidationError, match="scheme 'gopher'"):
            validate_url("gopher://example.com/")

    def test_rejects_data_scheme(self):
        with pytest.raises(SpecValidationError, match="scheme 'data'"):
            validate_url("data:text/plain;base64,SGVsbG8=")

    def test_rejects_javascript_scheme(self):
        with pytest.raises(SpecValidationError, match="scheme 'javascript'"):
            validate_url("javascript:alert(1)")

    def test_rejects_aws_metadata_ip(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_gcp_metadata_host(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_rejects_azure_metadata_host(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://metadata.azure.com/")

    def test_rejects_localhost_host(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://localhost/admin")

    def test_rejects_loopback_ip(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://127.0.0.1/")

    def test_rejects_loopback_ip_alt(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://127.1.2.3/")

    def test_rejects_unspecified_ip(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://0.0.0.0/")

    def test_rejects_ipv6_loopback(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://[::1]/")

    def test_rejects_link_local_ipv6(self):
        with pytest.raises(SpecValidationError, match="hard-blocked"):
            validate_url("http://[fe80::1]/")

    def test_rejects_rfc1918_without_internal_trust(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TABLEAU_SERVER_URL", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(SpecValidationError, match="private IP"):
            validate_url("http://10.0.0.5/internal")

    def test_rejects_rfc1918_172(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TABLEAU_SERVER_URL", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(SpecValidationError, match="private IP"):
            validate_url("http://172.16.0.1/internal")

    def test_rejects_rfc1918_192(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TABLEAU_SERVER_URL", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(SpecValidationError, match="private IP"):
            validate_url("http://192.168.1.1/internal")

    def test_accepts_rfc1918_ip_when_listed_in_internal_hosts(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TABLEAU_SERVER_URL", raising=False)
        cfg_dir = tmp_path / ".tableau-prep-etl"
        cfg_dir.mkdir()
        (cfg_dir / "internal_hosts.txt").write_text("10.0.0.5\n# comment line\n")
        monkeypatch.setenv("HOME", str(tmp_path))
        validate_url("http://10.0.0.5/internal")

    def test_accepts_rfc1918_via_server_url_match_is_only_for_hostname_scope(
        self, monkeypatch, tmp_path
    ):
        # TABLEAU_SERVER_URL only confers trust on its OWN hostname, not
        # on arbitrary RFC1918 IPs. A bare IP needs to be explicitly listed.
        monkeypatch.setenv("TABLEAU_SERVER_URL", "https://prod.tableau.example.com")
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(SpecValidationError, match="private IP"):
            validate_url("http://10.0.0.5/internal")

    def test_rejects_url_with_newline(self):
        with pytest.raises(SpecValidationError, match="control characters"):
            validate_url("http://example.com\n  os.system('rm -rf /')")

    def test_rejects_url_with_nul(self):
        with pytest.raises(SpecValidationError, match="control characters"):
            validate_url("http://example.com/\x00path")

    def test_rejects_url_with_tab(self):
        with pytest.raises(SpecValidationError, match="control characters"):
            validate_url("http://exa\tmple.com/")

    def test_rejects_empty_string(self):
        with pytest.raises(SpecValidationError, match="empty"):
            validate_url("")

    def test_rejects_non_string(self):
        with pytest.raises(SpecValidationError, match="empty or not a string"):
            validate_url(None)  # type: ignore[arg-type]

    def test_rejects_no_host(self):
        with pytest.raises(SpecValidationError, match="missing host"):
            validate_url("https:///path")


# === validate_output_name ===========================================

class TestValidateOutputName:
    def test_accepts_simple(self):
        assert validate_output_name("federal_outlays") == "federal_outlays"

    def test_accepts_dotted(self):
        assert validate_output_name("foo.bar") == "foo.bar"

    def test_accepts_dashed(self):
        assert validate_output_name("foo-bar_baz") == "foo-bar_baz"

    def test_rejects_path_traversal(self):
        with pytest.raises(SpecValidationError, match="path separators"):
            validate_output_name("../../etc/passwd")

    def test_rejects_subdir(self):
        with pytest.raises(SpecValidationError, match="path separators"):
            validate_output_name("foo/bar")

    def test_rejects_backslash_subdir(self):
        with pytest.raises(SpecValidationError, match=r"path separators|forbidden"):
            validate_output_name("foo\\bar")

    def test_rejects_leading_dot(self):
        with pytest.raises(SpecValidationError, match="cannot start or end"):
            validate_output_name(".hidden")

    def test_rejects_trailing_dot(self):
        with pytest.raises(SpecValidationError, match="cannot start or end"):
            validate_output_name("foo.")

    def test_accepts_spaces(self):
        # Existing archived specs use display names with spaces.
        assert validate_output_name("CISA KEV Detail") == "CISA KEV Detail"

    def test_accepts_parens(self):
        assert validate_output_name("US Wildfires (EOC Enriched)") == \
               "US Wildfires (EOC Enriched)"

    def test_rejects_shell_metachar(self):
        with pytest.raises(SpecValidationError, match="forbidden"):
            validate_output_name("foo;rm")

    def test_rejects_dollar(self):
        with pytest.raises(SpecValidationError, match="forbidden"):
            validate_output_name("foo$bar")

    def test_rejects_pipe(self):
        with pytest.raises(SpecValidationError, match="forbidden"):
            validate_output_name("foo|bar")

    def test_rejects_double_dot(self):
        with pytest.raises(SpecValidationError, match=r"\.\."):
            validate_output_name("foo..bar")

    def test_rejects_empty(self):
        with pytest.raises(SpecValidationError, match="empty"):
            validate_output_name("")

    def test_rejects_too_long(self):
        with pytest.raises(SpecValidationError, match="exceeds 128"):
            validate_output_name("a" * 200)


# === validate_relative_path =========================================

class TestValidateRelativePath:
    def test_accepts_relative(self):
        assert validate_relative_path("data/foo.csv") == "data/foo.csv"

    def test_accepts_absolute(self):
        # Absolute paths are legitimate spec inputs (e.g. local_folder
        # pointing at /Users/me/data).
        assert validate_relative_path("/Users/me/data/x.csv") == "/Users/me/data/x.csv"

    def test_rejects_dotdot(self):
        with pytest.raises(SpecValidationError, match=r"\.\."):
            validate_relative_path("../../../etc/passwd")

    def test_rejects_embedded_dotdot(self):
        with pytest.raises(SpecValidationError, match=r"\.\."):
            validate_relative_path("data/../../etc/passwd")

    def test_rejects_nul_byte(self):
        with pytest.raises(SpecValidationError, match="control characters"):
            validate_relative_path("data\x00.csv")

    def test_rejects_newline(self):
        with pytest.raises(SpecValidationError, match="control characters"):
            validate_relative_path("data\n.csv")


# === validate_regex =================================================

class TestValidateRegex:
    def test_accepts_normal(self):
        validate_regex(r'href="([^"]+\.csv)"')

    def test_rejects_nested_star_plus(self):
        with pytest.raises(SpecValidationError, match="catastrophic"):
            validate_regex(r"(.*)+")

    def test_rejects_nested_plus_plus(self):
        with pytest.raises(SpecValidationError, match="catastrophic"):
            validate_regex(r"(.+)+")

    def test_rejects_nested_star_star(self):
        with pytest.raises(SpecValidationError, match="catastrophic"):
            validate_regex(r"(.*)*")

    def test_rejects_invalid(self):
        with pytest.raises(SpecValidationError, match="did not compile"):
            validate_regex(r"[unterminated")

    def test_rejects_too_long(self):
        with pytest.raises(SpecValidationError, match="exceeds 1024"):
            validate_regex("a" * 2000)


# === validate_extra =================================================

class TestValidateExtra:
    def test_empty_ok(self):
        cleaned, warnings = validate_extra({}, "rest_api")
        assert cleaned == {}
        assert warnings == []

    def test_none_ok(self):
        cleaned, warnings = validate_extra(None, "rest_api")  # type: ignore[arg-type]
        assert cleaned == {}
        assert warnings == []

    def test_known_keys_no_warning(self):
        _, warnings = validate_extra(
            {"verify_ssl": True, "timeout_s": 30}, "rest_api"
        )
        assert warnings == []

    def test_unknown_key_warns(self):
        _, warnings = validate_extra({"weird_key": "x"}, "rest_api")
        assert len(warnings) == 1
        assert "weird_key" in warnings[0]

    def test_rejects_non_dict(self):
        with pytest.raises(SpecValidationError, match="must be a dict"):
            validate_extra("not-a-dict", "rest_api")  # type: ignore[arg-type]

    def test_rejects_bad_index_link_pattern(self):
        with pytest.raises(SpecValidationError, match="catastrophic"):
            validate_extra({"index_link_pattern": "(.*)+"}, "rest_api")

    def test_rejects_non_bool_verify_ssl(self):
        with pytest.raises(SpecValidationError, match="verify_ssl"):
            validate_extra({"verify_ssl": "yes"}, "rest_api")

    def test_rejects_empty_domains_allowlist(self):
        with pytest.raises(SpecValidationError, match="domains_allowlist is empty"):
            validate_extra({"domains_allowlist": []}, "web_crawl")

    def test_accepts_domains_allowlist(self):
        validate_extra({"domains_allowlist": ["example.gov"]}, "web_crawl")

    def test_rejects_bad_query_param_name(self):
        with pytest.raises(SpecValidationError, match="query_param_name"):
            validate_extra(
                {"domains_allowlist": ["example.com"], "query_param_name": "bad name"},
                "web_crawl",
            )


# === validate_spec / validate_spec_strict ===========================

def _ok_spec():
    return {
        "request": "test",
        "sources": [
            {
                "type": "rest_api",
                "url": "https://api.example.com/data.json",
                "format": "json",
                "extra": {"verify_ssl": True},
            }
        ],
        "transformations": [],
        "outputs": [{"kind": "hyper", "name": "test_output"}],
        "qa_tier": "deterministic",
        "eval_strategy": "sample_validation",
        "refresh_cadence": "daily",
    }


class TestValidateSpec:
    def test_minimal_valid_spec(self):
        assert validate_spec(_ok_spec()) == []

    def test_strict_returns_spec(self):
        spec = _ok_spec()
        assert validate_spec_strict(spec) is spec

    def test_rejects_missing_sources(self):
        spec = _ok_spec()
        spec["sources"] = []
        errors = validate_spec(spec)
        assert any("at least one source" in e for e in errors)

    def test_rejects_bad_source_type(self):
        spec = _ok_spec()
        spec["sources"][0]["type"] = "bogus_type"
        errors = validate_spec(spec)
        assert any("type must be one of" in e for e in errors)

    def test_rejects_file_url_in_source(self):
        spec = _ok_spec()
        spec["sources"][0]["url"] = "file:///etc/passwd"
        errors = validate_spec(spec)
        assert any("scheme" in e for e in errors)

    def test_rejects_metadata_url(self):
        spec = _ok_spec()
        spec["sources"][0]["url"] = "http://169.254.169.254/latest/meta-data/"
        errors = validate_spec(spec)
        assert any("hard-blocked" in e for e in errors)

    def test_rejects_path_traversal_output(self):
        spec = _ok_spec()
        spec["outputs"][0]["name"] = "../../etc/foo"
        errors = validate_spec(spec)
        assert any("path separators" in e for e in errors)

    def test_rejects_bad_qa_tier(self):
        spec = _ok_spec()
        spec["qa_tier"] = "extreme"
        errors = validate_spec(spec)
        assert any("qa_tier" in e for e in errors)

    def test_rejects_bad_eval_strategy(self):
        spec = _ok_spec()
        spec["eval_strategy"] = "vibes"
        errors = validate_spec(spec)
        assert any("eval_strategy" in e for e in errors)

    def test_rejects_bad_cadence(self):
        spec = _ok_spec()
        spec["refresh_cadence"] = "fortnightly"
        errors = validate_spec(spec)
        assert any("refresh_cadence" in e for e in errors)

    def test_rejects_dotdot_in_source_path(self):
        spec = _ok_spec()
        spec["sources"][0] = {
            "type": "local_folder",
            "path": "../../etc/passwd",
            "format": "csv",
        }
        errors = validate_spec(spec)
        assert any(".." in e for e in errors)

    def test_strict_raises(self):
        spec = _ok_spec()
        spec["outputs"][0]["name"] = "../../bad"
        with pytest.raises(SpecValidationError):
            validate_spec_strict(spec)

    def test_strict_collects_all_errors(self):
        spec = _ok_spec()
        spec["sources"][0]["url"] = "file:///etc/passwd"
        spec["outputs"][0]["name"] = "../../bad"
        spec["qa_tier"] = "extreme"
        try:
            validate_spec_strict(spec)
            pytest.fail("expected SpecValidationError")
        except SpecValidationError as e:
            assert len(e.errors) >= 3


# === safe_*_dict ====================================================

class TestSafeDictGuards:
    def test_source_accepts_known(self):
        d = {"type": "rest_api", "url": "https://x.com", "format": "json"}
        assert safe_source_dict(d) is d

    def test_source_rejects_unknown(self):
        with pytest.raises(SpecValidationError, match="unknown fields"):
            safe_source_dict({
                "type": "rest_api",
                "url": "https://x.com",
                "INTERNAL_BACKDOOR_FLAG": True,
            })

    def test_output_rejects_unknown(self):
        with pytest.raises(SpecValidationError, match="unknown fields"):
            safe_output_dict({"kind": "hyper", "name": "x", "evil": 1})

    def test_source_rejects_non_dict(self):
        with pytest.raises(SpecValidationError, match="must be a dict"):
            safe_source_dict("not a dict")  # type: ignore[arg-type]
