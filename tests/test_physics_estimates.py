"""Fast unit tests for the physics estimate modules.

No large fixtures, no .ibt imports, no .mt2 imports.
"""

from __future__ import annotations

import math

import pytest

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
    dynamic_grade_rad,
    dynamic_grade_deg,
    grade_force_proxy_n,
    grade_corrected_long_accel_mps2,
    MAX_GRADE_COMPONENT,
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


def test_longitudinal_weight_transfer_requires_cg_height() -> None:
    wt, conf = longitudinal_weight_transfer_n(1500.0, 3.0, None, 3.0)
    assert wt is None
    assert "cg_height_m" in conf.missing_inputs
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


def test_understeer_proxy_missing_input_stays_unavailable() -> None:
    proxy, conf = understeer_yaw_error_proxy(None, 0.10)
    assert proxy is None
    assert "expected_yaw_rate_rad_s" in conf.missing_inputs


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


# ── Dynamic grade isolation ───────────────────────────────────

def test_dynamic_grade_flat() -> None:
    """Flat track: long_accel ≈ speed_rate → grade ≈ 0."""
    grade, conf = dynamic_grade_rad(2.0, 2.0)
    assert grade is not None
    assert abs(grade) < 0.001
    assert conf.tier == "high"


def test_dynamic_grade_uphill() -> None:
    """Uphill: sensor reads more acceleration than speed change."""
    grade, conf = dynamic_grade_rad(5.0, 2.0)
    assert grade is not None
    assert grade > 0  # uphill
    assert conf.tier == "high"


def test_dynamic_grade_downhill() -> None:
    """Downhill: sensor reads less acceleration than speed change."""
    grade, conf = dynamic_grade_rad(-1.0, 2.0)
    assert grade is not None
    assert grade < 0  # downhill
    assert conf.tier == "high"


def test_dynamic_grade_clamp_prevents_asin_crash() -> None:
    """Extreme values should be clamped, not crash asin."""
    grade, conf = dynamic_grade_rad(100.0, 0.0)  # far beyond realistic
    assert grade is not None
    assert abs(grade) <= math.asin(MAX_GRADE_COMPONENT) + 0.001


def test_dynamic_grade_missing_inputs() -> None:
    for args in [(None, 2.0), (2.0, None)]:
        grade, conf = dynamic_grade_rad(*args)
        assert grade is None
        assert conf.score < 0.5


def test_dynamic_grade_deg_conversion() -> None:
    """Degrees version should be consistent with radians."""
    grade_rad, _ = dynamic_grade_rad(5.0, 2.0)
    grade_deg, _ = dynamic_grade_deg(5.0, 2.0)
    assert grade_rad is not None and grade_deg is not None
    assert abs(grade_deg - math.degrees(grade_rad)) < 0.001


def test_grade_force_uphill() -> None:
    """Uphill grade produces positive grade force (resisting motion)."""
    grade_rad = math.radians(5.0)  # ~5° uphill
    force, conf = grade_force_proxy_n(1500.0, grade_rad)
    assert force is not None
    expected = 1500.0 * 9.81 * math.sin(grade_rad)
    assert abs(force - expected) < 0.1
    assert force > 0  # uphill resists motion


def test_grade_force_downhill() -> None:
    """Downhill grade produces negative grade force (aiding motion)."""
    grade_rad = math.radians(-3.0)  # ~3° downhill
    force, conf = grade_force_proxy_n(1500.0, grade_rad)
    assert force is not None
    assert force < 0  # downhill aids motion


def test_grade_force_missing_inputs() -> None:
    force, conf = grade_force_proxy_n(None, 0.1)
    assert force is None
    force2, conf2 = grade_force_proxy_n(1500.0, None)
    assert force2 is None


def test_grade_corrected_long_accel() -> None:
    """Grade correction removes gravity component from sensor acceleration."""
    # Uphill: sensor reads 5.0, but true accel is lower
    grade_rad = math.radians(5.0)
    corrected, conf = grade_corrected_long_accel_mps2(5.0, grade_rad)
    assert corrected is not None
    expected = 5.0 - 9.81 * math.sin(grade_rad)
    assert abs(corrected - expected) < 0.01
    assert corrected < 5.0  # uphill reduces true acceleration


