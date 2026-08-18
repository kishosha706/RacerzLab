from __future__ import annotations

import math

from racelab_engine.analysis.geometry import (
    compute_pitch_deg,
    compute_roll_deg,
    corrected_delta_m,
    ride_height_m_to_in,
    ride_height_mm_to_m,
)


def test_corrected_delta_no_motion_ratio() -> None:
    assert corrected_delta_m(5.0, None) is None
    assert corrected_delta_m(5.0, 0.0) is None


def test_corrected_delta_with_ratio() -> None:
    assert corrected_delta_m(10.0, 0.5) == 5.0


def test_pitch_deg_zero_when_equal() -> None:
    pitch = compute_pitch_deg(0.1, 0.1, 3.0, 1.0, 1.0)
    assert pitch is not None
    assert abs(pitch) < 0.01


def test_pitch_deg_positive_when_rear_higher() -> None:
    pitch = compute_pitch_deg(0.1, 0.15, 3.0, 1.0, 1.0)
    assert pitch is not None
    assert pitch > 0


def test_pitch_deg_none_missing_data() -> None:
    assert compute_pitch_deg(None, 0.15, 3.0) is None
    assert compute_pitch_deg(0.1, None, 3.0) is None
    assert compute_pitch_deg(0.1, 0.15, None) is None
    assert compute_pitch_deg(0.1, 0.15, 3.0) is None


def test_roll_deg_zero_when_equal() -> None:
    roll = compute_roll_deg(0.1, 0.1, 2.0, 1.0, 1.0)
    assert roll is not None
    assert abs(roll) < 0.01


def test_roll_deg_positive_when_right_higher() -> None:
    roll = compute_roll_deg(0.1, 0.12, 2.0, 1.0, 1.0)
    assert roll is not None
    assert roll > 0


def test_ride_height_conversions() -> None:
    assert ride_height_m_to_in(1.0) == 39.37007874
    assert ride_height_m_to_in(None) is None
    assert ride_height_mm_to_m(1000.0) == 1.0
    assert ride_height_mm_to_m(None) is None
    assert ride_height_m_to_in(math.nan) is None
    assert ride_height_mm_to_m(math.inf) is None
    assert compute_pitch_deg(0.1, 0.15, math.nan, 1.0, 1.0) is None
    assert compute_roll_deg(0.1, 0.12, math.inf, 1.0, 1.0) is None
