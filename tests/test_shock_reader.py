from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from racelab_engine.analysis.shock_reader import (
    build_shock_reader_response as _build_shock_reader_response,
    compute_corner_read,
)
from racelab_engine.analysis.setup_controls import (
    resolve_adjacent_setup_target,
    setup_control_spec,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import (
    TelemetryArtifactIdentityError,
    parquet_path,
    write_telemetry_cache,
)


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


def _rows(
    values: list[float],
    *,
    contact: bool = False,
    chatter: bool = False,
    laps: int = 1,
    zone: tuple[float, float] | None = None,
) -> list[dict]:
    rows = []
    for lap_number in range(1, laps + 1):
        for idx, value in enumerate(values):
            rows.append(
                {
                "lap": lap_number,
                "session_time": ((lap_number - 1) * (len(values) + 60) + idx) / 60,
                "lap_dist_pct": (
                    zone[0] + (zone[1] - zone[0]) * idx / max(len(values) - 1, 1)
                    if zone is not None
                    else idx / max(len(values) - 1, 1)
                ),
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


def test_shock_reader_rejects_cache_relabelled_from_another_run(tmp_path: Path) -> None:
    _write(tmp_path, [0.2, -0.2] * 40)
    write_telemetry_cache(
        "run-2",
        _rows([3.0, -3.0] * 40),
        data_dir=tmp_path,
    )
    shutil.copyfile(
        parquet_path(tmp_path, "run-2"),
        parquet_path(tmp_path, "run-1"),
    )

    with pytest.raises(TelemetryArtifactIdentityError, match="does not match"):
        build_shock_reader_response("run-1", data_dir=tmp_path)


def _lap_summary(*, useful: bool, tags: list[str] | None = None, lap_number: int = 1) -> LapSummary:
    return LapSummary(
        lap_id=f"run-1:lap:{lap_number}",
        run_id="run-1",
        lap_number=lap_number,
        lap_type="timed" if useful else "complete_invalid",
        is_complete=True,
        is_useful=useful,
        lap_time=30.0,
        sample_count=120,
        classification_tags=tags or [],
    )


def build_shock_reader_response(*args, **kwargs):
    kwargs.setdefault("lap_summaries", [_lap_summary(useful=True)])
    return _build_shock_reader_response(*args, **kwargs)


_INLINE_SHOCK_SETTINGS = (
    "ls_compression",
    "hs_compression",
    "hs_compression_slope",
    "ls_rebound",
    "hs_rebound",
    "hs_rebound_slope",
)


def _qualified_legal_options(value: int = 5) -> dict[str, object]:
    values = (value - 1, value, value + 1)
    return {
        "legal_options_by_corner_setting": {
            corner: {setting: list(values) for setting in _INLINE_SHOCK_SETTINGS}
            for corner in ("LF", "RF", "LR", "RR")
        },
        "legal_option_provenance_by_corner_setting": {
            corner: {
                setting: {
                    option: [f"tech-passing-setup:{corner}:{setting}:{option}"]
                    for option in values
                }
                for setting in _INLINE_SHOCK_SETTINGS
            }
            for corner in ("LF", "RF", "LR", "RR")
        },
    }


def _single_row_options(
    values: list[int],
    provenance: dict[int, list[str]],
) -> dict[str, object]:
    return {
        "legal_options_by_corner_setting": {"LF": {"ls_compression": values}},
        "legal_option_provenance_by_corner_setting": {
            "LF": {"ls_compression": provenance},
        },
    }


def _assert_action_is_fully_withheld(recommendation) -> None:
    dumped = " ".join(
        str(value)
        for value in (
            recommendation.action_text,
            recommendation.expected_effect,
            recommendation.change_size_explanation,
            recommendation.keep_if,
            recommendation.undo_if,
        )
    ).lower()
    assert recommendation.delta is None
    assert recommendation.suggested_value is None
    assert recommendation.direction == "needs_more_evidence"
    assert recommendation.magnitude == "hold"
    assert not any(token in dumped for token in ("increase ", "decrease ", "one click", "one available click"))


@pytest.mark.parametrize("setting", _INLINE_SHOCK_SETTINGS)
@pytest.mark.parametrize(("direction_sign", "expected"), [(-1, 4), (1, 6)])
def test_every_shock_row_resolves_the_exact_one_click_garage_direction(
    setting: str,
    direction_sign: int,
    expected: int,
) -> None:
    resolution = resolve_adjacent_setup_target(
        setting,
        5,
        direction_sign,
        legal_values=[4, 5, 6],
        legal_value_provenance={
            4: [f"tech-passing-setup:{setting}:4"],
            6: [f"tech-passing-setup:{setting}:6"],
        },
    )

    assert resolution.ready is True
    assert resolution.target_value == expected
    assert resolution.provenance == (f"tech-passing-setup:{setting}:{expected}",)
    spec = setup_control_spec(setting)
    assert spec.nominal_test_increment == 1.0
    if setting.endswith("_slope"):
        expected_shape = "more linear" if direction_sign > 0 else "more digressive"
        effect = spec.increase_effect if direction_sign > 0 else spec.decrease_effect
        assert expected_shape in effect
    else:
        expected_strength = "adds" if direction_sign > 0 else "removes"
        effect = spec.increase_effect if direction_sign > 0 else spec.decrease_effect
        assert expected_strength in effect


def test_selected_pit_lap_keeps_observations_but_suppresses_exact_actions(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 20) + ([1.4] * 10))
    response = build_shock_reader_response(
        "run-1",
        lap=1,
        setup_snapshot=_setup(),
        lap_summaries=[_lap_summary(useful=False, tags=["PIT_ROAD", "NO_SETUP_CONCLUSION"])],
        data_dir=tmp_path,
    )

    assert response.corners and response.corners[0].sample_count > 0
    assert response.recommendations == []
    assert all(
        recommendation.delta is None
        and recommendation.suggested_value is None
        and recommendation.direction == "needs_more_evidence"
        and recommendation.evidence_state == "blocked_by_context"
        and bool(recommendation.blocker_reasons)
        for corner in response.corners
        for recommendation in corner.setting_recommendations
    )
    for corner in response.corners:
        for recommendation in corner.setting_recommendations:
            _assert_action_is_fully_withheld(recommendation)
    assert response.evidence_state == "blocked_by_context"
    assert response.blocker_reasons
    assert any("exact setting actions are suppressed" in warning for warning in response.warnings)


def test_no_eligible_laps_suppresses_all_run_shock_actions(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response(
        "run-1",
        setup_snapshot=_setup(),
        lap_summaries=[],
        data_dir=tmp_path,
    )

    assert response.corners
    assert response.recommendations == []
    for corner in response.corners:
        for recommendation in corner.setting_recommendations:
            _assert_action_is_fully_withheld(recommendation)


def test_missing_lap_eligibility_context_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))

    response = _build_shock_reader_response(
        "run-1",
        lap=1,
        setup_snapshot=_setup(),
        data_dir=tmp_path,
    )

    assert response.corners
    assert response.recommendations == []
    for corner in response.corners:
        for recommendation in corner.setting_recommendations:
            _assert_action_is_fully_withheld(recommendation)
    assert any("eligibility is unavailable" in warning for warning in response.warnings)


def test_balanced_histogram_returns_leave_alone(tmp_path: Path) -> None:
    _write(tmp_path, [-0.8, -0.4, 0.2, 0.7] * 30)
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
        **_qualified_legal_options(),
    )
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


