from __future__ import annotations

import polars as pl

from racelab_engine.analysis.lap_detection import detect_laps
from racelab_engine.analysis.lap_classification import classify_laps


def _lap_row(lap: object, pct: float, time: float, speed: float = 120.0) -> dict[str, object]:
    return {
        "lap": lap,
        "lap_dist_pct": pct,
        "session_time": time,
        "speed_mph": speed,
        "rpm": 7000,
        "throttle_pct": 95.0,
        "brake_pct": 0.0,
    }


def _complete_lap_rows(
    lap: int,
    lap_time: float,
    *,
    start_time: float = 0.0,
    speed: float = 120.0,
    samples: int | None = None,
) -> list[dict[str, object]]:
    samples = samples or max(101, int(lap_time * 3) + 1)
    return [
        _lap_row(
            lap,
            index / (samples - 1),
            start_time + lap_time * index / (samples - 1),
            speed,
        )
        for index in range(samples)
    ]


def test_detects_normal_complete_lap_boundary() -> None:
    laps = detect_laps(_complete_lap_rows(1, 40.0, start_time=10.0), run_id="run")

    assert len(laps) == 1
    assert laps[0].is_complete is True
    assert laps[0].is_useful is True
    assert laps[0].lap_time == 40.0


def test_incomplete_out_lap_is_partial_short_run() -> None:
    laps = detect_laps([_lap_row(0, 0.2, 0.0), _lap_row(0, 0.8, 12.0)], run_id="run")

    assert laps[0].is_complete is False
    assert "SHORT_RUN" in laps[0].classification_tags
    assert laps[0].confidence_notes


def test_duplicate_lap_numbers_group_and_invalid_laps_are_ignored() -> None:
    laps = detect_laps([
        _lap_row(2, 0.0, 0.0),
        _lap_row(2, 1.0, 20.0),
        _lap_row("bad", 0.5, 30.0),
    ])

    assert [lap.lap_number for lap in laps] == [2]
    assert laps[0].sample_count == 2


def test_missing_lap_column_returns_no_fake_laps() -> None:
    assert detect_laps([{"lap_dist_pct": 0.5, "session_time": 1.0, "speed_mph": 100.0}]) == []


def test_non_monotonic_sample_times_use_observed_time_bounds() -> None:
    laps = detect_laps([_lap_row(3, 0.0, 20.0), _lap_row(3, 0.5, 10.0), _lap_row(3, 1.0, 30.0)])

    assert laps[0].start_time == 10.0
    assert laps[0].end_time == 30.0
    assert laps[0].lap_time == 20.0


def test_complete_pit_road_lap_is_not_setup_evidence() -> None:
    rows = [_lap_row(4, 0.0, 0.0), _lap_row(4, 0.5, 20.0), _lap_row(4, 1.0, 40.0)]
    rows[1]["on_pit_road"] = True

    lap = detect_laps(rows)[0]

    assert lap.is_complete is True
    assert lap.is_useful is False
    assert "PIT_ROAD" in lap.classification_tags
    assert "NO_SETUP_CONCLUSION" in lap.classification_tags

    classified = classify_laps([lap])[0]
    assert "PARTIAL" not in classified.classification_tags


def test_complete_off_track_lap_is_not_setup_evidence() -> None:
    rows = [_lap_row(5, 0.0, 0.0), _lap_row(5, 0.5, 20.0), _lap_row(5, 1.0, 40.0)]
    rows[1]["player_track_surface"] = 0

    lap = detect_laps(rows)[0]

    assert lap.is_useful is False
    assert "OFF_TRACK" in lap.classification_tags


def test_relative_pace_filter_rejects_obvious_cooldown() -> None:
    rows: list[dict[str, object]] = []
    for lap_number, lap_time, throttle in [
        (1, 50.0, 95.0),
        (2, 50.2, 94.0),
        (3, 49.9, 96.0),
        (4, 65.0, 45.0),
    ]:
        lap_rows = _complete_lap_rows(lap_number, lap_time, speed=150.0)
        for row in lap_rows:
            row["throttle_pct"] = throttle
        rows.extend(lap_rows)

    laps = detect_laps(rows)
    cooldown = next(lap for lap in laps if lap.lap_number == 4)

    assert cooldown.is_useful is False
    assert "COOLDOWN" in cooldown.classification_tags


def test_session_tick_gap_blocks_row_and_frame_setup_evidence() -> None:
    rows = [_lap_row(6, 0.0, 0.0), _lap_row(6, 0.5, 20.0), _lap_row(6, 1.0, 40.0)]
    for row, tick in zip(rows, (100, 102, 103)):
        row["session_tick"] = tick

    row_lap = detect_laps(rows)[0]
    frame_lap = detect_laps(pl.DataFrame(rows, strict=False))[0]

    for lap in (row_lap, frame_lap):
        assert lap.is_useful is False
        assert "SAMPLE_DISCONTINUITY" in lap.classification_tags
        assert "NO_SETUP_CONCLUSION" in lap.classification_tags


