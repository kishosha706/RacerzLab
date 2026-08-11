from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.shock_reader import (
    build_shock_reader_response as _build_shock_reader_response,
    compute_corner_read,
)
from racelab_engine.analysis.shock_reader_schema import ShockCornerRead
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


def test_corner_contract_rejects_deprecated_action_fields() -> None:
    base = compute_corner_read("LF", [0.2, -0.2] * 40).model_dump()
    hostile_payloads = [
        {**base, "suggested_value": 4, "action_text": "Lower the setting one click."},
        {**base, "setup_values": {"suggested_value": 4}},
    ]

    for payload in hostile_payloads:
        with pytest.raises(ValidationError, match="suggested_value|action_text"):
            ShockCornerRead.model_validate(payload)


def _assert_observation_only(response) -> None:
    payload = response.model_dump(mode="json")
    serialized = json.dumps(payload).casefold()
    assert response.setup_authority == "withheld"
    assert "recommendations" not in payload
    assert "setting_recommendations" not in serialized
    assert "shock tuning" not in serialized
    assert "exact setting actions" not in serialized
    for forbidden in (
        "suggested_value",
        "target_value_raw",
        "action_text",
        "keep_if",
        "undo_if",
        "numeric_step",
    ):
        assert forbidden not in serialized


def test_selected_pit_lap_retains_only_a_blocked_observation(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 20) + ([1.4] * 10))
    response = build_shock_reader_response(
        "run-1",
        lap=1,
        setup_snapshot=_setup(),
        lap_summaries=[_lap_summary(useful=False, tags=["PIT_ROAD", "NO_SETUP_CONCLUSION"])],
        data_dir=tmp_path,
    )

    assert response.corners and response.corners[0].sample_count > 0
    assert response.evidence_state.value == "blocked_by_context"
    assert any("pit road" in warning.casefold() for warning in response.warnings)
    _assert_observation_only(response)


def test_no_eligible_laps_and_missing_eligibility_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    no_laps = build_shock_reader_response(
        "run-1", setup_snapshot=_setup(), lap_summaries=[], data_dir=tmp_path,
    )
    missing_gate = _build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
    )

    for response in (no_laps, missing_gate):
        assert response.corners
        assert response.evidence_state.value == "blocked_by_context"
        assert response.blocker_reasons
        _assert_observation_only(response)


def test_balanced_and_high_speed_patterns_remain_observations(tmp_path: Path) -> None:
    _write(tmp_path, [-0.8, -0.4, 0.2, 0.7] * 30)
    balanced = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
    )
    assert {corner.pattern for corner in balanced.corners} == {"balanced"}
    _assert_observation_only(balanced)

    _write(tmp_path, ([2.4] * 60) + ([-0.3] * 20) + ([0.2] * 20), contact=True)
    contact = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
    )
    assert {corner.pattern for corner in contact.corners} == {"high_speed_bump_heavy"}
    _assert_observation_only(contact)


def test_all_corners_expose_current_setup_context_without_targets(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 20) + ([1.4] * 10))
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
    )

    assert [corner.corner for corner in response.corners] == ["LF", "RF", "LR", "RR"]
    assert all(set(corner.setup_values) == set(_INLINE_SHOCK_SETTINGS) for corner in response.corners)
    assert all(set(corner.setup_values.values()) == {5} for corner in response.corners)
    _assert_observation_only(response)


def test_selected_zone_fails_closed_without_lap_position(tmp_path: Path) -> None:
    rows = _rows([0.2, -0.2] * 40)
    for row in rows:
        row.pop("lap_dist_pct", None)
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1",
        lap=1,
        zone_start_pct=20.0,
        zone_end_pct=30.0,
        setup_snapshot=_setup(),
        data_dir=tmp_path,
    )

    assert response.corners == []
    assert response.evidence_state.value == "unavailable"
    assert any("lap-position" in warning for warning in response.warnings)
    _assert_observation_only(response)


@pytest.mark.parametrize(
    ("phase", "missing_channels"),
    [
        ("braking", {"brake_pct"}),
        ("entry", {"abs_steering_deg"}),
        ("exit", {"throttle_pct"}),
        ("straight", {"abs_steering_deg", "throttle_pct"}),
    ],
)
def test_explicit_phase_fails_closed_without_selector_channels(
    tmp_path: Path,
    phase: str,
    missing_channels: set[str],
) -> None:
    rows = _rows([0.2, -0.2] * 40)
    for row in rows:
        for channel in missing_channels:
            row.pop(channel, None)
    write_telemetry_cache("run-1", rows, data_dir=tmp_path)

    response = build_shock_reader_response(
        "run-1", lap=1, phase=phase, setup_snapshot=_setup(), data_dir=tmp_path,
    )

    assert response.corners == []
    assert any("selector telemetry" in warning for warning in response.warnings)
    _assert_observation_only(response)


def test_multilap_boundary_stability_is_reported_without_slope_authority(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ([2.0] * 40) + ([-2.0] * 40) + ([0.2] * 20),
        contact=True,
        laps=2,
        zone=(0.2, 0.3),
    )
    response = build_shock_reader_response(
        "run-1",
        lap_window=(1, 2),
        zone_start_pct=20.0,
        zone_end_pct=30.0,
        boundary_in_s=1.5,
        setup_snapshot=_setup(),
        lap_summaries=[
            _lap_summary(useful=True, lap_number=1),
            _lap_summary(useful=True, lap_number=2),
        ],
        data_dir=tmp_path,
    )

    assert all(corner.repeatability_lap_count == 2 for corner in response.corners)
    assert all(corner.boundary_sensitivity_patterns for corner in response.corners)
    _assert_observation_only(response)


def test_no_shock_telemetry_returns_unavailable(tmp_path: Path) -> None:
    write_telemetry_cache("run-1", [{"lap": 1, "speed_mph": 100.0}], data_dir=tmp_path)
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path,
    )

    assert response.corners == []
    assert response.evidence_state.value == "unavailable"
    _assert_observation_only(response)


def test_missing_setup_retains_motion_but_no_setup_values(tmp_path: Path) -> None:
    _write(tmp_path, [0.2, -0.2] * 40)
    response = build_shock_reader_response(
        "run-1", lap=1, setup_snapshot=None, data_dir=tmp_path,
    )

    assert response.corners
    assert response.setup_snapshot_available is False
    assert all(all(value is None for value in corner.setup_values.values()) for corner in response.corners)
    _assert_observation_only(response)


def test_no_full_row_materialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, [-0.8, -0.4, 0.2, 0.7] * 30)
    import polars as pl

    def _boom(*args, **kwargs):
        raise AssertionError("shock reader should use lazy scan, not read_parquet")

    monkeypatch.setattr(pl, "read_parquet", _boom)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    assert response.corners


def test_histogram_never_claims_a_proven_setup_change(tmp_path: Path) -> None:
    _write(tmp_path, ([0.2] * 70) + ([-0.2] * 30))
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    dumped = json.dumps(response.model_dump()).lower()
    assert "histogram proves" not in dumped
    assert "proves a shock" not in dumped


def test_complex_histogram_still_has_no_setup_authority(tmp_path: Path) -> None:
    _write(tmp_path, ([2.4] * 60) + ([-2.1] * 30) + ([0.2] * 10), contact=True, chatter=True)
    response = build_shock_reader_response("run-1", lap=1, setup_snapshot=_setup(), data_dir=tmp_path)
    _assert_observation_only(response)


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
