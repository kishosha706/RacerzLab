from __future__ import annotations

import pytest
import polars as pl
from pydantic import ValidationError

from racelab_engine.analysis.stint_response_migration import (
    PhysicalPhaseWindow,
    StintResponseMigrationReport,
    analyze_stint_response_migration,
)
from racelab_engine.models.lap import LapSummary


_SOURCE_SHA = "a" * 64


def _laps(count: int) -> list[LapSummary]:
    return [
        LapSummary(
            lap_id=f"run:lap:{lap}",
            run_id="run",
            lap_number=lap,
            is_complete=True,
            is_useful=True,
            lap_time=50.0,
            classification_tags=["ELIGIBLE_FLYING_LAP"],
        )
        for lap in range(1, count + 1)
    ]


def _rows(
    lap_count: int,
    *,
    duplicate_session_time: tuple[int, int] | None = None,
    setup_change_lap: int | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    tick = 0
    for lap in range(1, lap_count + 1):
        for sample in range(11):
            position = 20.0 + sample
            session_time = tick / 10.0
            if duplicate_session_time == (lap, sample):
                session_time = (tick - 1) / 10.0
            rows.append(
                {
                    "run_id": "run",
                    "lap": lap,
                    "lap_dist_pct_100": position,
                    "session_tick": tick,
                    "session_time": session_time,
                    "setup_id": (
                        "setup-b"
                        if setup_change_lap is not None and lap >= setup_change_lap
                        else "setup-a"
                    ),
                    "steering_deg": 5.0 + lap * 0.20 + sample * 0.01,
                    "yaw_rate": 0.70 - lap * 0.01 + sample * 0.001,
                    "throttle_pct": 70.0 if position >= 22.0 + lap * 0.5 else 0.0,
                    "cfs_ride_height_mm": 15.0 - lap * 0.10 + sample * 0.01,
                    "lf_ride_height_mm": 16.0 - lap * 0.08,
                    "rf_ride_height_mm": 15.5 - lap * 0.08,
                    "lr_ride_height_mm": 20.0 - lap * 0.05,
                    "rr_ride_height_mm": 19.5 - lap * 0.05,
                    "on_pit_road": False,
                    "pitstop_active": False,
                    "enter_exit_reset_state": 0,
                }
            )
            tick += 1
    return rows


def _scope() -> PhysicalPhaseWindow:
    return PhysicalPhaseWindow(
        scope_id="t3-exit",
        phase="initial_throttle",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        grid_step_pct=1.0,
        max_interpolation_gap_pct=1.5,
    )


def _report(rows, laps):
    return analyze_stint_response_migration(
        rows,
        laps=laps,
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
        expected_run_id="run",
        expected_source_file_sha256=_SOURCE_SHA,
    )


def test_long_stint_uses_qualified_ticks_and_matched_physical_positions() -> None:
    report = _report(
        _rows(10, duplicate_session_time=(5, 5)),
        _laps(10),
    )

    assert report.status == "ready"
    assert len(report.segments) == 1
    segment = report.segments[0]
    assert segment.lap_numbers == tuple(range(1, 11))
    signature = segment.phase_signatures[0]
    assert signature.physical_grid_pct == tuple(float(value) for value in range(20, 31))
    assert {item.clock_primary for item in signature.lap_responses} == {"session_tick"}
    assert {item.clock_state for item in signature.lap_responses} == {"qualified"}
    assert [item.phase_time_s for item in signature.lap_responses] == pytest.approx(
        [1.0] * 10
    )

    trends = {item.metric: item for item in signature.trends}
    assert trends["phase_time_s"].robust_slope_per_lap == pytest.approx(0.0)
    assert trends["phase_time_s"].direction == "not_established"
    assert trends["steering_demand_rms_deg"].direction == "increasing"
    assert trends["yaw_response_rms_rad_s"].direction == "decreasing"
    assert trends["throttle_pickup_position_pct"].direction == "increasing"
    assert trends["whole_platform_clearance_min_mm"].direction == "decreasing"
    assert all(item.attribution == "unresolved_observational" for item in signature.trends)
    assert all(item.setup_authorized is False for item in signature.trends)
    assert report.tire_degradation_authorized is False
    assert report.cooling_conclusion_authorized is False


def test_driver_demand_shift_does_not_warp_phase_time() -> None:
    rows = _rows(10)
    for row in rows:
        lap = int(row["lap"])
        position = float(row["lap_dist_pct_100"])
        row["steering_deg"] = 2.0 if position < 23.0 + lap * 0.4 else 8.0

    report = _report(rows, _laps(10))
    signature = report.segments[0].phase_signatures[0]
    trends = {item.metric: item for item in signature.trends}

    assert trends["steering_demand_rms_deg"].direction == "decreasing"
    assert trends["phase_time_s"].robust_slope_per_lap == pytest.approx(0.0)
    assert all(item.phase_time_s == pytest.approx(1.0) for item in signature.lap_responses)


def test_frame_and_row_inputs_have_exact_projection_parity() -> None:
    rows = _rows(10)

    assert _report(pl.DataFrame(rows), _laps(10)) == _report(rows, _laps(10))


def test_foreign_run_rows_fail_closed_before_a_ten_lap_finding() -> None:
    rows = _rows(10)
    for row in rows:
        row["run_id"] = "foreign-run"

    report = _report(rows, _laps(10))

    assert report.status == "blocked"
    assert report.segments == ()
    assert "foreign run" in " ".join(report.blocker_reasons).lower()


def test_run_labels_must_be_complete_or_have_explicit_trusted_binding() -> None:
    mixed = _rows(10)
    mixed[0].pop("run_id")
    blocked = _report(mixed, _laps(10))
    assert blocked.status == "blocked"
    assert "labeled and unlabeled run identity" in " ".join(
        blocked.blocker_reasons
    ).lower()

    unlabeled = _rows(10)
    for row in unlabeled:
        row.pop("run_id")
    assert _report(unlabeled, _laps(10)).status == "ready"

    unbound = analyze_stint_response_migration(
        unlabeled,
        laps=_laps(10),
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
        expected_source_file_sha256=_SOURCE_SHA,
    )
    assert unbound.status == "blocked"
    assert "caller-owned run identity" in " ".join(unbound.blocker_reasons).lower()


def test_recording_sha_must_match_caller_owned_identity_when_rows_are_labeled() -> None:
    source_sha = _SOURCE_SHA
    foreign_sha = "b" * 64
    rows = _rows(10)
    for row in rows:
        row["source_file_sha256"] = source_sha

    matched = analyze_stint_response_migration(
        rows,
        laps=_laps(10),
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
        expected_source_file_sha256=source_sha,
    )
    mismatched = analyze_stint_response_migration(
        rows,
        laps=_laps(10),
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
        expected_source_file_sha256=foreign_sha,
    )
    partially_labeled = [dict(row) for row in rows]
    partially_labeled[0].pop("source_file_sha256")
    partial = analyze_stint_response_migration(
        partially_labeled,
        laps=_laps(10),
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
        expected_source_file_sha256=source_sha,
    )
    unlabeled = _rows(10)
    caller_bound = analyze_stint_response_migration(
        unlabeled,
        laps=_laps(10),
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
        expected_source_file_sha256=source_sha,
    )
    unbound_recording = analyze_stint_response_migration(
        _rows(10),
        laps=_laps(10),
        phase_windows=(_scope(),),
        expected_sample_rate_hz=10.0,
    )

    assert matched.status == "ready"
    assert matched.source_file_sha256 == source_sha
    assert matched.segments[0].source_file_sha256 == source_sha
    assert mismatched.status == "blocked"
    assert mismatched.segments == ()
    assert "caller-owned recording" in " ".join(mismatched.blocker_reasons).lower()
    assert partial.status == "blocked"
    assert "labeled and unlabeled recording identity" in " ".join(
        partial.blocker_reasons
    ).lower()
    assert caller_bound.status == "ready"
    assert caller_bound.source_file_sha256 == source_sha
    assert unbound_recording.status == "blocked"
    assert unbound_recording.segments == ()
    assert "caller-owned recording sha-256" in " ".join(
        unbound_recording.blocker_reasons
    ).lower()


def test_invalid_pit_lap_splits_history_and_tire_values_stay_pit_snapshots() -> None:
    rows = _rows(12)
    pit_rows = [row for row in rows if row["lap"] == 6]
    for row in pit_rows:
        row["on_pit_road"] = True
        for index, corner in enumerate(("lf", "rf", "lr", "rr"), start=1):
            row[f"{corner}_tires_used"] = float(index)
            row[f"{corner}_tires_available"] = float(10 - index)
            row[f"{corner}_carcass_temp_m"] = 80.0 + index
            row[f"{corner}_wear_middle"] = 0.95 - index * 0.01
    laps = _laps(12)
    laps[5] = laps[5].model_copy(
        update={"is_useful": False, "classification_tags": ["PIT_ROAD"]}
    )

    report = _report(rows, laps)

    assert report.status == "limited"
    assert [segment.lap_numbers for segment in report.segments] == [
        tuple(range(1, 6)),
        tuple(range(7, 13)),
    ]
    assert all(
        trend.state != "observed"
        for segment in report.segments
        for signature in segment.phase_signatures
        for trend in signature.trends
    )
    assert len(report.pit_tire_snapshots) == 2
    assert {item.boundary for item in report.pit_tire_snapshots} == {"pit_entry", "pit_exit"}
    for snapshot in report.pit_tire_snapshots:
        assert snapshot.authority == "inventory_snapshot_only"
        assert all(corner.update_semantic == "pit_snapshot" for corner in snapshot.corners)
        assert all(corner.continuous_on_track_authorized is False for corner in snapshot.corners)
        assert all(corner.mechanism_authorized is False for corner in snapshot.corners)
    assert "lf_carcass_temp_m" not in report.source_channels
    assert "lf_wear_middle" not in report.source_channels


def test_same_setup_change_and_reset_epoch_cannot_be_pooled() -> None:
    setup_rows = _rows(12, setup_change_lap=7)
    setup_report = _report(setup_rows, _laps(12))
    assert [segment.lap_numbers for segment in setup_report.segments] == [
        tuple(range(1, 7)),
        tuple(range(7, 13)),
    ]
    assert setup_report.status == "limited"

    reset_rows = _rows(12)
    reset_index = next(
        index
        for index, row in enumerate(reset_rows)
        if row["lap"] == 7 and row["lap_dist_pct_100"] == 20.0
    )
    tick_offset = int(reset_rows[reset_index]["session_tick"])
    time_offset = float(reset_rows[reset_index]["session_time"])
    for row in reset_rows[reset_index:]:
        row["session_tick"] = int(row["session_tick"]) - tick_offset
        row["session_time"] = float(row["session_time"]) - time_offset
    reset_report = _report(reset_rows, _laps(12))
    assert [segment.lap_numbers for segment in reset_report.segments] == [
        tuple(range(1, 7)),
        tuple(range(7, 13)),
    ]
    assert {segment.clock_epoch for segment in reset_report.segments} == {0, 1}


def test_tick_discontinuity_blocks_the_affected_lap_without_bridging() -> None:
    rows = _rows(12)
    first = next(
        index
        for index, row in enumerate(rows)
        if row["lap"] == 6 and row["lap_dist_pct_100"] == 25.0
    )
    for row in rows[first:]:
        row["session_tick"] = int(row["session_tick"]) + 1

    report = _report(rows, _laps(12))

    assert [segment.lap_numbers for segment in report.segments] == [
        tuple(range(1, 6)),
        tuple(range(7, 13)),
    ]
    assert "qualified telemetry clock" in " ".join(report.blocker_reasons).lower()
    assert all(segment.status == "limited" for segment in report.segments)


def test_ready_segment_cannot_hide_a_skipped_boundary_lap() -> None:
    laps = _laps(11)
    laps[-1] = laps[-1].model_copy(
        update={"is_useful": False, "classification_tags": ["PIT_ROAD"]}
    )
    rows = _rows(11)
    for row in rows:
        if row["lap"] == 11:
            row["on_pit_road"] = True

    report = _report(rows, laps)

    assert report.segments[0].status == "ready"
    assert report.segments[0].lap_numbers == tuple(range(1, 11))
    assert report.status == "limited"
    assert "not canonically eligible" in " ".join(report.blocker_reasons).lower()


def test_short_run_exposes_measurements_but_withholds_progression_and_cause() -> None:
    report = _report(_rows(4), _laps(4))

    assert report.status == "limited"
    signature = report.segments[0].phase_signatures[0]
    assert len(signature.lap_responses) == 4
    assert all(trend.state in {"blocked", "unavailable"} for trend in signature.trends)
    assert all(trend.robust_slope_per_lap is None for trend in signature.trends)
    assert "short runs cannot support tire degradation" in " ".join(
        reason for trend in signature.trends for reason in trend.blocker_reasons
    ).lower()
    serialized = report.model_dump()
    assert serialized["setup_authorized"] is False
    assert serialized["component_cause_authorized"] is False


def test_on_track_tire_values_never_create_a_pit_snapshot() -> None:
    rows = _rows(10)
    for row in rows:
        row["lf_tires_used"] = 3.0
        row["lf_carcass_temp_m"] = 92.0
        row["lf_wear_middle"] = 0.91

    report = _report(rows, _laps(10))

    assert report.pit_tire_snapshots == ()
    assert "lf_tires_used" not in report.source_channels
    assert "lf_carcass_temp_m" not in report.source_channels


def test_contract_rejects_setup_authority_smuggling() -> None:
    report = _report(_rows(10), _laps(10))
    payload = report.model_dump()
    payload["setup_authorized"] = True

    with pytest.raises(ValidationError):
        StintResponseMigrationReport.model_validate(payload)