def test_grade_corrected_long_accel_missing() -> None:
    corrected, conf = grade_corrected_long_accel_mps2(None, 0.1)
    assert corrected is None
    corrected2, conf2 = grade_corrected_long_accel_mps2(5.0, None)
    assert corrected2 is None


# ── Grade context label ───────────────────────────────────────

def test_grade_context_label_uphill() -> None:
    """Positive grade should produce 'uphill'."""
    from racelab_engine.analysis.calculated_channels import _grade_context_label
    assert _grade_context_label(3.0) == "uphill"


def test_grade_context_label_downhill() -> None:
    """Negative grade should produce 'downhill'."""
    from racelab_engine.analysis.calculated_channels import _grade_context_label
    assert _grade_context_label(-2.0) == "downhill"


def test_grade_context_label_flat() -> None:
    """Near-zero grade should produce 'flat'."""
    from racelab_engine.analysis.calculated_channels import _grade_context_label
    assert _grade_context_label(0.1) == "flat"
    assert _grade_context_label(-0.1) == "flat"
    assert _grade_context_label(0.0) == "flat"


# ── Grade channel integration via normalize_telemetry_rows ────

def test_grade_channels_produced_on_synthetic_rows(monkeypatch) -> None:
    """normalize_telemetry_rows should produce all grade channels."""
    monkeypatch.setenv("RACELAB_ANALYSIS_ENGINE", "row")
    from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
    rows = [
        {"SessionTime": 0.0, "LapDist": 0.0, "LapDistPct": 0.0, "Speed": 0.0,
         "Throttle": 0.0, "Brake": 0.0, "SteeringWheelAngle": 0.0,
         "LatAccel": 0.0, "LongAccel": 0.0, "RPM": 0.0, "Gear": 0,
         "CFSRrideHeight": 0.05, "LFrideHeight": 0.05, "RFrideHeight": 0.05,
         "LRrideHeight": 0.05, "RRrideHeight": 0.05,
         "LFSHshockDefl": 0.0, "RFSHshockDefl": 0.0,
         "LRSHshockDefl": 0.0, "RRSHshockDefl": 0.0,
         "LFSHshockVel": 0.0, "RFSHshockVel": 0.0,
         "LRSHshockVel": 0.0, "RRSHshockVel": 0.0,
         "AirDensity": 1.225, "mass_kg": 1500.0},
        {"SessionTime": 0.1, "LapDist": 10.0, "LapDistPct": 0.02, "Speed": 20.0,
         "Throttle": 0.5, "Brake": 0.0, "SteeringWheelAngle": 0.0,
         "LatAccel": 0.0, "LongAccel": 2.0, "RPM": 3000.0, "Gear": 3,
         "CFSRrideHeight": 0.05, "LFrideHeight": 0.05, "RFrideHeight": 0.05,
         "LRrideHeight": 0.05, "RRrideHeight": 0.05,
         "LFSHshockDefl": 0.0, "RFSHshockDefl": 0.0,
         "LRSHshockDefl": 0.0, "RRSHshockDefl": 0.0,
         "LFSHshockVel": 0.0, "RFSHshockVel": 0.0,
         "LRSHshockVel": 0.0, "RRSHshockVel": 0.0,
         "AirDensity": 1.225, "mass_kg": 1500.0},
    ]
    result = normalize_telemetry_rows(rows)
    assert len(result) == 2
    row = result[1]
    # First row has None for derivatives
    assert result[0].get("dynamic_grade_deg") is None
    assert result[0].get("dynamic_grade_rad") is None
    assert result[0].get("grade_corrected_long_accel_mps2") is None
    assert result[0].get("grade_force_proxy_n") is None
    assert result[0].get("grade_context_label") is None
    assert result[0].get("grade_corrected_speed_loss_mph_s") is None
    # Second row should have grade channels
    assert row.get("dynamic_grade_deg") is not None
    assert row.get("dynamic_grade_rad") is not None
    assert row.get("grade_corrected_long_accel_mps2") is not None
    assert row.get("grade_force_proxy_n") is not None
    assert row.get("grade_context_label") is not None
    assert row.get("grade_corrected_speed_loss_mph_s") is not None


