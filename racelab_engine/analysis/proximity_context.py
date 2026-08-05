from __future__ import annotations

import math
from enum import Enum
from typing import Any, Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


class ProximityState(str, Enum):
    """Observed nearby-car distance context, not aerodynamic classification."""

    NO_NEARBY_CAR_REPORTED = "no_nearby_car_reported"
    NEARBY_CAR_AHEAD = "nearby_car_ahead"
    NEARBY_CAR_BEHIND = "nearby_car_behind"
    NEARBY_CARS_AHEAD_AND_BEHIND = "nearby_cars_ahead_and_behind"
    CONTEXT_UNKNOWN = "context_unknown"


class ProximityContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ProximityState
    basis: Literal["distance", "time_gap"]
    exclusion_distance_m: float | None = Field(default=None, gt=0)
    ahead_exclusion_seconds: float | None = Field(default=None, gt=0)
    behind_exclusion_seconds: float | None = Field(default=None, gt=0)
    min_distance_ahead_m: float | None = Field(default=None, ge=0)
    min_distance_behind_m: float | None = Field(default=None, ge=0)
    min_time_gap_ahead_s: float | None = Field(default=None, ge=0)
    min_time_gap_behind_s: float | None = Field(default=None, ge=0)
    valid_pair_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    blocks_relative_resistance: bool
    explanation: str

    @property
    def hard_blocker_active(self) -> bool:
        """Value expected by the evidence-contract blocker result."""

        return self.blocks_relative_resistance


def _distance(row: Mapping[str, Any], canonical: str, raw: str) -> float | None:
    value = row.get(canonical, row.get(raw))
    if value is None or isinstance(value, bool):
        return None
    try:
        distance = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(distance) or distance < 0:
        return None
    return distance


def _speed_mps(row: Mapping[str, Any]) -> float | None:
    value = row.get("speed_mps", row.get("Speed"))
    scale = 1.0
    if value is None:
        value = row.get("speed_mph")
        scale = 1.0 / 2.23693629
    if value is None or isinstance(value, bool):
        return None
    try:
        speed = float(value) * scale
    except (TypeError, ValueError, OverflowError):
        return None
    return speed if math.isfinite(speed) and speed > 0 else None


def classify_proximity_window(
    rows: Iterable[Mapping[str, Any]],
    *,
    exclusion_distance_m: float,
) -> ProximityContext:
    """Classify only what the two distance channels directly establish.

    A large sentinel-like distance is treated as "no nearby car reported," not
    certified clean air.  This function does not infer tow, draft, side-draft,
    aerodynamic pressure, drag reduction, or force.
    """

    if not math.isfinite(exclusion_distance_m) or exclusion_distance_m <= 0:
        raise ValueError("exclusion_distance_m must be finite and greater than zero")

    row_list = list(rows)
    ahead_values: list[float] = []
    behind_values: list[float] = []
    valid_pairs = 0
    for row in row_list:
        ahead = _distance(row, "car_distance_ahead_m", "CarDistAhead")
        behind = _distance(row, "car_distance_behind_m", "CarDistBehind")
        if ahead is None or behind is None:
            continue
        valid_pairs += 1
        ahead_values.append(ahead)
        behind_values.append(behind)

    sample_count = len(row_list)
    coverage = valid_pairs / sample_count if sample_count else 0.0
    min_ahead = min(ahead_values, default=None)
    min_behind = min(behind_values, default=None)

    if sample_count == 0 or valid_pairs != sample_count:
        return ProximityContext(
            state=ProximityState.CONTEXT_UNKNOWN,
            basis="distance",
            exclusion_distance_m=exclusion_distance_m,
            min_distance_ahead_m=min_ahead,
            min_distance_behind_m=min_behind,
            valid_pair_count=valid_pairs,
            sample_count=sample_count,
            coverage_fraction=coverage,
            blocks_relative_resistance=True,
            explanation=(
                "Nearby-car distance coverage is incomplete, so proximity context "
                "cannot support a relative-resistance conclusion."
            ),
        )

    ahead_near = min_ahead is not None and min_ahead <= exclusion_distance_m
    behind_near = min_behind is not None and min_behind <= exclusion_distance_m
    if ahead_near and behind_near:
        state = ProximityState.NEARBY_CARS_AHEAD_AND_BEHIND
        explanation = "Cars were reported inside the exclusion distance both ahead and behind."
    elif ahead_near:
        state = ProximityState.NEARBY_CAR_AHEAD
        explanation = "A car ahead was reported inside the exclusion distance."
    elif behind_near:
        state = ProximityState.NEARBY_CAR_BEHIND
        explanation = "A car behind was reported inside the exclusion distance."
    else:
        state = ProximityState.NO_NEARBY_CAR_REPORTED
        explanation = (
            "No nearby car was reported inside the configured exclusion distance; "
            "this is proximity evidence, not measured aerodynamic cleanliness."
        )

    return ProximityContext(
        state=state,
        basis="distance",
        exclusion_distance_m=exclusion_distance_m,
        min_distance_ahead_m=min_ahead,
        min_distance_behind_m=min_behind,
        valid_pair_count=valid_pairs,
        sample_count=sample_count,
        coverage_fraction=coverage,
        blocks_relative_resistance=state is not ProximityState.NO_NEARBY_CAR_REPORTED,
        explanation=explanation,
    )


