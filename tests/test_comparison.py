from __future__ import annotations

import pytest

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    TargetZoneComparison,
    build_lap_grid,
    compare_target_zone,
    interpolate_run_to_grid,
)
from racelab_engine.analysis.did_it_work import compute_verdict
from racelab_engine.analysis.setup_diff import diff_context, diff_setups
from racelab_engine.analysis.test_discipline import score_test_discipline


def test_build_lap_grid() -> None:
    grid = build_lap_grid(0, 100, 10)
    assert grid[0] == 0.0
    assert grid[-1] == 100.0
    assert len(grid) == 11  # 0, 10, 20, ..., 100


def test_build_lap_grid_rejects_invalid_ranges_and_steps() -> None:
    with pytest.raises(ValueError):
        build_lap_grid(70, 55, 0.1)
    with pytest.raises(ValueError):
        build_lap_grid(0, 100, 0)


def test_interpolation_same_run() -> None:
    """Comparing a run against itself should show zero deltas."""
    rows = [{"lap_dist_pct_100": float(i), "speed_mph": 180.0 + i * 0.1} for i in range(101)]
    zone = compare_target_zone(rows, rows, 20, 80)
    speed = next(d for d in zone.channel_deltas if d.channel == "speed_mph")
    assert speed.delta is not None
    assert abs(speed.delta) < 0.001
    assert zone.speed_gain_or_loss_label == "unchanged"


def test_target_zone_speed_delta() -> None:
    bl = [{"lap_dist_pct_100": float(i), "speed_mph": 185.0} for i in range(101)]
    t = [{"lap_dist_pct_100": float(i), "speed_mph": 186.0} for i in range(101)]
    zone = compare_target_zone(bl, t, 55, 70)
    speed = next(d for d in zone.channel_deltas if d.channel == "speed_mph")
    assert speed.delta == 1.0
    assert zone.speed_gain_or_loss_label == "gained"


def test_track_position_interpolation_handles_duplicate_and_jittered_positions() -> None:
    rows = [
        {"lap_dist_pct_100": 50.0, "speed_mph": 100.0},
        {"lap_dist_pct_100": 50.0, "speed_mph": 102.0},
        {"lap_dist_pct_100": 49.9, "speed_mph": 99.0},
        {"lap_dist_pct_100": 50.1, "speed_mph": 103.0},
    ]

    result = interpolate_run_to_grid(rows, ["speed_mph"], [50.0])

    assert result["speed_mph"] == [101.0]








def test_test_discipline_clean() -> None:
    from racelab_engine.analysis.comparison import SetupChange
    empty: list[SetupChange] = []
    result = score_test_discipline(empty, context_problems=0)
    assert result.label == "clean"
    assert result.score >= 85


def test_test_discipline_mixed() -> None:
    from racelab_engine.analysis.comparison import SetupChange
    empty: list[SetupChange] = []
    result = score_test_discipline(empty, context_problems=0, setup_groups_touched=3)
    assert result.label == "mixed"


def test_did_it_work_speed_gain() -> None:
    zone = TargetZoneComparison(
        start_pct=55, end_pct=70,
        channel_deltas=[
            ComparedChannelDelta(channel="speed_mph", label="Speed", unit="mph", baseline_avg=185.0, test_avg=186.0, delta=1.0),
            ComparedChannelDelta(channel="cfs_ride_height_in", label="CFS", unit="in", baseline_avg=0.15, test_avg=0.15, delta=0.0),
        ],
        speed_gain_or_loss_label="gained", platform_risk_delta_label="unchanged",
    )
    from racelab_engine.analysis.comparison import TestDisciplineResult
    disc = TestDisciplineResult(score=90, label="clean", positive_factors=[], negative_factors=[])
    verdict = compute_verdict(zone, disc)
    assert verdict.verdict == "keep_direction"
    assert verdict.confidence_score > 0.5


def test_did_it_work_speed_loss() -> None:
    zone = TargetZoneComparison(
        start_pct=55, end_pct=70,
        channel_deltas=[
            ComparedChannelDelta(channel="speed_mph", label="Speed", unit="mph", baseline_avg=186.0, test_avg=185.0, delta=-1.0),
        ],
        speed_gain_or_loss_label="lost", platform_risk_delta_label="unchanged",
    )
    from racelab_engine.analysis.comparison import TestDisciplineResult
    disc = TestDisciplineResult(score=90, label="clean", positive_factors=[], negative_factors=[])
    verdict = compute_verdict(zone, disc)
    assert verdict.verdict == "undo"


def test_did_it_work_inconclusive() -> None:
    zone = TargetZoneComparison(
        start_pct=55, end_pct=70,
        channel_deltas=[
            ComparedChannelDelta(channel="speed_mph", label="Speed", unit="mph", baseline_avg=185.0, test_avg=185.0, delta=0.0),
        ],
        speed_gain_or_loss_label="unchanged", platform_risk_delta_label="unchanged",
    )
    from racelab_engine.analysis.comparison import TestDisciplineResult
    disc = TestDisciplineResult(score=90, label="clean", positive_factors=[], negative_factors=[])
    verdict = compute_verdict(zone, disc)
    assert verdict.verdict == "inconclusive"
