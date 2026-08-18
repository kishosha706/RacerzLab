from __future__ import annotations

from pathlib import Path

import polars as pl

import racelab_engine.analysis as analysis_pkg
from racelab_engine.analysis.platform_events import (
    PLATFORM_EVENT_COLUMNS,
    PlatformEvent,
    PlatformEventType,
    detect_platform_events,
)
from racelab_engine.analysis.platform_metrics import classify_splitter_height_mm
from racelab_engine.io.ibt_reader import _build_overview_platform_events, _safe_float
from racelab_engine.models.event import TelemetryEvent


ROOT = Path(__file__).resolve().parents[1]


def _row(
    *,
    lap: int = 2,
    lap_dist_pct: float | None = None,
    lap_dist_pct_100: float | None = None,
    lap_dist_m: float = 0.0,
    lap_dist_ft: float = 0.0,
    speed_mph: float | None = 185.0,
    throttle_pct: float | None = 100.0,
    brake_pct: float | None = 0.0,
    cfsr_height_mm: float | None = 8.0,
    cfs_risk_score: float = 0.08,
    session_time: float | None = None,
    on_pit_road: bool | None = None,
) -> dict[str, float | int | None]:
    cfs_in = None if cfsr_height_mm is None else cfsr_height_mm / 25.4
    row: dict[str, float | int | None] = {
        "lap": lap,
        "lap_dist_m": lap_dist_m,
        "lap_dist_ft": lap_dist_ft,
        "speed_mph": speed_mph,
        "throttle_pct": throttle_pct,
        "brake_pct": brake_pct,
        "cfsr_height_mm": cfsr_height_mm,
        "cfs_ride_height_mm": cfsr_height_mm,
        "cfs_ride_height_in": cfs_in,
        "cfs_risk_score": cfs_risk_score,
        "center_rake_fs_in": 1.2,
        "platform_compression_index": 0.0,
        "shock_activity_index": 0.0,
        "dynamic_pressure_psf": 120.0,
        "air_density": 1.22,
        "rear_min_ride_height_mm": 15.0,
        "rear_min_ride_height_in": 15.0 / 25.4,
        "rear_scrape_margin_mm": 15.0,
        "rear_scrape_risk_score": 0.08,
        "front_platform_risk_score": 0.08,
        "rear_platform_risk_score": 0.08,
        "whole_car_bottoming_risk": 0.08,
    }
    if lap_dist_pct is not None:
        row["lap_dist_pct"] = lap_dist_pct
    if lap_dist_pct_100 is not None:
        row["lap_dist_pct_100"] = lap_dist_pct_100
    if session_time is not None:
        row["session_time"] = session_time
    if on_pit_road is not None:
        row["on_pit_road"] = on_pit_road
    return row


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _dense_platform_lap(
    *,
    duration_s: float,
    splitter_by_index: dict[int, float],
    default_splitter_mm: float = 15.0,
) -> list[dict[str, float | int | None]]:
    rows: list[dict[str, float | int | None]] = []
    for index in range(101):
        pct = index / 100.0
        splitter = splitter_by_index.get(index, default_splitter_mm)
        rows.append({
            **_row(
                lap_dist_pct=pct,
                lap_dist_m=4230.0 * pct,
                lap_dist_ft=13877.95 * pct,
                cfsr_height_mm=splitter,
                session_time=duration_s * pct,
            ),
            "session_tick": index,
        })
    return rows


def _declared_rate(rows: list[dict[str, float | int | None]]) -> float:
    start = float(rows[0]["session_time"])
    end = float(rows[-1]["session_time"])
    return (len(rows) - 1) / (end - start)


def test_analysis_package_exports_only_canonical_platform_detector_names() -> None:
    assert analysis_pkg.detect_platform_events is detect_platform_events
    assert analysis_pkg.PlatformEvent is PlatformEvent
    assert analysis_pkg.PlatformEventType is PlatformEventType
    assert analysis_pkg.classify_splitter_height_mm is classify_splitter_height_mm
    assert not hasattr(analysis_pkg, "detect_rich_platform_events")
    assert not hasattr(analysis_pkg, "detect_legacy_platform_telemetry_events")


def test_platform_threshold_classification() -> None:
    assert classify_splitter_height_mm(0.0) == "scrape"
    assert classify_splitter_height_mm(3.0) == "critical"
    assert classify_splitter_height_mm(6.0) == "high"
    assert classify_splitter_height_mm(10.0) == "watch"
    assert classify_splitter_height_mm(12.0) == "safe"


