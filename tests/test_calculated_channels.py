from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.units import KPA_TO_PSI, M_TO_IN


def _raw_row(**overrides: float | int | None) -> dict[str, float | int | None]:
    row: dict[str, float | int | None] = {
        "SessionTime": 0.0,
        "Lap": 1,
        "LapDist": 100.0,
        "LapDistPct": 0.25,
        "Speed": 50.0,
        "AirDensity": 1.225,
        "Throttle": 0.95,
        "Brake": 0.0,
        "CFSRrideHeight": 0.050,
        "LFrideHeight": 0.070,
        "RFrideHeight": 0.072,
        "LRrideHeight": 0.080,
        "RRrideHeight": 0.082,
        "LFshockDefl": 0.100,
        "RFshockDefl": 0.101,
        "LRshockDefl": 0.102,
        "RRshockDefl": 0.103,
        "LFshockVel": 0.200,
        "RFshockVel": 0.210,
        "LRshockVel": 0.220,
        "RRshockVel": 0.230,
        "LFtempL": 81.0,
        "LFtempM": 84.0,
        "LFtempR": 87.0,
        "LFpressure": 28.0,
        "LFcoldPressure": 26.0,
    }
    row.update(overrides)
    return row


def test_representative_ride_height_and_rake_formula_contracts() -> None:
    row = normalize_telemetry_rows([_raw_row()])[0]

    assert row["front_avg_rh_in"] == pytest.approx(((0.070 + 0.072) / 2) * M_TO_IN)
    assert row["rear_avg_rh_in"] == pytest.approx(((0.080 + 0.082) / 2) * M_TO_IN)
    assert row["center_rake_fs_in"] == pytest.approx(row["rear_avg_rh_in"] - row["cfs_ride_height_in"])
    assert row["side_rake_in"] == pytest.approx(row["right_avg_rh_in"] - row["left_avg_rh_in"])


def test_tire_delta_representative_contracts() -> None:
    row = normalize_telemetry_rows([_raw_row()])[0]

    assert row["lf_pressure_gain"] == pytest.approx(2.0 * KPA_TO_PSI)
    assert row["lf_temp_spread"] == pytest.approx(6.0)


def test_tire_wear_spread_is_percentage_points_not_fraction_or_length() -> None:
    row = normalize_telemetry_rows([
        _raw_row(LFwearL=0.994, LFwearM=0.992, LFwearR=0.990),
    ])[0]

    assert row["lf_wear_spread"] == pytest.approx(0.4)


def test_speed_and_dynamic_pressure_contracts() -> None:
    row = normalize_telemetry_rows([_raw_row()])[0]

    assert row["speed_mps"] == pytest.approx(50.0)
    assert row["speed_mph"] == pytest.approx(50.0 * 2.23693629)
    assert row["dynamic_pressure_pa"] == pytest.approx(0.5 * 1.225 * 50.0 * 50.0)
    assert row["dynamic_pressure_psf"] > 0


def test_speed_rate_mps2_uses_metric_speed_derivative() -> None:
    rows = normalize_telemetry_rows([
        _raw_row(SessionTime=0.0, Speed=50.0, LapDist=100.0),
        _raw_row(SessionTime=0.5, Speed=51.5, LapDist=125.0),
    ])

    assert rows[0]["speed_rate_mps2"] is None
    assert rows[1]["speed_rate_mps2"] == pytest.approx(3.0)


def test_shock_velocity_fields_use_inches_per_second() -> None:
    row = normalize_telemetry_rows([_raw_row()])[0]

    assert row["lf_shock_vel_in_s"] == pytest.approx(0.200 * M_TO_IN)
    assert row["rr_shock_vel_in_s"] == pytest.approx(0.230 * M_TO_IN)


def test_missing_channels_stay_missing_not_zero() -> None:
    row = normalize_telemetry_rows([{"SessionTime": 0.0, "Speed": 50.0}])[0]

    assert row.get("front_avg_rh_in") is None
    assert row.get("center_rake_fs_in") is None
    assert row.get("lf_pressure_gain") is None


def test_nan_inputs_do_not_create_derived_values() -> None:
    row = normalize_telemetry_rows([_raw_row(CFSRrideHeight=math.nan, LFrideHeight=math.nan, RFrideHeight=math.nan)])[0]

    assert row.get("cfs_ride_height_in") is None
    assert row.get("front_avg_rh_in") is None


def test_steering_wheel_angle_cannot_become_road_wheel_slip_angle() -> None:
    source = _raw_row(SteeringWheelAngle=0.08)
    source.update(
        {
            "VelocityZ": 50.0,
            "VelocityX": 1.0,
            "YawRate": 0.2,
            "front_axle_to_cg_m": 1.5,
            "rear_axle_to_cg_m": 1.5,
        }
    )

    row = normalize_telemetry_rows([source])[0]

    assert row["steering_rad"] == pytest.approx(0.08)
    assert row.get("front_slip_angle_deg") is None
    assert row.get("rear_slip_angle_deg") is None
    assert row.get("slip_angle_balance_deg") is None


def test_platform_angles_require_source_backed_motion_ratios() -> None:
    source = _raw_row()
    source.update(
        {
            "wheelbase_m": 2.8,
            "front_track_width_m": 1.65,
            "rear_track_width_m": 1.65,
        }
    )
    missing = normalize_telemetry_rows([source])[0]
    supplied = normalize_telemetry_rows(
        [{**source, "motion_ratio_front": 0.8, "motion_ratio_rear": 0.7}]
    )[0]

    assert missing.get("platform_pitch_deg_from_rh") is None
    assert missing.get("front_platform_roll_deg_from_rh") is None
    assert missing.get("rear_platform_roll_deg_from_rh") is None
    assert supplied.get("platform_pitch_deg_from_rh") is not None
    assert supplied.get("front_platform_roll_deg_from_rh") is not None
    assert supplied.get("rear_platform_roll_deg_from_rh") is not None
    assert supplied.get("platform_roll_deg_from_rh") is None
