from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    TargetZoneComparison,
    build_lap_grid,
    compare_target_zone,
)
from racelab_engine.analysis.did_it_work import compute_verdict
from racelab_engine.analysis.setup_diff import diff_context, diff_setups
from racelab_engine.analysis.test_discipline import score_test_discipline


def test_build_lap_grid() -> None:
    grid = build_lap_grid(0, 100, 10)
    assert grid[0] == 0.0
    assert grid[-1] == 100.0
    assert len(grid) == 11  # 0, 10, 20, ..., 100


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


def test_setup_diff_detects_changes() -> None:
    bl = {"lf_ride_height_mm": 77.0, "rf_ride_height_mm": 78.0, "tape_percent": 10}
    t = {"lf_ride_height_mm": 78.0, "rf_ride_height_mm": 78.0, "tape_percent": 10}
    changes = diff_setups(bl, t)
    assert any(c.setup_key == "lf_ride_height_mm" for c in changes)
    lf = next(c for c in changes if c.setup_key == "lf_ride_height_mm")
    assert lf.significance == "moderate"


def test_setup_diff_no_changes() -> None:
    bl = {"lf_ride_height_mm": 77.0}
    t = {"lf_ride_height_mm": 77.0}
    assert diff_setups(bl, t) == []


def test_setup_diff_none_setups() -> None:
    assert diff_setups(None, None) == []


def test_context_diff_detects_weather() -> None:
    bl = {"air_temp": 20.0, "track_temp": 30.0, "duration_seconds": 100.0}
    t = {"air_temp": 26.0, "track_temp": 30.0, "duration_seconds": 100.0}
    changes = diff_context(bl, t)
    assert any(c.key == "air_temp" and c.is_problem for c in changes)


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
