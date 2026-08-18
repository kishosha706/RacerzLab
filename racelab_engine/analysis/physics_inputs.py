"""Source-backed vehicle physics inputs.

Unknown physical constants stay unknown. Production analysis never substitutes
nominal values for a quantity that was not measured or supplied by setup truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
        return {
            key
            for key, value in self.__dict__.items()
            if _valid_physics_value(key, value) is not None
        }

    def confidence(self, required: list[str]) -> EstimateConfidence:
        """Return confidence that the required inputs are available."""
        provided = self.provided()
        missing = [name for name in required if name not in provided]
        return confidence_from_missing(
            required,
            provided,
            [
                f"{name} is unavailable; the dependent physical quantity is unavailable."
                for name in missing
            ],
        )

    def resolve_mass_kg(self) -> float | None:
        return _valid_physics_value("mass_kg", self.mass_kg)

    def resolve_cg_height_m(self) -> float | None:
        """Return only a supplied CG height."""
        return _valid_physics_value("cg_height_m", self.cg_height_m)

    def resolve_crr(self) -> float | None:
        """Return only a supplied rolling-resistance coefficient."""
        return _valid_physics_value("crr", self.crr)

    def resolve_motion_ratio_front(self) -> float | None:
        """Return only a supplied front motion ratio."""
        return _valid_physics_value("motion_ratio_front", self.motion_ratio_front)

    def resolve_motion_ratio_rear(self) -> float | None:
        """Return only a supplied rear motion ratio."""
        return _valid_physics_value("motion_ratio_rear", self.motion_ratio_rear)

    def resolve_motion_ratio_corner(self, corner: str) -> float | None:
        """Return a supplied axle motion ratio for a known corner."""
        if corner in {"lf", "rf"}:
            return self.resolve_motion_ratio_front()
        return self.resolve_motion_ratio_rear() if corner in {"lr", "rr"} else None

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
        number = float(v)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_physics_value(key: str, value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if key == "crr":
        return number if number >= 0.0 else None
    return number if number > 0.0 else None
