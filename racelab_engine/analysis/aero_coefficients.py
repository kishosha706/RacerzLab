"""Research-only aerodynamic coefficient estimates.

All force/aero values are ESTIMATES / proxies — not direct measurements and
not admissible as Crew Chief or P19 mechanism support. Missing inputs make the
dependent quantity unavailable.
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


def _first_finite(*values: Any) -> float | None:
    for value in values:
        number = _finite(value)
        if number is not None:
            return number
    return None


def air_speed_mps(
    vehicle_speed_mps: float | None,
    wind_speed_mps: float | None = None,
    vehicle_heading_rad: float | None = None,
    wind_heading_rad: float | None = None,
) -> tuple[float | None, EstimateConfidence]:
    """Compute air-relative speed from vehicle speed and wind vector.

    Wind speed and both headings are required; ground speed is not air speed.
    """
    vehicle_speed_mps = _finite(vehicle_speed_mps)
    wind_speed_mps = _finite(wind_speed_mps)
    vehicle_heading_rad = _finite(vehicle_heading_rad)
    wind_heading_rad = _finite(wind_heading_rad)
    if vehicle_speed_mps is not None and vehicle_speed_mps < 0:
        vehicle_speed_mps = None
    if wind_speed_mps is not None and wind_speed_mps < 0:
        wind_speed_mps = None
    if vehicle_speed_mps is None:
        return None, confidence_from_missing(
            ["vehicle_speed_mps"], set(),
            ["Vehicle speed unavailable."],
        )
    if (
        wind_speed_mps is None
        or wind_heading_rad is None
        or vehicle_heading_rad is None
    ):
        return None, confidence_from_missing(
            ["wind_speed_mps", "wind_heading_rad", "vehicle_heading_rad"],
            set(),
            ["Air-relative speed is unavailable because wind/heading context is incomplete."],
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

    Air density and air-relative speed are both required.
    """
    air_density_kg_m3 = _finite(air_density_kg_m3)
    speed_mps = _finite(speed_mps)
    if air_density_kg_m3 is not None and air_density_kg_m3 <= 0:
        air_density_kg_m3 = None
    if speed_mps is not None and speed_mps < 0:
        speed_mps = None
    if (
        speed_mps is None
        or air_density_kg_m3 is None
    ):
        return None, confidence_from_missing(
            [
                name
                for name, value in (
                    ("air_density_kg_m3", air_density_kg_m3),
                    ("speed_mps", speed_mps),
                )
                if value is None
            ],
            set(),
            ["Dynamic pressure is unavailable without measured density and air speed."],
        )
    q = 0.5 * air_density_kg_m3 * speed_mps * speed_mps
    return q, confidence_from_missing(
        [], set(),
        ["Dynamic pressure computed from measured air density and speed."],
    )


def aero_load_index(dynamic_pressure_pa: float | None) -> tuple[float | None, EstimateConfidence]:
    """Research-only fixed-reference pressure ratio, never measured aero load."""
    dynamic_pressure_pa = _finite(dynamic_pressure_pa)
    if dynamic_pressure_pa is not None and dynamic_pressure_pa < 0:
        dynamic_pressure_pa = None
    if (
        dynamic_pressure_pa is None
        or REFERENCE_DYNAMIC_PRESSURE_PA <= 0
    ):
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
    _ = inputs  # retained for API compatibility; nominal physics is never read here
    v_mps = _float(row, "speed_mps")
    wind_spd = _first_finite(row.get("wind_speed_mps"), row.get("WindVel"))
    wind_dir = _first_finite(row.get("wind_dir_rad"), row.get("WindDir"))
    yaw = _first_finite(row.get("yaw_rad"), row.get("Yaw"))
    air_density = _first_finite(row.get("air_density"), row.get("AirDensity"))
    air_speed, air_speed_confidence = air_speed_mps(v_mps, wind_spd, yaw, wind_dir)
    if air_speed is None:
        return None, air_speed_confidence
    q, conf = dynamic_pressure_pa(air_density, air_speed)
    return q, conf


# ── CdA Proxy estimates ───────────────────────────────────────