def test_strong_low_speed_bump_signal_stays_one_adjacent_click(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 20) + ([1.4] * 10))
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
        **_qualified_legal_options(),
    )
    rec = response.corners[0].setting_recommendations[0]
    assert response.corners[0].pattern == "low_speed_bump_heavy"
    assert rec.setting == "ls_compression"
    assert rec.direction == "subtract"
    assert rec.delta == -1
    assert rec.current_value is not None
    assert rec.suggested_value == 4
    assert rec.target_value_raw == 4
    assert rec.legal_option_provenance == ["tech-passing-setup:LF:ls_compression:4"]


def test_low_speed_rebound_heavy_returns_subtract_ls_rebound(tmp_path: Path) -> None:
    _write(tmp_path, ([-0.2] * 70) + ([0.2] * 20) + ([-1.4] * 10))
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
        **_qualified_legal_options(),
    )
    rec = response.corners[0].setting_recommendations[3]
    assert response.corners[0].pattern == "low_speed_rebound_heavy"
    assert rec.setting == "ls_rebound"
    assert rec.direction == "subtract"
    assert rec.suggested_value == 4


def test_excessive_high_speed_shoulders_no_contact_returns_soften_candidate(tmp_path: Path) -> None:
    _write(tmp_path, ([2.2] * 35) + ([-2.1] * 35) + ([0.2] * 30), chatter=True)
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
        **_qualified_legal_options(),
    )
    rec = response.recommendations[0]
    assert response.corners[0].pattern == "excessive_high_speed_shoulders"
    assert rec.semantic_direction == "leave_alone"
    assert all(
        slope.direction == "needs_more_evidence"
        for corner in response.corners
        for slope in corner.setting_recommendations
        if slope.setting in {"hs_compression_slope", "hs_rebound_slope"}
    )