def test_grade_channels_missing_long_accel() -> None:
    """Missing long_accel should produce None for all grade channels."""
    from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
    rows = [
        {"SessionTime": 0.0, "LapDist": 0.0, "LapDistPct": 0.0, "Speed": 0.0,
         "Throttle": 0.0, "Brake": 0.0, "SteeringWheelAngle": 0.0,
         "LatAccel": 0.0, "RPM": 0.0, "Gear": 0,
         "CFSRrideHeight": 0.05, "LFrideHeight": 0.05, "RFrideHeight": 0.05,
         "LRrideHeight": 0.05, "RRrideHeight": 0.05,
         "LFSHshockDefl": 0.0, "RFSHshockDefl": 0.0,
         "LRSHshockDefl": 0.0, "RRSHshockDefl": 0.0,
         "LFSHshockVel": 0.0, "RFSHshockVel": 0.0,
         "LRSHshockVel": 0.0, "RRSHshockVel": 0.0,
         "AirDensity": 1.225, "mass_kg": 1500.0},
        {"SessionTime": 0.1, "LapDist": 10.0, "LapDistPct": 0.02, "Speed": 20.0,
         "Throttle": 0.5, "Brake": 0.0, "SteeringWheelAngle": 0.0,
         "LatAccel": 0.0, "RPM": 3000.0, "Gear": 3,
         "CFSRrideHeight": 0.05, "LFrideHeight": 0.05, "RFrideHeight": 0.05,
         "LRrideHeight": 0.05, "RRrideHeight": 0.05,
         "LFSHshockDefl": 0.0, "RFSHshockDefl": 0.0,
         "LRSHshockDefl": 0.0, "RRSHshockDefl": 0.0,
         "LFSHshockVel": 0.0, "RFSHshockVel": 0.0,
         "LRSHshockVel": 0.0, "RRSHshockVel": 0.0,
         "AirDensity": 1.225, "mass_kg": 1500.0},
    ]
    result = normalize_telemetry_rows(rows)
    row = result[1]
    assert row.get("dynamic_grade_deg") is None
    assert row.get("dynamic_grade_rad") is None
    assert row.get("grade_corrected_long_accel_mps2") is None
    assert row.get("grade_force_proxy_n") is None
    assert row.get("grade_context_label") is None
    assert row.get("grade_corrected_speed_loss_mph_s") is None


def test_grade_force_proxy_none_without_mass() -> None:
    """grade_force_proxy_n should be None when mass_kg is missing."""
    from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
    rows = [
        {"SessionTime": 0.0, "LapDist": 0.0, "LapDistPct": 0.0, "Speed": 0.0,
         "Throttle": 0.0, "Brake": 0.0, "SteeringWheelAngle": 0.0,
         "LatAccel": 0.0, "LongAccel": 0.0, "RPM": 0.0, "Gear": 0,
         "CFSRrideHeight": 0.05, "LFrideHeight": 0.05, "RFrideHeight": 0.05,
         "LRrideHeight": 0.05, "RRrideHeight": 0.05,
         "LFSHshockDefl": 0.0, "RFSHshockDefl": 0.0,
         "LRSHshockDefl": 0.0, "RRSHshockDefl": 0.0,
         "LFSHshockVel": 0.0, "RFSHshockVel": 0.0,
         "LRSHshockVel": 0.0, "RRSHshockVel": 0.0,
         "AirDensity": 1.225},
        {"SessionTime": 0.1, "LapDist": 10.0, "LapDistPct": 0.02, "Speed": 20.0,
         "Throttle": 0.5, "Brake": 0.0, "SteeringWheelAngle": 0.0,
         "LatAccel": 0.0, "LongAccel": 2.0, "RPM": 3000.0, "Gear": 3,
         "CFSRrideHeight": 0.05, "LFrideHeight": 0.05, "RFrideHeight": 0.05,
         "LRrideHeight": 0.05, "RRrideHeight": 0.05,
         "LFSHshockDefl": 0.0, "RFSHshockDefl": 0.0,
         "LRSHshockDefl": 0.0, "RRSHshockDefl": 0.0,
         "LFSHshockVel": 0.0, "RFSHshockVel": 0.0,
         "LRSHshockVel": 0.0, "RRSHshockVel": 0.0,
         "AirDensity": 1.225},
    ]
    result = normalize_telemetry_rows(rows)
    row = result[1]
    # Grade channels that don't need mass should still work
    assert row.get("dynamic_grade_deg") is not None
    assert row.get("grade_corrected_long_accel_mps2") is not None
    # Grade force needs mass
    assert row.get("grade_force_proxy_n") is None


