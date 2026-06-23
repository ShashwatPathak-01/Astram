"""
features.py
-----------
Centralised feature engineering for the Astram traffic-event dataset.

Both the Jupyter notebook (for exploration / training) and the FastAPI backend
(for live prediction) import from this module so the feature definitions can
never drift apart.

The raw dataset is a log of traffic *events* in Bengaluru (planned and
unplanned). For the hackathon problem -- "forecast event-related traffic impact
and recommend optimal manpower, barricading and diversion plans" -- we engineer
two supervised-learning targets:

    1. clearance_minutes  (regression) -> how long the event blocks the road.
                                          This is our proxy for "traffic impact".
    2. requires_road_closure (binary)  -> whether barricading / diversion is
                                          likely to be required.

The same feature builder is used for both targets.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Column groups used by the model
# ---------------------------------------------------------------------------
CATEGORICAL_FEATURES = [
    "event_type",      # planned / unplanned
    "event_cause",     # vehicle_breakdown, accident, construction, ...
    "priority",        # High / Low
    "veh_type",        # bmtc_bus, heavy_vehicle, lcv, ...
    "corridor",        # arterial corridor name or "Non-corridor"
    "zone",            # traffic police zone
]

NUMERIC_FEATURES = [
    "latitude",
    "longitude",
    "hour",            # hour of day 0-23
    "day_of_week",     # 0=Mon .. 6=Sun
    "month",           # 1-12
    "is_weekend",      # 0/1
    "is_peak_hour",    # 0/1 (08-11 or 17-21)
    "is_night",        # 0/1 (22-05)
    "has_junction",    # 0/1 event mapped to a named junction
]

ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Sentinel string used to fill missing categoricals so the encoder learns an
# explicit "unknown" category instead of dropping rows.
MISSING = "unknown"

# Reasonable bounds (in minutes) for a believable clearance duration. Anything
# outside this is treated as a data-entry artefact and excluded from training
# of the regression target.
MIN_DURATION_MIN = 1.0
# Cap at 24h: clearance times beyond this are almost always data-entry
# artefacts (an event left "open" in the system), and including them only adds
# noise to the regression target.
MAX_DURATION_MIN = 60 * 24


def load_raw(csv_path: str) -> pd.DataFrame:
    """Read the raw CSV, treating the literal string 'NULL' as missing."""
    return pd.read_csv(csv_path, na_values=["NULL", "NaN", ""], low_memory=False)


def _to_dt(series: pd.Series) -> pd.Series:
    """Parse a column to timezone-aware (UTC) datetimes, coercing errors."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add the two learning targets to a copy of ``df``.

    * ``clearance_minutes`` -- (resolved_datetime or closed_datetime) - start.
      Used for the regression model. Implausible values become NaN.
    * ``road_closure``      -- 1 if requires_road_closure is truthy else 0.
    """
    df = df.copy()

    start = _to_dt(df["start_datetime"])
    # Prefer an explicit "resolved" time; fall back to "closed".
    end = _to_dt(df["resolved_datetime"]).fillna(_to_dt(df["closed_datetime"]))
    dur = (end - start).dt.total_seconds() / 60.0
    dur = dur.where((dur >= MIN_DURATION_MIN) & (dur <= MAX_DURATION_MIN))
    df["clearance_minutes"] = dur

    df["road_closure"] = (
        df["requires_road_closure"].astype(str).str.strip().str.lower()
        .isin(["true", "1", "yes"]).astype(int)
    )
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Turn raw event rows into the model feature matrix (one row per event).

    This function is intentionally pure / stateless so it can run identically
    during offline training and during a single online prediction.
    """
    df = df.copy()

    # --- temporal features derived from the event start time ---------------
    start = _to_dt(df["start_datetime"])
    df["hour"] = start.dt.hour
    df["day_of_week"] = start.dt.dayofweek
    df["month"] = start.dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_peak_hour"] = df["hour"].between(8, 11).astype(int) | \
        df["hour"].between(17, 21).astype(int)
    df["is_peak_hour"] = df["is_peak_hour"].astype(int)
    df["is_night"] = ((df["hour"] >= 22) | (df["hour"] <= 5)).astype(int)

    # --- geometry / location flags -----------------------------------------
    # NOTE: we deliberately do NOT use endlatitude/endlongitude. A closed road
    # is logged as a start->end *stretch*, so an end point exists *because* of
    # the closure -- using it leaks the road_closure target (corr ~0.99) and is
    # not legitimately known when forecasting a fresh event.
    if "junction" in df.columns:
        df["has_junction"] = df["junction"].notna().astype(int)
    else:
        df["has_junction"] = 0

    # --- fill missing categoricals with an explicit sentinel ---------------
    for col in CATEGORICAL_FEATURES:
        if col not in df.columns:
            df[col] = MISSING
        df[col] = df[col].astype("object").where(df[col].notna(), MISSING)
        df[col] = df[col].astype(str).str.strip().replace({"": MISSING})

    # --- fill any missing numerics safely ----------------------------------
    for col in NUMERIC_FEATURES:
        if col not in df.columns:
            df[col] = 0
    df[NUMERIC_FEATURES] = df[NUMERIC_FEATURES].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0)

    return df[ALL_FEATURES]
