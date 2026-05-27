from __future__ import annotations

from racelab_engine.analysis.drag_scrub import (
    aero_normalized_resistance,
    compute_drag_scrub_index,
)


def test_aero_normalized_resistance_zero_decel() -> None:
    row = {"speed_rate_mph_s": 0.0, "dynamic_pressure_psf": 100.0}
    assert aero_normalized_resistance(row) == 0.0


def test_aero_normalized_resistance_positive() -> None:
    row = {"speed_rate_mph_s": -2.0, "dynamic_pressure_psf": 100.0}
    assert aero_normalized_resistance(row) == 0.02


def test_aero_normalized_resistance_floor_dp() -> None:
    """Dynamic pressure floors at 1.0 psf to prevent division-by-zero."""
    row = {"speed_rate_mph_s": -2.0, "dynamic_pressure_psf": 0.0}
    assert aero_normalized_resistance(row) == 2.0  # 2.0 / 1.0


def test_drag_scrub_zero_below_min_speed() -> None:
    row = {"speed_mph": 100.0, "throttle_pct": 99.0, "brake_pct": 0.0}
    assert compute_drag_scrub_index(row) == 0.0


def test_drag_scrub_zero_during_braking() -> None:
    row = {"speed_mph": 180.0, "throttle_pct": 0.0, "brake_pct": 50.0}
    assert compute_drag_scrub_index(row) == 0.0


def test_drag_scrub_zero_low_throttle() -> None:
    row = {"speed_mph": 180.0, "throttle_pct": 50.0, "brake_pct": 0.0}
    assert compute_drag_scrub_index(row) == 0.0


def test_drag_scrub_nonzero_full_throttle() -> None:
    row = {
        "speed_mph": 180.0,
        "throttle_pct": 99.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -2.0,
        "dynamic_pressure_psf": 100.0,
        "abs_steering_deg": 2.0,
        "yaw_rate": 0.05,
        "cfs_risk_score": 0.2,
    }
    index = compute_drag_scrub_index(row)
    assert 0.0 < index <= 1.0


def test_drag_scrub_high_resistance() -> None:
    """High aero-normalized resistance should produce a high index."""
    row = {
        "speed_mph": 200.0,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -10.0,
        "dynamic_pressure_psf": 50.0,
        "abs_steering_deg": 30.0,
        "yaw_rate": 2.0,
        "cfs_risk_score": 1.0,
    }
    index = compute_drag_scrub_index(row)
    # resistance_coeff = 10/50 = 0.2, resistance_index = 0.2/0.02 capped at 1.0
    # steering = 30/15 capped at 1.0, yaw = 2.0/1.0 capped at 1.0, cfs = 1.0
    # index = 1.0*0.45 + 1.0*0.20 + 1.0*0.15 + 1.0*0.10 = 0.90
    assert index == 0.90


def test_drag_scrub_missing_fields_default_to_zero() -> None:
    row: dict = {"speed_mph": 180.0, "throttle_pct": 99.0, "brake_pct": 0.0}
    index = compute_drag_scrub_index(row)
    assert 0.0 <= index <= 1.0
