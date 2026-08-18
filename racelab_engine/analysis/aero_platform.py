from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

from racelab_engine.analysis.constants import FORCE_PROXY_WARNING


@dataclass(frozen=True)
class ProxyEstimate:
    name: str
    value: float | None
    unit: str
    confidence: str
    assumptions: list[str] = field(default_factory=list)
    missing_constants: list[str] = field(default_factory=list)
    warning_text: str = FORCE_PROXY_WARNING

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "assumptions": self.assumptions,
            "missing_constants": self.missing_constants,
            "warning_text": self.warning_text,
        }


def dynamic_pressure_pa(speed_mps: float | None, air_density_kg_m3: float | None) -> float | None:
    """Ground-speed pressure proxy; not wind-relative aerodynamic pressure."""
    speed_mps = _finite(speed_mps)
    air_density_kg_m3 = _finite(air_density_kg_m3)
    if (
        speed_mps is None
        or speed_mps < 0.0
        or air_density_kg_m3 is None
        or air_density_kg_m3 <= 0.0
    ):
        return None
    return 0.5 * float(air_density_kg_m3) * float(speed_mps) * float(speed_mps)


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _get_float(source: Any, key: str) -> float | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        value = source.get(key)
    else:
        value = getattr(source, key, None)
    return _finite(value)


def spring_load_delta_proxy_n(
    current_height_mm: float | None,
    baseline_height_mm: float | None,
    spring_rate_n_per_mm: float | None,
    motion_ratio: float | None = None,
) -> float | None:
    current_height_mm = _finite(current_height_mm)
    baseline_height_mm = _finite(baseline_height_mm)
    spring_rate_n_per_mm = _finite(spring_rate_n_per_mm)
    motion_ratio = _finite(motion_ratio)
    if (
        current_height_mm is None
        or baseline_height_mm is None
        or spring_rate_n_per_mm is None
        or spring_rate_n_per_mm <= 0.0
        or motion_ratio is None
        or motion_ratio <= 0.0
    ):
        return None
    compression_mm = (baseline_height_mm - current_height_mm) * motion_ratio
    return compression_mm * spring_rate_n_per_mm


