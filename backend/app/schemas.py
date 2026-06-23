"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EventInput(BaseModel):
    """One event to forecast and plan resources for."""
    event_type: str = Field("unplanned", examples=["planned", "unplanned"])
    event_cause: str = Field("vehicle_breakdown", examples=["accident"])
    priority: str = Field("High", examples=["High", "Low"])
    veh_type: Optional[str] = Field("unknown", examples=["heavy_vehicle"])
    corridor: str = Field("Non-corridor", examples=["Mysore Road"])
    zone: Optional[str] = Field("unknown", examples=["Central Zone 2"])
    latitude: float = Field(12.9716, ge=-90, le=90)
    longitude: float = Field(77.5946, ge=-180, le=180)
    # ISO-8601 start time. If omitted, "now" is used.
    start_datetime: Optional[str] = None
    requires_road_closure: bool = False
    junction: Optional[str] = None


class PredictionResponse(BaseModel):
    severity: str
    severity_score: float
    predicted_clearance_min: float
    road_closure_probability: bool | float
    manpower: int
    barricades: int
    diversion_required: bool
    diversion_advice: str
    drivers: List[str]


class HealthResponse(BaseModel):
    status: str
    models_loaded: bool
    regression_model: Optional[str] = None
    classification_model: Optional[str] = None
