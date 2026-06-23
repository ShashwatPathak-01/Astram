"""
train.py
--------
Train, evaluate and persist the two models that power the backend:

    * a regression model  -> predicts clearance_minutes (traffic-impact proxy)
    * a classification model -> predicts road_closure (barricading/diversion)

For each task several candidate algorithms are compared and the best one
(by cross-validated score) is saved. Running this module also writes a
``metadata.json`` with the category vocabularies, evaluation metrics and
pre-computed analytics aggregates (corridor / junction hotspots) used by the
dashboard endpoints.

Usage:
    python -m ml.train --csv "<path to csv>" --out models
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    f1_score,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .features import (
    ALL_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    add_targets,
    build_features,
    load_raw,
)

RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Shared preprocessing: one-hot encode categoricals, scale numerics.
# ---------------------------------------------------------------------------
def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", min_frequency=5),
                CATEGORICAL_FEATURES,
            ),
            ("num", StandardScaler(), NUMERIC_FEATURES),
        ]
    )


# ---------------------------------------------------------------------------
# Regression: clearance minutes. We model log1p(minutes) because the duration
# distribution is heavily right-skewed (median ~52 min, long tail to days).
# ---------------------------------------------------------------------------
def train_regression(X: pd.DataFrame, y: pd.Series):
    y_log = np.log1p(y)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y_log, test_size=0.2, random_state=RANDOM_STATE
    )

    candidates = {
        "linear": LinearRegression(),
        "random_forest": RandomForestRegressor(
            n_estimators=300, max_depth=None, min_samples_leaf=3,
            n_jobs=-1, random_state=RANDOM_STATE,
        ),
        "grad_boost": GradientBoostingRegressor(random_state=RANDOM_STATE),
    }

    results = {}
    best_name, best_pipe, best_mae = None, None, np.inf
    for name, model in candidates.items():
        pipe = Pipeline([("prep", make_preprocessor()), ("model", model)])
        pipe.fit(X_tr, y_tr)
        pred_log = pipe.predict(X_te)
        # Evaluate in the original (minutes) space, not log space.
        pred = np.expm1(pred_log)
        true = np.expm1(y_te)
        mae = mean_absolute_error(true, pred)
        r2 = r2_score(true, pred)
        results[name] = {"mae_minutes": round(float(mae), 2),
                         "r2": round(float(r2), 4)}
        if mae < best_mae:
            best_name, best_pipe, best_mae = name, pipe, mae

    return best_name, best_pipe, results


# ---------------------------------------------------------------------------
# Classification: will the event require road closure (barricades/diversion)?
# Classes are imbalanced (~8% positive) so we use class_weight="balanced".
# ---------------------------------------------------------------------------
def train_classification(X: pd.DataFrame, y: pd.Series):
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    candidates = {
        "logreg": LogisticRegression(
            max_iter=1000, class_weight="balanced"
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, class_weight="balanced",
            n_jobs=-1, random_state=RANDOM_STATE,
        ),
        "grad_boost": GradientBoostingClassifier(random_state=RANDOM_STATE),
    }

    results = {}
    best_name, best_pipe, best_auc = None, None, -np.inf
    for name, model in candidates.items():
        pipe = Pipeline([("prep", make_preprocessor()), ("model", model)])
        pipe.fit(X_tr, y_tr)
        proba = pipe.predict_proba(X_te)[:, 1]
        pred = (proba >= 0.5).astype(int)
        auc = roc_auc_score(y_te, proba)
        f1 = f1_score(y_te, pred)
        results[name] = {"roc_auc": round(float(auc), 4),
                         "f1": round(float(f1), 4)}
        if auc > best_auc:
            best_name, best_pipe, best_auc = name, pipe, auc

    return best_name, best_pipe, results


# ---------------------------------------------------------------------------
# Analytics aggregates for the dashboard (hotspots & distributions).
# ---------------------------------------------------------------------------
def build_analytics(raw: pd.DataFrame) -> dict:
    feats = add_targets(raw)

    def top_counts(col, n=12):
        s = raw[col].dropna().astype(str).str.strip()
        s = s[s != ""]
        return s.value_counts().head(n).to_dict()

    # Corridor-level median clearance time -> "which roads recover slowest".
    corridor_impact = (
        feats.dropna(subset=["clearance_minutes"])
        .assign(corridor=lambda d: d["corridor"].fillna("Non-corridor"))
        .groupby("corridor")["clearance_minutes"]
        .median().sort_values(ascending=False).head(15)
        .round(1).to_dict()
    )

    return {
        "total_events": int(len(raw)),
        "by_event_type": top_counts("event_type", 5),
        "by_event_cause": top_counts("event_cause", 17),
        "by_corridor": top_counts("corridor", 22),
        "by_zone": top_counts("zone", 12),
        "top_junctions": top_counts("junction", 15),
        "top_police_stations": top_counts("police_station", 15),
        "corridor_median_clearance_min": corridor_impact,
        "road_closure_rate": round(float(feats["road_closure"].mean()), 4),
    }


def category_vocab(raw: pd.DataFrame) -> dict:
    """Distinct values for each categorical -> powers the frontend dropdowns."""
    vocab = {}
    for col in CATEGORICAL_FEATURES:
        s = raw[col].dropna().astype(str).str.strip()
        s = s[s != ""]
        vocab[col] = sorted(s.unique().tolist())
    return vocab


def main(csv_path: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Loading {csv_path} ...")
    raw = load_raw(csv_path)
    labelled = add_targets(raw)
    X_all = build_features(raw)

    # ---- regression: only rows with a believable clearance duration -------
    reg_mask = labelled["clearance_minutes"].notna()
    Xr, yr = X_all[reg_mask], labelled.loc[reg_mask, "clearance_minutes"]
    print(f"Regression rows: {len(Xr)}")
    reg_name, reg_pipe, reg_results = train_regression(Xr, yr)
    print(f"  best regressor: {reg_name} -> {reg_results[reg_name]}")

    # ---- classification: full dataset -------------------------------------
    yc = labelled["road_closure"]
    print(f"Classification rows: {len(X_all)} (positives={int(yc.sum())})")
    clf_name, clf_pipe, clf_results = train_classification(X_all, yc)
    print(f"  best classifier: {clf_name} -> {clf_results[clf_name]}")

    # ---- persist artifacts -------------------------------------------------
    joblib.dump(reg_pipe, out / "duration_model.joblib")
    joblib.dump(clf_pipe, out / "closure_model.joblib")

    # Reference statistics for the severity score (data-driven thresholds).
    q = yr.quantile([0.5, 0.75, 0.9]).round(1).to_dict()

    metadata = {
        "features": {
            "all": ALL_FEATURES,
            "categorical": CATEGORICAL_FEATURES,
            "numeric": NUMERIC_FEATURES,
        },
        "category_vocab": category_vocab(raw),
        "regression": {"best_model": reg_name, "candidates": reg_results},
        "classification": {"best_model": clf_name, "candidates": clf_results},
        "duration_quantiles_min": {str(k): v for k, v in q.items()},
        "analytics": build_analytics(raw),
    }
    with open(out / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Saved models + metadata to {out.resolve()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default="models")
    args = ap.parse_args()
    main(args.csv, args.out)
