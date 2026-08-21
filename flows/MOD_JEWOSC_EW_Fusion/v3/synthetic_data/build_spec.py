#!/usr/bin/env python3
"""
Build v3/spec.json for the MOD JEWOSC EW multi-source fusion flow.

v3 rebuilds v2 to DEMONSTRATE FUSION as visible Prep join nodes rather than
baking every reference table into one monolithic Script node. The honest split:

  * MODELLING (Python, unavoidable) — nearest-neighbour parametric match of a
    measured cut's freq/PRI/PW to the emitter fingerprint. Nearest-neighbour is
    not equality, so it can't be a native join. This node emits `emitter_id`
    (the join key) + match_quality + reprogramming-trigger + own-ship geometry.
    Only the numeric fingerprint (emitter_id + freq/PRI/PW) is baked here.

  * FUSION (native Prep SuperJoins) — three reference tables, each keyed 1:1 on
    emitter_id, joined onto the matched intercepts:
      1. threat_library    — the descriptive emitter record (NATO name, system
                             type, lethality, weapon, priority, library parametrics)
      2. eob_rollup        — per-emitter EOB laydown rollup (site count,
                             affiliation summary, confirmed/active counts)
      3. platform_coverage — per-emitter MDF coverage gap (how many platforms
                             are blind to this emitter, and which)

All three are 1:1 on emitter_id so chained leftOuter joins preserve the
one-row-per-intercept grain. leftOuter (not inner) so unknown/changed cuts
(emitter_id "") flow through with NULL enrichment — a threat with no library
record is itself the reprogramming-trigger signal.

Deterministic: reads committed CSVs, derives the three reference products, and
emits a stable spec.json. No network, no clock. Re-run whenever the synthetic
data is regenerated.
"""
import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
SPEC_PATH = V3 / "spec.json"

# Own-ship reference — matches generate_synthetic_ew.py.
OWN_SHIP_LAT, OWN_SHIP_LON = 55.10, 18.30
OWN_SHIP_LABEL = "BLUE-ISR ORBIT ALPHA"

# Per-column type coercion for the reference tables.
NUM_FLOAT = {"centre_freq_ghz", "pri_us", "pw_us", "scan_period_s", "erp_dbw", "lat", "lon"}
NUM_INT = {"max_range_km", "priority", "last_seen_days",
           "mdf_load_days_ago", "reprogram_cycle_days", "coverage_count"}


def _coerce(col, val):
    if col in NUM_FLOAT:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    if col in NUM_INT:
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return None
    return val


def read_ref(name):
    rows = []
    with (HERE / name).open(newline="") as f:
        for r in csv.DictReader(f):
            rows.append({k: _coerce(k, v) for k, v in r.items()})
    return rows


