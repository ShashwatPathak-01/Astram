"""
recommender.py
--------------
Turns the two model outputs (predicted clearance duration + road-closure
probability) into an actionable, explainable resource-deployment plan:
manpower, barricades and a diversion recommendation.

The logic is deliberately rule-based on top of the ML predictions so that the
recommendation is transparent and defensible to traffic-operations staff
(a black-box number of officers is not actionable). Thresholds are anchored to
the data-driven duration quantiles produced during training.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

# Event causes that, by their physical nature, usually need physical barricading
# / lane management regardless of duration.
PHYSICAL_OBSTRUCTION_CAUSES = {
    "construction", "tree_fall", "accident", "water_logging",
    "road_conditions", "pot_holes", "debris",
}

# Planned crowd events where manpower (not just barricades) dominates.
CROWD_CAUSES = {"public_event", "procession", "vip_movement", "protest"}


@dataclass
class Recommendation:
    severity: str                 # Low / Medium / High / Critical
    severity_score: float         # 0-100
    predicted_clearance_min: float
    road_closure_probability: float
    manpower: int                 # recommended officers / wardens
    barricades: int               # number of barricade units
    diversion_required: bool
    diversion_advice: str
    drivers: list = field(default_factory=list)  # human-readable rationale

    def to_dict(self) -> dict:
        return asdict(self)


def _severity_from(duration_min: float, closure_prob: float,
                   q: dict, is_crowd: bool) -> tuple[str, float]:
    """
    Combine predicted duration (vs. data quantiles) and closure probability
    into a 0-100 severity score and a label.
    """
    q50 = q.get("0.5", 55)
    q75 = q.get("0.75", 110)
    q90 = q.get("0.9", 240)

    # Duration component (0-60): scaled against the 90th percentile.
    dur_score = min(duration_min / max(q90, 1), 1.0) * 60

    # Closure component (0-30).
    closure_score = closure_prob * 30

    # Crowd events carry inherent public-safety load (0 or 10).
    crowd_score = 10 if is_crowd else 0

    score = round(min(dur_score + closure_score + crowd_score, 100), 1)

    if score >= 70 or duration_min >= q90:
        label = "Critical"
    elif score >= 45 or duration_min >= q75:
        label = "High"
    elif score >= 25 or duration_min >= q50:
        label = "Medium"
    else:
        label = "Low"
    return label, score


def recommend(
    *,
    duration_min: float,
    closure_prob: float,
    event_cause: str,
    corridor: str,
    requires_road_closure: bool,
    duration_quantiles: dict,
) -> Recommendation:
    """Produce the full resource plan for a single event."""
    cause = (event_cause or "").strip().lower()
    is_crowd = cause in CROWD_CAUSES
    is_physical = cause in PHYSICAL_OBSTRUCTION_CAUSES
    on_corridor = bool(corridor) and corridor.strip().lower() != "non-corridor"

    severity, score = _severity_from(
        duration_min, closure_prob, duration_quantiles, is_crowd
    )

    # --- base manpower by severity ----------------------------------------
    base_manpower = {"Low": 2, "Medium": 4, "High": 8, "Critical": 14}[severity]
    manpower = base_manpower
    drivers: list[str] = [f"Base {base_manpower} for {severity} severity"]

    # Arterial corridors carry more traffic -> add officers.
    if on_corridor:
        manpower += 2
        drivers.append(f"+2 on arterial corridor '{corridor}'")
    # Crowd events need crowd-control wardens on top of traffic officers.
    if is_crowd:
        manpower += 4
        drivers.append("+4 crowd-control wardens (crowd event)")

    # --- barricades --------------------------------------------------------
    barricade_base = {"Low": 0, "Medium": 2, "High": 6, "Critical": 12}[severity]
    barricades = barricade_base
    if is_physical or requires_road_closure or closure_prob >= 0.5:
        barricades += 4
        drivers.append("+4 barricades (physical obstruction / closure likely)")

    # --- diversion ---------------------------------------------------------
    diversion_required = (
        requires_road_closure
        or closure_prob >= 0.5
        or severity in {"High", "Critical"} and on_corridor
    )
    if diversion_required:
        if on_corridor:
            advice = (
                f"Set up a signed diversion off '{corridor}'. Pre-position "
                "traffic wardens at the two nearest upstream junctions and "
                "alert control room to retime adjacent signals."
            )
        else:
            advice = (
                "Divert through parallel local streets and post wardens at the "
                "entry/exit points; notify nearby junctions."
            )
    else:
        advice = (
            "No full diversion needed. Manage with lane coning and on-site "
            "officers; keep one lane flowing."
        )

    return Recommendation(
        severity=severity,
        severity_score=score,
        predicted_clearance_min=round(float(duration_min), 1),
        road_closure_probability=round(float(closure_prob), 3),
        manpower=int(manpower),
        barricades=int(barricades),
        diversion_required=bool(diversion_required),
        diversion_advice=advice,
        drivers=drivers,
    )
