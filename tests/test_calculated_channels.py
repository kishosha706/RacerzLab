from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.units import M_TO_IN


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

    assert row["lf_pressure_gain"] == pytest.approx(2.0)
    assert row["lf_temp_spread"] == pytest.approx(6.0)


def test_speed_and_dynamic_pressure_contracts() -> None:
    row = normalize_telemetry_rows([_raw_row()])[0]

    assert row["speed_mph"] == pytest.approx(50.0 * 2.23693629)
    assert row["dynamic_pressure_pa"] == pytest.approx(0.5 * 1.225 * 50.0 * 50.0)
    assert row["dynamic_pressure_psf"] > 0


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