def test_high_speed_bump_contact_returns_add_hs_or_linear_slope(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
        **_qualified_legal_options(),
    )
    rec = response.recommendations[0]
    assert response.corners[0].pattern == "high_speed_bump_heavy"
    assert rec.setting == "hs_compression"
    assert rec.semantic_direction == "add"
    assert rec.suggested_value == 6
    assert rec.target_value_raw == 6
    assert rec.legal_option_provenance == ["tech-passing-setup:LF:hs_compression:6"]


def test_slope_candidate_requires_selected_platform_context(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response("run-1", setup_snapshot=_setup(), data_dir=tmp_path)
    slope = response.corners[0].setting_recommendations[2]
    assert slope.setting == "hs_compression_slope"
    assert slope.direction in {"hold", "needs_more_evidence"}


def test_selected_zone_still_requires_two_continuous_laps(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20),
        contact=True,
        zone=(0.20, 0.30),
    )
    response = build_shock_reader_response(
        "run-1",
        lap=1,
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        boundary_basis="Verified test fixture boundary.",
        slope_boundary_verified=True,
        setup_snapshot=_setup(),
        data_dir=tmp_path,
    )

    slope = response.corners[0].setting_recommendations[2]
    assert slope.direction == "needs_more_evidence"
    assert "at least two eligible laps" in (slope.blocked_reason or "")


