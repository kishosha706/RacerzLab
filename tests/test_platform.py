from __future__ import annotations

from racelab_engine.analysis.platform import classify_splitter_height_mm, detect_platform_events


def test_platform_threshold_classification() -> None:
    assert classify_splitter_height_mm(-0.1) == "scrape"
    assert classify_splitter_height_mm(2.9) == "critical"
    assert classify_splitter_height_mm(3.58) == "high"
    assert classify_splitter_height_mm(8) == "watch"
    assert classify_splitter_height_mm(12) == "safe"


def test_platform_analyzer_empty_and_valid_event() -> None:
    assert detect_platform_events([], run_id="test-run") == []

    events = detect_platform_events(
        [
            {
                "lap": 2,
                "lap_dist_pct": 0.0,
                "lap_dist_m": 0.0,
                "speed_mph": 185.0,
                "throttle_pct": 100,
                "brake_pct": 0,
                "cfsr_height_mm": 8.0,
            },
            {
                "lap": 2,
                "lap_dist_pct": 0.6702,
                "lap_dist_m": 2864.23,
                "speed_mph": 186.08,
                "throttle_pct": 100,
                "brake_pct": 0,
                "cfsr_height_mm": 3.58,
            },
            {
                "lap": 2,
                "lap_dist_pct": 0.99,
                "lap_dist_m": 4230.0,
                "speed_mph": 186.0,
                "throttle_pct": 100,
                "brake_pct": 0,
                "cfsr_height_mm": 9.0,
            }
        ],
        run_id="test-run",
    )

    assert len(events) == 1
    assert events[0].severity == "high"
    assert events[0].valid_for_tuning is True
    assert events[0].lap_pct_peak == 67.02
