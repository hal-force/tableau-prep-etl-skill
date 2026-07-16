"""
Spec validation: defensive gate between LLM/archive-supplied JSON and
generated Python. Importable from intake.py and run_loop.py so both
the LLM intake path and the `--spec` archive-load path go through one
shared boundary.

Threat model summary (full doc in `skill/reference/security.md`):
  - LLM-derived URLs end up in `API_URL = "{{ url }}"` and on
    `urlrequest.urlopen(...)` calls — must reject non-HTTP schemes,
    cloud-metadata endpoints, and unscoped private-IP targets.
  - LLM-derived output names land in `outputs_dir / o.name` — must
    reject any non-leaf path.
  - LLM-derived regex (api_caller.INDEX_LINK_PATTERN) is fed to
    `re.findall(...)` — must reject obviously catastrophic patterns.

This module defines pure validators (no IO). The host-approval flow
(LLM-backed pre-flight + first-time prompt) lives in `host_trust.py`.

Public surface:
  validate_url(url)          -> normalized_url
  validate_relative_path(p)  -> p
  validate_output_name(n)    -> n
  validate_regex(pat)        -> compiled regex
  validate_extra(extra, t)   -> sanitized extra dict + warnings
  validate_spec(spec_dict)   -> list[str]   (back-compat shape)
  validate_spec_strict(d)    -> raises SpecValidationError on failure

`validate_spec` returns a list of error strings so it slots in next to
the existing `_validate_spec` in intake.py without rewiring callers.
`validate_spec_strict` is the new entry point used by run_loop on
archive load.
"""
from __future__ import annotations

import ipaddress
import os
import re
import signal
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse


SOURCE_TYPES = (
    "local_folder", "native_connector", "rest_api", "graphql_api",
    "web_crawl", "pki_endpoint", "internal_published_ds",
)
QA_TIERS = ("none", "deterministic", "llm")
EVAL_STRATEGIES = (
    "extract_from_source", "sample_validation", "synthesized",
    "user_supplied", "self_consistency",
)
REFRESH_CADENCES = ("once", "hourly", "every_3_hours", "every_6_hours",
                    "daily", "weekly", "monthly", "on_demand")
OUTPUT_KINDS = ("hyper", "csv", "published_data_source")


