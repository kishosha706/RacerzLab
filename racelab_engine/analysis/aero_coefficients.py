"""Aerodynamic coefficient estimates.

All force/aero values are ESTIMATES / proxies — not direct measurements.
Uses SI units internally. Converts to display units only through metadata.

Formulas:
  q = 0.5 * rho * v_air^2
  F_rr = Crr * m * g
  F_grade = m * g * sin(grade)
  F_drag = m * (-ax) - F_rr - F_grade
  CdA_proxy = F_drag / q

Naming:
  - "CdA" alone is never used. All estimates are labeled "CdA Proxy" or
    "Full-Throttle Resistance CdA Proxy" to avoid implying direct measurement.
"""

from __future__ import annotations

import math
from typing import Any

from racelab_engine.analysis.constants import (
    REFERENCE_DYNAMIC_PRESSURE_PA,
    SEA_LEVEL_AIR_DENSITY_KG_M3,
)
from racelab_engine.analysis.estimate_confidence import (
    EstimateConfidence,
    confidence_from_missing,
)
from racelab_engine.analysis.physics_inputs import VehiclePhysicsInputs

G = 9.81  # m/s²


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def air_speed_mps(
    vehicle_speed_mps: float | None,
    wind_speed_mps: float | None = None,
    vehicle_heading_rad: float | None = None,
    wind_heading_rad: float | None = None,
) -> tuple[float | None, EstimateConfidence]:
    """Compute air-relative speed from vehicle speed and wind vector.

    If wind data is missing, falls back to ground speed with lower confidence.
    """
    vehicle_speed_mps = _finite(vehicle_speed_mps)
    wind_speed_mps = _finite(wind_speed_mps)
    vehicle_heading_rad = _finite(vehicle_heading_rad)
    wind_heading_rad = _finite(wind_heading_rad)
    if vehicle_speed_mps is None:
        return None, confidence_from_missing(
            ["vehicle_speed_mps"], set(),
            ["Vehicle speed unavailable."],
        )
    if wind_speed_mps is None or wind_heading_rad is None or vehicle_heading_rad is None:
        return vehicle_speed_mps, confidence_from_missing(
            ["wind_speed_mps", "wind_heading_rad", "vehicle_heading_rad"],
            set(),
            ["Used ground-speed dynamic pressure; wind/heading unavailable."],
        )
    # Vector addition: v_air = v_vehicle - v_wind
    vvx = vehicle_speed_mps * math.cos(vehicle_heading_rad)
    vvy = vehicle_speed_mps * math.sin(vehicle_heading_rad)
    vwx = wind_speed_mps * math.cos(wind_heading_rad)
    vwy = wind_speed_mps * math.sin(wind_heading_rad)
    vax = vvx - vwx
    vay = vvy - vwy
    air_speed = math.hypot(vax, vay)
    return air_speed, confidence_from_missing(
        [], set(),
        ["Air-relative speed computed from wind vector."],
    )


