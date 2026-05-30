from __future__ import annotations

from typing import Any

from racelab_engine.analysis.constants import (
    DRAG_SCRUB_MIN_SPEED_MPH,
    FULL_THROTTLE_PCT,
    LOW_BRAKE_PCT,
    RESISTANCE_COEFF_CRITICAL,
)
from racelab_engine.models.event import TelemetryEvent


def aero_normalized_resistance(row: dict[str, Any]) -> float:
    """Compute aero-normalized resistance coefficient.

    Returns deceleration (mph/s) divided by dynamic pressure (psf).
    Higher values mean more speed loss than expected for the current
    aero load — indicating mechanical scrub, drag, or platform issues.
    """
    decel_mph_s = max(0.0, -float(row.get("speed_rate_mph_s") or 0.0))
    dynamic_pressure_psf = max(float(row.get("dynamic_pressure_psf") or 0.0), 1.0)
    return decel_mph_s / dynamic_pressure_psf


def compute_drag_scrub_index(row: dict[str, Any]) -> float:
    """Canonical drag/scrub suspicion index (0.0–1.0).

    Uses aero-normalized resistance as the backbone, then blends in
    steering, yaw, and CFS risk signals. Only computes meaningful
    values during full-throttle, low-brake, high-speed conditions.
    Returns 0.0 outside those conditions.
    """
    speed = float(row.get("speed_mph") or 0.0)
    throttle = float(row.get("throttle_pct") or 0.0)
    brake = float(row.get("brake_pct") or 0.0)

    if speed < DRAG_SCRUB_MIN_SPEED_MPH:
        return 0.0
    if throttle < FULL_THROTTLE_PCT or brake > LOW_BRAKE_PCT:
        return 0.0

    # Aero-normalized resistance is the primary signal
    resistance_coeff = aero_normalized_resistance(row)
    resistance_index = min(1.0, resistance_coeff / RESISTANCE_COEFF_CRITICAL)

    steering = abs(float(row.get("abs_steering_deg") or 0.0))
    yaw_rate = abs(float(row.get("yaw_rate") or 0.0))
    cfs_risk = max(0.0, float(row.get("cfs_risk_score") or 0.0))

    index = (
        resistance_index * 0.45
        + min(steering / 15.0, 1.0) * 0.20
        + min(yaw_rate / 1.0, 1.0) * 0.15
        + min(cfs_risk, 1.0) * 0.10
        # Reserve 0.10 for future yaw-error component
    )
    return max(0.0, min(1.0, index))


def detect_drag_scrub_risk_zones(table_or_segments: Any, run_id: str = "unassigned", lap_number: int | None = None) -> list[TelemetryEvent]:
    from racelab_engine.analysis.segments import SegmentSummary, build_fixed_pct_segments
    if table_or_segments is None:
        return []
    if isinstance(table_or_segments, list) and all(isinstance(item, SegmentSummary) for item in table_or_segments):
        segments = table_or_segments
    else:
        segments = build_fixed_pct_segments(table_or_segments, run_id=run_id, lap_number=lap_number)

    ranked = sorted(
        [segment for segment in segments if segment.drag_scrub_score >= 0.35],
        key=lambda segment: segment.drag_scrub_score,
        reverse=True,
    )
    return [
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
        for rank, segment in enumerate(ranked, start=1)
    ]
