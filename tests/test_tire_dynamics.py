from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.tire_dynamics import (
    carcass_temp_avg,
    front_slip_angle_rad,
    scrub_heat_index,
    surface_temp_avg,
    thermal_origin_label,
    tire_utilization_total_proxy,
    vehicle_sideslip_beta_rad,
    wheel_speed_bias_mps,
)


def test_slip_angle_formula_and_low_speed_boundary() -> None:
    beta, beta_conf = vehicle_sideslip_beta_rad(40.0, 2.0)
    alpha, alpha_conf = front_slip_angle_rad(0.08, 40.0, 2.0, 0.2, 1.4)
    stopped_alpha, stopped_conf = front_slip_angle_rad(0.08, 0.001, 2.0, 0.2, 1.4)

    assert beta == pytest.approx(math.atan2(2.0, 40.0))
    assert beta_conf.tier == "high"
    assert alpha == pytest.approx(0.08 - math.atan2(2.0 + 1.4 * 0.2, 40.0))
    assert alpha_conf.tier == "high"
    assert stopped_alpha == 0.0
    assert stopped_conf.assumptions


def test_nan_and_infinity_inputs_are_unavailable_not_precise() -> None:
    beta, beta_conf = vehicle_sideslip_beta_rad(math.nan, 1.0)
    mu, mu_conf = tire_utilization_total_proxy(1500.0, math.inf, 4.0, 4000.0)
    heat, heat_conf = scrub_heat_index(math.nan, 80.0)

    assert beta is None
    assert beta_conf.missing_inputs
    assert mu is None
    assert mu_conf.missing_inputs
    assert heat is None
    assert heat_conf.missing_inputs


def test_temperature_averages_ignore_non_finite_values() -> None:
    assert surface_temp_avg(80.0, math.nan, 100.0) == pytest.approx(90.0)
    assert carcass_temp_avg(math.inf, None, 90.0) == pytest.approx(90.0)
    assert surface_temp_avg(math.nan, math.inf, None) is None


def test_thermal_origin_and_wheel_speed_proxy_are_honest() -> None:
    label, conf = thermal_origin_label(105.0, 90.0)
    bias, bias_conf = wheel_speed_bias_mps(52.0, 50.0)
    unavailable, unavailable_conf = wheel_speed_bias_mps(math.nan, 50.0)

    assert label == "sliding_scrub"
    assert any("Surface" in note for note in conf.assumptions)
    assert bias == pytest.approx(2.0)
    assert bias_conf.tier == "high"
    assert unavailable is None
    assert unavailable_conf.missing_inputs
