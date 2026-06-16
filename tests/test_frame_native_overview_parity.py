from __future__ import annotations

import polars as pl

from racelab_engine.analysis.drag_scrub import detect_drag_scrub_risk_zones
from racelab_engine.analysis.lap_detection import detect_laps
from racelab_engine.io.ibt_reader import _build_overview_platform_events
from racelab_engine.io.ibt_reader import read_normalized_records


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
