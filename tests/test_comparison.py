from __future__ import annotations

import math

import pytest
from fastapi import HTTPException

import api.routes_compare as routes_compare
from api.routes_compare import (
    _assert_run_compatibility,
    _proximity_context_changes,
    _telemetry_context_changes,
)
from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    TargetZoneComparison,
    build_lap_grid,
    compare_target_zone,
    interpolate_run_to_grid,
)
from racelab_engine.analysis.did_it_work import compute_verdict
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


def test_interpolation_never_clamps_outside_observed_channel_support() -> None:
    rows = [
        {"lap_dist_pct_100": 0.0, "cfs_ride_height_in": 0.20},
        {"lap_dist_pct_100": 1.0, "cfs_ride_height_in": 0.21},
    ]

    result = interpolate_run_to_grid(rows, ["cfs_ride_height_in"], [0.0, 0.5, 1.0, 55.0])

    assert result["cfs_ride_height_in"][:3] == [0.20, pytest.approx(0.205), 0.21]
    assert result["cfs_ride_height_in"][3] is None


def test_interpolation_does_not_bridge_large_interior_telemetry_gaps() -> None:
    rows = [
        {"lap_dist_pct_100": 0.0, "cfs_ride_height_in": 0.20},
        {"lap_dist_pct_100": 100.0, "cfs_ride_height_in": 0.20},
    ]

    result = interpolate_run_to_grid(rows, ["cfs_ride_height_in"], [0.0, 50.0, 100.0])

    assert result["cfs_ride_height_in"] == [0.20, None, 0.20]








def test_test_discipline_zero_change_is_reference() -> None:
    from racelab_engine.analysis.comparison import SetupChange
    empty: list[SetupChange] = []
    result = score_test_discipline(empty, context_problems=0)
    assert result.label == "reference"
    assert result.score >= 85
    assert result.is_reliable is False


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
            ComparedChannelDelta(channel="cfs_ride_height_in", label="CFS", unit="in", baseline_avg=0.2, test_avg=0.2, delta=0.0),
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


def test_compare_proximity_gate_keeps_lap_but_blocks_setup_attribution() -> None:
    baseline = [
        {"speed_mps": 60.0, "car_distance_ahead_m": 500_000.0, "car_distance_behind_m": 500_000.0}
    ]
    test = [
        {"speed_mps": 60.0, "car_distance_ahead_m": 500_000.0, "car_distance_behind_m": 29.0}
    ]

    changes, blocked, evidence = _proximity_context_changes(baseline, test)

    assert blocked is True
    assert len(changes) == 1
    assert changes[0].is_problem is True
    assert "lap and its measured speed remain valid" in changes[0].warning
    assert "within 0.5 s behind" in changes[0].warning
    assert "traffic influence on the measured speed cannot be ruled out" in changes[0].warning
    assert "behind 0.48 s" in evidence[1]


def test_compare_proximity_warning_only_names_observed_ahead_context() -> None:
    baseline = [
        {"speed_mps": 60.0, "car_distance_ahead_m": 500_000.0, "car_distance_behind_m": 500_000.0}
    ]
    test = [
        {"speed_mps": 60.0, "car_distance_ahead_m": 80.0, "car_distance_behind_m": 500_000.0}
    ]

    changes, blocked, _ = _proximity_context_changes(baseline, test)

    assert blocked is True
    assert "within 1.5 s ahead" in changes[0].warning
    assert "0.5 s behind" not in changes[0].warning


def test_compare_proximity_gate_allows_attribution_outside_both_windows() -> None:
    rows = [
        {"speed_mps": 60.0, "car_distance_ahead_m": 91.0, "car_distance_behind_m": 31.0}
    ]

    changes, blocked, evidence = _proximity_context_changes(rows, rows)

    assert changes == []
    assert blocked is False
    assert evidence == []


def _matched_context_row(wind_dir: float) -> dict[str, float]:
    return {
        "fuel_level": 50.0,
        "air_density": 1.20,
        "air_temp": 25.0,
        "track_temp": 35.0,
        "wind_vel": 2.0,
        "wind_dir": wind_dir,
        "lf_tire_distance_m": 1_000.0,
        "rf_tire_distance_m": 1_000.0,
        "lr_tire_distance_m": 1_000.0,
        "rr_tire_distance_m": 1_000.0,
    }


def test_wind_direction_context_uses_radians_and_handles_wraparound() -> None:
    near_wrap = _telemetry_context_changes(
        [_matched_context_row(math.radians(359.0))],
        [_matched_context_row(math.radians(1.0))],
    )
    reversal = _telemetry_context_changes(
        [_matched_context_row(0.0)],
        [_matched_context_row(math.pi)],
    )

    assert not any(change.key == "wind_dir" for change in near_wrap)
    assert any(change.key == "wind_dir" for change in reversal)


def test_compatibility_gate_rejects_cross_car_or_track_comparisons(monkeypatch: pytest.MonkeyPatch) -> None:
    base = {key: f"same-{key}" for key in routes_compare._COMPATIBILITY_FIELDS}
    base["track_configuration_name"] = "baseline-layout"
    identities = {
        "baseline": base,
        "test": {**base, "track_configuration_name": "different-layout"},
    }
    monkeypatch.setattr(
        routes_compare,
        "read_telemetry_manifest",
        lambda run_id: {"compatibility_identity": identities[run_id]},
    )

    with pytest.raises(HTTPException, match="track configuration"):
        _assert_run_compatibility("baseline", "test")


def test_compatibility_gate_fails_closed_when_identity_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_compare, "read_telemetry_manifest", lambda _run_id: {})

    missing = _assert_run_compatibility("baseline", "test")

    assert "car ID" in missing
    assert "track ID" in missing


def test_compatibility_gate_rejects_known_mismatch_even_with_other_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = {
        "baseline": {"car_id": 1, "car_path": "car/a", "iracing_build_version": None},
        "test": {"car_id": 99, "car_path": "car/b", "iracing_build_version": None},
    }
    monkeypatch.setattr(
        routes_compare,
        "read_telemetry_manifest",
        lambda run_id: {"compatibility_identity": identities[run_id]},
    )

    with pytest.raises(HTTPException, match="car ID"):
        _assert_run_compatibility("baseline", "test")
