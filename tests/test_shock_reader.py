from __future__ import annotations

import json
from pathlib import Path

import pytest

from racelab_engine.analysis.shock_reader import build_shock_reader_response
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import write_telemetry_cache


def _setup(value: int = 5, *, include: bool = True, setting: str | None = None) -> SetupSnapshot | None:
    if not include:
        return None
    base = {
        "ls_compression": value,
        "hs_compression": value,
        "hs_comp_slope": value,
        "ls_rebound": value,
        "hs_rebound": value,
        "hs_reb_slope": value,
    }
    if setting:
        base = {**base, setting: value}
    return SetupSnapshot(
        setup_id="run-1:setup",
        run_id="run-1",
        setup_name="Baseline",
        extracted_values={corner: dict(base) for corner in ("lf", "rf", "lr", "rr")},
    )


def _rows(values: list[float], *, contact: bool = False, chatter: bool = False) -> list[dict]:
    rows = []
    for idx, value in enumerate(values):
        rows.append(
            {
                "lap": 1,
                "session_time": idx / 60,
                "lap_dist_pct": idx / max(len(values) - 1, 1),
                "speed_mph": 150.0,
                "throttle_pct": 80.0,
                "brake_pct": 0.0,
                "abs_steering_deg": 4.0,
                "lf_shock_vel_in_s": value,
                "rf_shock_vel_in_s": value,
                "lr_shock_vel_in_s": value,
                "rr_shock_vel_in_s": value,
                "lf_shock_defl_delta_in": value / 20,
                "rf_shock_defl_delta_in": value / 20,
                "lr_shock_defl_delta_in": value / 20,
                "rr_shock_defl_delta_in": value / 20,
                "shock_activity_index": 2.0 if chatter else 0.8,
                "rear_scrape_risk_score": 0.75 if contact else 0.0,
                "rear_platform_contact_risk": 0.7 if contact else 0.0,
                "rear_scrape_margin_mm": -1.0 if contact else 20.0,
                "cfs_ride_height_in": 0.08 if contact else 1.5,
            }
        )
    return rows


def _write(tmp_path: Path, values: list[float], **kwargs) -> None:
    write_telemetry_cache("run-1", _rows(values, **kwargs), data_dir=tmp_path)


def test_balanced_histogram_returns_leave_alone(tmp_path: Path) -> None:
    _write(tmp_path, [-0.8, -0.4, 0.2, 0.7] * 30)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    assert response.corners[0].pattern == "balanced"
    assert all(len(corner.setting_recommendations) == 6 for corner in response.corners)
    assert response.recommendations[0].semantic_direction == "leave_alone"
    assert response.recommendations[0].numeric_step is None


def test_per_corner_setting_recommendations_exist_for_all_corners(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 20) + ([1.4] * 10))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    assert [corner.corner for corner in response.corners] == ["LF", "RF", "LR", "RR"]
    for corner in response.corners:
        assert [rec.display_label for rec in corner.setting_recommendations] == [
            "LS Comp",
            "HS Comp",
            "HS-S Comp",
            "LS Reb",
            "HS Reb",
            "HS-S Reb",
        ]


def test_strong_low_speed_bump_signal_scales_beyond_one_click(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 20) + ([1.4] * 10))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert response.corners[0].pattern == "low_speed_bump_heavy"
    assert rec.setting == "ls_compression"
    assert rec.direction == "subtract"
    assert rec.delta is not None and rec.delta < -1
    assert rec.current_value is not None
    assert rec.suggested_value == rec.current_value + rec.delta


def test_low_speed_rebound_heavy_returns_subtract_ls_rebound(tmp_path: Path) -> None:
    _write(tmp_path, ([-0.2] * 70) + ([0.2] * 20) + ([-1.4] * 10))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[3]
    assert response.corners[0].pattern == "low_speed_rebound_heavy"
    assert rec.setting == "ls_rebound"
    assert rec.direction == "subtract"


def test_excessive_high_speed_shoulders_no_contact_returns_soften_candidate(tmp_path: Path) -> None:
    _write(tmp_path, ([2.2] * 35) + ([-2.1] * 35) + ([0.2] * 30), chatter=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    rec = response.recommendations[0]
    assert response.corners[0].pattern == "excessive_high_speed_shoulders"
    assert rec.setting in {"hs_compression", "hs_rebound", "hs_compression_slope", "hs_rebound_slope"}
    assert rec.semantic_direction in {"subtract", "move_more_digressive"}


def test_high_speed_bump_contact_returns_add_hs_or_linear_slope(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    rec = response.recommendations[0]
    assert response.corners[0].pattern == "impact_contact_driven"
    assert rec.setting in {"hs_compression", "hs_compression_slope"}
    assert rec.semantic_direction in {"add", "move_more_linear"}


def test_slope_candidate_requires_selected_platform_context(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response("run-1", setup_snapshot=_setup(), data_dir=tmp_path)
    slope = response.corners[0].setting_recommendations[2]
    assert slope.setting == "hs_compression_slope"
    assert slope.direction in {"hold", "needs_more_evidence"}


def test_slope_candidate_uses_strong_selected_context(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    slope = response.corners[0].setting_recommendations[2]
    assert slope.setting == "hs_compression_slope"
    assert slope.direction == "add"
    assert slope.delta is not None and slope.delta > 1


def test_no_shock_telemetry_returns_unavailable(tmp_path: Path) -> None:
    write_telemetry_cache("run-1", [{"lap": 1, "speed_mph": 100.0}], data_dir=tmp_path)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    assert response.corners == []
    assert response.recommendations == []
    assert any("unavailable" in warning.lower() for warning in response.warnings)


def test_setup_snapshot_missing_prevents_numeric_values(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=None, data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert rec.current_value is None
    assert rec.suggested_value is None
    assert rec.delta is None
    assert rec.blocked_reason == "setup value missing"


def test_weak_signal_stays_one_click_when_context_is_unselected(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 46) + ([-0.2] * 34))
    response = build_shock_reader_response("run-1", setup_snapshot=_setup(), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert rec.direction == "subtract"
    assert rec.delta == -1


def test_click_bounds_enforced(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(5), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert rec.current_value == 5
    assert rec.suggested_value == 2
    assert 1 <= rec.suggested_value <= 10


def test_at_limit_blocks_recommendation(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(1), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert rec.current_value == 1
    assert rec.suggested_value is None
    assert rec.delta is None
    assert rec.direction == "blocked"
    assert rec.blocked_reason == "limit"


def test_large_positive_delta_clamps_to_upper_bound(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(8), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[1]
    assert rec.setting == "hs_compression"
    assert rec.direction == "add"
    assert rec.delta == 2
    assert rec.suggested_value == 10


def test_no_full_row_materialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, [-0.8, -0.4, 0.2, 0.7] * 30)
    import polars as pl

    def _boom(*args, **kwargs):
        raise AssertionError("shock reader should use lazy scan, not read_parquet")

    monkeypatch.setattr(pl, "read_parquet", _boom)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    assert response.corners


def test_no_recommendation_says_histogram_proves_change(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    dumped = json.dumps(response.model_dump()).lower()
    assert "histogram proves" not in dumped
    assert "proves a shock" not in dumped


def test_no_recommendation_stacks_multiple_changes(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-2.1] * 30) + ([0.2] * 10), contact=True, chatter=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    assert len(response.recommendations) <= 1
