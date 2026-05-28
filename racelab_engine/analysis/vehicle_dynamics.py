"""Vehicle dynamics force and energy estimates.

All force/energy values are ESTIMATES / proxies — not direct measurements.
Uses SI units internally.

Formulas:
  DeltaF_long = m * ax * cg_height / wheelbase
  DeltaF_lat = m * ay * cg_height / track_width
  aero_residual = inferred_spring_load_delta - mechanical_transfer
  brake_energy = 0.5 * m * (v_entry^2 - v_exit^2)
  brake_power = brake_energy / duration
  accel_power = m * ax * v
  drag_power = F_drag * v
  wheel_power = accel_power + drag_power + rolling_power + grade_power
"""

from __future__ import annotations

import math
from typing import Any

from racelab_engine.analysis.estimate_confidence import (
    EstimateConfidence,
    confidence_from_missing,
)
from racelab_engine.analysis.physics_inputs import VehiclePhysicsInputs

G = 9.81  # m/s²


# ── Weight transfer ───────────────────────────────────────────

def longitudinal_weight_transfer_n(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    cg_height_m: float | None,
    wheelbase_m: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """DeltaF_long = m * ax * cg_height / wheelbase

    Positive ax (acceleration) transfers weight to rear.
    Negative ax (braking) transfers weight to front.
    """
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if long_accel_mps2 is None:
        return None, confidence_from_missing(
            ["long_accel_mps2"], set(),
            ["Longitudinal acceleration unavailable."],
        )
    if wheelbase_m is None or wheelbase_m <= 0:
        return None, confidence_from_missing(
            ["wheelbase_m"], set(),
            ["Wheelbase unavailable or invalid."],
        )
    effective_cg = cg_height_m if cg_height_m is not None else 0.30
    assumptions: list[str] = []
    if cg_height_m is None:
        assumptions.append("cg_height_m defaulted to 0.30 m (low confidence).")
    transfer = mass_kg * long_accel_mps2 * effective_cg / wheelbase_m
    return transfer, confidence_from_missing(
        [] if cg_height_m is not None else ["cg_height_m"],
        set(),
        assumptions,
    )


def lateral_weight_transfer_n(
    mass_kg: float | None,
    lat_accel_mps2: float | None,
    cg_height_m: float | None,
    track_width_m: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """DeltaF_lat = m * ay * cg_height / track_width

    Positive ay (left turn) transfers weight to right side.
    """
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if lat_accel_mps2 is None:
        return None, confidence_from_missing(
            ["lat_accel_mps2"], set(),
            ["Lateral acceleration unavailable."],
        )
    if track_width_m is None or track_width_m <= 0:
        return None, confidence_from_missing(
            ["track_width_m"], set(),
            ["Track width unavailable or invalid."],
        )
    effective_cg = cg_height_m if cg_height_m is not None else 0.30
    assumptions: list[str] = []
    if cg_height_m is None:
        assumptions.append("cg_height_m defaulted to 0.30 m (low confidence).")
    transfer = mass_kg * lat_accel_mps2 * effective_cg / track_width_m
    return transfer, confidence_from_missing(
        [] if cg_height_m is not None else ["cg_height_m"],
        {"mass_kg", "lat_accel_mps2", "track_width_m"},
        assumptions,
    )


def axle_transfer_distribution(
    front_axle_to_cg_m: float | None,
    rear_axle_to_cg_m: float | None,
    wheelbase_m: float | None,
) -> tuple[float | None, float | None, EstimateConfidence]:
    """Return (front_fraction, rear_fraction) of total lateral weight transfer.

    Front fraction = rear_axle_to_cg / wheelbase (weight on front axle).
    Rear fraction = front_axle_to_cg / wheelbase.
    """
    if wheelbase_m is None or wheelbase_m <= 0:
        return None, None, confidence_from_missing(
            ["wheelbase_m"], set(),
            ["Wheelbase unavailable."],
        )
    if front_axle_to_cg_m is None or rear_axle_to_cg_m is None:
        return None, None, confidence_from_missing(
            ["front_axle_to_cg_m", "rear_axle_to_cg_m"], set(),
            ["Axle-to-CG distances unavailable."],
        )
    front_frac = rear_axle_to_cg_m / wheelbase_m
    rear_frac = front_axle_to_cg_m / wheelbase_m
    return front_frac, rear_frac, confidence_from_missing(
        [], set(),
        [],
    )


def aero_residual_load_proxy_n(
    inferred_spring_load_delta_n: float | None,
    mechanical_transfer_n: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """aero_residual = inferred_spring_load - mechanical_transfer

    Positive residual suggests aero downforce proxy (or bump/transient noise).
    Negative residual suggests aero lift or measurement error.
    """
    if inferred_spring_load_delta_n is None:
        return None, confidence_from_missing(
            ["inferred_spring_load_delta_n"], set(),
            ["Spring load delta unavailable."],
        )
    if mechanical_transfer_n is None:
        return None, confidence_from_missing(
            ["mechanical_transfer_n"], set(),
            ["Mechanical transfer unavailable."],
        )
    residual = inferred_spring_load_delta_n - mechanical_transfer_n
    return residual, confidence_from_missing(
        [], set(),
        ["Aero residual load proxy. ESTIMATE — not a direct force measurement."],
    )


# ── Curvature / yaw math (pure functions, no .mt2 dependency) ─

def curvature_from_heading_distance(
    prev_heading_rad: float,
    next_heading_rad: float,
    prev_distance_m: float,
    next_distance_m: float,
) -> float | None:
    """Compute curvature (1/m) from heading change over distance.

    curvature = d(heading) / d(distance)
    """
    d_heading = next_heading_rad - prev_heading_rad
    d_distance = next_distance_m - prev_distance_m
    if abs(d_distance) < 1e-9:
        return None
    # Normalize heading delta to [-pi, pi]
    while d_heading > math.pi:
        d_heading -= math.tau
    while d_heading < -math.pi:
        d_heading += math.tau
    return d_heading / d_distance


def yaw_rate_expected_rad_s(
    speed_mps: float | None,
    curvature_1_per_m: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Expected yaw rate = speed * curvature."""
    if speed_mps is None:
        return None, confidence_from_missing(
            ["speed_mps"], set(),
            ["Speed unavailable."],
        )
    if curvature_1_per_m is None:
        return None, confidence_from_missing(
            ["curvature_1_per_m"], set(),
            ["Curvature unavailable."],
        )
    return speed_mps * curvature_1_per_m, confidence_from_missing(
        [], set(), [],
    )


def lat_accel_expected_mps2(
    speed_mps: float | None,
    curvature_1_per_m: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Expected lateral acceleration = speed^2 * curvature."""
    if speed_mps is None:
        return None, confidence_from_missing(
            ["speed_mps"], set(),
            ["Speed unavailable."],
        )
    if curvature_1_per_m is None:
        return None, confidence_from_missing(
            ["curvature_1_per_m"], set(),
            ["Curvature unavailable."],
        )
    return speed_mps * speed_mps * curvature_1_per_m, confidence_from_missing(
        [], set(), [],
    )


def yaw_error_rad_s(
    expected_yaw_rate_rad_s: float | None,
    actual_yaw_rate_rad_s: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """yaw_error = expected - actual.

    Positive = understeer (car not rotating enough).
    Negative = oversteer (car rotating more than expected).
    """
    if expected_yaw_rate_rad_s is None or actual_yaw_rate_rad_s is None:
        return None, confidence_from_missing(
            ["expected_yaw_rate_rad_s", "actual_yaw_rate_rad_s"], set(),
            ["Yaw rate values unavailable."],
        )
    return expected_yaw_rate_rad_s - actual_yaw_rate_rad_s, confidence_from_missing(
        [], set(), [],
    )


def understeer_yaw_error_proxy(
    expected_yaw_rate_rad_s: float | None,
    actual_yaw_rate_rad_s: float | None,
) -> tuple[float, EstimateConfidence]:
    """Understeer proxy: max(0, expected - actual).

    Returns 0 if oversteer or data unavailable.
    """
    error, conf = yaw_error_rad_s(expected_yaw_rate_rad_s, actual_yaw_rate_rad_s)
    return (max(0.0, error), conf) if error is not None else (0.0, conf)


# ── Dynamic grade isolation ────────────────────────────────────

MAX_GRADE_COMPONENT = 0.30  # max |sin(grade)| before clamping; ~17.5°


def dynamic_grade_rad(
    long_accel_mps2: float | None,
    speed_rate_mps2: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Estimate track grade (slope) from sensor acceleration vs speed derivative.

    grade_rad = asin(clamp((long_accel - speed_rate) / g, -MAX_GRADE_COMPONENT, MAX_GRADE_COMPONENT))

    Positive = uphill (sensor reads more acceleration than speed change).
    Negative = downhill (sensor reads less acceleration than speed change).

    ESTIMATE — grade is inferred, not measured. Low confidence during
    braking, wheelspin, high yaw, or low speed.
    """
    if long_accel_mps2 is None:
        return None, confidence_from_missing(
            ["long_accel_mps2"], set(),
            ["Longitudinal acceleration unavailable."],
        )
    if speed_rate_mps2 is None:
        return None, confidence_from_missing(
            ["speed_rate_mps2"], set(),
            ["Speed rate (dv/dt) unavailable. Grade cannot be isolated without speed derivative."],
        )
    sin_theta = (long_accel_mps2 - speed_rate_mps2) / G
    sin_theta = max(-MAX_GRADE_COMPONENT, min(MAX_GRADE_COMPONENT, sin_theta))
    grade = math.asin(sin_theta)
    return grade, confidence_from_missing(
        [], set(),
        ["Dynamic grade ESTIMATE. Inferred from acceleration vs speed derivative. "
         "Low confidence during braking, wheelspin, high yaw, or low speed."],
    )


def dynamic_grade_deg(
    long_accel_mps2: float | None,
    speed_rate_mps2: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Dynamic grade in degrees. See dynamic_grade_rad."""
    grade_rad, conf = dynamic_grade_rad(long_accel_mps2, speed_rate_mps2)
    return (math.degrees(grade_rad), conf) if grade_rad is not None else (None, conf)


def grade_force_proxy_n(
    mass_kg: float | None,
    grade_rad: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Grade force = m * g * sin(grade).

    Positive grade (uphill) → positive grade force (resisting motion).
    Negative grade (downhill) → negative grade force (aiding motion).

    ESTIMATE — grade is inferred, not measured.
    """
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if grade_rad is None:
        return None, confidence_from_missing(
            ["grade_rad"], set(),
            ["Grade unavailable."],
        )
    force = mass_kg * G * math.sin(grade_rad)
    return force, confidence_from_missing(
        [], set(),
        ["Grade force ESTIMATE. Relies on inferred grade."],
    )


def grade_corrected_long_accel_mps2(
    long_accel_mps2: float | None,
    grade_rad: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Remove grade component from longitudinal acceleration.

    a_corrected = a_sensor - g * sin(grade)

    When grade is positive (uphill), the sensor reads extra acceleration
    from gravity. Subtracting g*sin(grade) gives the true car acceleration.
    """
    if long_accel_mps2 is None:
        return None, confidence_from_missing(
            ["long_accel_mps2"], set(),
            ["Longitudinal acceleration unavailable."],
        )
    if grade_rad is None:
        return None, confidence_from_missing(
            ["grade_rad"], set(),
            ["Grade unavailable."],
        )
    corrected = long_accel_mps2 - G * math.sin(grade_rad)
    return corrected, confidence_from_missing(
        [], set(),
        ["Grade-corrected acceleration ESTIMATE. Relies on inferred grade."],
    )


# ── Brake energy and wheel power ──────────────────────────────

def brake_energy_j(
    mass_kg: float | None,
    entry_speed_mps: float | None,
    exit_speed_mps: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Brake energy = 0.5 * m * (v_entry^2 - v_exit^2)"""
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if entry_speed_mps is None or exit_speed_mps is None:
        return None, confidence_from_missing(
            ["entry_speed_mps", "exit_speed_mps"], {"mass_kg"},
            ["Speed values unavailable."],
        )
    energy = 0.5 * mass_kg * (entry_speed_mps * entry_speed_mps - exit_speed_mps * exit_speed_mps)
    if energy < 0:
        energy = 0.0  # accelerating, not braking
    return energy, confidence_from_missing(
        [], set(),
        ["Brake energy estimate. Assumes no grade or drag contribution."],
    )


def brake_power_w(
    brake_energy_j: float | None,
    brake_duration_s: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Brake power = energy / duration"""
    if brake_energy_j is None:
        return None, confidence_from_missing(
            ["brake_energy_j"], set(),
            ["Brake energy unavailable."],
        )
    if brake_duration_s is None or brake_duration_s <= 0:
        return None, confidence_from_missing(
            ["brake_duration_s"], set(),
            ["Brake duration unavailable or invalid."],
        )
    return brake_energy_j / brake_duration_s, confidence_from_missing(
        [], set(), [],
    )


def accel_power_w(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    speed_mps: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Acceleration power = m * ax * v"""
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if long_accel_mps2 is None or speed_mps is None:
        return None, confidence_from_missing(
            ["long_accel_mps2", "speed_mps"], set(),
            ["Acceleration or speed unavailable."],
        )
    power = mass_kg * long_accel_mps2 * speed_mps
    return power, confidence_from_missing(
        [], set(),
        ["Acceleration power estimate."],
    )


def drag_power_w(
    drag_force_n: float | None,
    speed_mps: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Drag power = F_drag * v"""
    if drag_force_n is None:
        return None, confidence_from_missing(
            ["drag_force_n"], set(),
            ["Drag force unavailable."],
        )
    if speed_mps is None:
        return None, confidence_from_missing(
            ["speed_mps"], set(),
            ["Speed unavailable."],
        )
    return drag_force_n * speed_mps, confidence_from_missing(
        [], set(), [],
    )


def wheel_power_proxy_w(
    accel_power_w: float | None = None,
    drag_power_w: float | None = None,
    rolling_power_w: float | None = None,
    grade_power_w: float | None = None,
) -> tuple[float | None, EstimateConfidence]:
    """Wheel power = accel + drag + rolling + grade.

    Missing components are treated as zero (lower confidence).
    """
    components = [p for p in [accel_power_w, drag_power_w, rolling_power_w, grade_power_w] if p is not None]
    if not components:
        return None, confidence_from_missing(
            ["accel_power_w", "drag_power_w", "rolling_power_w", "grade_power_w"],
            set(),
            ["No power components available."],
        )
    total = sum(components)
    missing = []
    if accel_power_w is None:
        missing.append("accel_power_w")
    if drag_power_w is None:
        missing.append("drag_power_w")
    if rolling_power_w is None:
        missing.append("rolling_power_w")
    if grade_power_w is None:
        missing.append("grade_power_w")
    return total, confidence_from_missing(
        missing, set(),
        ["Wheel power proxy. ESTIMATE."],
    )