def test_canonical_detector_emits_min_splitter_platform_event() -> None:
    events = detect_platform_events(
        [
            _row(lap_dist_pct_100=0.0, lap_dist_m=0.0, lap_dist_ft=0.0, cfsr_height_mm=8.0),
            _row(lap_dist_pct_100=67.02, lap_dist_m=2864.23, lap_dist_ft=9397.08, speed_mph=186.08, cfsr_height_mm=3.58),
            _row(lap_dist_pct_100=99.0, lap_dist_m=4230.0, lap_dist_ft=13877.95, speed_mph=186.0, cfsr_height_mm=9.0),
        ],
        lap=2,
        event_types=["MIN_SPLITTER"],
    )

    assert len(events) == 1
    assert isinstance(events[0], PlatformEvent)
    assert events[0].event_type == "MIN_SPLITTER"
    assert events[0].lap_pct == 67.02


def test_overview_platform_event_conversion_uses_canonical_detector() -> None:
    rows = _dense_platform_lap(
        duration_s=45.0,
        splitter_by_index={66: 8.0, 67: 3.58, 68: 8.0},
    )
    rows[67]["lap_dist_pct"] = 0.6702
    rows[67]["speed_mph"] = 186.08

    events = _build_overview_platform_events(
        rows,
        run_id="test-run",
        expected_sample_rate_hz=_declared_rate(rows),
    )

    assert len(events) == 1
    assert isinstance(events[0], TelemetryEvent)
    assert events[0].event_type == "PLATFORM_LOW"
    assert events[0].severity == "high"
    assert events[0].valid_for_tuning is True
    assert events[0].lap_pct_peak == 67.02


def test_platform_numeric_parser_rejects_every_non_finite_value() -> None:
    assert _safe_float(float("nan")) is None
    assert _safe_float(float("inf")) is None
    assert _safe_float(float("-inf")) is None


def test_overview_platform_event_rejects_implausible_peak_context() -> None:
    hostile_values = (
        ("speed_mph", float("inf")),
        ("speed_mph", 301.0),
        ("throttle_pct", float("inf")),
        ("throttle_pct", 101.0),
        ("throttle_pct", -1.0),
        ("brake_pct", float("-inf")),
        ("brake_pct", 101.0),
        ("brake_pct", -1.0),
        ("cfsr_height_mm", float("-inf")),
        ("cfsr_height_mm", -25.5),
    )
    for channel, value in hostile_values:
        rows = _dense_platform_lap(
            duration_s=45.0,
            splitter_by_index={49: 3.0, 50: 2.5, 51: 3.0},
        )
        rows[50][channel] = value

        events = _build_overview_platform_events(rows, run_id=f"hostile-{channel}-{value}")

        assert len(events) == 1
        assert events[0].valid_for_tuning is False, (channel, value)
        assert "measurement_guidance" not in events[0].model_dump(), (channel, value)


def test_overview_platform_event_cannot_bypass_canonical_pit_lap_gate() -> None:
    rows = [
        _row(lap_dist_pct=0.0, cfsr_height_mm=8.0, session_time=0.0, on_pit_road=True),
        _row(lap_dist_pct=0.67, cfsr_height_mm=3.0, session_time=30.0, on_pit_road=True),
        _row(lap_dist_pct=0.99, cfsr_height_mm=9.0, session_time=45.0, on_pit_road=True),
    ]

    events = _build_overview_platform_events(rows, run_id="pit-lap")

    assert len(events) == 1
    assert events[0].valid_for_tuning is False
    assert events[0].evidence_json["is_eligible_lap"] is False


def test_platform_read_columns_include_canonical_lap_eligibility_state() -> None:
    assert {
        "session_time",
        "session_tick",
        "lap_dist_pct",
        "on_pit_road",
        "is_on_track",
        "player_track_surface",
        "session_flags",
        "player_incident_count",
        "player_driver_incident_count",
        "player_team_incident_count",
    } <= set(PLATFORM_EVENT_COLUMNS)


def test_overview_allows_sustained_negative_scrape_on_eligible_lap() -> None:
    rows = _dense_platform_lap(
        duration_s=40.0,
        splitter_by_index={49: -1.0, 50: -1.5, 51: -1.0},
    )

    events = _build_overview_platform_events(
        rows,
        run_id="sustained-scrape",
        expected_sample_rate_hz=_declared_rate(rows),
    )

    assert len(events) == 1
    assert events[0].event_type == "PLATFORM_SCRAPE"
    assert events[0].valid_for_tuning is True
    assert events[0].lap_pct_start < events[0].lap_pct_peak < events[0].lap_pct_end
    assert events[0].evidence_json["has_sustained_risk"] is True
    assert "measurement_guidance" not in events[0].model_dump()