def dynamic_pressure_pa(
    air_density_kg_m3: float | None,
    speed_mps: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Compute dynamic pressure q = 0.5 * rho * v^2.

    Falls back to sea-level air density if missing.
    """
    air_density_kg_m3 = _finite(air_density_kg_m3)
    speed_mps = _finite(speed_mps)
    if speed_mps is None:
        return None, confidence_from_missing(
            ["speed_mps"], set(),
            ["Speed unavailable."],
        )
    rho = air_density_kg_m3 if air_density_kg_m3 is not None else SEA_LEVEL_AIR_DENSITY_KG_M3
    q = 0.5 * rho * speed_mps * speed_mps
    if air_density_kg_m3 is None:
        return q, confidence_from_missing(
            ["air_density_kg_m3"],
            set(),
            ["Air density unavailable; used sea-level default (1.225 kg/m³)."],
        )
    return q, confidence_from_missing(
        [], set(),
        ["Dynamic pressure computed from measured air density and speed."],
    )


def aero_load_index(dynamic_pressure_pa: float | None) -> tuple[float | None, EstimateConfidence]:
    """Cross-run comparable aero load index relative to 180 mph sea-level reference."""
    dynamic_pressure_pa = _finite(dynamic_pressure_pa)
    if dynamic_pressure_pa is None or REFERENCE_DYNAMIC_PRESSURE_PA <= 0:
        return None, confidence_from_missing(
            ["dynamic_pressure_pa"], set(),
            ["Dynamic pressure unavailable."],
        )
    index = dynamic_pressure_pa / REFERENCE_DYNAMIC_PRESSURE_PA
    return index, confidence_from_missing([], set(), [])


def dynamic_pressure_air_context(
    row: dict[str, Any],
    inputs: VehiclePhysicsInputs,
) -> tuple[float | None, EstimateConfidence]:
    """Convenience: compute air-relative dynamic pressure from a telemetry row."""
    v_mps = _float(row, "speed_mps")
    wind_spd = _float(row, "wind_speed_mps") or _float(row, "WindVel")
    wind_dir = _float(row, "wind_dir_rad") or _float(row, "WindDir")
    yaw = _float(row, "yaw_rad") or _float(row, "Yaw")
    air_density = _float(row, "air_density") or _float(row, "AirDensity")
    air_speed, _ = air_speed_mps(v_mps, wind_spd, yaw, wind_dir)
    q, conf = dynamic_pressure_pa(air_density, air_speed or v_mps)
    return q, conf


# ── CdA Proxy estimates ───────────────────────────────────────

def rolling_resistance_force_n(
    mass_kg: float | None,
    crr: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """F_rr = Crr * m * g"""
    mass_kg = _finite(mass_kg)
    crr = _finite(crr)
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable; cannot compute rolling resistance."],
        )
    effective_crr = crr if crr is not None else 0.015
    assumptions: list[str] = []
    if crr is None:
        assumptions.append("crr defaulted to 0.015 (low confidence).")
    return effective_crr * mass_kg * G, confidence_from_missing(
        [] if crr is not None else ["crr"],
        set(),
        assumptions,
    )


def grade_force_n(
    mass_kg: float | None,
    grade_rad: float | None = 0.0,
) -> tuple[float | None, EstimateConfidence]:
    """F_grade = m * g * sin(grade)"""
    mass_kg = _finite(mass_kg)
    grade_rad = _finite(grade_rad)
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    return mass_kg * G * math.sin(grade_rad or 0.0), confidence_from_missing(
        [], set(),
        ["Grade assumed zero unless provided."],
    )


def _coastdown_is_valid(
    throttle_pct: float | None,
    brake_pct: float | None,
    speed_mps: float | None,
    long_accel_mps2: float | None,
    full_throttle_resistance_index: float | None = None,
    min_speed_mps: float = 5.0,
) -> bool:
    """Check whether conditions are valid for a coastdown CdA estimate.

    Requirements:
    - throttle near zero (< 1%)
    - brake near zero (< 1%)
    - speed above minimum
    - decelerating (long_accel < 0)
    - no active full-throttle resistance
    """
    return not (
        (throttle_pct is not None and throttle_pct >= 1.0)
        or (brake_pct is not None and brake_pct >= 1.0)
        or (speed_mps is not None and speed_mps < min_speed_mps)
        or (long_accel_mps2 is not None and long_accel_mps2 >= 0)
        or (full_throttle_resistance_index is not None and full_throttle_resistance_index > 0.01)
    )


def cda_coastdown_proxy_m2(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    q_air_pa: float | None,
    crr: float | None = None,
    grade_rad: float | None = 0.0,
) -> tuple[float | None, EstimateConfidence]:
    """CdA Proxy from coastdown: F_drag = m * (-ax) - F_rr - F_grade, CdA_proxy = F_drag / q

    Validity requires: throttle low, brake low, steering low, speed above minimum.
    Use _coastdown_is_valid() for runtime gating before calling this function.
    This function computes the math only.
    """
    mass_kg = _finite(mass_kg)
    long_accel_mps2 = _finite(long_accel_mps2)
    q_air_pa = _finite(q_air_pa)
    crr = _finite(crr)
    grade_rad = _finite(grade_rad)
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable; cannot compute CdA Proxy."],
        )
    if long_accel_mps2 is None:
        return None, confidence_from_missing(
            ["long_accel_mps2"], set(),
            ["Longitudinal acceleration unavailable."],
        )
    if q_air_pa is None or q_air_pa <= 0:
        return None, confidence_from_missing(
            ["q_air_pa"], set(),
            ["Dynamic pressure unavailable or zero."],
        )
    frr, _ = rolling_resistance_force_n(mass_kg, crr)
    fg, _ = grade_force_n(mass_kg, grade_rad)
    # Deceleration is negative ax; drag opposes motion
    inertial_force = mass_kg * (-long_accel_mps2)
    f_drag = inertial_force - (frr or 0.0) - (fg or 0.0)
    if f_drag <= 0:
        return None, confidence_from_missing(
            [], set(),
            ["Computed drag force is non-positive; coastdown may not be active."],
        )
    cda_proxy = f_drag / q_air_pa
    return cda_proxy, confidence_from_missing(
        [] if crr is not None else ["crr"],
        set(),
        ["CdA Proxy from coastdown. ESTIMATE — not a direct measurement."],
    )


def full_throttle_resistance_cda_proxy_m2(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    q_air_pa: float | None,
    engine_force_n: float | None = None,
    crr: float | None = None,
    grade_rad: float | None = 0.0,
) -> tuple[float | None, EstimateConfidence]:
    """Full-Throttle Resistance CdA Proxy.

    F_drag = engine_force - m*ax - F_rr - F_grade
    CdA_proxy = F_drag / q

    Without engine_force_n, this is a residual proxy only.
    Never display as plain "CdA". Always label as "Full-Throttle Resistance CdA Proxy".
    """
    mass_kg = _finite(mass_kg)
    long_accel_mps2 = _finite(long_accel_mps2)
    q_air_pa = _finite(q_air_pa)
    engine_force_n = _finite(engine_force_n)
    crr = _finite(crr)
    grade_rad = _finite(grade_rad)
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if long_accel_mps2 is None or q_air_pa is None or q_air_pa <= 0:
        return None, confidence_from_missing(
            ["long_accel_mps2", "q_air_pa"], set(),
            ["Acceleration or dynamic pressure unavailable."],
        )
    frr, _ = rolling_resistance_force_n(mass_kg, crr)
    fg, _ = grade_force_n(mass_kg, grade_rad)
    inertial_force = mass_kg * long_accel_mps2
    if engine_force_n is not None:
        f_drag = engine_force_n - inertial_force - (frr or 0.0) - (fg or 0.0)
    else:
        # Without engine force, this is a residual: what's left after inertia + RR + grade
        f_drag = -inertial_force - (frr or 0.0) - (fg or 0.0)
    if f_drag <= 0:
        return None, confidence_from_missing(
            [], set(),
            ["Computed drag force is non-positive; may not be in a drag-limited condition."],
        )
    cda_proxy = f_drag / q_air_pa
    assumptions = ["Full-Throttle Resistance CdA Proxy. ESTIMATE — not a direct measurement."]
    if engine_force_n is None:
        assumptions.append("Engine force unavailable; this is a residual proxy with very low confidence.")
    return cda_proxy, confidence_from_missing(
        [] if crr is not None else ["crr"],
        set(),
        assumptions,
    )


def _float(d: dict[str, Any], key: str) -> float | None:
    v = d.get(key)
    return _finite(v)
