"""Fast unit tests for the physics estimate modules.

No large fixtures, no .ibt imports, no .mt2 imports.
"""

from __future__ import annotations

import math

from racelab_engine.analysis.estimate_confidence import confidence_from_missing
from racelab_engine.analysis.physics_inputs import VehiclePhysicsInputs
from racelab_engine.analysis.aero_coefficients import (
    air_speed_mps,
    dynamic_pressure_pa,
    aero_load_index,
    rolling_resistance_force_n,
    cda_coastdown_proxy_m2,
    full_throttle_resistance_cda_proxy_m2,
    _coastdown_is_valid,
)
from racelab_engine.analysis.vehicle_dynamics import (
    longitudinal_weight_transfer_n,
    lateral_weight_transfer_n,
    axle_transfer_distribution,
    aero_residual_load_proxy_n,
    curvature_from_heading_distance,
    yaw_rate_expected_rad_s,
    lat_accel_expected_mps2,
    yaw_error_rad_s,
    understeer_yaw_error_proxy,
    brake_energy_j,
    brake_power_w,
    accel_power_w,
    drag_power_w,
    wheel_power_proxy_w,
)
from racelab_engine.analysis.tire_dynamics import (
    vehicle_sideslip_beta_rad,
    front_slip_angle_rad,
    rear_slip_angle_rad,
    slip_angle_balance_rad,
    understeer_gradient_proxy_deg_per_g,
    tire_utilization_total_proxy,
    surface_temp_avg,
    carcass_temp_avg,
    scrub_heat_index,
    thermal_origin_label,
    wheel_speed_bias_mps,
)


# ── Confidence ────────────────────────────────────────────────

def test_confidence_all_present() -> None:
    conf = confidence_from_missing(["mass_kg", "wheelbase_m"], {"mass_kg", "wheelbase_m"})
    assert conf.tier == "high"
    assert conf.score == 0.90


def test_confidence_some_missing() -> None:
    conf = confidence_from_missing(["mass_kg", "wheelbase_m"], {"mass_kg"})
    assert conf.tier == "low"
    assert conf.score == 0.40
    assert "wheelbase_m" in conf.missing_inputs


def test_confidence_all_missing() -> None:
    conf = confidence_from_missing(["mass_kg", "wheelbase_m"], set())
    assert conf.tier == "low"
    assert conf.score == 0.40


# ── Physics inputs ────────────────────────────────────────────

def test_physics_inputs_provided() -> None:
    inputs = VehiclePhysicsInputs(mass_kg=1500.0, wheelbase_m=3.0)
    assert "mass_kg" in inputs.provided()
    assert "wheelbase_m" in inputs.provided()
    assert "cg_height_m" not in inputs.provided()


def test_physics_inputs_defaults() -> None:
    inputs = VehiclePhysicsInputs()
    assert inputs.resolve_cg_height_m() == 0.30
    assert inputs.resolve_crr() == 0.015
    assert inputs.resolve_motion_ratio_front() == 1.0
    assert inputs.resolve_motion_ratio_rear() == 1.0


# ── Aero coefficients ─────────────────────────────────────────

def test_air_speed_no_wind() -> None:
    speed, conf = air_speed_mps(50.0)
    assert speed == 50.0
    assert conf.tier == "low"


def test_air_speed_headwind() -> None:
    speed, conf = air_speed_mps(50.0, wind_speed_mps=5.0, vehicle_heading_rad=0.0, wind_heading_rad=math.pi)
    assert speed is not None
    assert speed > 50.0  # headwind increases air speed
    assert conf.tier == "high"


def test_air_speed_tailwind() -> None:
    speed, conf = air_speed_mps(50.0, wind_speed_mps=5.0, vehicle_heading_rad=0.0, wind_heading_rad=0.0)
    assert speed is not None
    assert speed < 50.0  # tailwind decreases air speed
    assert conf.tier == "high"


def test_air_speed_crosswind() -> None:
    """Crosswind should produce air speed different from ground speed."""
    speed, conf = air_speed_mps(50.0, wind_speed_mps=5.0, vehicle_heading_rad=0.0, wind_heading_rad=math.pi / 2)
    assert speed is not None
    # Crosswind at 90°: v_air = sqrt(50^2 + 5^2) = 50.25
    assert abs(speed - 50.25) < 0.01
    assert conf.tier == "high"


def test_dynamic_pressure_known() -> None:
    q, conf = dynamic_pressure_pa(1.225, 50.0)
    assert q is not None
    expected = 0.5 * 1.225 * 2500
    assert abs(q - expected) < 0.01
    assert conf.tier == "high"


