from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.aero_coefficients import (
    _coastdown_is_valid,
    aero_load_index,
    air_speed_mps,
    cda_coastdown_proxy_m2,
    dynamic_pressure_air_context,
    dynamic_pressure_pa as coeff_dynamic_pressure_pa,
    full_throttle_resistance_cda_proxy_m2,
)
from racelab_engine.analysis.physics_inputs import VehiclePhysicsInputs
from racelab_engine.analysis.aero_platform import (
    build_platform_proxy_estimates,
    dynamic_pressure_pa,
    spring_load_delta_proxy_n,
)


def test_aero_platform_proxy_keeps_warning_and_missing_constants() -> None:
    estimates = build_platform_proxy_estimates(
        {
            "lf_ride_height_mm": 48.0,
            "rf_ride_height_mm": 49.0,
            "lr_ride_height_mm": 8.0,
            "rr_ride_height_mm": 12.0,
            "lat_accel": 0.0,
            "long_accel": 0.0,
        },
        setup={
            "lf_ride_height_mm": 50.0,
            "rf_ride_height_mm": 50.0,
            "lr_ride_height_mm": 15.0,
            "rr_ride_height_mm": 15.0,
            "lf_front_spring_n_per_mm": 100.0,
            "rf_front_spring_n_per_mm": 100.0,
            "lr_rear_spring_n_per_mm": 120.0,
            "rr_rear_spring_n_per_mm": 120.0,
            "lf_motion_ratio": 1.0,
            "rf_motion_ratio": 1.0,
            "lr_motion_ratio": 1.0,
            "rr_motion_ratio": 1.0,
        },
    )

    assert estimates["front_load_proxy_n"].value == pytest.approx(300.0)
    assert estimates["rear_scrape_risk_score"].value == pytest.approx(0.38)
    assert "estimates/proxies" in estimates["front_load_proxy_n"].warning_text
    assert "wheelbase_m" in estimates["front_load_proxy_n"].missing_constants


def test_aero_platform_non_finite_inputs_are_unavailable() -> None:
    assert dynamic_pressure_pa(math.nan, 1.225) is None
    assert spring_load_delta_proxy_n(40.0, math.inf, 100.0, 1.0) is None
    assert spring_load_delta_proxy_n(40.0, 50.0, 100.0) is None
    estimates = build_platform_proxy_estimates({"lr_ride_height_mm": math.nan, "rr_ride_height_mm": 12.0}, setup=None)
    assert estimates["rear_scrape_risk_score"].value is None


def test_missing_motion_channels_do_not_become_zero_activity() -> None:
    estimates = build_platform_proxy_estimates(
        {
            "lf_ride_height_mm": 48.0,
            "rf_ride_height_mm": 49.0,
            "lr_ride_height_mm": 8.0,
            "rr_ride_height_mm": 12.0,
        },
        setup={
            "lf_ride_height_mm": 50.0,
            "rf_ride_height_mm": 50.0,
            "lr_ride_height_mm": 15.0,
            "rr_ride_height_mm": 15.0,
            "lf_front_spring_n_per_mm": 100.0,
            "rf_front_spring_n_per_mm": 100.0,
            "lr_rear_spring_n_per_mm": 120.0,
            "rr_rear_spring_n_per_mm": 120.0,
        },
    )

    estimate = estimates["front_load_proxy_n"]
    assert estimate.value is None
    assert estimate.confidence == "low"
    assert any("not treated as zero" in note for note in estimate.assumptions)
    assert any(
        "not treated as a settled platform" in note
        for note in estimate.assumptions
    )
    assert any("force-like" in note for note in estimate.assumptions)


def test_invalid_corner_motion_ratio_cannot_unlock_force_proxies() -> None:
    estimates = build_platform_proxy_estimates(
        {
            "lf_ride_height_mm": 48.0,
            "rf_ride_height_mm": 49.0,
            "lr_ride_height_mm": 8.0,
            "rr_ride_height_mm": 12.0,
        },
        setup={
            "lf_ride_height_mm": 50.0,
            "rf_ride_height_mm": 50.0,
            "lr_ride_height_mm": 15.0,
            "rr_ride_height_mm": 15.0,
            "lf_front_spring_n_per_mm": 100.0,
            "rf_front_spring_n_per_mm": 100.0,
            "lr_rear_spring_n_per_mm": 120.0,
            "rr_rear_spring_n_per_mm": 120.0,
            "lf_motion_ratio": 1.0,
            "rf_motion_ratio": 0.0,
            "lr_motion_ratio": 1.0,
            "rr_motion_ratio": 1.0,
        },
    )

    assert estimates["front_load_proxy_n"].value is None
    assert estimates["front_aero_proxy_n"].value is None
    assert "corner_motion_ratios" in estimates["front_load_proxy_n"].missing_constants


def test_aero_coefficients_dynamic_pressure_and_air_speed_confidence() -> None:
    ground_speed, ground_conf = air_speed_mps(50.0)
    q, q_conf = coeff_dynamic_pressure_pa(None, 50.0)
    index, index_conf = aero_load_index(q)

    assert ground_speed is None
    assert ground_conf.missing_inputs
    assert q is None
    assert q_conf.missing_inputs == ["air_density_kg_m3"]
    assert index is None
    assert index_conf.missing_inputs


def test_cda_proxies_return_unavailable_for_invalid_or_non_drag_conditions() -> None:
    coastdown, coast_conf = cda_coastdown_proxy_m2(1500.0, -2.0, math.nan)
    full_throttle, full_conf = full_throttle_resistance_cda_proxy_m2(1500.0, 2.0, 1500.0)

    assert coastdown is None
    assert "q_air_pa" in coast_conf.missing_inputs
    assert full_throttle is None
    assert "engine_force_n" in full_conf.missing_inputs


def test_zero_wind_and_zero_heading_are_valid_measured_context() -> None:
    q, confidence = dynamic_pressure_air_context(
        {
            "speed_mps": 50.0,
            "wind_speed_mps": 0.0,
            "wind_dir_rad": 0.0,
            "yaw_rad": 0.0,
            "air_density": 1.2,
        },
        VehiclePhysicsInputs(),
    )

    assert q == pytest.approx(0.5 * 1.2 * 50.0**2)
    assert confidence.missing_inputs == []


@pytest.mark.parametrize(
    ("density", "speed"),
    ((-1.2, 50.0), (0.0, 50.0), (1.2, -1.0)),
)
def test_nonphysical_dynamic_pressure_inputs_are_unavailable(
    density: float, speed: float
) -> None:
    value, confidence = coeff_dynamic_pressure_pa(density, speed)
    assert value is None
    assert confidence.missing_inputs


def test_coastdown_gate_fails_closed_on_missing_or_nonfinite_inputs() -> None:
    assert not _coastdown_is_valid(None, 0.0, 50.0, -0.5)
    assert not _coastdown_is_valid(0.0, 0.0, math.nan, -0.5)
    assert not _coastdown_is_valid(0.0, 0.0, 50.0, None)