def test_overview_internal_one_frame_low_has_no_action_field() -> None:
    rows = [
        _row(lap_dist_pct=0.0, lap_dist_ft=0.0, cfsr_height_mm=15.0, session_time=0.0),
        _row(lap_dist_pct=0.50, lap_dist_ft=2000.0, cfsr_height_mm=9.0, session_time=20.0),
        _row(lap_dist_pct=0.99, lap_dist_ft=4000.0, cfsr_height_mm=15.0, session_time=40.0),
    ]

    events = _build_overview_platform_events(rows, run_id="one-frame-low")

    assert len(events) == 1
    assert events[0].evidence_json["display_scope"] == "internal"
    assert events[0].valid_for_tuning is False
    assert "measurement_guidance" not in events[0].model_dump()


def test_overview_platform_event_conversion_handles_multiple_laps() -> None:
    rows = [
        _row(lap=2, lap_dist_pct_100=0.0, cfsr_height_mm=8.0),
        _row(lap=2, lap_dist_pct_100=50.0, cfsr_height_mm=4.0),
        _row(lap=2, lap_dist_pct_100=99.0, cfsr_height_mm=9.0),
        _row(lap=3, lap_dist_pct_100=0.0, cfsr_height_mm=7.0),
        _row(lap=3, lap_dist_pct_100=55.0, cfsr_height_mm=-1.0, cfs_risk_score=0.72),
        _row(lap=3, lap_dist_pct_100=99.0, cfsr_height_mm=8.0),
    ]

    events = _build_overview_platform_events(rows, run_id="multi")

    assert [event.lap_number for event in events] == [2, 3]
    assert [event.event_type for event in events] == ["PLATFORM_LOW", "PLATFORM_SCRAPE"]
    assert [event.primary_metric_value for event in events] == [4.0, -1.0]


def test_overview_platform_event_conversion_row_vs_frame_parity() -> None:
    rows = [
        _row(lap_dist_pct_100=0.0, lap_dist_m=0.0, cfsr_height_mm=8.0),
        _row(lap_dist_pct_100=67.02, lap_dist_m=2864.23, speed_mph=186.08, cfsr_height_mm=3.58),
        _row(lap_dist_pct_100=99.0, lap_dist_m=4230.0, speed_mph=186.0, cfsr_height_mm=9.0),
    ]
    frame = pl.DataFrame(rows)

    row_events = _build_overview_platform_events(rows, run_id="parity")
    frame_events = _build_overview_platform_events(frame, run_id="parity")

    assert row_events == frame_events


def test_import_boundaries_exclude_removed_platform_detector_path() -> None:
    racelab_engine_sources = list((ROOT / "racelab_engine").rglob("*.py"))
    api_sources = list((ROOT / "api").rglob("*.py"))
    all_sources = racelab_engine_sources + api_sources

    assert not (ROOT / "racelab_engine/analysis/platform.py").exists()

    banned_imports = (
        "from racelab_engine.analysis.platform import",
        "import racelab_engine.analysis.platform",
        "detect_legacy_platform_telemetry_events",
    )
    for path in all_sources:
        source = path.read_text(encoding="utf-8")
        assert all(token not in source for token in banned_imports), path.as_posix()

    detector_defs = []
    for path in racelab_engine_sources:
        source = path.read_text(encoding="utf-8")
        if "def detect_platform_events(" in source:
            detector_defs.append(path.relative_to(ROOT).as_posix())
    assert detector_defs == ["racelab_engine/analysis/platform_events.py"]


def test_platform_routes_use_canonical_detector_path() -> None:
    routes_events = _read("api/routes_events.py")
    routes_track_map = _read("api/routes_track_map.py")
    ibt_reader = _read("racelab_engine/io/ibt_reader.py")

    assert "from racelab_engine.analysis.platform_events import PLATFORM_EVENT_COLUMNS, detect_platform_events" in routes_events
    assert "from api.routes_events import get_platform_events" in routes_track_map
    assert "from racelab_engine.analysis.platform_events import (" in ibt_reader
    assert "PlatformEvent," in ibt_reader
    assert "detect_platform_events," in ibt_reader
