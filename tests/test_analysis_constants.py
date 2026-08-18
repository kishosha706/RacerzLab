from __future__ import annotations

import pytest

from racelab_engine.analysis.constants import (
    SPLITTER_SCRAPE_MM,
    SPLITTER_CRITICAL_MM,
    SPLITTER_HIGH_MM,
    SPLITTER_WATCH_MM,
    PLATFORM_VALID_MIN_SPEED_MPH,
    PLATFORM_VALID_THROTTLE_PCT,
    DRAG_SCRUB_MIN_SPEED_MPH,
    FULL_THROTTLE_PCT,
    LOW_BRAKE_PCT,
    SEGMENT_WIDTH_PCT,
    SLIP_RATIO_SPEED_FLOOR_MPS,
    SLIP_RATIO_CLAMP_MAX,
    LAP_WRAP_DROP_THRESHOLD_PCT,
    RESISTANCE_COEFF_CRITICAL,
    REFERENCE_DYNAMIC_PRESSURE_PA,
    WCI_WEIGHT_PROFILES,
    apply_motion_ratio,
    logistic_score,
)


def test_splitter_thresholds_ordered() -> None:
    assert SPLITTER_SCRAPE_MM < SPLITTER_CRITICAL_MM < SPLITTER_HIGH_MM < SPLITTER_WATCH_MM


def test_platform_valid_speed_positive() -> None:
    assert PLATFORM_VALID_MIN_SPEED_MPH > 0


def test_drag_scrub_min_speed_above_valid() -> None:
    assert DRAG_SCRUB_MIN_SPEED_MPH > PLATFORM_VALID_MIN_SPEED_MPH


def test_throttle_brake_thresholds_sane() -> None:
    assert FULL_THROTTLE_PCT > PLATFORM_VALID_THROTTLE_PCT
    assert LOW_BRAKE_PCT < 10


def test_segment_width_positive() -> None:
    assert SEGMENT_WIDTH_PCT > 0


def test_slip_ratio_floor_positive() -> None:
    assert SLIP_RATIO_SPEED_FLOOR_MPS > 0
    assert SLIP_RATIO_CLAMP_MAX > 0


def test_lap_wrap_threshold_negative() -> None:
    assert LAP_WRAP_DROP_THRESHOLD_PCT < 0


def test_wci_profiles_have_required_keys() -> None:
    required = {"speed", "platform", "driver", "powertrain", "shock", "discipline"}
    for name, profile in WCI_WEIGHT_PROFILES.items():
        assert set(profile.keys()) == required, f"{name} missing keys"
        assert abs(sum(profile.values()) - 1.0) < 0.01, f"{name} weights don't sum to 1.0"


def test_wci_profiles_contain_expected_types() -> None:
    expected = {"superspeedway", "oval", "short_track", "road_course"}
    assert set(WCI_WEIGHT_PROFILES.keys()) == expected


def test_apply_motion_ratio_requires_source_backed_ratio() -> None:
    assert apply_motion_ratio(5.0, None) is None
    assert apply_motion_ratio(5.0, 0.0) is None
    assert apply_motion_ratio(5.0, -1.0) is None


def test_apply_motion_ratio_scales() -> None:
    assert apply_motion_ratio(10.0, 0.5) == 5.0
    assert apply_motion_ratio(10.0, 1.0) == 10.0
    assert apply_motion_ratio(10.0, 0.75) == 7.5


def test_resistance_coeff_positive() -> None:
    assert RESISTANCE_COEFF_CRITICAL > 0


def test_reference_dynamic_pressure_positive() -> None:
    assert REFERENCE_DYNAMIC_PRESSURE_PA > 0


def test_logistic_score_neutral_at_noise() -> None:
    score = logistic_score(delta=0.05, noise=0.05, steepness=2.5, higher_is_better=True)
    assert 45 <= score <= 55  # near 50


def test_logistic_score_high_for_positive_delta() -> None:
    score = logistic_score(delta=2.0, noise=0.05, steepness=2.5, higher_is_better=True)
    assert score > 80


def test_logistic_score_low_for_negative_delta() -> None:
    score = logistic_score(delta=-2.0, noise=0.05, steepness=2.5, higher_is_better=True)
    assert score < 20


def test_logistic_score_higher_is_worse() -> None:
    score = logistic_score(delta=2.0, noise=0.25, steepness=3.0, higher_is_better=False)
    assert score < 30  # large steering = bad


def test_logistic_score_none_returns_50() -> None:
    assert logistic_score(None, 0.05, 2.5) == 50.0


def test_logistic_score_noise_band_is_neutral_and_symmetric() -> None:
    assert logistic_score(0.0, 0.05, 2.5) == 50.0
    assert logistic_score(0.04, 0.05, 2.5) == 50.0
    assert logistic_score(-0.04, 0.05, 2.5) == 50.0
    assert logistic_score(0.25, 0.05, 2.5) == pytest.approx(
        100.0 - logistic_score(-0.25, 0.05, 2.5)
    )
