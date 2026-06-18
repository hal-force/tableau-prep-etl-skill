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
    "year", "month", "day", "count", "_id",
    # Note: bare "id" was here historically but mis-fires on string-id
    # columns like HIFLD's `ID` (which holds e.g. "100123" but as a
    # string). Callers can pin the type with `arcgis_field_types: ID: int`
    # if they really do mean an integer ID. The `_id` suffix still fires
    # for `record_id`, `event_id`, etc. via the underscore-bounded check.
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


# Known names that English-trail with the suffix "date" but are NOT
# date columns. Any column whose lowercased name ENDS in one of these
# blocks the date heuristic outright. Add to this list whenever a real
# spec hits a misfire - safer than reverse-engineering English morphology.
_DATE_SUFFIX_BLOCKLIST = (
    "candidate", "candidates",
    "todate", "to_date", "month_to_date", "year_to_date",
    "update", "updates", "mandate", "mandates",
    "validate", "invalidate", "consolidate",
    "accommodate", "intimidate", "inundate",
    "elucidate",
)


def _ends_with_word(name: str, word: str) -> bool:
    """`name` ends with `word` on a word boundary.

    A word boundary is one of:
      - exact match (n == w)
      - the suffix already begins with '_' (e.g. `_dt`, `_id`, `_date`)
        and `n.endswith(w)` -- the underscore IS the boundary
      - the suffix is bare (no leading '_') and the char before it in
        `n` is '_' -- e.g. `report` + `date` matches `report_date`.

    CamelCase boundaries are deliberately NOT honored here - too many
    English words trail in 'date' (Candidate, ToDate, Update, Mandate).
    Concrete-name datetime columns (e.g. `FireDiscoveryDateTime`) get
    matched via _CAMEL_DT_SUFFIXES, which is allow-listed and case-aware
    on the original name (not the lowercased one)."""
    n = name.lower()
    w = word.lower()
    if not n or not w:
        return False
    if n == w:
        return True
    if not n.endswith(w):
        return False
    # Suffix that already starts with '_' carries its own boundary.
    if w.startswith("_"):
        return True
    # Otherwise require the preceding char in `n` to be '_'.
    prev = n[-len(w) - 1]
    return prev == "_"


# CamelCase datetime suffixes worth auto-casting - these are unambiguous
# (no English word ends in them). All match against the ORIGINAL-case
# column name (not the lowercased version) so we genuinely recognize
# CamelCase boundaries: `FireDiscoveryDateTime` matches `DateTime`,
# `containmentdatetime` (lowercased) does NOT match `DateTime` and
# falls through to the underscore-bounded `_DATETIME_SUFFIXES` check.
_CAMEL_DT_SUFFIXES = ("DateTime", "Timestamp")


def detect_cast(column_name: str) -> Optional[str]:
    """Return a Maestro type string for `column_name` if a heuristic
    fires, else None. Datetime check runs before date so '_datetime'
    doesn't get misclassified as a plain date.

    Suffix matches require word-boundary semantics:
      - underscore-bounded (e.g. `report_date`, `event_dt`)
      - exact match (e.g. `date`)
      - CamelCase tails matching `_CAMEL_DT_SUFFIXES` (e.g.
        `FireDiscoveryDateTime` -> datetime). The CamelCase list is
        allow-listed and short on purpose - English words trailing in
        'date' (Candidate, ToDate, Update) blow up otherwise.

    The `_DATE_SUFFIX_BLOCKLIST` guards against known English-word
    collisions before any `date` heuristic fires. Caller can always
    force a cast by declaring the type in source.extra.arcgis_field_types
    / csv_schema - those declared types are honored verbatim."""
    n = _norm(column_name)
    if not n:
        return None
    # 0) Block known false positives outright.
    for blk in _DATE_SUFFIX_BLOCKLIST:
        if n.endswith(blk):
            return None
    # 1) CamelCase datetime tails (case-sensitive on original name)
    for cs in _CAMEL_DT_SUFFIXES:
        if column_name and column_name.endswith(cs) and len(column_name) > len(cs):
            # Boundary check: char before cs must be lowercase (so
            # `FireDiscoveryDateTime` matches but `DATETIME` alone does
            # not -- it'll match via the underscore branch instead).
            prev = column_name[-len(cs) - 1]
            if prev.islower():
                return "datetime"
    # 2) Underscore-bounded datetime suffixes
    for suf in _DATETIME_SUFFIXES:
        if _ends_with_word(n, suf):
            return "datetime"
    # 3) Underscore-bounded date suffixes
    for suf in _DATE_SUFFIXES:
        if _ends_with_word(n, suf):
            return "date"
    if n in _INT_KEYWORDS:
        return "int"
    for kw in _DECIMAL_KEYWORDS:
        if n == kw or _ends_with_word(n, kw):
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