def rolling_resistance_force_n(
    mass_kg: float | None,
    crr: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """F_rr = Crr * m * g"""
    mass_kg = _finite(mass_kg)
    crr = _finite(crr)
    if mass_kg is not None and mass_kg <= 0:
        mass_kg = None
    if crr is not None and crr < 0:
        crr = None
    if mass_kg is None or crr is None:
        return None, confidence_from_missing(
            [
                name
                for name, value in (("mass_kg", mass_kg), ("crr", crr))
                if value is None
            ],
            set(),
            ["Rolling resistance is unavailable without mass and a source-backed Crr."],
        )
    return crr * mass_kg * G, confidence_from_missing([], set(), [])


def grade_force_n(
    mass_kg: float | None,
    grade_rad: float | None = None,
) -> tuple[float | None, EstimateConfidence]:
    """F_grade = m * g * sin(grade)"""
    mass_kg = _finite(mass_kg)
    grade_rad = _finite(grade_rad)
    if mass_kg is not None and mass_kg <= 0:
        mass_kg = None
    if mass_kg is None or grade_rad is None:
        return None, confidence_from_missing(
            [
                name
                for name, value in (("mass_kg", mass_kg), ("grade_rad", grade_rad))
                if value is None
            ],
            set(),
            ["Grade force is unavailable without mass and measured grade context."],
        )
    return mass_kg * G * math.sin(grade_rad), confidence_from_missing([], set(), [])


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
    throttle_pct = _finite(throttle_pct)
    brake_pct = _finite(brake_pct)
    speed_mps = _finite(speed_mps)
    long_accel_mps2 = _finite(long_accel_mps2)
    resistance = _finite(full_throttle_resistance_index)
    if None in {throttle_pct, brake_pct, speed_mps, long_accel_mps2}:
        return False
    return bool(
        0.0 <= throttle_pct < 1.0
        and 0.0 <= brake_pct < 1.0
        and speed_mps >= min_speed_mps
        and long_accel_mps2 < 0.0
        and (resistance is None or resistance <= 0.01)
    )


def cda_coastdown_proxy_m2(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    q_air_pa: float | None,
    crr: float | None = None,
    grade_rad: float | None = None,
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
    if mass_kg is not None and mass_kg <= 0:
        mass_kg = None
    if crr is not None and crr < 0:
        crr = None
    if q_air_pa is not None and q_air_pa <= 0:
        q_air_pa = None
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
    if q_air_pa is None:
        return None, confidence_from_missing(
            ["q_air_pa"], set(),
            ["Dynamic pressure unavailable or zero."],
        )
    frr, _ = rolling_resistance_force_n(mass_kg, crr)
    fg, _ = grade_force_n(mass_kg, grade_rad)
    if frr is None or fg is None:
        return None, confidence_from_missing(
            [
                name
                for name, value in (("crr", crr), ("grade_rad", grade_rad))
                if value is None
            ],
            set(),
            ["CdA-like coastdown residual is unavailable when road-load components are unknown."],
        )
    # Deceleration is negative ax; drag opposes motion
    inertial_force = mass_kg * (-long_accel_mps2)
    f_drag = inertial_force - frr - fg
    if f_drag <= 0:
        return None, confidence_from_missing(
            [], set(),
            ["Computed drag force is non-positive; coastdown may not be active."],
        )
    cda_proxy = f_drag / q_air_pa
    return cda_proxy, confidence_from_missing(
        [],
        set(),
        ["CdA Proxy from coastdown. ESTIMATE — not a direct measurement."],
    )


def full_throttle_resistance_cda_proxy_m2(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    q_air_pa: float | None,
    engine_force_n: float | None = None,
    crr: float | None = None,
    grade_rad: float | None = None,
) -> tuple[float | None, EstimateConfidence]:
    """Full-Throttle Resistance CdA Proxy.

    F_drag = engine_force - m*ax - F_rr - F_grade
    CdA_proxy = F_drag / q

    All force-balance inputs, including measured engine force, are required.
    Never display as plain "CdA". Always label as "Full-Throttle Resistance CdA Proxy".
    """
    mass_kg = _finite(mass_kg)
    long_accel_mps2 = _finite(long_accel_mps2)
    q_air_pa = _finite(q_air_pa)
    engine_force_n = _finite(engine_force_n)
    crr = _finite(crr)
    grade_rad = _finite(grade_rad)
    if mass_kg is not None and mass_kg <= 0:
        mass_kg = None
    if engine_force_n is not None and engine_force_n <= 0:
        engine_force_n = None
    if crr is not None and crr < 0:
        crr = None
    if q_air_pa is not None and q_air_pa <= 0:
        q_air_pa = None
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if (
        long_accel_mps2 is None
        or q_air_pa is None
        or engine_force_n is None
    ):
        return None, confidence_from_missing(
            [
                name
                for name, value in (
                    ("long_accel_mps2", long_accel_mps2),
                    ("q_air_pa", q_air_pa),
                    ("engine_force_n", engine_force_n),
                )
                if value is None
            ],
            set(),
            ["Full-throttle resistance is unavailable without measured engine force."],
        )
    frr, _ = rolling_resistance_force_n(mass_kg, crr)
    fg, _ = grade_force_n(mass_kg, grade_rad)
    if frr is None or fg is None:
        return None, confidence_from_missing(
            [
                name
                for name, value in (("crr", crr), ("grade_rad", grade_rad))
                if value is None
            ],
            set(),
            ["Full-throttle resistance is unavailable when road-load components are unknown."],
        )
    inertial_force = mass_kg * long_accel_mps2
    f_drag = engine_force_n - inertial_force - frr - fg
    if f_drag <= 0:
        return None, confidence_from_missing(
            [], set(),
            ["Computed drag force is non-positive; may not be in a drag-limited condition."],
        )
    cda_proxy = f_drag / q_air_pa
    assumptions = ["Full-Throttle Resistance CdA Proxy. ESTIMATE — not a direct measurement."]
    return cda_proxy, confidence_from_missing(
        [],
        set(),
        assumptions,
    )


def _float(d: dict[str, Any], key: str) -> float | None:
    v = d.get(key)
    return _finite(v)
