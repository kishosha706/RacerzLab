from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.proximity_context import (
    ProximityState,
    classify_proximity_time_gap_window,
    classify_proximity_window,
    proximity_time_gap_exposure_fraction,
)


def test_large_distance_sentinel_means_no_nearby_car_reported_not_certified_clean() -> None:
    result = classify_proximity_window(
        [{"CarDistAhead": 500_000.0, "CarDistBehind": 500_000.0}] * 10,
        exclusion_distance_m=50.0,
    )

    assert result.state is ProximityState.NO_NEARBY_CAR_REPORTED
    assert result.basis == "distance"
    assert result.blocks_relative_resistance is False
    assert "not measured aerodynamic cleanliness" in result.explanation


@pytest.mark.parametrize(
    ("ahead", "behind", "state"),
    [
        (18.0, 500_000.0, ProximityState.NEARBY_CAR_AHEAD),
        (500_000.0, 22.0, ProximityState.NEARBY_CAR_BEHIND),
        (18.0, 22.0, ProximityState.NEARBY_CARS_AHEAD_AND_BEHIND),
    ],
)
def test_nearby_states_block_relative_resistance(
    ahead: float,
    behind: float,
    state: ProximityState,
) -> None:
    result = classify_proximity_window(
        [{"car_distance_ahead_m": ahead, "car_distance_behind_m": behind}],
        exclusion_distance_m=50.0,
    )

    assert result.state is state
    assert result.hard_blocker_active is True


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"CarDistAhead": 500_000.0}],
        [{"CarDistAhead": math.nan, "CarDistBehind": 500_000.0}],
        [{"CarDistAhead": -1.0, "CarDistBehind": 500_000.0}],
        [
            {"CarDistAhead": 500_000.0, "CarDistBehind": 500_000.0},
            {"CarDistAhead": None, "CarDistBehind": 500_000.0},
        ],
    ],
)
def test_missing_or_invalid_coverage_fails_closed(rows: list[dict[str, float | None]]) -> None:
    result = classify_proximity_window(rows, exclusion_distance_m=50.0)

    assert result.state is ProximityState.CONTEXT_UNKNOWN
    assert result.blocks_relative_resistance is True


@pytest.mark.parametrize("distance", [0.0, -1.0, math.nan, math.inf])
def test_exclusion_distance_must_be_finite_and_positive(distance: float) -> None:
    with pytest.raises(ValueError, match="finite and greater than zero"):
        classify_proximity_window([], exclusion_distance_m=distance)


def test_user_time_gap_rules_classify_ahead_at_1_5s_and_behind_at_0_5s() -> None:
    ahead = classify_proximity_time_gap_window(
        [{"CarDistAhead": 90.0, "CarDistBehind": 500_000.0, "speed_mps": 60.0}],
    )
    behind = classify_proximity_time_gap_window(
        [{"CarDistAhead": 500_000.0, "CarDistBehind": 30.0, "speed_mps": 60.0}],
    )

    assert ahead.state is ProximityState.NEARBY_CAR_AHEAD
    assert ahead.min_time_gap_ahead_s == pytest.approx(1.5)
    assert behind.state is ProximityState.NEARBY_CAR_BEHIND
    assert behind.min_time_gap_behind_s == pytest.approx(0.5)
    assert "measured speed remains valid" in behind.explanation
    assert "could have contributed" in behind.explanation


def test_time_gap_rules_do_not_block_outside_asymmetric_windows() -> None:
    result = classify_proximity_time_gap_window(
        [{"CarDistAhead": 91.0, "CarDistBehind": 31.0, "speed_mps": 60.0}],
    )

    assert result.state is ProximityState.NO_NEARBY_CAR_REPORTED
    assert result.blocks_relative_resistance is False
    assert result.basis == "time_gap"


def test_time_gap_context_requires_valid_speed_for_every_sample() -> None:
    result = classify_proximity_time_gap_window(
        [{"CarDistAhead": 500_000.0, "CarDistBehind": 500_000.0, "speed_mps": 0.0}],
    )

    assert result.state is ProximityState.CONTEXT_UNKNOWN
    assert result.blocks_relative_resistance is True


def test_time_gap_exposure_fraction_is_measured_and_missing_is_not_zero_filled() -> None:
    rows = [
        {"CarDistAhead": 60.0, "CarDistBehind": 500_000.0, "speed_mps": 50.0},
        {"CarDistAhead": 100.0, "CarDistBehind": 500_000.0, "speed_mps": 50.0},
    ]

    assert proximity_time_gap_exposure_fraction(rows) == 0.5
    rows[1].pop("CarDistBehind")
    assert proximity_time_gap_exposure_fraction(rows) is None
