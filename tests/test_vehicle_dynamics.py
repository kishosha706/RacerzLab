from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.vehicle_dynamics import (
    brake_energy_j,
    dynamic_grade_rad,
    grade_force_proxy_n,
    longitudinal_weight_transfer_n,
    wheel_power_proxy_w,
    yaw_rate_expected_rad_s,
)


def test_weight_transfer_formula_and_missing_cg_stays_unavailable() -> None:
    transfer, conf = longitudinal_weight_transfer_n(1500.0, 3.0, 0.4, 2.8)
    defaulted, default_conf = longitudinal_weight_transfer_n(1500.0, 3.0, None, 2.8)

    assert transfer == pytest.approx(1500.0 * 3.0 * 0.4 / 2.8)
    assert conf.tier == "high"
    assert defaulted is None
    assert "cg_height_m" in default_conf.missing_inputs
    assert default_conf.assumptions


def test_dynamic_grade_clamps_extreme_values_and_rejects_non_finite() -> None:
    grade, conf = dynamic_grade_rad(100.0, 0.0)
    unavailable, unavailable_conf = dynamic_grade_rad(math.nan, 0.0)

    assert grade == pytest.approx(math.asin(0.30))
    assert conf.assumptions
    assert unavailable is None
    assert "long_accel_mps2" in unavailable_conf.missing_inputs


def test_force_energy_and_power_helpers_do_not_missing_to_zero() -> None:
    force, force_conf = grade_force_proxy_n(1500.0, math.nan)
    energy, energy_conf = brake_energy_j(1500.0, 80.0, 90.0)
    power, power_conf = wheel_power_proxy_w(accel_power_w=100.0, drag_power_w=math.inf)
    yaw, yaw_conf = yaw_rate_expected_rad_s(math.inf, 0.01)

    assert force is None
    assert "grade_rad" in force_conf.missing_inputs
    assert energy == 0.0
    assert energy_conf.assumptions
    assert power == pytest.approx(100.0)
    assert "drag_power_w" in power_conf.missing_inputs
    assert yaw is None
    assert "speed_mps" in yaw_conf.missing_inputs