def test_grade_channels_metadata_exists() -> None:
    """All grade channels should have CHANNEL_METADATA entries."""
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
    grade_channels = [
        "dynamic_grade_rad",
        "dynamic_grade_deg",
        "grade_corrected_long_accel_mps2",
        "grade_force_proxy_n",
        "grade_context_label",
        "grade_corrected_speed_loss_mph_s",
    ]
    for ch in grade_channels:
        assert ch in CHANNEL_METADATA, f"Missing metadata for {ch}"
        assert "ESTIMATE" in CHANNEL_METADATA[ch].get("description", "").upper() or \
               "proxy" in CHANNEL_METADATA[ch].get("description", "").lower(), \
               f"{ch} metadata missing estimate/proxy wording"


# ── Speed rate zero-division guards ───────────────────────────

def test_speed_rate_repeated_timestamps() -> None:
    """Repeated timestamps (dt=0) should produce None, not crash."""
    from racelab_engine.analysis.calculated_channels import _compute_speed_rates
    row = {"speed_mph": 100.0, "session_time": 10.0, "lap_dist_ft": 5000.0, "speed_mps": 44.7}
    prev = {"speed_mph": 95.0, "session_time": 10.0, "lap_dist_ft": 4900.0, "speed_mps": 42.5}
    result = _compute_speed_rates(row, prev)
    assert result is None  # dt=0 → None
    assert row.get("speed_rate_mph_s") is None
    assert row.get("speed_rate_mps2") is None


def test_speed_rate_negative_dt() -> None:
    """Negative dt (time going backwards) should produce None, not crash."""
    from racelab_engine.analysis.calculated_channels import _compute_speed_rates
    row = {"speed_mph": 100.0, "session_time": 5.0, "lap_dist_ft": 5000.0, "speed_mps": 44.7}
    prev = {"speed_mph": 95.0, "session_time": 10.0, "lap_dist_ft": 4900.0, "speed_mps": 42.5}
    result = _compute_speed_rates(row, prev)
    assert result is None  # dt=-5 → None
    assert row.get("speed_rate_mph_s") is None


def test_speed_rate_tiny_distance_delta() -> None:
    """Tiny distance delta should leave speed_rate_mph_1000ft as None."""
    from racelab_engine.analysis.calculated_channels import _compute_speed_rates
    row = {"speed_mph": 100.0, "session_time": 11.0, "lap_dist_ft": 5000.05, "speed_mps": 44.7}
    prev = {"speed_mph": 95.0, "session_time": 10.0, "lap_dist_ft": 5000.0, "speed_mps": 42.5}
    _compute_speed_rates(row, prev)
    assert row.get("speed_rate_mph_1000ft") is None  # dd=0.05 < 0.1


def test_speed_rate_first_row() -> None:
    """First row (no previous) should have all speed rates as None."""
    from racelab_engine.analysis.calculated_channels import _init_derivative_row
    row: dict = {}
    _init_derivative_row(row)
    assert row["speed_rate_mph_s"] is None
    assert row["speed_rate_mph_1000ft"] is None
    assert row["speed_rate_mps2"] is None