def test_dynamic_pressure_missing_density() -> None:
    q, conf = dynamic_pressure_pa(None, 50.0)
    assert q is not None
    assert conf.tier == "low"


def test_aero_load_index_known() -> None:
    from racelab_engine.analysis.constants import REFERENCE_DYNAMIC_PRESSURE_PA
    q = 0.5 * 1.225 * 80.4672 * 80.4672  # ~180 mph reference
    index, conf = aero_load_index(q)
    assert index is not None
    assert abs(index - 1.0) < 0.01


def test_rolling_resistance_known() -> None:
    frr, conf = rolling_resistance_force_n(1500.0, 0.015)
    assert frr is not None
    assert abs(frr - 1500 * 9.81 * 0.015) < 0.1
    assert conf.tier == "high"


def test_rolling_resistance_missing_crr() -> None:
    frr, conf = rolling_resistance_force_n(1500.0, None)
    assert frr is not None  # defaults to 0.015
    assert conf.tier == "low"


# ── CdA coastdown validity ───────────────────────────────────

def test_coastdown_valid_true() -> None:
    assert _coastdown_is_valid(throttle_pct=0.0, brake_pct=0.0, speed_mps=50.0, long_accel_mps2=-0.5)


def test_coastdown_valid_rejects_throttle() -> None:
    assert not _coastdown_is_valid(throttle_pct=5.0, brake_pct=0.0, speed_mps=50.0, long_accel_mps2=-0.5)


def test_coastdown_valid_rejects_brake() -> None:
    assert not _coastdown_is_valid(throttle_pct=0.0, brake_pct=5.0, speed_mps=50.0, long_accel_mps2=-0.5)


def test_coastdown_valid_rejects_accelerating() -> None:
    assert not _coastdown_is_valid(throttle_pct=0.0, brake_pct=0.0, speed_mps=50.0, long_accel_mps2=0.5)


def test_coastdown_valid_rejects_low_speed() -> None:
    assert not _coastdown_is_valid(throttle_pct=0.0, brake_pct=0.0, speed_mps=1.0, long_accel_mps2=-0.5)


def test_coastdown_valid_rejects_full_throttle_resistance() -> None:
    assert not _coastdown_is_valid(throttle_pct=0.0, brake_pct=0.0, speed_mps=50.0, long_accel_mps2=-0.5, full_throttle_resistance_index=0.5)


# ── Motion ratio fallback ─────────────────────────────────────

def test_motion_ratio_corner_front() -> None:
    from racelab_engine.analysis.physics_inputs import VehiclePhysicsInputs
    inputs = VehiclePhysicsInputs(motion_ratio_front=0.8, motion_ratio_rear=0.6)
    assert inputs.resolve_motion_ratio_corner("lf") == 0.8
    assert inputs.resolve_motion_ratio_corner("rf") == 0.8
    assert inputs.resolve_motion_ratio_corner("lr") == 0.6
    assert inputs.resolve_motion_ratio_corner("rr") == 0.6


def test_motion_ratio_corner_default() -> None:
    from racelab_engine.analysis.physics_inputs import VehiclePhysicsInputs
    inputs = VehiclePhysicsInputs()
    assert inputs.resolve_motion_ratio_corner("lf") == 1.0
    assert inputs.resolve_motion_ratio_corner("unknown") == 1.0


def test_cda_coastdown_known() -> None:
    # m=1500, ax=-0.5 m/s² (coasting), q=1000 Pa, crr=0.015
    # F_drag = 1500*0.5 - 1500*9.81*0.015 = 750 - 220.7 = 529.3
    # CdA = 529.3 / 1000 = 0.529
    cda, conf = cda_coastdown_proxy_m2(1500.0, -0.5, 1000.0, crr=0.015)
    assert cda is not None
    assert abs(cda - 0.529) < 0.01
    assert conf.tier == "high"


def test_cda_coastdown_missing_mass() -> None:
    cda, conf = cda_coastdown_proxy_m2(None, -0.5, 1000.0)
    assert cda is None
    assert conf.score < 0.5


# ── Weight transfer ───────────────────────────────────────────

def test_longitudinal_weight_transfer_known() -> None:
    # m=1500, ax=3.0, cg=0.30, wb=3.0
    # transfer = 1500 * 3.0 * 0.30 / 3.0 = 450
    wt, conf = longitudinal_weight_transfer_n(1500.0, 3.0, 0.30, 3.0)
    assert wt is not None
    assert abs(wt - 450.0) < 0.1
    assert conf.tier == "high"