def classify_proximity_time_gap_window(
    rows: Iterable[Mapping[str, Any]],
    *,
    ahead_exclusion_seconds: float = 1.5,
    behind_exclusion_seconds: float = 0.5,
) -> ProximityContext:
    """Apply asymmetric proximity gates using distance divided by player speed.

    The resulting time gap is an operational screening approximation. It is not
    an aerodynamic measurement and does not prove a tow, draft, side-draft, or
    rear-aero-pressure effect.
    """

    thresholds = (ahead_exclusion_seconds, behind_exclusion_seconds)
    if not all(math.isfinite(value) and value > 0 for value in thresholds):
        raise ValueError("time-gap thresholds must be finite and greater than zero")

    row_list = list(rows)
    ahead_distances: list[float] = []
    behind_distances: list[float] = []
    ahead_gaps: list[float] = []
    behind_gaps: list[float] = []
    for row in row_list:
        ahead = _distance(row, "car_distance_ahead_m", "CarDistAhead")
        behind = _distance(row, "car_distance_behind_m", "CarDistBehind")
        speed = _speed_mps(row)
        if ahead is None or behind is None or speed is None:
            continue
        ahead_distances.append(ahead)
        behind_distances.append(behind)
        ahead_gaps.append(ahead / speed)
        behind_gaps.append(behind / speed)

    sample_count = len(row_list)
    valid_pairs = len(ahead_gaps)
    coverage = valid_pairs / sample_count if sample_count else 0.0
    min_ahead_distance = min(ahead_distances, default=None)
    min_behind_distance = min(behind_distances, default=None)
    min_ahead_gap = min(ahead_gaps, default=None)
    min_behind_gap = min(behind_gaps, default=None)

    common = {
        "basis": "time_gap",
        "ahead_exclusion_seconds": ahead_exclusion_seconds,
        "behind_exclusion_seconds": behind_exclusion_seconds,
        "min_distance_ahead_m": min_ahead_distance,
        "min_distance_behind_m": min_behind_distance,
        "min_time_gap_ahead_s": min_ahead_gap,
        "min_time_gap_behind_s": min_behind_gap,
        "valid_pair_count": valid_pairs,
        "sample_count": sample_count,
        "coverage_fraction": coverage,
    }
    if sample_count == 0 or valid_pairs != sample_count:
        return ProximityContext(
            **common,
            state=ProximityState.CONTEXT_UNKNOWN,
            blocks_relative_resistance=True,
            explanation=(
                "Distance or player-speed coverage is incomplete, so time-gap "
                "proximity cannot support a relative-resistance conclusion."
            ),
        )

    ahead_near = min_ahead_gap is not None and min_ahead_gap <= ahead_exclusion_seconds
    behind_near = min_behind_gap is not None and min_behind_gap <= behind_exclusion_seconds
    if ahead_near and behind_near:
        state = ProximityState.NEARBY_CARS_AHEAD_AND_BEHIND
        explanation = "Cars were reported inside both time-gap exclusion windows."
    elif ahead_near:
        state = ProximityState.NEARBY_CAR_AHEAD
        explanation = f"A car ahead was reported within {ahead_exclusion_seconds:.2f} seconds."
    elif behind_near:
        state = ProximityState.NEARBY_CAR_BEHIND
        explanation = (
            f"A car behind was reported within {behind_exclusion_seconds:.2f} seconds. "
            "The measured speed remains valid, but nearby traffic could have contributed to it."
        )
    else:
        state = ProximityState.NO_NEARBY_CAR_REPORTED
        explanation = (
            "No car was reported inside the configured time-gap exclusion windows; "
            "this does not measure aerodynamic influence."
        )

    return ProximityContext(
        **common,
        state=state,
        blocks_relative_resistance=state is not ProximityState.NO_NEARBY_CAR_REPORTED,
        explanation=explanation,
    )


__all__ = [
    "ProximityContext",
    "ProximityState",
    "classify_proximity_window",
    "classify_proximity_time_gap_window",
]