# ── Curvature smoothing ───────────────────────────────────────

def test_curvature_smoothing_constant() -> None:
    """Constant curvature should remain constant after smoothing."""
    from racelab_engine.io.mt2_reader import smooth_curvature_5point
    curvatures: list[float | None] = [0.001] * 20
    smoothed = smooth_curvature_5point(curvatures)
    assert len(smoothed) == 20
    for v in smoothed:
        if v is not None:
            assert abs(v - 0.001) < 1e-9


def test_curvature_smoothing_jitter_reduced() -> None:
    """Jittered curvature should have lower variance after smoothing."""
    from racelab_engine.io.mt2_reader import smooth_curvature_5point
    import statistics
    curvatures: list[float | None] = [0.001 + (i % 3 - 1) * 0.0005 for i in range(50)]
    smoothed = smooth_curvature_5point(curvatures)
    raw_var = statistics.variance([v for v in curvatures if v is not None])
    smooth_vals = [v for v in smoothed if v is not None]
    smooth_var = statistics.variance(smooth_vals) if len(smooth_vals) > 1 else 0.0
    assert smooth_var < raw_var


def test_curvature_smoothing_short_array() -> None:
    """Arrays shorter than 5 should pass through unchanged."""
    from racelab_engine.io.mt2_reader import smooth_curvature_5point
    curvatures: list[float | None] = [0.001, 0.002, 0.003]
    smoothed = smooth_curvature_5point(curvatures)
    assert smoothed == curvatures


def test_curvature_smoothing_none_values() -> None:
    """None values should propagate correctly."""
    from racelab_engine.io.mt2_reader import smooth_curvature_5point
    curvatures: list[float | None] = [0.001, None, 0.003, 0.004, 0.005, 0.006, 0.007]
    smoothed = smooth_curvature_5point(curvatures)
    assert len(smoothed) == len(curvatures)
    assert smoothed[1] is None  # None propagates


def test_curvature_smoothing_closed_loop_no_spike() -> None:
    """Closed-loop start/finish should not produce a spike."""
    from racelab_engine.io.mt2_reader import smooth_curvature_5point
    # Simulate a closed loop: start and end have same curvature
    curvatures: list[float | None] = [0.001] * 10 + [0.01] * 10 + [0.001] * 10  # type: ignore[assignment]
    smoothed = smooth_curvature_5point(curvatures)
    # No value should exceed the max raw value significantly
    max_raw = max(v for v in curvatures if v is not None)
    max_smooth = max(v for v in smoothed if v is not None)
    assert max_smooth <= max_raw * 1.1  # no amplification


# ── Ackermann steering ────────────────────────────────────────

def test_ackermann_expected_known() -> None:
    """wb=3.0, curv=0.001 → expected = atan(0.003) ≈ 0.003 rad ≈ 0.172°."""
    from racelab_engine.analysis.vehicle_dynamics import ackermann_steering_expected_deg
    expected, conf = ackermann_steering_expected_deg(3.0, 0.001)
    assert expected is not None
    assert abs(expected - math.degrees(math.atan(0.003))) < 0.001
    assert conf.tier == "high"


def test_ackermann_expected_missing_wheelbase() -> None:
    from racelab_engine.analysis.vehicle_dynamics import ackermann_steering_expected_deg
    expected, conf = ackermann_steering_expected_deg(None, 0.001)
    assert expected is None


def test_ackermann_expected_missing_curvature() -> None:
    from racelab_engine.analysis.vehicle_dynamics import ackermann_steering_expected_deg
    expected, conf = ackermann_steering_expected_deg(3.0, None)
    assert expected is None


def test_ackermann_error_extra_steering() -> None:
    """More steering than Ackermann → positive error."""
    from racelab_engine.analysis.vehicle_dynamics import ackermann_steering_error_deg
    error, conf = ackermann_steering_error_deg(10.0, 5.0)
    assert error is not None
    assert abs(error - 5.0) < 0.001


