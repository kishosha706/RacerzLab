"""Vehicle physics input dataclass.

Centralizes the vehicle parameters needed for force, aero, and tire estimates.
Default values carry low confidence and are documented as assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from racelab_engine.analysis.estimate_confidence import (
    EstimateConfidence,
    confidence_from_missing,
)


@dataclass(frozen=True)
class VehiclePhysicsInputs:
    mass_kg: float | None = None
    cg_height_m: float | None = None
    wheelbase_m: float | None = None
    front_track_width_m: float | None = None
    rear_track_width_m: float | None = None
    front_axle_to_cg_m: float | None = None
    rear_axle_to_cg_m: float | None = None
    crr: float | None = None
    motion_ratio_front: float | None = None
    motion_ratio_rear: float | None = None

    def provided(self) -> set[str]:
        return {k for k, v in self.__dict__.items() if v is not None}

    def confidence(self, required: list[str]) -> EstimateConfidence:
        """Return confidence that the required inputs are available."""
        provided = self.provided()
        assumptions: list[str] = []
        if self.cg_height_m is None and "cg_height_m" in required:
            assumptions.append("cg_height_m defaulted to 0.30 m (low confidence).")
        if self.crr is None and "crr" in required:
            assumptions.append("crr defaulted to 0.015 (low confidence).")
        if self.motion_ratio_front is None and "motion_ratio_front" in required:
            assumptions.append("motion_ratio_front defaulted to 1.0 (low confidence).")
        if self.motion_ratio_rear is None and "motion_ratio_rear" in required:
            assumptions.append("motion_ratio_rear defaulted to 1.0 (low confidence).")
        return confidence_from_missing(required, provided, assumptions)

    def resolve_mass_kg(self) -> float | None:
        return self.mass_kg

    def resolve_cg_height_m(self) -> float:
        """Return cg_height_m or a low-confidence default of 0.30 m."""
        return self.cg_height_m if self.cg_height_m is not None else 0.30

    def resolve_crr(self) -> float:
        """Return crr or a low-confidence default of 0.015."""
        return self.crr if self.crr is not None else 0.015

    def resolve_motion_ratio_front(self) -> float:
        """Return motion_ratio_front or a low-confidence default of 1.0."""
        return self.motion_ratio_front if self.motion_ratio_front is not None else 1.0

    def resolve_motion_ratio_rear(self) -> float:
        """Return motion_ratio_rear or a low-confidence default of 1.0."""
        return self.motion_ratio_rear if self.motion_ratio_rear is not None else 1.0

    def resolve_motion_ratio_corner(self, corner: str) -> float:
        """Return motion ratio for a specific corner (lf/rf/lr/rr).

        Falls back to front or rear average, then 1.0.
        """
        if corner in {"lf", "rf"}:
            return self.resolve_motion_ratio_front()
        return self.resolve_motion_ratio_rear() if corner in {"lr", "rr"} else 1.0

    @staticmethod
    def from_row(row: dict[str, Any]) -> VehiclePhysicsInputs:
        """Extract available physics inputs from a telemetry row or setup dict."""
        return VehiclePhysicsInputs(
            mass_kg=_float(row, "mass_kg"),
            cg_height_m=_float(row, "cg_height_m"),
            wheelbase_m=_float(row, "wheelbase_m"),
            front_track_width_m=_float(row, "front_track_width_m"),
            rear_track_width_m=_float(row, "rear_track_width_m"),
            front_axle_to_cg_m=_float(row, "front_axle_to_cg_m"),
            rear_axle_to_cg_m=_float(row, "rear_axle_to_cg_m"),
            crr=_float(row, "crr"),
            motion_ratio_front=_float(row, "motion_ratio_front"),
            motion_ratio_rear=_float(row, "motion_ratio_rear"),
        )


def _float(d: dict[str, Any], key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