def test_unverified_car_boundary_withholds_slope_action(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20),
        contact=True,
        laps=2,
        zone=(0.20, 0.30),
    )
    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        setup_snapshot=_setup(),
        **_qualified_legal_options(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.slope_actions_available is False
    slope = response.corners[0].setting_recommendations[2]
    assert slope.direction == "needs_more_evidence"
    assert "verified high-speed transition boundary" in (slope.blocked_reason or "")


def test_rear_contact_cannot_authorize_front_slope_change(tmp_path: Path) -> None:
    rows = _rows(
        ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20),
        contact=True,
        laps=2,
        zone=(0.20, 0.30),
    )
    for row in rows:
        row["cfs_ride_height_in"] = 1.5
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        boundary_basis="Verified test fixture boundary.",
        slope_boundary_verified=True,
        setup_snapshot=_setup(),
        **_qualified_legal_options(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    front_slope = response.corners[0].setting_recommendations[2]
    rear_slope = response.corners[2].setting_recommendations[2]
    assert front_slope.direction == "needs_more_evidence"
    assert "LF axle" in (front_slope.blocked_reason or "")
    assert rear_slope.direction == "add"


def test_selected_zone_fails_closed_without_lap_position(tmp_path: Path) -> None:
    rows = _rows(([2.4] * 80) + ([-0.3] * 20), contact=True, laps=2)
    for row in rows:
        row.pop("lap_dist_pct")
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        slope_boundary_verified=True,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.corners == []
    assert response.slope_actions_available is False
    assert any("full-lap data was not substituted" in warning for warning in response.warnings)


@pytest.mark.parametrize(
    "selection",
    [
        {"lap": 1},
        {"lap_window": (1, 2)},
    ],
    ids=("lap", "lap-window"),
)
def test_explicit_lap_scope_fails_closed_without_lap_identity(
    tmp_path: Path,
    selection: dict[str, object],
) -> None:
    rows = _rows(([0.2] * 70) + ([-0.2] * 30), laps=2)
    for row in rows:
        row.pop("lap")
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        **selection,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.evidence_state == "unavailable"
    assert response.corners == []
    assert response.recommendations == []
    assert any("lap identity telemetry is missing" in warning for warning in response.warnings)
    assert any("full-run data was not substituted" in warning for warning in response.warnings)


@pytest.mark.parametrize(
    ("phase", "missing_channels"),
    [
        ("braking", ("brake_pct",)),
        ("entry", ("abs_steering_deg", "steering_deg")),
        ("exit", ("throttle_pct",)),
        ("straight", ("throttle_pct",)),
    ],
)
def test_explicit_phase_fails_closed_without_selector_channels(
    tmp_path: Path,
    phase: str,
    missing_channels: tuple[str, ...],
) -> None:
    rows = _rows(([0.2] * 70) + ([-0.2] * 30))
    for row in rows:
        for channel in missing_channels:
            row.pop(channel, None)
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1", lap=1, phase=phase, setup_snapshot=_setup(), data_dir=tmp_path,
    )

    assert response.evidence_state == "unavailable"
    assert response.corners == []
    assert response.recommendations == []
    assert any("selector telemetry is missing" in warning for warning in response.warnings)
    assert any("unfiltered data was not substituted" in warning for warning in response.warnings)


def test_shock_recommendation_provenance_names_only_archived_channels(tmp_path: Path) -> None:
    rows = _rows(([0.2] * 70) + ([-0.2] * 30))
    for row in rows:
        row.pop("lap_dist_pct")
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
        **_qualified_legal_options(),
    )

    archived = set(rows[0])
    actionable = [
        recommendation
        for corner in response.corners
        for recommendation in corner.setting_recommendations
        if recommendation.direction in {"add", "subtract"}
    ]
    assert actionable
    assert all(set(recommendation.source_channels) <= archived for recommendation in actionable)
    assert all("lap_dist_pct" not in recommendation.source_channels for recommendation in actionable)


def test_boundary_stability_must_hold_on_each_lap_not_the_pooled_window(tmp_path: Path) -> None:
    lap_one = _rows(([1.6] * 80) + ([-0.3] * 20), contact=True, zone=(0.20, 0.30))
    lap_two = _rows(([2.4] * 80) + ([-0.3] * 20), contact=True, zone=(0.20, 0.30))
    for row in lap_two:
        row["lap"] = 2
        row["session_time"] += 3.0
    write_telemetry_cache("run-1", [*lap_one, *lap_two], data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        boundary_basis="Verified test fixture boundary.",
        slope_boundary_verified=True,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    corner = response.corners[0]
    slope = corner.setting_recommendations[2]
    assert corner.compression_boundary_stable is False
    assert any(item == "L1@1.25:neutral" for item in corner.boundary_sensitivity_patterns)
    assert slope.direction == "needs_more_evidence"


def test_sparse_one_hz_samples_cannot_unlock_slope(tmp_path: Path) -> None:
    rows = _rows(([2.4] * 80) + ([-0.3] * 20), contact=True, laps=2, zone=(0.20, 0.30))
    for index, row in enumerate(rows):
        row["session_time"] = float(index)
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        slope_boundary_verified=True,
        expected_sample_rate_hz=60.0,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.corners[0].repeatability_lap_count == 0
    assert response.corners[0].setting_recommendations[2].direction == "needs_more_evidence"


def test_short_dense_burst_cannot_masquerade_as_full_zone_coverage(tmp_path: Path) -> None:
    rows = _rows(([2.4] * 600), contact=True, laps=2, zone=(0.20, 0.30))
    for lap_number in (1, 2):
        lap_rows = [row for row in rows if row["lap"] == lap_number]
        for row in lap_rows[64:]:
            for corner in ("lf", "rf", "lr", "rr"):
                row[f"{corner}_shock_vel_in_s"] = None
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        slope_boundary_verified=True,
        expected_sample_rate_hz=60.0,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.corners[0].repeatability_lap_count == 0
    assert response.slope_actions_available is False


def test_missing_clock_and_shock_tail_cannot_shrink_the_coverage_denominator(tmp_path: Path) -> None:
    rows = _rows(([2.4] * 600), contact=True, laps=2, zone=(0.20, 0.30))
    for lap_number in (1, 2):
        lap_rows = [row for row in rows if row["lap"] == lap_number]
        for row in lap_rows[64:]:
            row["session_time"] = None
            for corner in ("lf", "rf", "lr", "rr"):
                row[f"{corner}_shock_vel_in_s"] = None
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        slope_boundary_verified=True,
        expected_sample_rate_hz=60.0,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.corners[0].repeatability_lap_count == 0
    assert response.slope_actions_available is False


def test_rear_contact_cannot_boost_front_low_speed_action(tmp_path: Path) -> None:
    rows = _rows(([-0.2] * 70) + ([0.2] * 20) + ([-1.4] * 10), contact=True)
    for row in rows:
        row["cfs_ride_height_in"] = 1.5
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)

    lf_ls_compression = response.corners[0].setting_recommendations[0]
    assert lf_ls_compression.direction not in {"add", "subtract"}


