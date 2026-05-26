from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from racelab_engine.analysis.platform_events import (
    PlatformEvent,
    detect_platform_events,
    detect_highest_platform_compression,
    detect_highest_rake,
    detect_highest_shock_activity,
    detect_max_dynamic_pressure,
    detect_min_splitter,
    detect_worst_drag_scrub,
    detect_worst_speed_loss,
)
from racelab_engine.io.ibt_reader import read_normalized_records


@pytest.fixture(scope="session")
def lap2_rows(talladega_ibt_path: Path) -> list[dict[str, Any]]:
    rows, _missing = read_normalized_records(talladega_ibt_path)
    return [row for row in rows if row.get("lap") == 2]


def test_detect_min_splitter(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_min_splitter(lap2_rows)
    assert event is not None
    assert event.event_type == "MIN_SPLITTER"
    assert event.primary_unit == "in"
    assert event.primary_value == pytest.approx(0.141, abs=0.02)
    assert event.lap_dist_ft == pytest.approx(9397, abs=500)
    assert event.lap_pct == pytest.approx(67.02, abs=1.0)
    # 0.141 in falls in 0.118–0.236 high-risk band per spec thresholds
    assert event.severity == "high"
    assert event.confidence == "high"
    assert len(event.evidence) >= 3
    assert event.recommended_action is not None
    assert "cfs_ride_height_in" in event.channels_used


def test_detect_worst_speed_loss(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_worst_speed_loss(lap2_rows)
    assert event is not None
    assert event.event_type == "WORST_SPEED_LOSS"
    assert event.primary_value is not None
    # Throttle/brake filter should ensure this is a real full-throttle event
    assert "Speed was falling" in event.evidence[0]


def test_detect_worst_drag_scrub_proxy_flags(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_worst_drag_scrub(lap2_rows)
    assert event is not None
    assert event.is_proxy_based is True
    assert event.proxy_warning is not None
    assert "estimate" in event.proxy_warning.lower()


def test_detect_highest_rake(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_highest_rake(lap2_rows)
    assert event is not None
    assert event.event_type == "HIGHEST_RAKE"
    assert event.primary_value is not None
    assert event.primary_unit == "in"
    assert "center_rake_fs_in" in event.channels_used


def test_detect_highest_platform_compression_proxy(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_highest_platform_compression(lap2_rows)
    assert event is not None
    assert event.is_proxy_based is True
    assert event.proxy_warning is not None
    assert "platform_compression_index" in event.channels_used


def test_detect_highest_shock_activity(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_highest_shock_activity(lap2_rows)
    assert event is not None
    assert event.event_type == "HIGHEST_SHOCK_ACTIVITY"
    assert event.is_proxy_based is True
    assert event.primary_value is not None


def test_detect_max_dynamic_pressure(lap2_rows: list[dict[str, Any]]) -> None:
    event = detect_max_dynamic_pressure(lap2_rows)
    assert event is not None
    assert event.event_type == "MAX_DYNAMIC_PRESSURE"
    assert event.primary_unit == "psf"
    assert event.confidence == "high"
    assert "dynamic_pressure_psf" in event.channels_used


def test_detect_platform_events_all(lap2_rows: list[dict[str, Any]]) -> None:
    events = detect_platform_events(lap2_rows)
    types = {e.event_type for e in events}
    assert "MIN_SPLITTER" in types
    assert "WORST_SPEED_LOSS" in types
    assert "WORST_DRAG_SCRUB" in types
    assert "HIGHEST_RAKE" in types
    assert "HIGHEST_PLATFORM_COMPRESSION" in types
    assert "HIGHEST_SHOCK_ACTIVITY" in types
    assert "MAX_DYNAMIC_PRESSURE" in types


def test_detect_platform_events_event_ids_are_stable(lap2_rows: list[dict[str, Any]]) -> None:
    events1 = detect_platform_events(lap2_rows)
    events2 = detect_platform_events(lap2_rows)
    ids1 = [e.event_id for e in events1]
    ids2 = [e.event_id for e in events2]
    assert ids1 == ids2


def test_detect_platform_events_missing_channels_do_not_crash() -> None:
    """Missing channels should never crash event detection."""
    empty_rows: list[dict[str, Any]] = [{"lap": 1}]
    events = detect_platform_events(empty_rows)
    assert events == []

    sparse_rows: list[dict[str, Any]] = [{"lap": 1, "session_time": 0.0}]
    events2 = detect_platform_events(sparse_rows)
    assert events2 == []


def test_detect_platform_events_lap_filter(talladega_ibt_path: Path) -> None:
    """Filtering by lap should only return events from that lap."""
    rows, _missing = read_normalized_records(talladega_ibt_path)
    events = detect_platform_events(rows, lap=2)
    assert len(events) >= 1
    for event in events:
        assert event.lap == 2


def test_platform_event_as_dict() -> None:
    event = PlatformEvent(
        event_id="test_1",
        event_type="MIN_SPLITTER",
        title="Test",
        severity="info",
        confidence="high",
        lap=2,
        sample_index=42,
        lap_dist_ft=1000.0,
        lap_pct=50.0,
        primary_value=0.141,
        primary_unit="in",
        channels_used=["cfs_ride_height_in"],
        evidence=["test evidence"],
        recommended_action="test action",
        is_proxy_based=False,
    )
    d = event.as_dict()
    assert d["event_id"] == "test_1"
    assert d["event_type"] == "MIN_SPLITTER"
    assert d["severity"] == "info"
    assert d["confidence"] == "high"
    assert d["primary_value"] == pytest.approx(0.141)


def test_detect_platform_events_event_type_filter(lap2_rows: list[dict[str, Any]]) -> None:
    events = detect_platform_events(lap2_rows, event_types=["MIN_SPLITTER"])
    assert len(events) == 1
    assert events[0].event_type == "MIN_SPLITTER"

    events2 = detect_platform_events(lap2_rows, event_types=["NONEXISTENT"])
    assert events2 == []
