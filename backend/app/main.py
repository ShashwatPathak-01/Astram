"""
main.py
-------
FastAPI backend for the Event-Driven Congestion project.

Responsibilities:
  * Load the trained ML pipelines + metadata produced by ``ml.train``.
  * /api/predict      -> forecast clearance time + closure prob, then return a
                         full manpower / barricade / diversion plan.
  * /api/analytics    -> pre-computed hotspot aggregates for the dashboard.
  * /api/events       -> a sample of real geolocated events for the map.
  * /api/metadata     -> category vocab (powers the frontend dropdowns) + model
                         evaluation metrics.
  * /api/maps/token   -> exchanges the Mappls client_id/secret (kept server-side)
                         for a short-lived OAuth access token the React map uses.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

try:  # load backend/.env if python-dotenv is available
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

from .recommender import recommend
from .schemas import EventInput, HealthResponse, PredictionResponse

# Allow ml.features to be importable (backend/ is on the path when run as a pkg).
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.features import build_features  # noqa: E402

# ---------------------------------------------------------------------------
# Paths / config (overridable via environment variables)
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = Path(os.getenv("MODELS_DIR", BACKEND_DIR / "models"))
DATA_CSV = os.getenv(
    "DATA_CSV",
    str(BACKEND_DIR.parent /
        "Astram event data_anonymized - Astram event data_anonymizedb40ac87.csv"),
)
MAPPLS_CLIENT_ID = os.getenv("MAPPLS_CLIENT_ID", "")
MAPPLS_CLIENT_SECRET = os.getenv("MAPPLS_CLIENT_SECRET", "")
MAPPLS_TOKEN_URL = "https://outpost.mappls.com/api/security/oauth/token"

app = FastAPI(title="Event-Driven Congestion API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lazy-loaded global state
# ---------------------------------------------------------------------------
STATE: dict = {
    "duration_model": None,
    "closure_model": None,
    "metadata": None,
    "events": None,        # cached sample of real events for the map
    "mappls_token": None,  # {"access_token":..., "expires_at": epoch}
}


def _load_models() -> None:
    if STATE["duration_model"] is None:
        STATE["duration_model"] = joblib.load(MODELS_DIR / "duration_model.joblib")
        STATE["closure_model"] = joblib.load(MODELS_DIR / "closure_model.joblib")
        with open(MODELS_DIR / "metadata.json") as f:
            STATE["metadata"] = json.load(f)


@app.on_event("startup")
def startup() -> None:
    try:
        _load_models()
    except FileNotFoundError:
        # Models not trained yet; endpoints will report not-ready.
        pass


# ---------------------------------------------------------------------------
# Health & metadata
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    loaded = STATE["duration_model"] is not None
    md = STATE["metadata"] or {}
    return HealthResponse(
        status="ok",
        models_loaded=loaded,
        regression_model=(md.get("regression") or {}).get("best_model"),
        classification_model=(md.get("classification") or {}).get("best_model"),
    )


@app.get("/api/metadata")
def metadata() -> dict:
    _load_models()
    md = STATE["metadata"]
    return {
        "category_vocab": md["category_vocab"],
        "regression": md["regression"],
        "classification": md["classification"],
        "duration_quantiles_min": md["duration_quantiles_min"],
    }


@app.get("/api/analytics")
def analytics() -> dict:
    _load_models()
    return STATE["metadata"]["analytics"]


# ---------------------------------------------------------------------------
# Real events for the map (sampled & cleaned)
# ---------------------------------------------------------------------------
def _load_events(limit: int) -> list[dict]:
    if STATE["events"] is None:
        df = pd.read_csv(DATA_CSV, na_values=["NULL", "NaN", ""], low_memory=False)
        df = df[
            df["latitude"].between(12.7, 13.3)
            & df["longitude"].between(77.2, 77.9)
        ].copy()
        cols = ["id", "event_type", "event_cause", "priority", "corridor",
                "zone", "junction", "police_station", "latitude", "longitude",
                "address", "start_datetime", "status", "requires_road_closure"]
        df = df[[c for c in cols if c in df.columns]]
        df = df.replace({np.nan: None})
        STATE["events"] = df.to_dict(orient="records")
    return STATE["events"][:limit]


@app.get("/api/events")
def events(limit: int = Query(1500, ge=1, le=8200)) -> dict:
    data = _load_events(limit)
    return {"count": len(data), "events": data}


# ---------------------------------------------------------------------------
# Prediction + recommendation
# ---------------------------------------------------------------------------
def _predict_one(ev: EventInput) -> PredictionResponse:
    _load_models()
    md = STATE["metadata"]

    row = ev.model_dump()
    if not row.get("start_datetime"):
        row["start_datetime"] = pd.Timestamp.utcnow().isoformat()
    # Build a single-row frame and run the shared feature pipeline.
    X = build_features(pd.DataFrame([row]))

    # Regression predicts log1p(minutes) -> invert.
    dur_log = STATE["duration_model"].predict(X)[0]
    duration_min = float(np.expm1(dur_log))
    duration_min = max(1.0, min(duration_min, 60 * 24))

    closure_prob = float(STATE["closure_model"].predict_proba(X)[0, 1])

    rec = recommend(
        duration_min=duration_min,
        closure_prob=closure_prob,
        event_cause=ev.event_cause,
        corridor=ev.corridor,
        requires_road_closure=ev.requires_road_closure,
        duration_quantiles=md["duration_quantiles_min"],
    )
    return PredictionResponse(**rec.to_dict())


@app.post("/api/predict", response_model=PredictionResponse)
def predict(event: EventInput) -> PredictionResponse:
    try:
        return _predict_one(event)
    except Exception as exc:  # pragma: no cover - surface clean error
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/predict/batch")
def predict_batch(events_in: list[EventInput]) -> dict:
    return {"results": [_predict_one(e).model_dump() for e in events_in]}


# ---------------------------------------------------------------------------
# Mappls OAuth token (client_id/secret stay on the server)
# ---------------------------------------------------------------------------
@app.get("/api/maps/token")
def mappls_token() -> dict:
    if not MAPPLS_CLIENT_ID or not MAPPLS_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Mappls credentials not configured. Set MAPPLS_CLIENT_ID "
                   "and MAPPLS_CLIENT_SECRET environment variables.",
        )
    # Reuse a cached token until ~60s before expiry.
    cached = STATE["mappls_token"]
    if cached and cached["expires_at"] - 60 > time.time():
        return {"access_token": cached["access_token"],
                "expires_in": int(cached["expires_at"] - time.time())}

    resp = requests.post(
        MAPPLS_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": MAPPLS_CLIENT_ID,
            "client_secret": MAPPLS_CLIENT_SECRET,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"Mappls token error: {resp.text}")
    payload = resp.json()
    expires_in = int(payload.get("expires_in", 3600))
    STATE["mappls_token"] = {
        "access_token": payload["access_token"],
        "expires_at": time.time() + expires_in,
    }
    return {"access_token": payload["access_token"], "expires_in": expires_in}
