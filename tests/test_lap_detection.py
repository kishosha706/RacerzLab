from __future__ import annotations

from racelab_engine.analysis.lap_detection import detect_laps


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


def test_detects_normal_complete_lap_boundary() -> None:
    laps = detect_laps([_lap_row(1, 0.0, 10.0), _lap_row(1, 0.5, 25.0), _lap_row(1, 1.0, 50.0)], run_id="run")

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
