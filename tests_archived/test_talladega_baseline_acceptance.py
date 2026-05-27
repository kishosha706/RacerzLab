from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.io.ibt_reader import import_ibt
from racelab_engine.reports.markdown_report import generate_markdown_report

pytestmark = pytest.mark.slow


def test_talladega_baseline_acceptance(talladega_ibt_path: Path) -> None:
    result = import_ibt(talladega_ibt_path)
    overview = result.overview

    assert result.status.status == "imported"
    assert overview is not None
    assert result.header is not None
    assert result.header.telemetry_rate_hz == 60
    assert result.header.record_count == 6277
    assert result.header.variable_count == 275
    assert result.header.duration_seconds == pytest.approx(104.6, abs=0.5)

    assert overview.session.car_name == "Chevrolet Camaro ZL1 Class A"
    assert overview.session.track_display_name == "Talladega Super Speedway"
    assert overview.session.setup_name == "talladega.sto"

    best = overview.best_useful_lap
    assert best is not None
    assert best.lap_number == 2
    assert best.lap_time == pytest.approx(51.13, abs=0.5)
    assert best.avg_speed_mph == pytest.approx(186.5, abs=0.5)
    assert best.max_speed_mph == pytest.approx(188.6, abs=0.5)
    assert best.avg_throttle_pct == pytest.approx(100.0, abs=0.1)
    assert best.max_brake_pct == pytest.approx(0.0, abs=0.1)
    assert best.min_rpm == pytest.approx(7763, abs=100)
    assert best.max_rpm == pytest.approx(8022, abs=100)
    assert best.min_splitter_mm == pytest.approx(3.58, abs=0.25)
    assert best.min_splitter_pct == pytest.approx(67.02, abs=0.5)
    assert best.min_splitter_distance_m == pytest.approx(2864, abs=25)
    assert best.min_splitter_speed_mph == pytest.approx(186, abs=0.5)

    platform_events = [event for event in overview.events if event.event_type.startswith("PLATFORM")]
    valid_platform = [event for event in platform_events if event.valid_for_tuning]
    invalid_lap3 = [event for event in platform_events if event.lap_number == 3]

    assert len(valid_platform) == 1
    assert valid_platform[0].lap_number == 2
    assert valid_platform[0].primary_metric_value == pytest.approx(3.58, abs=0.25)
    assert invalid_lap3
    assert invalid_lap3[0].event_type == "PLATFORM_SCRAPE"
    assert invalid_lap3[0].valid_for_tuning is False

    drag_events = [event for event in overview.events if event.event_type == "FULL_THROTTLE_SPEED_LOSS"]
    assert drag_events
    # Aero-normalized drag/scrub correctly identifies the highest-resistance zone
    # at Talladega's high-speed portion rather than the old raw-deceleration zone
    assert drag_events[0].evidence_json.get("drag_scrub_score", 0) > 0.3

    report = generate_markdown_report(overview)
    assert "Lap 2 is the best useful lap" in report
    assert "3.58 mm" in report
    assert "Do not overclaim exact aerodynamic drag force" in report