class SpecValidationError(ValueError):
    """Raised when validate_spec_strict finds a violation."""

    def __init__(self, message: str, *, errors: Optional[list[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


# === URL / SSRF guard ================================================

# Hard-block: cloud-metadata services + the canonical loopback hosts.
# An LLM should never legitimately need to reach these from a spec.
_HARD_BLOCK_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata.aws.com",
    "metadata.azure.com",
    "169.254.169.254",                  # AWS / GCP / Azure IMDS v1
    "fd00:ec2::254",                    # AWS IMDSv2 IPv6
    "localhost",
})


def _is_hard_block_ip(ip: ipaddress._BaseAddress) -> bool:
    """Loopback + the AWS/GCP IMDS v4 link-local."""
    if ip.is_loopback:
        return True
    if ip.is_unspecified:
        return True
    # IPv4 link-local 169.254.0.0/16: AWS / Azure / GCP cloud-metadata
    # all live here. Everything in the link-local range is hard-blocked.
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.IPv4Network("169.254.0.0/16"):
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.is_link_local:
        return True
    return False


def _is_private_ip(ip: ipaddress._BaseAddress) -> bool:
    """RFC1918 + ULA. Soft-blocked unless internal-trust marker matches."""
    return ip.is_private and not ip.is_loopback and not ip.is_link_local


def _internal_trust_suffixes() -> list[str]:
    """Hosts whose suffix grants RFC1918 / soft-block bypass.

    Sources, in order:
      1. `$TABLEAU_SERVER_URL` host (so the user's own site / on-prem
         warehouse cluster is reachable).
      2. `~/.tableau-prep-etl/internal_hosts.txt` (one suffix per line,
         '#' for comments). Edit this file to extend trust.
    """
    suffixes: list[str] = []
    server_url = os.environ.get("TABLEAU_SERVER_URL", "").strip()
    if server_url:
        try:
            host = (urlparse(server_url).hostname or "").strip().lower()
            if host:
                suffixes.append(host)
        except Exception:
            pass
    cfg = Path.home() / ".tableau-prep-etl" / "internal_hosts.txt"
    try:
        if cfg.exists():
            for raw in cfg.read_text().splitlines():
                line = raw.strip().lower()
                if line and not line.startswith("#"):
                    suffixes.append(line)
    except Exception:
        pass
    return suffixes


def _host_matches_internal_trust(host: str) -> bool:
    h = (host or "").strip().lower()
    if not h:
        return False
    for suf in _internal_trust_suffixes():
        if h == suf or h.endswith("." + suf):
            return True
    return False


def validate_url(
    url: str,
    *,
    allow_schemes: Iterable[str] = ("http", "https"),
    label: str = "url",
) -> str:
    """Reject URLs that look like SSRF targets, malformed URIs, or
    schemes outside the allowlist. Returns the normalized URL on
    success. Raises SpecValidationError otherwise.

    Note: this does NOT prompt for first-time host approval — that's
    `host_trust.ensure_host_approved`. This function is purely a
    static gate. The two run in sequence: validate_url first
    (hard-rejects garbage), then host_trust (interactive trust).
    """
    if not isinstance(url, str) or not url:
        raise SpecValidationError(f"{label} is empty or not a string")

    if any(c in url for c in "\r\n\t\x00"):
        raise SpecValidationError(
            f"{label} contains control characters (\\r/\\n/\\t/NUL); "
            "likely an injection attempt or copy-paste artifact"
        )

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SpecValidationError(f"{label} could not be parsed: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in tuple(allow_schemes):
        raise SpecValidationError(
            f"{label} scheme {scheme!r} not in allowlist {tuple(allow_schemes)!r}"
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise SpecValidationError(f"{label} missing host")

    if host in _HARD_BLOCK_HOSTS:
        raise SpecValidationError(
            f"{label} host {host!r} is hard-blocked (cloud-metadata / loopback)"
        )

    # IP-literal hosts bypass DNS, so check directly. Hostnames are
    # left to the host_trust layer (which can also resolve + check).
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if _is_hard_block_ip(ip):
            raise SpecValidationError(
                f"{label} resolves to hard-blocked IP {ip!s} "
                "(loopback / link-local / cloud-metadata)"
            )
        if _is_private_ip(ip):
            # Soft block: allowed only when internal trust covers it.
            # IP-literal trust means "the operator wrote a literal IP
            # in internal_hosts.txt" or set TABLEAU_SERVER_URL to one.
            if not _host_matches_internal_trust(str(ip)):
                raise SpecValidationError(
                    f"{label} targets private IP {ip!s} but is not covered "
                    "by an internal-trust marker (TABLEAU_SERVER_URL / "
                    "~/.tableau-prep-etl/internal_hosts.txt)"
                )

    return url


# === Path / output name guards ======================================

# Reject only true traversal / shell-injection signals. Spaces, parens,
# and unicode letters are allowed because existing archived specs use
# display names like "CISA KEV Detail" — the actual vectors we care
# about are `/`, `\`, `..`, NUL, and control / shell metachars.
_OUTPUT_NAME_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f/\\<>|;&`$\*\?\"']")


def validate_output_name(name: str, *, label: str = "output.name") -> str:
    """Reject anything that isn't a clean, single-segment basename.

    The skill plugs `name` into `outputs_dir / name`. An LLM-supplied
    `../../etc/passwd` would otherwise resolve outside the intended
    runtime dir.
    """
    if not isinstance(name, str) or not name:
        raise SpecValidationError(f"{label} is empty or not a string")
    if len(name) > 128:
        raise SpecValidationError(f"{label}={name!r} exceeds 128 chars")
    if name != Path(name).name:
        raise SpecValidationError(
            f"{label}={name!r} contains path separators; must be a "
            "single filename component"
        )
    if ".." in name:
        raise SpecValidationError(
            f"{label}={name!r} contains '..'; path traversal not allowed"
        )
    if name.startswith(".") or name.endswith("."):
        raise SpecValidationError(
            f"{label}={name!r} cannot start or end with '.'"
        )
    m = _OUTPUT_NAME_FORBIDDEN.search(name)
    if m:
        raise SpecValidationError(
            f"{label}={name!r} contains forbidden character {m.group(0)!r} "
            "(path separator / control / shell metacharacter)"
        )
    return name


def validate_relative_path(p: str, *, label: str = "path") -> str:
    """Reject path-traversal in spec.sources[*].path.

    Source paths CAN be absolute (a user pointing the skill at
    /Users/me/data/x.csv is normal), so the rule is narrower than for
    output names: no `..` segments, no NUL/control chars, no embedded
    newlines. Symlink walking is the OS's job, not ours.
    """
    if not isinstance(p, str):
        raise SpecValidationError(f"{label} is not a string")
    if "\x00" in p or "\r" in p or "\n" in p:
        raise SpecValidationError(f"{label} contains control characters")
    parts = [seg for seg in re.split(r"[/\\]", p) if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise SpecValidationError(
            f"{label}={p!r} contains '..' segment; path traversal not allowed"
        )
    return p


# === ReDoS guard ====================================================

# Patterns that are obviously catastrophic. Not exhaustive — the
# alarm-ringer compile-timeout below is the safety belt.
_REDOS_RED_FLAGS = (
    re.compile(r"\(\.?\*\)\+"),       # (.*)+
    re.compile(r"\(\.?\+\)\+"),       # (.+)+
    re.compile(r"\(\.?\*\)\*"),       # (.*)*
    re.compile(r"\(\.?\+\)\*"),       # (.+)*
    re.compile(r"\(\[[^\]]*\]\*\)\+"),  # ([abc]*)+
    re.compile(r"\(\[[^\]]*\]\+\)\+"),  # ([abc]+)+
)


def validate_regex(pat: str, *, label: str = "pattern", max_compile_ms: int = 50):
    """Compile `pat` under a wall-clock budget; reject obvious
    backtracking-bomb shapes outright.

    Returns the compiled regex on success; raises SpecValidationError
    otherwise. SIGALRM is POSIX-only; on platforms without it (Windows)
    we skip the timer and rely on shape detection alone.
    """
    if not isinstance(pat, str):
        raise SpecValidationError(f"{label} is not a string")
    if len(pat) > 1024:
        raise SpecValidationError(
            f"{label} pattern exceeds 1024 chars; likely a copy-paste error"
        )
    for rx in _REDOS_RED_FLAGS:
        if rx.search(pat):
            raise SpecValidationError(
                f"{label}={pat!r} matches a known catastrophic-backtracking "
                "shape (nested unbounded quantifier)"
            )

    if hasattr(signal, "SIGALRM"):
        def _on_alarm(_signum, _frame):
            raise TimeoutError("regex compile exceeded budget")

        prev = signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, max_compile_ms / 1000.0)
        try:
            compiled = re.compile(pat)
        except TimeoutError:
            raise SpecValidationError(
                f"{label} compile exceeded {max_compile_ms}ms; refusing to use"
            )
        except re.error as e:
            raise SpecValidationError(f"{label} did not compile: {e}")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prev)
        return compiled

    try:
        return re.compile(pat)
    except re.error as e:
        raise SpecValidationError(f"{label} did not compile: {e}")


# === extra-dict whitelist ===========================================

# Per-source-type known keys. Unknown keys aren't a hard error
# (templates evolve faster than this list), but they're flagged in
# the warnings list so reviewers see them.
_EXTRA_KEYS_BY_TYPE: dict[str, frozenset[str]] = {
    "rest_api": frozenset({
        "verify_ssl", "timeout_s", "max_retries", "country_filter",
        "index_link_pattern", "arcgis_where", "arcgis_out_fields",
        "arcgis_page_size", "arcgis_max_records", "arcgis_return_geometry",
        "arcgis_out_sr", "arcgis_geometry_kind", "arcgis_field_types",
        "csv_encoding", "csv_rename_map", "csv_schema", "csv_usecols",
        "csv_zip_member", "json_schema", "json_http_method", "json_body",
        "json_records_path", "json_flatten_inner_key",
        "json_flatten_parent_keys", "json_derived_columns",
        "json_array_columns", "json_paginate", "json_page_param",
        "json_page_size_param", "json_page_size", "json_page_start",
        "json_page_kind", "json_max_pages", "json_page_in_body",
        "json_has_next_path", "api_key_env", "user_env", "pwd_env",
        "max_response_bytes", "max_response_rows",
        # query_key auth (EIA v2 / NREL / Data.gov style: `?api_key=…`)
        "query_key_param_name",
        # XML source knobs (OFAC SDN, EU sanctions, RSS/Atom feeds)
        "xml_entry_path", "xml_strip_ns",
        # ACLED-specific
        "email_env", "lookback_days", "page_size", "max_pages", "max_rows",
        "acled_query_params",
    }),
    "graphql_api": frozenset({
        "query", "verify_ssl", "timeout_s", "max_retries",
        "max_response_bytes",
    }),
    "web_crawl": frozenset({
        "engine", "query_param_name", "max_results_per_run",
        "domains_allowlist", "browser_timeout_s", "max_response_bytes",
        "search_engine_host",
    }),
    "pki_endpoint": frozenset({
        "cert_path_env", "cert_key_env", "timeout_s",
    }),
    "local_folder": frozenset({
        "include_glob", "exclude_glob", "encoding", "format_hint",
    }),
    "native_connector": frozenset({
        "connector_id", "datasource_name", "project", "site",
    }),
    "internal_published_ds": frozenset({
        "luid", "datasource_name", "project", "site",
        # `_pds_*` keys are populated at runtime by the extract
        # downloader (Phase 4a); they're not user-supplied but they
        # land in spec.json on archive, so accept them on reload.
        "_pds_local_csv_path", "_pds_local_hyper_path",
        "_pds_actual_ds_name", "_pds_actual_project", "_pds_row_count",
    }),
}


def validate_extra(extra: dict, source_type: str, *, label: str = "source.extra") -> tuple[dict, list[str]]:
    """Return (sanitized_extra, warnings). Unknown keys generate
    warnings; structurally-bad extras (non-dict, deeply-nested
    surprises) raise."""
    if extra is None:
        return {}, []
    if not isinstance(extra, dict):
        raise SpecValidationError(f"{label} must be a dict, got {type(extra).__name__}")

    known = _EXTRA_KEYS_BY_TYPE.get(source_type, frozenset())
    warnings: list[str] = []
    for k in extra.keys():
        if not isinstance(k, str):
            raise SpecValidationError(f"{label} has non-string key {k!r}")
        if known and k not in known:
            warnings.append(f"unknown {label} key {k!r} for source type {source_type!r}")

    # Per-key shape validation for the security-load-bearing fields.
    if source_type == "rest_api":
        ilp = extra.get("index_link_pattern")
        if ilp:
            validate_regex(ilp, label=f"{label}.index_link_pattern")
        if "verify_ssl" in extra and not isinstance(extra["verify_ssl"], bool):
            raise SpecValidationError(f"{label}.verify_ssl must be bool")
    if source_type == "web_crawl":
        allowlist = extra.get("domains_allowlist")
        if allowlist is not None:
            if not isinstance(allowlist, list) or not all(isinstance(d, str) for d in allowlist):
                raise SpecValidationError(f"{label}.domains_allowlist must be list[str]")
            if not allowlist:
                # Empty list is the same as missing — refuse so generated
                # crawler scripts can't fan out unrestricted.
                raise SpecValidationError(
                    f"{label}.domains_allowlist is empty; web_crawl sources "
                    "must declare at least one allowed domain"
                )
        qp = extra.get("query_param_name")
        if qp is not None and not (isinstance(qp, str) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", qp)):
            raise SpecValidationError(
                f"{label}.query_param_name={qp!r} must be a Python identifier"
            )

    return extra, warnings


# === Top-level spec validator =======================================

def validate_spec(spec_dict: dict) -> list[str]:
    """Return a list of error strings. Empty list = valid.

    Back-compat shape: callers in intake.py treat empty-list as success
    and flatten the rest into an IntakeIncomplete message. New callers
    should prefer validate_spec_strict, which raises with structured
    error info.
    """
    try:
        validate_spec_strict(spec_dict)
        return []
    except SpecValidationError as e:
        return list(e.errors)


def validate_spec_strict(spec_dict: dict) -> dict:
    """Walk the spec, gather every issue, raise once. Returns the
    spec dict unchanged on success.
    """
    errors: list[str] = []

    sources = spec_dict.get("sources") or []
    if not sources:
        errors.append("at least one source required")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []

    for i, s in enumerate(sources):
        prefix = f"source[{i}]"
        if not isinstance(s, dict):
            errors.append(f"{prefix} must be a dict")
            continue
        st = s.get("type")
        if st not in SOURCE_TYPES:
            errors.append(f"{prefix}.type must be one of {SOURCE_TYPES}")
            continue
        url = s.get("url") or ""
        if url:
            try:
                validate_url(url, label=f"{prefix}.url")
            except SpecValidationError as e:
                errors.append(str(e))
        path = s.get("path") or ""
        if path:
            try:
                validate_relative_path(path, label=f"{prefix}.path")
            except SpecValidationError as e:
                errors.append(str(e))
        try:
            validate_extra(s.get("extra") or {}, st, label=f"{prefix}.extra")
        except SpecValidationError as e:
            errors.append(str(e))

    if spec_dict.get("qa_tier") not in QA_TIERS:
        errors.append(f"qa_tier must be one of {QA_TIERS}")
    if spec_dict.get("eval_strategy") not in EVAL_STRATEGIES:
        errors.append(f"eval_strategy must be one of {EVAL_STRATEGIES}")
    cadence = spec_dict.get("refresh_cadence", "once")
    if cadence not in REFRESH_CADENCES:
        errors.append(f"refresh_cadence must be one of {REFRESH_CADENCES}")

    outputs = spec_dict.get("outputs") or []
    if not outputs:
        errors.append("at least one output required")
    if not isinstance(outputs, list):
        errors.append("outputs must be a list")
        outputs = []
    for i, o in enumerate(outputs):
        prefix = f"output[{i}]"
        if not isinstance(o, dict):
            errors.append(f"{prefix} must be a dict")
            continue
        kind = o.get("kind")
        if kind not in OUTPUT_KINDS:
            errors.append(f"{prefix}.kind must be one of {OUTPUT_KINDS}")
        name = o.get("name") or ""
        try:
            validate_output_name(name, label=f"{prefix}.name")
        except SpecValidationError as e:
            errors.append(str(e))

    if errors:
        raise SpecValidationError(
            "spec validation failed: " + "; ".join(errors),
            errors=errors,
        )
    return spec_dict


# === Source-dataclass guarded constructor ===========================

# Whitelist of fields the LLM is allowed to set on Source/Output/etc.
# Any extra key is rejected — prevents an LLM-introduced field name
# from sneaking into an internal flag or breaking dataclass init.
_SOURCE_FIELDS = frozenset({
    "type", "path", "url", "format", "auth", "extra", "name", "description",
})
_OUTPUT_FIELDS = frozenset({
    "kind", "name", "path", "description", "source", "project",
})
_TRANSFORM_FIELDS = frozenset({"kind", "args"})


def safe_source_dict(d: dict) -> dict:
    """Pre-coerce + reject-unknown for Source(**...). Raises on extras."""
    if not isinstance(d, dict):
        raise SpecValidationError("source entry must be a dict")
    extras = set(d.keys()) - _SOURCE_FIELDS
    if extras:
        raise SpecValidationError(
            f"source has unknown fields: {sorted(extras)!r}"
        )
    return d


def safe_output_dict(d: dict) -> dict:
    if not isinstance(d, dict):
        raise SpecValidationError("output entry must be a dict")
    extras = set(d.keys()) - _OUTPUT_FIELDS
    if extras:
        raise SpecValidationError(
            f"output has unknown fields: {sorted(extras)!r}"
        )
    return d


def safe_transform_dict(d: dict) -> dict:
    if not isinstance(d, dict):
        raise SpecValidationError("transformation entry must be a dict")
    extras = set(d.keys()) - _TRANSFORM_FIELDS
    if extras:
        raise SpecValidationError(
            f"transformation has unknown fields: {sorted(extras)!r}"
        )
    return d