def test_only_one_inline_shock_action_survives_with_exact_sourced_target(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(9), data_dir=tmp_path,
        **_qualified_legal_options(9),
    )

    actionable = [
        recommendation
        for corner in response.corners
        for recommendation in corner.setting_recommendations
        if recommendation.direction in {"add", "subtract"}
    ]
    assert len(actionable) == 1
    assert actionable[0].delta in {-1, 1}
    assert actionable[0].suggested_value == 10
    assert actionable[0].target_value_raw == 10
    assert actionable[0].legal_option_provenance


def test_slope_availability_requires_an_actionable_row_not_only_context(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20),
        contact=True,
        laps=2,
        zone=(0.20, 0.30),
    )
    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        slope_boundary_verified=True,
        setup_snapshot=None,
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert response.slope_actions_available is False
    assert all(
        recommendation.direction not in {"add", "subtract"}
        for corner in response.corners
        for recommendation in corner.setting_recommendations
        if recommendation.setting in {"hs_compression_slope", "hs_rebound_slope"}
    )


def test_slope_candidate_uses_strong_selected_context(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20),
        contact=True,
        laps=2,
        zone=(0.20, 0.30),
    )
    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20,
        zone_end_pct=30,
        boundary_in_s=1.5,
        boundary_basis="Verified test fixture boundary.",
        slope_boundary_verified=True,
        setup_snapshot=_setup(),
        **_qualified_legal_options(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )
    slope = response.corners[0].setting_recommendations[2]
    assert slope.setting == "hs_compression_slope"
    assert slope.direction == "add"
    assert slope.delta == 1
    assert slope.suggested_value == 6
    assert slope.target_value_raw == 6
    assert slope.legal_option_provenance == ["tech-passing-setup:LF:hs_compression_slope:6"]
    assert slope.action_text == (
        "Increase compression slope from 5 to 6 toward a more linear curve."
    )
    assert slope.change_size_explanation.startswith("One adjacent slope option is a small control input")
    assert response.corners[0].repeatability_lap_count == 2
    assert response.corners[0].high_speed_compression_repeatable is True
    assert response.corners[0].compression_boundary_stable is True


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
    assert rec.direction == "needs_more_evidence"
    assert rec.delta is None


