from __future__ import annotations

import polars as pl

from racelab_engine.analysis.drag_scrub import (
    aero_normalized_resistance,
    compute_drag_scrub_index,
    detect_drag_scrub_risk_zones,
)
from racelab_engine.analysis.segments import build_fixed_pct_segments
from racelab_engine.io.ibt_reader import _build_overview_drag_events, _qualify_overview_drag_events
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.segment import SegmentSummary


def test_aero_normalized_resistance_zero_decel() -> None:
    row = {"speed_rate_mph_s": 0.0, "dynamic_pressure_psf": 100.0}
    assert aero_normalized_resistance(row) == 0.0


def test_aero_normalized_resistance_positive() -> None:
    row = {"speed_rate_mph_s": -2.0, "dynamic_pressure_psf": 100.0}
    assert aero_normalized_resistance(row) == 0.02


def test_aero_normalized_resistance_requires_positive_dynamic_pressure() -> None:
    row = {"speed_rate_mph_s": -2.0, "dynamic_pressure_psf": 0.0}
    assert aero_normalized_resistance(row) is None


def test_drag_scrub_zero_below_min_speed() -> None:
    row = {"speed_mph": 100.0, "throttle_pct": 99.0, "brake_pct": 0.0}
    assert compute_drag_scrub_index(row) == 0.0


def test_drag_scrub_zero_during_braking() -> None:
    row = {"speed_mph": 180.0, "throttle_pct": 0.0, "brake_pct": 50.0}
    assert compute_drag_scrub_index(row) == 0.0


def test_drag_scrub_zero_low_throttle() -> None:
    row = {"speed_mph": 180.0, "throttle_pct": 50.0, "brake_pct": 0.0}
    assert compute_drag_scrub_index(row) == 0.0


def test_drag_scrub_nonzero_full_throttle() -> None:
    row = {
        "speed_mph": 180.0,
        "throttle_pct": 99.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -2.0,
        "dynamic_pressure_psf": 100.0,
        "abs_steering_deg": 2.0,
        "yaw_rate": 0.05,
        "cfs_risk_score": 0.2,
    }
    index = compute_drag_scrub_index(row)
    assert 0.0 < index <= 1.0


def test_drag_scrub_high_resistance() -> None:
    """High aero-normalized resistance should produce a high index."""
    row = {
        "speed_mph": 200.0,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -10.0,
        "dynamic_pressure_psf": 50.0,
        "abs_steering_deg": 30.0,
        "yaw_rate": 2.0,
        "cfs_risk_score": 1.0,
    }
    index = compute_drag_scrub_index(row)
    # resistance_coeff = 10/50 = 0.2, resistance_index = 0.2/0.02 capped at 1.0
    # steering = 30/15 capped at 1.0, yaw = 2.0/1.0 capped at 1.0, cfs = 1.0
    # index = 1.0*0.45 + 1.0*0.20 + 1.0*0.15 + 1.0*0.10 = 0.90
    assert index == 0.90


def test_drag_scrub_missing_fields_remain_unavailable() -> None:
    row: dict = {"speed_mph": 180.0, "throttle_pct": 99.0, "brake_pct": 0.0}
    assert compute_drag_scrub_index(row) is None


def test_segment_preserves_unavailable_drag_scrub_instead_of_converting_to_zero() -> None:
    rows = [
        {
            "lap_dist_pct": 0.10 + index * 0.001,
            "speed_mph": 180.0,
            "throttle_pct": 99.0,
            "brake_pct": 0.0,
        }
        for index in range(3)
    ]

    segments = build_fixed_pct_segments(rows, run_id="missing-drag")

    assert len(segments) == 1
    assert segments[0].drag_scrub_score is None
    assert detect_drag_scrub_risk_zones(segments) == []


def test_flat_or_positive_speed_delta_never_emits_speed_loss_event() -> None:
    base = {
        "segment_id": "run-1:lap:1:0-5",
        "run_id": "run-1",
        "lap_number": 1,
        "segment_name": "0-5%",
        "pct_start": 0.0,
        "pct_end": 5.0,
        "drag_scrub_score": 0.9,
        "driver_input_score": 0.0,
        "confidence_score": 0.9,
    }
    segments = [
        SegmentSummary(**base, speed_delta_mph=0.0),
        SegmentSummary(**{**base, "segment_id": "run-1:lap:1:5-10", "segment_name": "5-10%"}, speed_delta_mph=1.0),
    ]

    assert detect_drag_scrub_risk_zones(segments) == []