def write_csv(name, rows, fieldnames):
    with (HERE / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    return HERE / name


# --- Reference-product builders (all keyed 1:1 on emitter_id) -----------------

def build_fingerprints(emitters):
    """The minimal numeric signature baked into the match node."""
    return [
        {"emitter_id": e["emitter_id"],
         "centre_freq_ghz": e["centre_freq_ghz"],
         "pri_us": e["pri_us"],
         "pw_us": e["pw_us"]}
        for e in emitters
    ]


def build_threat_library(emitters):
    """The descriptive emitter record — 1 row per emitter. Joined onto matched
    intercepts to fuse the library attributes the match node deliberately does
    not carry. Prefix the parametrics as lib_* so they read as 'library value'
    next to the intercept's measured value in the fused output."""
    cols = ["emitter_id", "lib_nato_name", "lib_system_type", "lib_band",
            "lib_centre_freq_ghz", "lib_pri_us", "lib_pw_us", "lib_scan_type",
            "lib_erp_dbw", "lib_modes", "lib_lethality", "lib_assoc_weapon",
            "lib_max_range_km", "lib_threat_priority"]
    rows = []
    for e in emitters:
        rows.append({
            "emitter_id":          e["emitter_id"],
            "lib_nato_name":       e.get("nato_name", ""),
            "lib_system_type":     e.get("system_type", ""),
            "lib_band":            e.get("band", ""),
            "lib_centre_freq_ghz": e.get("centre_freq_ghz"),
            "lib_pri_us":          e.get("pri_us"),
            "lib_pw_us":           e.get("pw_us"),
            "lib_scan_type":       e.get("scan_type", ""),
            "lib_erp_dbw":         e.get("erp_dbw"),
            "lib_modes":           e.get("modes", ""),
            "lib_lethality":       e.get("lethality", "none"),
            "lib_assoc_weapon":    e.get("assoc_weapon", "-"),
            "lib_max_range_km":    e.get("max_range_km"),
            "lib_threat_priority": e.get("priority"),
        })
    return rows, cols


def build_eob_rollup(emitters, eob_sites):
    """Per-emitter EOB laydown rollup — 1 row per emitter. Sites are 1:many per
    emitter, so we roll them up to keep the join 1:1 (a raw site join would
    fan out the intercept grain). Emitters with no known site get a zero row so
    the leftOuter still lands a record."""
    cols = ["emitter_id", "eob_site_count", "eob_primary_affiliation",
            "eob_affiliations", "eob_confirmed_count", "eob_active_count",
            "eob_site_ids", "eob_summary"]
    by_emitter = {}
    for s in eob_sites:
        by_emitter.setdefault(s.get("emitter_id"), []).append(s)
    rows = []
    for e in emitters:
        eid = e["emitter_id"]
        sites = by_emitter.get(eid, [])
        affs = [s.get("affiliation", "UNKNOWN") for s in sites]
        primary = Counter(affs).most_common(1)[0][0] if affs else "NONE"
        confirmed = sum(1 for s in sites if (s.get("confidence") or "").lower() == "confirmed")
        active = sum(1 for s in sites if (s.get("status") or "").lower() == "active")
        site_ids = "|".join(s.get("site_id", "") for s in sites)
        if sites:
            summary = (f"{len(sites)} known site(s), primary affiliation "
                       f"{primary}; {confirmed} confirmed, {active} active.")
        else:
            summary = "No known EOB site on file for this emitter."
        rows.append({
            "emitter_id":              eid,
            "eob_site_count":          len(sites),
            "eob_primary_affiliation": primary,
            "eob_affiliations":        "|".join(sorted(set(affs))),
            "eob_confirmed_count":     confirmed,
            "eob_active_count":        active,
            "eob_site_ids":            site_ids,
            "eob_summary":             summary,
        })
    return rows, cols


def build_platform_coverage(emitters, platforms):
    """Per-emitter mission-data-file coverage gap — 1 row per emitter. Counts
    how many BLUE platform MDFs do NOT list this emitter (the reprogramming
    workload), and names them."""
    cols = ["emitter_id", "mdf_covered_count", "coverage_gap_count",
            "covering_platforms", "uncovered_platforms", "coverage_summary"]
    total = len(platforms)
    rows = []
    for e in emitters:
        eid = e["emitter_id"]
        covering, uncovered = [], []
        for p in platforms:
            cov = set((p.get("coverage_emitters") or "").split("|"))
            (covering if eid in cov else uncovered).append(p.get("platform_id", ""))
        rows.append({
            "emitter_id":          eid,
            "mdf_covered_count":   len(covering),
            "coverage_gap_count":  len(uncovered),
            "covering_platforms":  "|".join(covering),
            "uncovered_platforms": "|".join(uncovered),
            "coverage_summary":    (f"{len(covering)}/{total} platform MDFs recognise "
                                    f"this emitter; {len(uncovered)} coverage gap(s)."),
        })
    return rows, cols


def intercepts_schema():
    """Declared post-read schema for intercepts.csv. Only the PRIMARY feed
    declares csv_schema — the three reference sources let LoadCsv infer types
    from their headers, so their columns don't pollute the match node's
    INPUT_SCHEMA (which is built by merging every source's csv_schema)."""
    return {
        "intercept_id": "string",
        # datetime (not string): the match node parses this to a real
        # datetime64 and emits a native Hyper TIMESTAMP, so the published DS
        # supports date math / range filters. Prep's LoadCsv auto-types the
        # ISO column and appends a "[UTC]" zone suffix en route to TabPy; the
        # coercion strips it before parsing. See ew_intercept_match.py.j2.
        "detect_time_iso": "datetime",
        "lat": "decimal",
        "lon": "decimal",
        "band": "string",
        "meas_freq_ghz": "decimal",
        "meas_pri_us": "decimal",
        "meas_pw_us": "decimal",
        "snr_db": "decimal",
        "bearing_deg_meas": "decimal",
        "sensor_id": "string",
        "truth_emitter_id": "string",
        "truth_class": "string",
    }


def main():
    emitters = read_ref("emitters.csv")
    eob_sites = read_ref("eob_sites.csv")
    platforms = read_ref("platforms.csv")

    fingerprints = build_fingerprints(emitters)
    lib_rows, lib_cols = build_threat_library(emitters)
    eob_rows, eob_cols = build_eob_rollup(emitters, eob_sites)
    cov_rows, cov_cols = build_platform_coverage(emitters, platforms)

    lib_path = write_csv("threat_library.csv", lib_rows, lib_cols)
    eob_path = write_csv("eob_rollup.csv", eob_rows, eob_cols)
    cov_path = write_csv("platform_coverage.csv", cov_rows, cov_cols)

    disclaimer = (
        "SYNTHETIC / NOTIONAL DEMONSTRATION DATA — NOT operational, NOT "
        "classified, NOT derived from any classified source. Built for a "
        "UK MoD JEWOSC maturity-evaluation demo of Tableau + the agentic "
        "Prep ETL skill. v3 demonstrates DATA FUSION as native Prep join "
        "nodes: a fuzzy parametric MATCH (modelling, Python) assigns an "
        "emitter_id, then three reference sources — threat library, EOB "
        "laydown rollup, and platform mission-data coverage — are fused "
        "onto each intercept with native SuperJoins on emitter_id. "
        "NATO-reporting-name-style emitter designations are used for "
        "audience resonance; every parametric value (frequency, PRI, pulse "
        "width, ERP, lethality, ranges) is fabricated. The Electronic Order "
        "of Battle laydown, platform mission-data coverage, and ELINT "
        "intercepts are all synthetic. Theatre: Baltic / NATO eastern flank "
        f"(notional own-ship {OWN_SHIP_LABEL!r}). GAP DECLARATION: real "
        "emitter parametrics, true EOB geolocation, and actual platform MDF "
        "contents are classified and out of scope; this flow demonstrates "
        "the FUSION WORKFLOW and OPERATIONAL PRESENTATION, not real threat data."
    )

    def ref_source(name, path, desc):
        # Reference sources: NO csv_schema (LoadCsv infers types from header),
        # so their columns don't merge into the match node's INPUT_SCHEMA.
        return {
            "type": "local_csv",
            "path": str(path),
            "format": "csv",
            "auth": "none",
            "name": name,
            "description": desc + " SYNTHETIC — notional Baltic scenario.",
            "extra": {},
        }

    spec = {
        "request": (
            "MOD JEWOSC EW intercept -> mission-data fusion (v3, native "
            "joins). A fuzzy parametric MATCH node assigns each ELINT/ES "
            "intercept cut a library emitter_id (modelling; nearest-neighbour "
            "can't be an equality join), then three reference sources — an "
            "emitter threat library, an Electronic Order of Battle laydown "
            "rollup, and platform mission-data-file coverage — are FUSED onto "
            "the matched intercepts with native Prep SuperJoins on emitter_id. "
            "Surfaces matched/ambiguous/unknown emitters, reprogramming "
            "triggers, library-vs-measured parametrics, EOB affiliation, and "
            "platform coverage gaps. Baltic scenario. All data "
            "synthetic/notional for a JEWOSC evaluation demo."
        ),
        "sources": [
            {
                "type": "local_csv",
                "path": str(HERE / "intercepts.csv"),
                "format": "csv",
                "auth": "none",
                "name": "ELINT Intercepts",
                "description": (
                    "ELINT/ES intercept cuts (one row per detection) with "
                    "measured RF frequency, PRI, pulse width, bearing, SNR, "
                    "and sensor id. The refreshable operational feed. "
                    "SYNTHETIC — notional Baltic scenario."
                ),
                "extra": {
                    "csv_schema": intercepts_schema(),
                    "_skip_auto_casts": True,
                },
            },
            ref_source("Threat Library", lib_path,
                       "Emitter threat-library reference: one row per emitter "
                       "(NATO-style name, system type, library parametrics, "
                       "lethality, associated weapon, priority)."),
            ref_source("EOB Laydown Rollup", eob_path,
                       "Electronic Order of Battle rollup: one row per emitter "
                       "summarising known sites (count, affiliation, "
                       "confirmed/active) so the join stays 1:1."),
            ref_source("Platform MDF Coverage", cov_path,
                       "Per-emitter platform mission-data-file coverage: how "
                       "many BLUE platform MDFs recognise the emitter and "
                       "which are blind to it (the reprogramming workload)."),
        ],
        "transformations": [
            {
                "kind": "ew_intercept_match",
                "args": {
                    "name": "EW Intercept Match",
                    "branch": 0,
                    "freq_col": "meas_freq_ghz",
                    "pri_col": "meas_pri_us",
                    "pw_col": "meas_pw_us",
                    "lat_col": "lat",
                    "lon_col": "lon",
                    "own_ship_lat": OWN_SHIP_LAT,
                    "own_ship_lon": OWN_SHIP_LON,
                    "own_ship_label": OWN_SHIP_LABEL,
                    # Calibrated in v2's build-spec sweep: 0.12 gives ~79%
                    # clean-cut correct-match, ~1% false triggers, 100% of
                    # genuine unknown/changed cuts caught.
                    "match_tolerance": 0.12,
                    "fingerprints": fingerprints,
                    # Ground-truth label (synthetic only) → lets the match node
                    # split the 128-cut reprogramming queue by CAUSE
                    # (novel_emitter / library_ambiguity / correlator_miss) and
                    # emit the correlator confusion matrix. Turns the
                    # calibration gap into a demoable feature rather than hiding
                    # it. Removed trivially for a real (unlabelled) feed.
                    "truth_class_col": "truth_class",
                },
            },
            # Native FUSION — three SuperJoins on emitter_id. Each sets
            # left_branch=0 so they chain left-deep onto branch 0's tail:
            #   ((match ⋈ library) ⋈ eob_rollup) ⋈ platform_coverage
            # leftOuter so unknown cuts (emitter_id "") pass through with NULLs.
            {
                "kind": "join",
                "args": {
                    "name": "⋈ Threat Library",
                    "description": ("Fuse the emitter threat-library record "
                                    "onto each matched intercept on emitter_id "
                                    "(NATO name, system type, lethality, "
                                    "weapon, library parametrics)."),
                    "left_branch": 0, "right_branch": 1,
                    "on": "emitter_id", "join_type": "leftOuter",
                },
            },
            {
                "kind": "join",
                "args": {
                    "name": "⋈ EOB Laydown",
                    "description": ("Fuse the Electronic Order of Battle rollup "
                                    "on emitter_id (known-site count, "
                                    "affiliation, confirmed/active)."),
                    "left_branch": 0, "right_branch": 2,
                    "on": "emitter_id", "join_type": "leftOuter",
                },
            },
            {
                "kind": "join",
                "args": {
                    "name": "⋈ Platform Coverage",
                    "description": ("Fuse platform mission-data-file coverage "
                                    "on emitter_id (coverage gap count + which "
                                    "platforms are blind to this emitter)."),
                    "left_branch": 0, "right_branch": 3,
                    "on": "emitter_id", "join_type": "leftOuter",
                },
            },
        ],
        "outputs": [
            {
                "kind": "published_data_source",
                "name": "MOD JEWOSC EW Fusion v3",
                "project": "31 - MOD JEWOSC EW Fusion Demo",
                "description": disclaimer,
            }
        ],
        # Cloud site (usfederaldemos) + a Script (match) node → backgrounder
        # can't run scripts, so run_loop runs the flow locally to produce the
        # .hyper, uploads it as the published data source via TSC, publishes
        # the .tfl for visibility (schedule is a no-op on Cloud for
        # script-bearing flows), then applies column metadata via the .tds
        # round-trip. See feedback_cloud_vs_server_execution.
        "server_publish": {
            "project": "31 - MOD JEWOSC EW Fusion Demo",
            "parent_project": "Prep Agent",
            "flow_name": "MOD JEWOSC EW Fusion v3",
            "overwrite": True,
            "cadence": "hourly",
            "hour_utc": 0,
            "minute_utc": 0,
            "schedule_name_hint": "MOD JEWOSC v3 Hourly Refresh",
        },
        # qa_tier=none: the match Script node declares its own output schema and
        # the joins pass columns through natively. A deterministic Validator
        # would redeclare only source columns and silently drop the match +
        # joined columns (Maestro honours each node's declared schema).
        "qa_tier": "none",
        "eval_strategy": "self_consistency",
        "deployment": "tableau_server",
        "refresh_cadence": "hourly",
    }

    SPEC_PATH.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"wrote {SPEC_PATH}")
    print(f"  fingerprints={len(fingerprints)} threat_library={len(lib_rows)} "
          f"eob_rollup={len(eob_rows)} platform_coverage={len(cov_rows)}")
    print(f"  ref CSVs: {lib_path.name}, {eob_path.name}, {cov_path.name}")


if __name__ == "__main__":
    main()