def test_click_action_fails_closed_without_a_sourced_adjacent_legal_option(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(5), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert rec.current_value == 5
    _assert_action_is_fully_withheld(rec)
    assert "option" in (rec.blocked_reason or "").lower()
    assert "source" in (rec.blocked_reason or "").lower()


def test_adjacent_option_requires_provenance_for_that_exact_target(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response(
        "run-1",
        lap=1,
        setup_snapshot=_setup(5),
        data_dir=tmp_path,
        **_single_row_options([4, 5], {5: ["tech-passing-setup:current-only"]}),
    )

    rec = response.corners[0].setting_recommendations[0]
    _assert_action_is_fully_withheld(rec)
    assert rec.target_value_raw is None
    assert rec.legal_option_provenance == []
    assert "no observed or configured source provenance" in (rec.blocked_reason or "")


def test_sparse_far_only_shock_option_cannot_authorize_multi_click_jump(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response(
        "run-1",
        lap=1,
        setup_snapshot=_setup(5),
        data_dir=tmp_path,
        **_single_row_options([2, 5], {2: ["tech-passing-setup:far-option"]}),
    )

    rec = response.corners[0].setting_recommendations[0]
    _assert_action_is_fully_withheld(rec)
    assert rec.target_value_raw is None
    assert rec.legal_option_provenance == []
    assert "smallest controlled increment" in (rec.blocked_reason or "")


def test_exact_adjacent_shock_target_and_only_its_provenance_are_preserved(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response(
        "run-1",
        lap=1,
        setup_snapshot=_setup(5),
        data_dir=tmp_path,
        **_single_row_options(
            [4, 5],
            {
                4: ["tech-passing-setup:exact-target"],
                5: ["tech-passing-setup:current-value"],
            },
        ),
    )

    rec = response.corners[0].setting_recommendations[0]
    assert rec.direction == "subtract"
    assert rec.delta == -1
    assert rec.suggested_value == 4
    assert rec.target_value_raw == 4
    assert rec.legal_option_provenance == ["tech-passing-setup:exact-target"]
    assert response.recommendations[0].target_value_raw == 4
    assert response.recommendations[0].legal_option_provenance == [
        "tech-passing-setup:exact-target"
    ]


def test_unknown_legal_range_cannot_authorize_a_direction_only_click(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(1), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[0]
    assert rec.current_value == 1
    _assert_action_is_fully_withheld(rec)


def test_high_speed_action_fails_closed_without_sourced_upper_option(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(8), data_dir=tmp_path)
    rec = response.corners[0].setting_recommendations[1]
    assert rec.setting == "hs_compression"
    _assert_action_is_fully_withheld(rec)


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


def test_corner_read_ignores_nan_and_infinity_without_fake_samples() -> None:
    read = compute_corner_read("LF", [float("nan"), float("inf"), -float("inf"), 0.2] * 10)

    assert read.pattern == "insufficient_evidence"
    assert read.sample_count == 10
    assert read.rms_in_s is None


def test_boundary_zero_falls_back_to_minimum_positive_gate() -> None:
    read = compute_corner_read("LF", [-0.02, -0.005, 0.0, 0.005, 0.02] * 16, boundary_in_s=0.0)

    assert read.sample_count == 80
    assert read.rebound_hi_pct > 0
    assert read.bump_hi_pct > 0


def test_zero_velocity_is_deadband_not_compression_and_boundaries_are_high_speed() -> None:
    read = compute_corner_read("LF", [-1.0, -0.5, 0.0, 0.5, 1.0] * 16, boundary_in_s=1.0)

    assert read.center_pct == pytest.approx(20.0)
    assert read.rebound_hi_pct == pytest.approx(25.0)
    assert read.rebound_lo_pct == pytest.approx(25.0)
    assert read.bump_lo_pct == pytest.approx(25.0)
    assert read.bump_hi_pct == pytest.approx(25.0)


def test_invalid_boundary_input_uses_default_boundary_in_response(tmp_path: Path) -> None:
    _write(tmp_path, [-0.8, -0.4, 0.2, 0.7] * 30)

    response = build_shock_reader_response(
        "run-1",
        lap=1,
        boundary_in_s=float("nan"),
        setup_snapshot=_setup(),
        data_dir=tmp_path,
    )

    assert response.boundary_in_s == 1.0
    assert response.corners
