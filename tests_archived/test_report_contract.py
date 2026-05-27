from __future__ import annotations

import json
from pathlib import Path

from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.reports.markdown_report import generate_markdown_report


def _sample_overview() -> RunOverview:
    run_id = "sample-run"
    lap = LapSummary(
        lap_id=f"{run_id}:lap:2",
        run_id=run_id,
        lap_number=2,
        lap_type="complete",
        is_complete=True,
        is_useful=True,
        lap_time=51.133,
        avg_speed_mph=186.53,
        max_speed_mph=188.60,
        min_rpm=7763,
        max_rpm=8022,
        avg_throttle_pct=100,
        avg_brake_pct=0,
        min_splitter_mm=3.58,
    )
    platform_event = TelemetryEvent(
        event_id=f"{run_id}:event:platform",
        run_id=run_id,
        lap_number=2,
        event_type="PLATFORM_LOW",
        lap_pct_peak=67.02,
        distance_m_peak=2864.23,
        zone_name="65-70%",
        severity="high",
        confidence_score=0.78,
        valid_for_tuning=True,
        primary_metric_name="cfsr_height_mm",
        primary_metric_value=3.58,
        evidence_json={"speed_mph": 186.08},
    )
    drag_event = TelemetryEvent(
        event_id=f"{run_id}:event:drag",
        run_id=run_id,
        lap_number=2,
        event_type="FULL_THROTTLE_SPEED_LOSS",
        lap_pct_start=55,
        lap_pct_end=60,
        zone_name="55-60%",
        severity="high",
        confidence_score=0.7,
        valid_for_tuning=True,
        primary_metric_name="speed_delta_mph",
        primary_metric_value=-1.32,
        evidence_json={"avg_throttle_pct": 100, "avg_brake_pct": 0},
    )
    setup = SetupSnapshot(
        setup_id=f"{run_id}:setup",
        run_id=run_id,
        setup_name="talladega.sto",
        tape_percent=10,
        rear_end_ratio=3.45,
        lf_ride_height_mm=66,
        rf_ride_height_mm=77,
        lr_ride_height_mm=127,
        rr_ride_height_mm=137,
    )
    recommendation = Recommendation(
        recommendation_id=f"{run_id}:rec:1",
        run_id=run_id,
        issue="Speed decay under full throttle",
        cause_bucket="aero/platform + steering scrub suspicion",
        recommendation_text="Run one controlled platform/scrub test.",
        confidence_score=0.72,
        evidence_strength="medium",
        do_not_change_warnings=["Do not change gear and tape in the same test."],
    )
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            track_display_name="Talladega Super Speedway",
            car_name="Chevrolet Camaro ZL1 Class A",
            session_type="Test",
            setup_name="talladega.sto",
            telemetry_rate_hz=60,
            record_count=6277,
        ),
        best_useful_lap=lap,
        laps=[lap],
        events=[platform_event, drag_event],
        setup_snapshot=setup,
        recommendations=[recommendation],
        primary_findings=["Lap 2 is useful.", "55-70% behaves like a drag/scrub risk zone."],
        next_test="Run one controlled platform/scrub test.",
    )


def test_markdown_report_contract() -> None:
    expected = json.loads(Path("tests/fixtures/talladega_baseline_expected.json").read_text(encoding="utf-8"))
    report = generate_markdown_report(_sample_overview())

    for section in expected["required_report_sections"]:
        assert section in report
    assert "Lap 2 is useful." in report
    assert "55-60%" in report
    assert "Do not change gear and tape in the same test." in report
