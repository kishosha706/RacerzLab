from __future__ import annotations

from typing import Any

from racelab_engine.analysis.segments import SegmentSummary, build_fixed_pct_segments
from racelab_engine.models.event import TelemetryEvent


def detect_drag_scrub_risk_zones(table_or_segments: Any, run_id: str = "unassigned", lap_number: int | None = None) -> list[TelemetryEvent]:
    if table_or_segments is None:
        return []
    if isinstance(table_or_segments, list) and all(isinstance(item, SegmentSummary) for item in table_or_segments):
        segments = table_or_segments
    else:
        segments = build_fixed_pct_segments(table_or_segments, run_id=run_id, lap_number=lap_number)

    events: list[TelemetryEvent] = []
    ranked = sorted(
        [segment for segment in segments if segment.drag_scrub_score >= 0.35],
        key=lambda segment: segment.drag_scrub_score,
        reverse=True,
    )
    for rank, segment in enumerate(ranked, start=1):
        events.append(
            TelemetryEvent(
                event_id=f"{run_id}:drag-scrub:{segment.segment_name}",
                run_id=run_id,
                lap_number=segment.lap_number,
                event_type="FULL_THROTTLE_SPEED_LOSS",
                event_subtype="drag_scrub_like",
                lap_pct_start=segment.pct_start,
                lap_pct_end=segment.pct_end,
                lap_pct_peak=(segment.pct_start + segment.pct_end) / 2.0,
                distance_m_peak=segment.distance_start_m,
                zone_name=segment.segment_name,
                severity="high" if segment.drag_scrub_score >= 0.7 else "watch",
                confidence_score=segment.confidence_score,
                valid_for_tuning=segment.driver_input_score == 0.0,
                primary_metric_name="speed_delta_mph",
                primary_metric_value=segment.speed_delta_mph,
                evidence_json={
                    "rank": rank,
                    "avg_throttle_pct": segment.avg_throttle_pct,
                    "avg_brake_pct": segment.avg_brake_pct,
                    "avg_abs_steering_deg": segment.avg_abs_steering_deg,
                    "min_splitter_mm": segment.min_splitter_mm,
                    "drag_scrub_score": segment.drag_scrub_score,
                },
                related_setup_keys=["front_ride_height", "springs", "steering_offset", "rear_end_ratio"],
                recommended_actions=["Run one controlled platform/scrub test and compare this zone by lap percentage."],
            )
        )
    return events