def test_persisted_negative_segment_emits_speed_loss_event() -> None:
    segment = SegmentSummary(
        segment_id="run-1:lap:1:0-5",
        run_id="run-1",
        lap_number=1,
        segment_name="0-5%",
        pct_start=0.0,
        pct_end=5.0,
        drag_scrub_score=0.9,
        speed_delta_mph=-2.0,
        driver_input_score=0.0,
        confidence_score=0.9,
    )

    events = detect_drag_scrub_risk_zones([segment])

    assert len(events) == 1
    assert events[0].event_type == "FULL_THROTTLE_SPEED_LOSS"
    assert events[0].valid_for_tuning is False
    assert "measurement_guidance" not in events[0].model_dump()
    assert events[0].evidence_state == "estimated_proxy"
    assert "speed_mph" in events[0].source_channels


def test_segment_speed_delta_is_track_ordered_and_endpoint_robust() -> None:
    rows = [
        {
            "lap_dist_pct": index / 1_000.0,
            "speed_mph": 180.0 - (2.0 * index / 39.0),
            "rpm": 8_000.0 - (200.0 * index / 39.0),
            "throttle_pct": 100.0,
            "brake_pct": 0.0,
        }
        for index in range(40)
    ]

    forward = build_fixed_pct_segments(rows, run_id="ordered")[0]
    reversed_segment = build_fixed_pct_segments(list(reversed(rows)), run_id="reversed")[0]

    assert forward.speed_delta_mph is not None
    assert forward.speed_delta_mph < 0.0
    assert reversed_segment.speed_delta_mph == forward.speed_delta_mph
    assert reversed_segment.rpm_delta == forward.rpm_delta

    frame_rows = [
        {
            **row,
            "lap_dist_m": index * 5.0,
            "speed_rate_mph_s": -0.1,
            "dynamic_pressure_psf": 100.0,
            "abs_steering_deg": 0.0,
            "yaw_rate": 0.0,
            "cfs_risk_score": 0.0,
            "lat_accel": 0.0,
            "cfsr_height_mm": 30.0,
        }
        for index, row in enumerate(rows)
    ]
    vectorized = build_fixed_pct_segments(pl.DataFrame(list(reversed(frame_rows))), run_id="vectorized")[0]
    assert vectorized.speed_delta_mph == forward.speed_delta_mph
    assert vectorized.rpm_delta == forward.rpm_delta

    flat_with_last_sample_outlier = [dict(row, speed_mph=180.0) for row in rows]
    flat_with_last_sample_outlier[-1]["speed_mph"] = 170.0
    robust = build_fixed_pct_segments(flat_with_last_sample_outlier, run_id="outlier")[0]
    assert robust.speed_delta_mph == 0.0


def test_overview_drag_does_not_run_without_an_eligible_selected_lap() -> None:
    events, warning = _build_overview_drag_events(
        [{"lap": 1, "lap_dist_pct": 0.5}],
        run_id="no-eligible-lap",
        best_lap=None,
    )

    assert events == []
    assert warning is None


def test_selected_lap_proximity_retains_observation_but_suppresses_action() -> None:
    event = TelemetryEvent(
        event_id="run-1:drag-scrub:0-5%",
        run_id="run-1",
        lap_number=1,
        event_type="FULL_THROTTLE_SPEED_LOSS",
        confidence_score=0.8,
        valid_for_tuning=True,
    )
    rows = [
        {
            "CarDistAhead": 30.0,
            "CarDistBehind": 500_000.0,
            "speed_mps": 60.0,
        }
    ]

    qualified, warning = _qualify_overview_drag_events([event], rows)

    assert len(qualified) == 1
    assert qualified[0].valid_for_tuning is False
    assert "measurement_guidance" not in qualified[0].model_dump()
    assert qualified[0].evidence_json["observation_withheld"] is True
    assert warning is not None
