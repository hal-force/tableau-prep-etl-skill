"""DoD critical-infrastructure replacement-likelihood scoring.

Standalone module: takes the DataFrame produced by the api_caller (one
row per HIFLD Military_Installation record) and adds two columns:

  criticality_score          0-100  higher = harder to replace
  replacement_likelihood_score  = 100 - criticality_score

Weighted components (sum to 100):
  40  AREA (log-scaled)            — bigger complexes harder to replace
  25  JOINT_BASE flag (!= 'N/A')   — multi-service consolidations sticky
  20  COMPONENT strategic weight   — Navy / Air Force / Marines ranked
                                     above Guard / Reserve
  15  Overseas flag                — non-US SOFA-country negotiations

Scoring is designed to be transparent and reproducible; every weight
is documented. Not a policy signal — a demo aggregation over public
HIFLD attributes.
"""
from __future__ import annotations

import math
import pandas as pd


_STRATEGIC_COMPONENTS = {
    "NAVY": 1.0,
    "AIR FORCE": 0.95,
    "MARINE CORPS": 0.9,
    "ARMY": 0.85,
    "DLA": 0.7,
    "COAST GUARD": 0.6,
    "AIR NATIONAL GUARD": 0.4,
    "ARMY NATIONAL GUARD": 0.4,
    "AIR FORCE RESERVE": 0.35,
    "ARMY RESERVE": 0.35,
    "MARINE CORPS RESERVE": 0.35,
    "NAVY RESERVE": 0.35,
}


def _component_score(v: object) -> float:
    if not isinstance(v, str):
        return 0.3
    return _STRATEGIC_COMPONENTS.get(v.strip().upper(), 0.3)


def _area_score(v: object, area_ref: float = 1000.0) -> float:
    """Log-scale AREA against a 1000-unit reference. HIFLD's AREA
    column is reported in km^2 in this snapshot (JBLM ~684, Camp
    Pendleton ~510); 1000 km^2 is the calibration ceiling. Rank order
    is invariant to unit choice — the reference only sets where the
    log-scale saturates."""
    try:
        acres = float(v)
    except (TypeError, ValueError):
        return 0.0
    if acres <= 0 or math.isnan(acres):
        return 0.0
    return min(1.0, math.log10(acres + 1) / math.log10(area_ref))


def _joint_score(v: object) -> float:
    if not isinstance(v, str):
        return 0.0
    stripped = v.strip().upper()
    return 0.0 if stripped in ("", "N/A", "NONE", "NULL") else 1.0


def _overseas_score(country: object) -> float:
    if not isinstance(country, str):
        return 0.0
    return 0.0 if country.strip().upper() == "UNITED STATES" else 1.0


def score_row(row: pd.Series) -> float:
    """Return criticality_score in [0, 100] for one HIFLD row."""
    s = (
        40.0 * _area_score(row.get("AREA"))
        + 25.0 * _joint_score(row.get("JOINT_BASE"))
        + 20.0 * _component_score(row.get("COMPONENT"))
        + 15.0 * _overseas_score(row.get("COUNTRY"))
    )
    return max(0.0, min(100.0, s))


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["criticality_score"] = df.apply(score_row, axis=1).round(2)
    df["replacement_likelihood_score"] = (100.0 - df["criticality_score"]).round(2)
    return df
