#!/usr/bin/env python3
"""
Build v2/spec.json for the MOD JEWOSC EW multi-source fusion flow.

Reads the three slow-changing reference CSVs (emitters, eob_sites,
platforms) and bakes them into the ew_intercept_fusion transform as
Python-literal args, while the refreshable intercepts.csv rides as a
`local_csv` input feeding the fusion Script node.

Deterministic: reads committed CSVs, emits a stable spec.json. No
network, no clock. Re-run whenever the synthetic data is regenerated.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
SPEC_PATH = V2 / "spec.json"

# Own-ship reference — matches generate_synthetic_ew.py.
OWN_SHIP_LAT, OWN_SHIP_LON = 55.10, 18.30
OWN_SHIP_LABEL = "BLUE-ISR ORBIT ALPHA"

# Per-column type coercion for the reference tables so the baked
# literals are real floats/ints (the fusion math depends on it).
NUM_FLOAT = {
    "centre_freq_ghz", "pri_us", "pw_us", "scan_period_s", "erp_dbw", "lat", "lon",
}
NUM_INT = {
    "max_range_km", "priority", "last_seen_days",
    "mdf_load_days_ago", "reprogram_cycle_days", "coverage_count",
}


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


def intercepts_schema():
    """Declared post-read schema for intercepts.csv. detect_time_iso stays
    string (Maestro rejects ISO strings declared datetime); truth_* columns
    are kept as ground-truth passthrough for demo scoring."""
    return {
        "intercept_id": "string",
        "detect_time_iso": "string",
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

    disclaimer = (
        "SYNTHETIC / NOTIONAL DEMONSTRATION DATA — NOT operational, NOT "
        "classified, NOT derived from any classified source. Built for a "
        "UK MoD JEWOSC maturity-evaluation demo of Tableau + the agentic "
        "Prep ETL skill. NATO-reporting-name-style emitter designations "
        "are used for audience resonance; every parametric value "
        "(frequency, PRI, pulse width, ERP, lethality, ranges) is "
        "fabricated. The Electronic Order of Battle laydown, platform "
        "mission-data coverage, and ELINT intercepts are all synthetic. "
        "Theatre: Baltic / NATO eastern flank (notional own-ship "
        f"{OWN_SHIP_LABEL!r}). GAP DECLARATION: real emitter parametrics, "
        "true EOB geolocation, and actual platform MDF contents are "
        "classified and out of scope; this flow demonstrates the FUSION "
        "WORKFLOW and OPERATIONAL PRESENTATION, not real threat data."
    )

    spec = {
        "request": (
            "MOD JEWOSC EW intercept -> mission-data fusion (v2, "
            "multi-source). Correlate a feed of ELINT/ES intercept cuts "
            "against a synthetic emitter threat-library, Electronic Order "
            "of Battle laydown, and platform mission-data-file coverage; "
            "surface matched/ambiguous/unknown emitters, flag "
            "reprogramming triggers, resolve nearest EOB site + lethality "
            "+ weapon, compute own-ship range/bearing + weapon-engagement "
            "zone, and count platform coverage gaps. Baltic scenario. "
            "All data synthetic/notional for a JEWOSC evaluation demo."
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
                    # ISO-string + ground-truth columns must not be
                    # auto-cast (Maestro rejects ISO strings as datetime;
                    # truth_* are demo-scoring passthrough).
                    "_skip_auto_casts": True,
                },
            }
        ],
        "transformations": [
            {
                "kind": "ew_intercept_fusion",
                "args": {
                    "name": "EW Intercept Fusion",
                    "branch": 0,
                    "freq_col": "meas_freq_ghz",
                    "pri_col": "meas_pri_us",
                    "pw_col": "meas_pw_us",
                    "lat_col": "lat",
                    "lon_col": "lon",
                    "own_ship_lat": OWN_SHIP_LAT,
                    "own_ship_lon": OWN_SHIP_LON,
                    "own_ship_label": OWN_SHIP_LABEL,
                    # Calibrated against the generator's noise model
                    # (build-spec sweep): 0.12 gives ~79% clean-cut
                    # correct-match, ~1% false reprogramming-triggers,
                    # and catches 100% of genuine unknown/changed cuts.
                    "match_tolerance": 0.12,
                    "emitters": emitters,
                    "eob_sites": eob_sites,
                    "platforms": platforms,
                },
            }
        ],
        "outputs": [
            {
                "kind": "hyper",
                "name": "MOD JEWOSC EW Fusion",
                "description": disclaimer,
            }
        ],
        # qa_tier=none: the fusion Script node already declares its full
        # 33-column output schema via get_output_schema(). Inserting the
        # deterministic Validator downstream would REDECLARE only the
        # source columns + its own diagnostics, silently dropping the 20
        # fusion-added columns (Maestro honours each node's declared
        # output schema). Every production flow in this repo uses none for
        # the same reason. Correctness is enforced by the golden-render
        # test + the standalone fusion unit check, not an inline validator.
        "qa_tier": "none",
        "eval_strategy": "self_consistency",
        "deployment": "local",
        "refresh_cadence": "hourly",
    }

    SPEC_PATH.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"wrote {SPEC_PATH}")
    print(f"  emitters={len(emitters)} eob_sites={len(eob_sites)} "
          f"platforms={len(platforms)}")


if __name__ == "__main__":
    main()