def test_backward_position_jump_blocks_setup_evidence() -> None:
    rows = [
        _lap_row(7, 0.0, 0.0),
        _lap_row(7, 0.6, 15.0),
        _lap_row(7, 0.4, 25.0),
        _lap_row(7, 1.0, 40.0),
    ]

    lap = detect_laps(rows)[0]

    assert lap.is_complete is True
    assert lap.is_useful is False
    assert "POSITION_DISCONTINUITY" in lap.classification_tags


def test_negative_speed_sample_blocks_setup_evidence() -> None:
    rows = [_lap_row(8, 0.0, 0.0), _lap_row(8, 0.5, 20.0, -1.0), _lap_row(8, 1.0, 40.0)]

    lap = detect_laps(rows)[0]

    assert lap.is_useful is False
    assert "INVALID_SPEED_EVENT" in lap.classification_tags


def test_caution_and_yellow_flags_block_row_and_frame_setup_evidence() -> None:
    rows = [_lap_row(9, 0.0, 0.0), _lap_row(9, 0.5, 20.0), _lap_row(9, 1.0, 40.0)]
    rows[1]["SessionFlags"] = 0x4000 | 0x0008

    for lap in (detect_laps(rows)[0], detect_laps(pl.DataFrame(rows, strict=False))[0]):
        assert lap.is_useful is False
        assert "CAUTION" in lap.classification_tags
        assert "YELLOW" in lap.classification_tags
        assert "NO_SETUP_CONCLUSION" in lap.classification_tags


def test_enter_exit_reset_state_alone_does_not_claim_a_reset_event() -> None:
    rows = _complete_lap_rows(10, 40.0)
    rows[len(rows) // 2]["enter_exit_reset_state"] = 1

    for lap in (detect_laps(rows)[0], detect_laps(pl.DataFrame(rows, strict=False))[0]):
        assert lap.is_useful is True
        assert "ACTIVE_RESET" not in lap.classification_tags


def test_tiny_three_sample_lap_fails_row_and_frame_credibility_gate() -> None:
    rows = [_lap_row(11, 0.0, 0.0), _lap_row(11, 0.5, 0.016), _lap_row(11, 1.0, 0.033)]

    for lap in (detect_laps(rows)[0], detect_laps(pl.DataFrame(rows, strict=False))[0]):
        assert lap.is_complete is True
        assert lap.is_useful is False
        assert "NON_CREDIBLE_LAP_SAMPLING" in lap.classification_tags
        assert "SPARSE_POSITION_COVERAGE" in lap.classification_tags


def test_within_lap_incident_increase_fails_row_and_frame_gate() -> None:
    rows = _complete_lap_rows(12, 40.0)
    for index, row in enumerate(rows):
        row["player_incident_count"] = 4 if index >= 50 else 0

    for lap in (detect_laps(rows)[0], detect_laps(pl.DataFrame(rows, strict=False))[0]):
        assert lap.is_useful is False
        assert "INCIDENT_COUNT_INCREASE" in lap.classification_tags
        assert "NO_SETUP_CONCLUSION" in lap.classification_tags


def test_five_sample_full_span_lap_fails_sparse_coverage_in_both_engines() -> None:
    rows = _complete_lap_rows(13, 40.0, samples=5)

    for lap in (detect_laps(rows)[0], detect_laps(pl.DataFrame(rows, strict=False))[0]):
        assert lap.is_complete is True
        assert lap.is_useful is False
        assert "SPARSE_POSITION_COVERAGE" in lap.classification_tags
        assert "NON_CREDIBLE_LAP_SAMPLING" in lap.classification_tags


def test_sustained_spin_like_signature_blocks_row_and_frame_setup_evidence() -> None:
    rows = _complete_lap_rows(14, 40.0)
    for index, row in enumerate(rows):
        row["yaw_rate"] = 6.0 if 40 <= index < 60 else 0.2
        row["abs_steering_deg"] = 25.0 if 40 <= index < 60 else 4.0
        if 40 <= index < 60:
            row["speed_mph"] = 5.0

    for lap in (detect_laps(rows)[0], detect_laps(pl.DataFrame(rows, strict=False))[0]):
        assert lap.is_useful is False
        assert "WRECK_OR_SPIN" in lap.classification_tags
        assert "NO_SETUP_CONCLUSION" in lap.classification_tags


def test_three_lap_cohort_rejects_extreme_low_demand_outlier_in_both_engines() -> None:
    rows: list[dict[str, object]] = []
    start = 0.0
    for lap_number, lap_time, throttle in (
        (21, 40.0, 100.0),
        (22, 40.0, 100.0),
        (23, 70.0, 20.0),
    ):
        lap_rows = _complete_lap_rows(lap_number, lap_time, start_time=start)
        for row in lap_rows:
            row["throttle_pct"] = throttle
        rows.extend(lap_rows)
        start += lap_time + 1.0

    for detected in (detect_laps(rows), detect_laps(pl.DataFrame(rows, strict=False))):
        outlier = next(lap for lap in detected if lap.lap_number == 23)
        assert outlier.is_useful is False
        assert "COOLDOWN" in outlier.classification_tags
        assert "NO_SETUP_CONCLUSION" in outlier.classification_tags
