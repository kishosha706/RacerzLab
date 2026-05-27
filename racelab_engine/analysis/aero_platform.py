from __future__ import annotations

from dataclasses import dataclass, field
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
    if speed_mps is None or air_density_kg_m3 is None:
        return None
    return 0.5 * float(air_density_kg_m3) * float(speed_mps) * float(speed_mps)


def _get_float(source: Any, key: str) -> float | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        value = source.get(key)
    else:
        value = getattr(source, key, None)
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def spring_load_delta_proxy_n(
    current_height_mm: float | None,
    baseline_height_mm: float | None,
    spring_rate_n_per_mm: float | None,
) -> float | None:
    if current_height_mm is None or baseline_height_mm is None or spring_rate_n_per_mm is None:
        return None
    compression_mm = baseline_height_mm - current_height_mm
    return compression_mm * spring_rate_n_per_mm


def build_platform_proxy_estimates(row: Mapping[str, Any], setup: Any | None = None) -> dict[str, ProxyEstimate]:
    missing_constants = [
        key
        for key in ["wheelbase_m", "front_track_width_m", "rear_track_width_m", "cg_height_m", "motion_ratios"]
        if _get_float(setup, key) is None
    ]
    has_motion_ratios = all(
        _get_float(setup, key) is not None
        for key in ["lf_motion_ratio", "rf_motion_ratio", "lr_motion_ratio", "rr_motion_ratio"]
    ) if setup is not None else False
    if not has_motion_ratios:
        missing_constants.append("corner_motion_ratios")

    # Detect high transients (lat/long accel in m/s² → divide by 9.81 for g)
    lat_g = abs(_get_float(row, "lat_accel") or 0.0) / 9.81
    long_g = abs(_get_float(row, "long_accel") or 0.0) / 9.81
    transient_label: str | None = None
    if lat_g > 0.50 or long_g > 0.50:
        transient_label = "very_low (high-G transient >0.50g)"
    elif lat_g > 0.35 or long_g > 0.35:
        transient_label = "low (elevated-G transient >0.35g)"

    # Shock/noise: check shock velocity RMS
    shock_keys = ["lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"]
    shock_vals = [abs(_get_float(row, k) or 0.0) for k in shock_keys]
    shock_activity = max(shock_vals, default=0.0)
    shock_noisy = shock_activity > 2.5  # in/s threshold — high platform disturbance

    assumptions = [
        "Ride-height deltas are treated as relative compression proxies.",
        "A 1:1 Motion Ratio is assumed per corner unless setup provides motion ratios.",
        "Mechanical weight transfer is not subtracted from these raw platform load proxies. "
        "Use aero_residual_load_proxy_n (vehicle_dynamics) when mass, geometry, and "
        "mechanical transfer are available for a corrected aero residual estimate.",
        "Dynamic pressure is calculated from air density and speed when both are available.",
    ]
    if not has_motion_ratios:
        assumptions.append("Default 1:1 motion ratio assumed — may over/under-estimate load.")

    # Determine confidence
    warnings: list[str] = []
    confidence = "medium (steady-state comparison only)"
    if transient_label:
        confidence = transient_label
        warnings.append(
            "High-G transient detected; ride-height compression may include "
            "mechanical weight transfer, damping, and bump effects."
        )
    elif missing_constants:
        confidence = "low"
    if shock_noisy:
        if not transient_label:
            confidence = "low (shock-active)"
        warnings.append(
            "High shock activity detected; platform is noisy and steady-state "
            "aero/load proxy confidence is reduced."
        )

    corner_specs = {
        "lf": ("lf_ride_height_mm", "lf_ride_height_mm", "lf_front_spring_n_per_mm"),
        "rf": ("rf_ride_height_mm", "rf_ride_height_mm", "rf_front_spring_n_per_mm"),
        "lr": ("lr_ride_height_mm", "lr_ride_height_mm", "lr_rear_spring_n_per_mm"),
        "rr": ("rr_ride_height_mm", "rr_ride_height_mm", "rr_rear_spring_n_per_mm"),
    }
    corner_loads = {
        corner: spring_load_delta_proxy_n(
            _get_float(row, row_key),
            _get_float(setup, setup_height_key),
            _get_float(setup, spring_key),
        )
        for corner, (row_key, setup_height_key, spring_key) in corner_specs.items()
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

    return {
        "front_load_proxy_n": ProxyEstimate("front_load_proxy_n", front, "N", confidence, assumptions, missing_constants),
        "rear_load_proxy_n": ProxyEstimate("rear_load_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "front_aero_proxy_n": ProxyEstimate("front_aero_proxy_n", front, "N", confidence, assumptions, missing_constants),
        "rear_aero_proxy_n": ProxyEstimate("rear_aero_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "aero_balance_front_pct": ProxyEstimate("aero_balance_front_pct", balance, "%", confidence, assumptions, missing_constants),
        "rear_downforce_proxy_n": ProxyEstimate("rear_downforce_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "rear_platform_proxy_n": ProxyEstimate("rear_platform_proxy_n", rear, "N", confidence, assumptions, missing_constants),
        "rear_diffuser_proxy_n": ProxyEstimate("rear_diffuser_proxy_n", rear, "N", "low", assumptions, missing_constants),
    }
