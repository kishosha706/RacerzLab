from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.compare_math import (
    aggregate_channel_stats,
    aggregate_platform_stats,
    compute_whole_car_index,
)
from racelab_engine.analysis.comparison import ChannelDeltaStats, DriverComparison, PlatformComparison, PowertrainComparison


def _trace_row(pct: float, **values: float) -> dict[str, float]:
    return {"lap_dist_pct_100": pct, **values}


def test_channel_aggregation_ignores_nan_and_infinity() -> None:
    stats = aggregate_channel_stats(
        {"speed_mph": [100.0, math.nan, math.inf, None]},
        {"speed_mph": [101.0, 103.0, None]},
        "speed_mph",
        "Speed",
        "mph",
    )

    assert stats.baseline_avg == 100.0
    assert stats.test_avg == 102.0
    assert stats.delta_avg == 2.0
    assert stats.direction == "better"


def test_channel_aggregation_missing_side_stays_unavailable_not_zero() -> None:
    stats = aggregate_channel_stats({"speed_mph": [100.0]}, {}, "speed_mph", "Speed", "mph")

    assert stats.test_avg is None
    assert stats.delta_avg is None
    assert stats.confidence == 0.0


def test_platform_aggregation_with_missing_channel_keeps_null_delta() -> None:
    baseline = [_trace_row(0.0, cfs_ride_height_in=0.50), _trace_row(100.0, cfs_ride_height_in=0.50)]
    test = [_trace_row(0.0, cfs_ride_height_in=0.55), _trace_row(100.0, cfs_ride_height_in=0.55)]

    platform = aggregate_platform_stats(baseline, test)

    assert platform.cfs_height is not None
    assert platform.cfs_height.delta_avg == pytest.approx(0.05)
    assert platform.front_avg_rh is not None
    assert platform.front_avg_rh.delta_avg is None


def test_whole_car_index_aggregates_available_scores_without_fake_zero() -> None:
    platform = PlatformComparison(
        dynamic_pressure=ChannelDeltaStats("dynamic_pressure_psf", "Dynamic Pressure", "psf", delta_avg=0.2),
        cfs_height=ChannelDeltaStats("cfs_ride_height_in", "CFS", "in", delta_avg=0.02),
    )
    driver = DriverComparison(
        avg_abs_steering_deg=ChannelDeltaStats("abs_steering_deg", "Steering", "deg", delta_avg=-0.4)
    )
    powertrain = PowertrainComparison(
        pull_score=ChannelDeltaStats("speed_rate_mph_1000ft", "Pull", "mph/1000ft", delta_avg=None)
    )

    index = compute_whole_car_index(platform, driver, powertrain, discipline_score=88.0, context_problems=0)

    assert index.powertrain_index == 50.0
    assert index.confidence_index == 70.0
    assert index.overall_index is not None
