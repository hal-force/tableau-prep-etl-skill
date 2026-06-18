"""
Cast / semantic-role planner.

Given a source's declared columns (or a regular schema dict), pick:
  * Tableau Prep column-type casts (string|date|datetime|int|decimal|bool)
  * geographic + URL semantic roles (state/city/country/postal_code, url)

Heuristics fire on column-name suffix/keyword matches; explicit per-spec
overrides under `source.extra.casts` and `source.extra.semantic_roles`
take precedence so users can correct or extend the auto-detection
without editing this module.

Public entry points:
  plan_casts_for_columns(columns, overrides) -> dict[col, type_str]
  plan_semantic_roles_for_columns(columns, overrides) -> dict[col, (role_id, role_name)]
  semantic_role_lookup(role_name) -> (role_id, role_name)
"""
from __future__ import annotations

from typing import Iterable, Optional

# --- Semantic role registry ---
# Tableau's role IDs are stable across versions; the 5 below are what
# Prep Builder emits when you right-click a column and pick a geographic
# / URL role from the canvas. `name` is what shows in the Tableau pill.
SEMANTIC_ROLES: dict[str, tuple[str, str]] = {
    "state":       ("global/geo/state",       "state"),
    "province":    ("global/geo/state",       "state"),
    "city":        ("global/geo/city",        "city"),
    "country":     ("global/geo/country",     "country"),
    "postal_code": ("global/geo/postal_code", "postal_code"),
    "postcode":    ("global/geo/postal_code", "postal_code"),
    "zip":         ("global/geo/postal_code", "postal_code"),
    "url":         ("global/resource/url",    "url"),
}

# --- Cast heuristics ---
# Column-name keywords → Maestro type. Order matters when keywords
# overlap; we check `endswith` first (more specific suffix wins) then
# exact matches (lowercased).
_DATETIME_SUFFIXES = (
    "datetime", "_datetime", "_dt", "_at", "_ts",
    "timestamp", "_timestamp",
    "rep_date", "report_datetime",  # YRP: report-time has a real timestamp
)
_DATE_SUFFIXES = (
    "_date", "date", "occ_date", "occurrence_date", "report_date",
)
_INT_KEYWORDS = (
    "year", "month", "day", "count", "_id", "id",
)
_DECIMAL_KEYWORDS = (
    "lat", "latitude", "lon", "long", "longitude",
    "_pct", "_percent", "rate", "amount", "score", "value",
)

# Geographic semantic roles use exact-name match (case-insensitive)
# because partial keywords overfire on columns like "country_code"
# (which is a string, not a `country` semantic role itself).
_GEO_NAME_MATCHES: dict[str, str] = {
    "state": "state",
    "province": "province",
    "us_state": "state",
    "city": "city",
    "country": "country",
    "country_name": "country",
    "postal_code": "postal_code",
    "postalcode": "postal_code",
    "zip": "zip",
    "zip_code": "zip",
    "zipcode": "zip",
}
_URL_NAME_MATCHES: dict[str, str] = {
    "url": "url",
    "homepage": "url",
    "website": "url",
    "link": "url",
    "source_url": "url",
    "sourceurl": "url",
    "entity_url": "url",
}


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def detect_cast(column_name: str) -> Optional[str]:
    """Return a Maestro type string for `column_name` if a heuristic
    fires, else None. Datetime check runs before date so '_datetime'
    doesn't get misclassified as a plain date."""
    n = _norm(column_name)
    if not n:
        return None
    # datetime first — its suffixes are strict supersets of date's
    for suf in _DATETIME_SUFFIXES:
        if n == suf or n.endswith(suf):
            return "datetime"
    for suf in _DATE_SUFFIXES:
        if n == suf or n.endswith(suf):
            return "date"
    if n in _INT_KEYWORDS:
        return "int"
    for kw in _DECIMAL_KEYWORDS:
        if n == kw or n.endswith("_" + kw) or n.endswith(kw):
            return "decimal"
    return None


def detect_semantic_role(column_name: str) -> Optional[tuple[str, str]]:
    """Return (role_id, role_name) for `column_name` if a heuristic
    matches, else None. Returns None for obvious code-style columns
    like `country_code` to avoid mis-tagging them as geographic
    drill-up roles (a country code is a string, not a role)."""
    n = _norm(column_name)
    if not n:
        return None
    if n in _GEO_NAME_MATCHES:
        key = _GEO_NAME_MATCHES[n]
        return SEMANTIC_ROLES[key]
    if n in _URL_NAME_MATCHES:
        return SEMANTIC_ROLES["url"]
    return None


def semantic_role_lookup(role_name: str) -> Optional[tuple[str, str]]:
    """Resolve a user-supplied role name (e.g. 'state', 'postal_code',
    'url') to a Maestro (role_id, role_name) pair. Used when the spec
    overrides the heuristic by stating a column's role explicitly."""
    return SEMANTIC_ROLES.get(_norm(role_name))


def plan_casts_for_columns(
    columns: Iterable[str],
    overrides: Optional[dict] = None,
) -> dict[str, str]:
    """Build {col: type} for the given columns. `overrides` (from
    `source.extra.casts`) wins over heuristics and can also set a cast
    that the heuristics would have skipped."""
    overrides = overrides or {}
    out: dict[str, str] = {}
    for col in columns:
        if col in overrides:
            out[col] = overrides[col]
            continue
        detected = detect_cast(col)
        if detected is not None:
            out[col] = detected
    # Add overrides for columns that weren't in the input list (lets
    # users force a cast on a derived/renamed column).
    for col, t in overrides.items():
        out.setdefault(col, t)
    return out


def plan_semantic_roles_for_columns(
    columns: Iterable[str],
    overrides: Optional[dict] = None,
) -> dict[str, tuple[str, str]]:
    """Build {col: (role_id, role_name)}. `overrides` is a dict of
    {col: role_name} where role_name is one of SEMANTIC_ROLES' keys
    (state/province/city/country/postal_code/zip/url). Unknown role
    names are silently dropped."""
    overrides = overrides or {}
    out: dict[str, tuple[str, str]] = {}
    for col in columns:
        if col in overrides:
            resolved = semantic_role_lookup(overrides[col])
            if resolved is not None:
                out[col] = resolved
            continue
        detected = detect_semantic_role(col)
        if detected is not None:
            out[col] = detected
    for col, role in overrides.items():
        if col in out:
            continue
        resolved = semantic_role_lookup(role)
        if resolved is not None:
            out[col] = resolved
    return out
