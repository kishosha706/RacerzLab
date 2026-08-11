from __future__ import annotations

import polars as pl
import pytest

from racelab_engine.analysis.drag_scrub import detect_drag_scrub_risk_zones
from racelab_engine.analysis.lap_classification import classify_laps
from racelab_engine.analysis.lap_detection import detect_laps
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.io.ibt_reader import (
    _FRAME_NATIVE_DRAG_COLUMNS,
    _OVERVIEW_ROW_COLUMNS,
    _build_overview_drag_events,
    _build_overview_platform_events,
    _platform_detection_rows,
    _usable_channel_names,
    read_normalized_records,
)


def test_detect_laps_row_vs_frame_parity(talladega_ibt_path) -> None:
    rows, _ = read_normalized_records(talladega_ibt_path)
    frame = pl.DataFrame(rows)
    row_laps = detect_laps(rows, run_id="parity")
    frame_laps = detect_laps(frame, run_id="parity")
    assert len(row_laps) == len(frame_laps)
    for a, b in zip(row_laps, frame_laps):
        assert a.lap_number == b.lap_number
        assert a.is_complete == b.is_complete
        assert a.sample_count == b.sample_count
        assert a.min_splitter_mm == b.min_splitter_mm


def test_detect_platform_row_vs_frame_parity(talladega_ibt_path) -> None:
    rows, _ = read_normalized_records(talladega_ibt_path)
    frame = pl.DataFrame(rows)
    row_events = _build_overview_platform_events(rows, run_id="parity")
    frame_events = _build_overview_platform_events(frame, run_id="parity")
    assert len(row_events) == len(frame_events)
    for a, b in zip(row_events, frame_events):
        assert a.lap_number == b.lap_number
        assert a.event_subtype == b.event_subtype
        assert a.primary_metric_value == b.primary_metric_value


def test_detect_drag_scrub_row_vs_frame_parity(talladega_ibt_path) -> None:
    rows, _ = read_normalized_records(talladega_ibt_path)
    frame = pl.DataFrame(rows)
    row_events = detect_drag_scrub_risk_zones(rows, run_id="parity")
    frame_events = detect_drag_scrub_risk_zones(frame, run_id="parity")
    assert len(row_events) == len(frame_events)


def test_overview_drag_uses_frame_native_path_without_changing_evidence(talladega_ibt_path) -> None:
    rows, _ = read_normalized_records(talladega_ibt_path)
    frame = pl.DataFrame(rows)
    laps = eligible_laps(classify_laps(detect_laps(frame, run_id="parity")))
    best_lap = min(laps, key=lambda lap: lap.lap_time or 999_999.0)

    row_events, row_warning = _build_overview_drag_events(
        rows,
        run_id="parity",
        best_lap=best_lap,
    )
    frame_events, frame_warning = _build_overview_drag_events(
        frame,
        run_id="parity",
        best_lap=best_lap,
    )

    assert frame_warning == row_warning
    assert len(frame_events) == len(row_events)
    for row_event, frame_event in zip(row_events, frame_events):
        assert frame_event.event_id == row_event.event_id
        assert frame_event.event_type == row_event.event_type
        assert frame_event.valid_for_tuning == row_event.valid_for_tuning
        assert "measurement_guidance" not in frame_event.model_dump()
        assert "measurement_guidance" not in row_event.model_dump()
        assert frame_event.evidence_state == row_event.evidence_state
        assert frame_event.confidence_score == pytest.approx(row_event.confidence_score)
        assert frame_event.primary_metric_value == pytest.approx(row_event.primary_metric_value)
        assert set(frame_event.evidence_json) == set(row_event.evidence_json)
        for key, row_value in row_event.evidence_json.items():
            frame_value = frame_event.evidence_json[key]
            if isinstance(row_value, float):
                assert frame_value == pytest.approx(row_value)
            else:
                assert frame_value == row_value


def test_overview_row_projection_keeps_evidence_and_leaves_raw_vault_columnar() -> None:
    frame = pl.DataFrame({
        "lap": [1, 1],
        "speed_mph": [100.0, 101.0],
        "cfsr_height_mm": [20.0, 19.0],
        "unused_raw_archive_channel": [7.0, 8.0],
        "all_null_channel": [None, None],
    })

    rows = _platform_detection_rows(frame)
    usable = _usable_channel_names(frame)

    assert set(rows[0]) == {"lap", "speed_mph", "cfsr_height_mm"}
    assert "unused_raw_archive_channel" in usable
    assert "all_null_channel" not in usable


def test_overview_fallback_projection_retains_every_drag_evidence_channel() -> None:
    assert _FRAME_NATIVE_DRAG_COLUMNS <= _OVERVIEW_ROW_COLUMNS