def test_ackermann_error_less_steering() -> None:
    """Less steering than Ackermann → negative error."""
    from racelab_engine.analysis.vehicle_dynamics import ackermann_steering_error_deg
    error, conf = ackermann_steering_error_deg(3.0, 8.0)
    assert error is not None
    assert error < 0


def test_ackermann_scrub_proxy_positive() -> None:
    """Extra steering creates positive scrub proxy."""
    from racelab_engine.analysis.vehicle_dynamics import ackermann_scrub_proxy
    proxy, conf = ackermann_scrub_proxy(10.0, 5.0)
    assert proxy > 0
    assert proxy <= 1.0


def test_ackermann_scrub_proxy_zero_when_understeering() -> None:
    """Less steering than Ackermann → zero scrub proxy."""
    from racelab_engine.analysis.vehicle_dynamics import ackermann_scrub_proxy
    proxy, conf = ackermann_scrub_proxy(3.0, 8.0)
    assert proxy == 0.0


def test_ackermann_scrub_proxy_missing_inputs() -> None:
    """Missing inputs remain unavailable, not false evidence of zero scrub."""
    from racelab_engine.analysis.vehicle_dynamics import ackermann_scrub_proxy
    proxy, conf = ackermann_scrub_proxy(None, 5.0)
    assert proxy is None


# ── Camber temp bias ──────────────────────────────────────────

def test_camber_bias_inner_hotter() -> None:
    """Inner hotter than outer → high_inside."""
    from racelab_engine.analysis.calculated_channels import _compute_camber_bias
    row: dict = {"lf_carcass_temp_l": 120.0, "lf_carcass_temp_r": 90.0}
    _compute_camber_bias(row)
    assert row.get("lf_camber_temp_bias_c") == -30.0
    assert row.get("lf_camber_bias_label") == "high_outside"


def test_camber_bias_outer_hotter() -> None:
    """Outer hotter than inner → high_outside."""
    from racelab_engine.analysis.calculated_channels import _compute_camber_bias
    row: dict = {"lf_carcass_temp_l": 80.0, "lf_carcass_temp_r": 110.0}
    _compute_camber_bias(row)
    assert row.get("lf_camber_temp_bias_c") == 30.0
    assert row.get("lf_camber_bias_label") == "high_inside"


def test_camber_bias_even() -> None:
    """Small temp difference → even."""
    from racelab_engine.analysis.calculated_channels import _compute_camber_bias
    row: dict = {"lf_carcass_temp_l": 100.0, "lf_carcass_temp_r": 105.0}
    _compute_camber_bias(row)
    assert row.get("lf_camber_bias_label") == "even"


def test_camber_bias_missing_temps() -> None:
    """Missing carcass temps → no crash, no channels."""
    from racelab_engine.analysis.calculated_channels import _compute_camber_bias
    row: dict = {}
    _compute_camber_bias(row)
    assert row.get("lf_camber_temp_bias_c") is None


# ── New channel metadata check ────────────────────────────────

def test_new_channels_metadata_exists() -> None:
    """All new vehicle dynamics channels should have CHANNEL_METADATA."""
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
    channels = [
        "ackermann_steering_expected_deg",
        "ackermann_steering_error_deg",
        "ackermann_scrub_proxy",
        "front_platform_roll_deg_from_rh",
        "rear_platform_roll_deg_from_rh",
        "platform_roll_balance_deg",
        "lf_camber_temp_bias_c",
        "rf_camber_temp_bias_c",
        "lr_camber_temp_bias_c",
        "rr_camber_temp_bias_c",
        "lf_camber_bias_label",
        "rf_camber_bias_label",
        "lr_camber_bias_label",
        "rr_camber_bias_label",
    ]
    for ch in channels:
        assert ch in CHANNEL_METADATA, f"Missing metadata for {ch}"
        desc = CHANNEL_METADATA[ch].get("description", "")
        assert "ESTIMATE" in desc.upper() or "proxy" in desc.lower(), \
            f"{ch} metadata missing estimate/proxy wording"