def test_longitudinal_weight_transfer_default_cg() -> None:
    wt, conf = longitudinal_weight_transfer_n(1500.0, 3.0, None, 3.0)
    assert wt is not None
    assert conf.tier == "low"


def test_lateral_weight_transfer_known() -> None:
    # m=1500, ay=4.0, cg=0.30, track=2.0
    # transfer = 1500 * 4.0 * 0.30 / 2.0 = 900
    wt, conf = lateral_weight_transfer_n(1500.0, 4.0, 0.30, 2.0)
    assert wt is not None
    assert abs(wt - 900.0) < 0.1


def test_axle_transfer_distribution_known() -> None:
    f, r, conf = axle_transfer_distribution(1.5, 1.5, 3.0)
    assert f is not None and r is not None
    assert abs(f - 0.5) < 0.01
    assert abs(r - 0.5) < 0.01


def test_aero_residual_proxy() -> None:
    residual, conf = aero_residual_load_proxy_n(1000.0, 300.0)
    assert residual is not None
    assert abs(residual - 700.0) < 0.1
    assert conf.tier == "high"


# ── Curvature / yaw ───────────────────────────────────────────

def test_curvature_from_heading() -> None:
    # heading changes by 0.1 rad over 100 m
    curv = curvature_from_heading_distance(0.0, 0.1, 0.0, 100.0)
    assert curv is not None
    assert abs(curv - 0.001) < 1e-9


def test_yaw_rate_expected() -> None:
    # speed=50, curvature=0.001 → yaw=0.05 rad/s
    yaw, conf = yaw_rate_expected_rad_s(50.0, 0.001)
    assert yaw is not None
    assert abs(yaw - 0.05) < 1e-9


def test_lat_accel_expected() -> None:
    # speed=50, curvature=0.001 → lat=2.5 m/s²
    accel, conf = lat_accel_expected_mps2(50.0, 0.001)
    assert accel is not None
    assert abs(accel - 2.5) < 0.01


def test_yaw_error_understeer() -> None:
    error, conf = yaw_error_rad_s(0.10, 0.06)
    assert error is not None
    assert abs(error - 0.04) < 1e-9


def test_understeer_proxy() -> None:
    proxy, conf = understeer_yaw_error_proxy(0.10, 0.06)
    assert abs(proxy - 0.04) < 1e-9


def test_understeer_proxy_oversteer_returns_zero() -> None:
    proxy, conf = understeer_yaw_error_proxy(0.06, 0.10)
    assert proxy == 0.0


# ── Slip angles ───────────────────────────────────────────────

def test_vehicle_sideslip() -> None:
    beta, conf = vehicle_sideslip_beta_rad(50.0, 1.0)
    assert beta is not None
    assert abs(beta - math.atan2(1.0, 50.0)) < 1e-9


def test_front_slip_angle() -> None:
    # Straight line, no steering → alpha ≈ 0
    alpha, conf = front_slip_angle_rad(0.0, 50.0, 0.0, 0.0, 1.5)
    assert alpha is not None
    assert abs(alpha) < 0.001


def test_rear_slip_angle() -> None:
    alpha, conf = rear_slip_angle_rad(50.0, 0.0, 0.0, 1.5)
    assert alpha is not None
    assert abs(alpha) < 0.001


def test_slip_angle_balance() -> None:
    bal, conf = slip_angle_balance_rad(0.05, 0.02)
    assert bal is not None
    assert abs(bal - 0.03) < 1e-9


def test_understeer_gradient() -> None:
    k, conf = understeer_gradient_proxy_deg_per_g(3.0, 1.0, 0.5)
    assert k is not None
    assert abs(k - 4.0) < 0.01


# ── Tire utilization ──────────────────────────────────────────

def test_tire_utilization() -> None:
    # m=1500, ax=3.0, ay=4.0, Fz=1500*9.81=14715
    # Fx=4500, Fy=6000, mu=sqrt(4500^2+6000^2)/14715 = 7500/14715 = 0.51
    mu, conf = tire_utilization_total_proxy(1500.0, 3.0, 4.0, 14715.0)
    assert mu is not None
    assert abs(mu - 0.51) < 0.01


def test_tire_utilization_missing_mass() -> None:
    mu, conf = tire_utilization_total_proxy(None, 3.0, 4.0, 14715.0)
    assert mu is None
    assert conf.score < 0.5


# ── Thermal origin ────────────────────────────────────────────

