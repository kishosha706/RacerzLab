from __future__ import annotations

from racelab_engine.analysis.lap_classification import classify_laps
from racelab_engine.analysis.lap_detection import detect_laps


def test_lap_detection_and_placeholder_classification() -> None:
    rows = [
        {"lap": 1, "lap_dist_pct": 0.25, "session_time": 0, "speed_mph": 120},
        {"lap": 1, "lap_dist_pct": 0.50, "session_time": 1, "speed_mph": 130},
        {"lap": 2, "lap_dist_pct": 0.00, "session_time": 10, "speed_mph": 185, "throttle_pct": 100, "brake_pct": 0},
        {"lap": 2, "lap_dist_pct": 0.50, "session_time": 35, "speed_mph": 187, "throttle_pct": 100, "brake_pct": 0},
        {"lap": 2, "lap_dist_pct": 0.99, "session_time": 61, "speed_mph": 186, "throttle_pct": 100, "brake_pct": 0},
    ]

    laps = classify_laps(detect_laps(rows, run_id="test-run"))

    assert len(laps) == 2
    assert laps[0].lap_type == "partial"
    assert "NO_SETUP_CONCLUSION" in laps[0].classification_tags
    assert laps[1].is_useful is True
    assert "SOLO_CLEAN" in laps[1].classification_tags