# ── Channel contract audit ────────────────────────────────────

def test_frontend_channels_are_backend_known() -> None:
    """Every frontend-requested channel must be known to the backend.

    This test catches typos or dead channel names in the frontend
    TRACE_WORKBENCH_CHANNELS list.  It does NOT require every backend
    channel to be frontend-requested — only that frontend requests
    point to real channels.
    """
    from pathlib import Path
    import re

    # Read frontend channel list
    frontend_file = Path(__file__).resolve().parents[1] / "ui/src/constants/workbenchChannels.ts"
    if not frontend_file.exists():
        pytest.skip("Frontend workbenchChannels.ts not found — skipping UI contract check")
    frontend_src = frontend_file.read_text()
    frontend_channels: set[str] = set()
    for line in frontend_src.split("\n"):
        if m := re.search(r'"([^"]+)"', line):
            frontend_channels.add(m.group(1))

    # Build set of all known backend channels (metadata + units + CORE)
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA, CALCULATED_CHANNEL_UNITS
    try:
        from racelab_engine.analysis.vectorized_channels import CORE_CHANNELS
    except ImportError:
        CORE_CHANNELS = set()

    known = set(CHANNEL_METADATA.keys()) | set(CALCULATED_CHANNEL_UNITS.keys()) | CORE_CHANNELS

    # Also accept raw iRacing channel names that the backend aliases
    # and computed channels that exist in row path but not in metadata/CORE
    known |= {
        "throttle_pct", "brake_pct", "steering_deg", "abs_steering_deg",
        "abs_lat_accel", "lat_accel_g", "long_accel_g", "vert_accel_g",
        "rpm", "gear", "lap_dist_pct_100", "speed_mph", "speed_fps",
        "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
        # slip ratio proxies — computed in row path _compute_tire_derived
        "lf_slip_ratio_proxy", "rf_slip_ratio_proxy",
        "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
    }

    unknown = frontend_channels - known
    assert not unknown, (
        f"Frontend requests {len(unknown)} channel(s) unknown to backend:\n"
        + "\n".join(f"  {ch}" for ch in sorted(unknown))
        + "\n\nFix: update TRACE_WORKBENCH_CHANNELS or add backend support."
    )


def test_core_channels_have_metadata() -> None:
    """Every CORE_CHANNEL should have a CHANNEL_METADATA entry."""
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
    try:
        from racelab_engine.analysis.vectorized_channels import CORE_CHANNELS
    except ImportError:
        pytest.skip("CORE_CHANNELS not available — skipping")
    missing = [ch for ch in sorted(CORE_CHANNELS) if ch not in CHANNEL_METADATA]
    assert not missing, (
        f"{len(missing)} CORE_CHANNELS missing metadata:\n"
        + "\n".join(f"  {ch}" for ch in missing)
    )


def test_core_channels_have_units() -> None:
    """Every CORE_CHANNEL should have a unit entry where applicable."""
    from racelab_engine.analysis.calculated_channels import CALCULATED_CHANNEL_UNITS
    try:
        from racelab_engine.analysis.vectorized_channels import CORE_CHANNELS
    except ImportError:
        pytest.skip("CORE_CHANNELS not available — skipping")
    # Label channels don't need units
    no_unit_needed = {
        "platform_balance_label", "platform_balance_explanation",
        "rear_scrape_side_label", "grade_context_label",
        "lf_camber_bias_label", "rf_camber_bias_label",
        "lr_camber_bias_label", "rr_camber_bias_label",
    }
    missing = [ch for ch in sorted(CORE_CHANNELS)
               if ch not in CALCULATED_CHANNEL_UNITS and ch not in no_unit_needed]
    assert not missing, (
        f"{len(missing)} CORE_CHANNELS missing units:\n"
        + "\n".join(f"  {ch}" for ch in missing)
    )
