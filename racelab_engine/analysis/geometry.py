"""SI-first platform geometry calculations.

Centralizes ride-height-based pitch/roll estimation with motion-ratio hooks.
All internal math uses meters and radians. Converts to inches/degrees only
for presentation channels.

Geometry estimate assumes 1:1 motion ratio until .sto or setup snapshot
provides motion-ratio data.
"""

from __future__ import annotations

import math
from typing import Any

from racelab_engine.analysis.constants import apply_motion_ratio


def corrected_delta_m(raw_delta_m: float, motion_ratio: float | None) -> float:
    """Apply motion ratio to a raw wheel-travel delta (meters).

    Falls back to 1:1 if motion_ratio is unavailable.
    """
    return apply_motion_ratio(raw_delta_m, motion_ratio)


def compute_pitch_deg(
    front_rh_m: float | None,
    rear_rh_m: float | None,
    wheelbase_m: float | None,
    front_motion_ratio: float | None = None,
    rear_motion_ratio: float | None = None,
) -> float | None:
    """Compute platform pitch angle from ride heights.

    Positive = rear higher than front (nose-down pitch).
    Uses atan2 for robustness.
    """
    if front_rh_m is None or rear_rh_m is None or wheelbase_m is None or wheelbase_m <= 0:
        return None
    front_corrected = corrected_delta_m(front_rh_m, front_motion_ratio)
    rear_corrected = corrected_delta_m(rear_rh_m, rear_motion_ratio)
    delta_m = rear_corrected - front_corrected
    return math.degrees(math.atan2(delta_m, wheelbase_m))


def compute_roll_deg(
    left_rh_m: float | None,
    right_rh_m: float | None,
    track_width_m: float | None,
    left_motion_ratio: float | None = None,
    right_motion_ratio: float | None = None,
) -> float | None:
    """Compute platform roll angle from ride heights.

    Positive = right side higher.
    Uses atan2 for robustness.
    """
    if left_rh_m is None or right_rh_m is None or track_width_m is None or track_width_m <= 0:
        return None
    left_corrected = corrected_delta_m(left_rh_m, left_motion_ratio)
    right_corrected = corrected_delta_m(right_rh_m, right_motion_ratio)
    delta_m = right_corrected - left_corrected
    return math.degrees(math.atan2(delta_m, track_width_m))


def ride_height_m_to_in(meters: float | None) -> float | None:
    """Convert ride height from meters to inches."""
    if meters is None:
        return None
    return meters * 39.37007874


def ride_height_mm_to_m(mm: float | None) -> float | None:
    """Convert ride height from millimeters to meters."""
    if mm is None:
        return None
    return mm / 1000.0