def test_surface_temp_avg() -> None:
    avg = surface_temp_avg(80.0, 85.0, 90.0)
    assert avg is not None
    assert abs(avg - 85.0) < 0.1


def test_carcass_temp_avg() -> None:
    avg = carcass_temp_avg(70.0, 75.0, 80.0)
    assert avg is not None
    assert abs(avg - 75.0) < 0.1


def test_scrub_heat_index() -> None:
    idx, conf = scrub_heat_index(90.0, 70.0)
    assert idx is not None
    assert abs(idx - 20.0) < 0.1


def test_thermal_origin_sliding_scrub() -> None:
    label, conf = thermal_origin_label(90.0, 70.0)
    assert label == "sliding_scrub"


def test_thermal_origin_load_deflection() -> None:
    label, conf = thermal_origin_label(102.0, 105.0)
    assert label == "load_deflection"


def test_thermal_origin_normal() -> None:
    label, conf = thermal_origin_label(80.0, 78.0)
    assert label == "normal"


def test_thermal_origin_missing_carcass() -> None:
    label, conf = thermal_origin_label(80.0, None)
    assert label == "unavailable"


# ── Wheel speed bias ──────────────────────────────────────────

def test_wheel_speed_bias() -> None:
    bias, conf = wheel_speed_bias_mps(50.5, 50.0)
    assert bias is not None
    assert abs(bias - 0.5) < 1e-9


# ── Brake energy and power ────────────────────────────────────

def test_brake_energy() -> None:
    # m=1500, v_entry=50, v_exit=30
    # E = 0.5 * 1500 * (2500 - 900) = 0.5 * 1500 * 1600 = 1,200,000 J
    e, conf = brake_energy_j(1500.0, 50.0, 30.0)
    assert e is not None
    assert abs(e - 1200000.0) < 1.0


def test_brake_energy_accelerating_returns_zero() -> None:
    """If exit speed > entry speed, brake energy should be 0 (not braking)."""
    e, conf = brake_energy_j(1500.0, 30.0, 50.0)
    assert e is not None
    assert e == 0.0


def test_brake_power() -> None:
    p, conf = brake_power_w(1200000.0, 3.0)
    assert p is not None
    assert abs(p - 400000.0) < 1.0


def test_accel_power() -> None:
    # P = 1500 * 3.0 * 50 = 225,000 W
    p, conf = accel_power_w(1500.0, 3.0, 50.0)
    assert p is not None
    assert abs(p - 225000.0) < 1.0


def test_drag_power() -> None:
    p, conf = drag_power_w(500.0, 50.0)
    assert p is not None
    assert abs(p - 25000.0) < 1.0


def test_wheel_power_proxy() -> None:
    total, conf = wheel_power_proxy_w(accel_power_w=225000.0, drag_power_w=25000.0)
    assert total is not None
    assert abs(total - 250000.0) < 1.0


def test_wheel_power_proxy_all_missing() -> None:
    total, conf = wheel_power_proxy_w()
    assert total is None
    assert conf.score < 0.5


# ── No crash with missing inputs ──────────────────────────────

def test_no_crash_missing_inputs() -> None:
    """All functions should return (None, EstimateConfidence) not crash."""
    assert longitudinal_weight_transfer_n(None, None, None, None)[0] is None
    assert lateral_weight_transfer_n(None, None, None, None)[0] is None
    assert yaw_rate_expected_rad_s(None, None)[0] is None
    assert lat_accel_expected_mps2(None, None)[0] is None
    assert yaw_error_rad_s(None, None)[0] is None
    assert vehicle_sideslip_beta_rad(None, None)[0] is None
    assert front_slip_angle_rad(None, None, None, None, None)[0] is None
    assert rear_slip_angle_rad(None, None, None, None)[0] is None
    assert slip_angle_balance_rad(None, None)[0] is None
    assert understeer_gradient_proxy_deg_per_g(None, None, None)[0] is None
    assert tire_utilization_total_proxy(None, None, None, None)[0] is None
    assert scrub_heat_index(None, None)[0] is None
    assert wheel_speed_bias_mps(None, None)[0] is None
    assert brake_energy_j(None, None, None)[0] is None
    assert brake_power_w(None, None)[0] is None
    assert accel_power_w(None, None, None)[0] is None
    assert drag_power_w(None, None)[0] is None
    assert cda_coastdown_proxy_m2(None, None, None)[0] is None
    assert full_throttle_resistance_cda_proxy_m2(None, None, None)[0] is None