def build_platform_proxy_estimates(row: Mapping[str, Any], setup: Any | None = None) -> dict[str, ProxyEstimate]:
    missing_constants = [
        key
        for key in ["wheelbase_m", "front_track_width_m", "rear_track_width_m", "cg_height_m"]
        if _get_float(setup, key) is None
    ]
    corner_motion_ratios = {
        key: _get_float(setup, key)
        for key in (
            "lf_motion_ratio",
            "rf_motion_ratio",
            "lr_motion_ratio",
            "rr_motion_ratio",
        )
    }
    has_motion_ratios = all(
        value is not None and value > 0.0
        for value in corner_motion_ratios.values()
    )
    if not has_motion_ratios:
        missing_constants.append("corner_motion_ratios")

    # Detect high transients (lat/long accel in m/s² → divide by 9.81 for g)
    lat_accel = _get_float(row, "lat_accel")
    long_accel = _get_float(row, "long_accel")
    lat_g = abs(lat_accel) / 9.81 if lat_accel is not None else None
    long_g = abs(long_accel) / 9.81 if long_accel is not None else None
    transient_label: str | None = None
    if (lat_g is not None and lat_g > 0.50) or (
        long_g is not None and long_g > 0.50
    ):
        transient_label = "very_low (high-G transient >0.50g)"
    elif (lat_g is not None and lat_g > 0.35) or (
        long_g is not None and long_g > 0.35
    ):
        transient_label = "low (elevated-G transient >0.35g)"

    # Shock/noise: check shock velocity RMS
    shock_keys = ["lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"]
    shock_vals = [
        abs(value)
        for key in shock_keys
        if (value := _get_float(row, key)) is not None
    ]
    shock_activity = max(shock_vals) if shock_vals else math.nan
    shock_noisy = shock_activity > 2.5  # in/s threshold — high platform disturbance

    assumptions = [
        "Ride-height deltas are treated as relative compression proxies.",
        "Mechanical weight transfer is not subtracted from these raw platform load proxies. "
        "Use aero_residual_load_proxy_n (vehicle_dynamics) when mass, geometry, and "
        "mechanical transfer are available for a corrected aero residual estimate.",
        "The ground-speed pressure proxy uses air density and speed; wind-relative air speed is unavailable.",
    ]
    if not has_motion_ratios:
        assumptions.append(
            "One or more corner motion ratios are unavailable; affected force-like spring/platform/aero proxies are withheld."
        )

    if lat_g is None or long_g is None:
        assumptions.append(
            "Acceleration context is incomplete; missing channels remain unavailable and are not treated as zero."
        )
    if not shock_vals:
        assumptions.append(
            "Damper-velocity context is unavailable; missing activity is not treated as a settled platform."
        )

    # Determine confidence
    warnings: list[str] = []
    confidence = "medium (steady-state comparison only)"
    if transient_label:
        confidence = transient_label
        warnings.append(
            "High-G transient detected; ride-height compression may include "
            "mechanical weight transfer, damping, and bump effects."
        )
    elif missing_constants or lat_g is None or long_g is None or not shock_vals:
        confidence = "low"
    if shock_noisy:
        if not transient_label:
            confidence = "low (shock-active)"
        warnings.append(
            "High shock activity detected; platform is noisy and steady-state "
            "platform proxy confidence is reduced."
        )

    corner_specs = {
        "lf": ("lf_ride_height_mm", "lf_ride_height_mm", "lf_front_spring_n_per_mm", "lf_motion_ratio"),
        "rf": ("rf_ride_height_mm", "rf_ride_height_mm", "rf_front_spring_n_per_mm", "rf_motion_ratio"),
        "lr": ("lr_ride_height_mm", "lr_ride_height_mm", "lr_rear_spring_n_per_mm", "lr_motion_ratio"),
        "rr": ("rr_ride_height_mm", "rr_ride_height_mm", "rr_rear_spring_n_per_mm", "rr_motion_ratio"),
    }
    corner_loads = {
        corner: spring_load_delta_proxy_n(
            _get_float(row, row_key),
            _get_float(setup, setup_height_key),
            _get_float(setup, spring_key),
            _get_float(setup, motion_ratio_key),
        )
        for corner, (
            row_key,
            setup_height_key,
            spring_key,
            motion_ratio_key,
        ) in corner_specs.items()
    }

    front = None
    if corner_loads["lf"] is not None and corner_loads["rf"] is not None:
        front = corner_loads["lf"] + corner_loads["rf"]
    rear = None
    if corner_loads["lr"] is not None and corner_loads["rr"] is not None:
        rear = corner_loads["lr"] + corner_loads["rr"]
    balance = None
    if front is not None and rear is not None and abs(front + rear) > 1e-9:
        balance = front / (front + rear) * 100.0

    # Rear scrape risk from ride heights
    lr_mm = _get_float(row, "lr_ride_height_mm")
    rr_mm = _get_float(row, "rr_ride_height_mm")
    rear_min_mm: float | None = None
    rear_risk: float | None = None
    if lr_mm is not None and rr_mm is not None:
        rear_min_mm = min(lr_mm, rr_mm)
        from racelab_engine.analysis.constants import REAR_SCRAPE_MM, REAR_CRITICAL_MM, REAR_HIGH_MM, REAR_WATCH_MM
        rear_risk = next((score for threshold, score in (
            (REAR_SCRAPE_MM, 1.0), (REAR_CRITICAL_MM, 0.92),
            (REAR_HIGH_MM, 0.72), (REAR_WATCH_MM, 0.38),
        ) if rear_min_mm <= threshold), 0.08)
        eps = 0.001
        if abs(lr_mm - rr_mm) < eps:
            rear_side_code = 0.0
        elif lr_mm < rr_mm:
            rear_side_code = -1.0
        else:
            rear_side_code = 1.0
    else:
        rear_side_code = None

    return {
        "front_load_proxy_n": ProxyEstimate("front_load_proxy_n", front, "N", confidence, assumptions, missing_constants),
        "rear_load_proxy_n": ProxyEstimate("rear_load_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "front_aero_proxy_n": ProxyEstimate("front_aero_proxy_n", front, "N", confidence, assumptions, missing_constants),
        "rear_aero_proxy_n": ProxyEstimate("rear_aero_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "aero_balance_front_pct": ProxyEstimate("aero_balance_front_pct", balance, "%", confidence, assumptions, missing_constants),
        "rear_downforce_proxy_n": ProxyEstimate("rear_downforce_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "rear_platform_proxy_n": ProxyEstimate("rear_platform_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "rear_diffuser_proxy_n": ProxyEstimate("rear_diffuser_proxy_n", rear, "N", "low", assumptions, missing_constants),
        "rear_min_ride_height_mm": ProxyEstimate("rear_min_ride_height_mm", rear_min_mm, "mm", confidence, assumptions, missing_constants),
        "rear_scrape_risk_score": ProxyEstimate("rear_scrape_risk_score", rear_risk, "score", confidence, assumptions, missing_constants),
        "rear_platform_contact_risk": ProxyEstimate("rear_platform_contact_risk", rear_risk, "score", confidence, assumptions, missing_constants),
        "rear_scrape_side": ProxyEstimate("rear_scrape_side", rear_side_code, "code", "medium", assumptions, missing_constants),
    }
