"""Tire dynamics estimates.

All tire force/slip values are ESTIMATES / proxies — not direct measurements.
Uses SI units internally.

Formulas:
  beta = atan2(v_y, v_x)
  alpha_front = steering - atan2(v_y + a * yaw_rate, v_x)
  alpha_rear = -atan2(v_y - b * yaw_rate, v_x)
  K_us = (alpha_front_deg - alpha_rear_deg) / lateral_accel_g
  mu_used = sqrt(Fx^2 + Fy^2) / Fz
"""

from __future__ import annotations

import math
from typing import Any

from racelab_engine.analysis.estimate_confidence import (
    EstimateConfidence,
    confidence_from_missing,
)

G = 9.81  # m/s²


# ── Kinematic slip angles ─────────────────────────────────────

def vehicle_sideslip_beta_rad(
    vx_mps: float | None,
    vy_mps: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Vehicle sideslip angle beta = atan2(v_y, v_x)."""
    if vx_mps is None or vy_mps is None:
        return None, confidence_from_missing(
            ["vx_mps", "vy_mps"], set(),
            ["Velocity components unavailable."],
        )
    if abs(vx_mps) < 0.01:
        return 0.0, confidence_from_missing(
            [], set(),
            ["Vehicle speed near zero; sideslip set to 0."],
        )
    return math.atan2(vy_mps, vx_mps), confidence_from_missing(
        [], set(), [],
    )


def front_slip_angle_rad(
    steering_rad: float | None,
    vx_mps: float | None,
    vy_mps: float | None,
    yaw_rate_rad_s: float | None,
    front_axle_to_cg_m: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Front slip angle alpha_f = steering - atan2(v_y + a * r, v_x)."""
    if steering_rad is None:
        return None, confidence_from_missing(
            ["steering_rad"], set(),
            ["Steering angle unavailable."],
        )
    if vx_mps is None or vy_mps is None:
        return None, confidence_from_missing(
            ["vx_mps", "vy_mps"], {"steering_rad"},
            ["Velocity components unavailable."],
        )
    if yaw_rate_rad_s is None:
        return None, confidence_from_missing(
            ["yaw_rate_rad_s"], {"steering_rad", "vx_mps", "vy_mps"},
            ["Yaw rate unavailable."],
        )
    if front_axle_to_cg_m is None:
        return None, confidence_from_missing(
            ["front_axle_to_cg_m"], {"steering_rad", "vx_mps", "vy_mps", "yaw_rate_rad_s"},
            ["Front axle to CG distance unavailable."],
        )
    if abs(vx_mps) < 0.01:
        return 0.0, confidence_from_missing(
            [], set(),
            ["Vehicle speed near zero; slip angle set to 0."],
        )
    alpha = steering_rad - math.atan2(vy_mps + front_axle_to_cg_m * yaw_rate_rad_s, vx_mps)
    return alpha, confidence_from_missing(
        [], set(), [],
    )


def rear_slip_angle_rad(
    vx_mps: float | None,
    vy_mps: float | None,
    yaw_rate_rad_s: float | None,
    rear_axle_to_cg_m: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Rear slip angle alpha_r = -atan2(v_y - b * r, v_x)."""
    if vx_mps is None or vy_mps is None:
        return None, confidence_from_missing(
            ["vx_mps", "vy_mps"], set(),
            ["Velocity components unavailable."],
        )
    if yaw_rate_rad_s is None:
        return None, confidence_from_missing(
            ["yaw_rate_rad_s"], {"vx_mps", "vy_mps"},
            ["Yaw rate unavailable."],
        )
    if rear_axle_to_cg_m is None:
        return None, confidence_from_missing(
            ["rear_axle_to_cg_m"], {"vx_mps", "vy_mps", "yaw_rate_rad_s"},
            ["Rear axle to CG distance unavailable."],
        )
    if abs(vx_mps) < 0.01:
        return 0.0, confidence_from_missing(
            [], set(),
            ["Vehicle speed near zero; slip angle set to 0."],
        )
    alpha = -math.atan2(vy_mps - rear_axle_to_cg_m * yaw_rate_rad_s, vx_mps)
    return alpha, confidence_from_missing(
        [], set(), [],
    )


def slip_angle_balance_rad(
    front_alpha_rad: float | None,
    rear_alpha_rad: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Slip angle balance = front - rear.

    Positive = more front slip = understeer tendency.
    Negative = more rear slip = oversteer tendency.
    """
    if front_alpha_rad is None or rear_alpha_rad is None:
        return None, confidence_from_missing(
            ["front_alpha_rad", "rear_alpha_rad"], set(),
            ["Slip angle values unavailable."],
        )
    return front_alpha_rad - rear_alpha_rad, confidence_from_missing(
        [], set(), [],
    )


def understeer_gradient_proxy_deg_per_g(
    front_alpha_deg: float | None,
    rear_alpha_deg: float | None,
    lateral_accel_g: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """Understeer gradient K_us = (alpha_front_deg - alpha_rear_deg) / ay_g.

    Positive = understeer. Near zero = neutral. Negative = oversteer.
    """
    if front_alpha_deg is None or rear_alpha_deg is None:
        return None, confidence_from_missing(
            ["front_alpha_deg", "rear_alpha_deg"], set(),
            ["Slip angle values unavailable."],
        )
    if lateral_accel_g is None or abs(lateral_accel_g) < 0.01:
        return None, confidence_from_missing(
            ["lateral_accel_g"], {"front_alpha_deg", "rear_alpha_deg"},
            ["Lateral acceleration too small for meaningful gradient."],
        )
    k_us = (front_alpha_deg - rear_alpha_deg) / lateral_accel_g
    return k_us, confidence_from_missing(
        [], set(),
        ["Understeer gradient proxy. ESTIMATE."],
    )


# ── Tire utilization proxy ────────────────────────────────────

def tire_utilization_total_proxy(
    mass_kg: float | None,
    long_accel_mps2: float | None,
    lat_accel_mps2: float | None,
    normal_load_n: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """mu_used = sqrt(Fx^2 + Fy^2) / Fz

    where Fx = m * ax, Fy = m * ay.
    """
    if mass_kg is None:
        return None, confidence_from_missing(
            ["mass_kg"], set(),
            ["Mass unavailable."],
        )
    if long_accel_mps2 is None or lat_accel_mps2 is None:
        return None, confidence_from_missing(
            ["long_accel_mps2", "lat_accel_mps2"], {"mass_kg"},
            ["Acceleration components unavailable."],
        )
    if normal_load_n is None or normal_load_n <= 0:
        return None, confidence_from_missing(
            ["normal_load_n"], {"mass_kg", "long_accel_mps2", "lat_accel_mps2"},
            ["Normal load unavailable or invalid."],
        )
    fx = mass_kg * long_accel_mps2
    fy = mass_kg * lat_accel_mps2
    mu = math.hypot(fx, fy) / normal_load_n
    return mu, confidence_from_missing(
        [], set(),
        ["Tire utilization proxy. ESTIMATE — not a direct friction measurement."],
    )


# ── Tire thermal origin ───────────────────────────────────────

def surface_temp_avg(
    inner: float | None,
    middle: float | None,
    outer: float | None,
) -> float | None:
    """Average surface temperature across the tread."""
    temps = [t for t in [inner, middle, outer] if t is not None]
    return sum(temps) / len(temps) if temps else None


def carcass_temp_avg(
    inner: float | None,
    middle: float | None,
    outer: float | None,
) -> float | None:
    """Average carcass (internal) temperature."""
    temps = [t for t in [inner, middle, outer] if t is not None]
    return sum(temps) / len(temps) if temps else None


def scrub_heat_index(
    surface_avg: float | None,
    carcass_avg: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """scrub_heat_index = surface_avg - carcass_avg

    Large positive = surface much hotter than carcass = sliding/scrubbing.
    """
    if surface_avg is None or carcass_avg is None:
        return None, confidence_from_missing(
            ["surface_avg", "carcass_avg"], set(),
            ["Temperature data unavailable."],
        )
    return surface_avg - carcass_avg, confidence_from_missing(
        [], set(), [],
    )


def thermal_origin_label(
    surface_avg: float | None,
    carcass_avg: float | None,
    baseline_carcass: float | None = None,
) -> tuple[str, EstimateConfidence]:
    """Classify the likely thermal origin of tire temperature.

    Rules:
    - surface hot, carcass normal → "sliding_scrub"
    - carcass hot, surface moderate → "load_deflection"
    - middle hotter than edges → "pressure_high"
    - edges hotter than middle → "pressure_low_or_slip"
    - missing carcass → "unavailable"
    """
    if surface_avg is None:
        return "unavailable", confidence_from_missing(
            ["surface_avg"], set(),
            ["Surface temperature unavailable."],
        )
    if carcass_avg is None:
        return "unavailable", confidence_from_missing(
            ["carcass_avg"], set(),
            ["Carcass temperature unavailable; cannot determine thermal origin."],
        )
    delta = surface_avg - carcass_avg
    if delta > 10.0:
        return "sliding_scrub", confidence_from_missing(
        [], set(),
        ["Surface much hotter than carcass — sliding/scrubbing."],
    )
    if carcass_avg > 100.0 and delta < 5.0:
        return "load_deflection", confidence_from_missing(
            [], set(),
            ["Carcass hot, surface moderate — load deflection."],
        )
    return "normal", confidence_from_missing(
        [], set(),
    )


# ── Wheel speed bias ──────────────────────────────────────────

def wheel_speed_bias_mps(
    wheel_speed_mps: float | None,
    vehicle_speed_mps: float | None,
) -> tuple[float | None, EstimateConfidence]:
    """wheel_speed_bias = wheel_speed - vehicle_speed

    Positive = wheel spinning faster than vehicle (acceleration slip).
    Negative = wheel slower than vehicle (braking slip).
    """
    if wheel_speed_mps is None or vehicle_speed_mps is None:
        return None, confidence_from_missing(
            ["wheel_speed_mps", "vehicle_speed_mps"], set(),
            ["Speed values unavailable."],
        )
    return wheel_speed_mps - vehicle_speed_mps, confidence_from_missing(
        [], set(), [],
    )
