from __future__ import annotations

import math
from typing import Any

from racelab_engine.analysis.constants import (
    DRAG_SCRUB_MIN_SPEED_MPH,
    FULL_THROTTLE_PCT,
    LOW_BRAKE_PCT,
    RESISTANCE_COEFF_CRITICAL,
    FORCE_PROXY_WARNING,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.event import TelemetryEvent


def _finite_number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def aero_normalized_resistance(row: dict[str, Any]) -> float | None:
    """Compute a dynamic-pressure-normalized deceleration proxy.

    Returns deceleration (mph/s) divided by dynamic pressure (psf).
    Higher values mean more speed loss per unit dynamic pressure. This is a
    resistance-like comparison proxy, not aerodynamic load, force, or CdA.
    """
    speed_rate = _finite_number(row, "speed_rate_mph_s")
    dynamic_pressure_psf = _finite_number(row, "dynamic_pressure_psf")
    if speed_rate is None or dynamic_pressure_psf is None or dynamic_pressure_psf <= 0:
        return None
    decel_mph_s = max(0.0, -speed_rate)
    return decel_mph_s / dynamic_pressure_psf


def compute_drag_scrub_index(row: dict[str, Any]) -> float | None:
    """Canonical drag/scrub suspicion index (0.0–1.0).

    Uses aero-normalized resistance as the backbone, then blends in
    steering, yaw, and CFS risk signals. Only computes meaningful
    values during full-throttle, low-brake, high-speed conditions.
    Returns 0.0 outside those conditions.
    """
    speed = _finite_number(row, "speed_mph")
    throttle = _finite_number(row, "throttle_pct")
    brake = _finite_number(row, "brake_pct")
    if speed is None or throttle is None or brake is None:
        return None

    if speed < DRAG_SCRUB_MIN_SPEED_MPH:
        return 0.0
    if throttle < FULL_THROTTLE_PCT or brake > LOW_BRAKE_PCT:
        return 0.0

    # Aero-normalized resistance is the primary signal
    resistance_coeff = aero_normalized_resistance(row)
    steering = _finite_number(row, "abs_steering_deg")
    yaw_rate = _finite_number(row, "yaw_rate")
    cfs_risk = _finite_number(row, "cfs_risk_score")
    if resistance_coeff is None or steering is None or yaw_rate is None or cfs_risk is None:
        return None
    resistance_index = min(1.0, resistance_coeff / RESISTANCE_COEFF_CRITICAL)

    steering = abs(steering)
    yaw_rate = abs(yaw_rate)
    cfs_risk = max(0.0, cfs_risk)

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
        [
            segment
            for segment in segments
            if segment.drag_scrub_score is not None and segment.drag_scrub_score >= 0.35
            and segment.speed_delta_mph is not None and segment.speed_delta_mph < 0.0
        ],
        key=lambda segment: segment.drag_scrub_score or 0.0,
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
            # Detectors emit observations only.  A central caller may promote
            # this after canonical lap/context/setup evidence is evaluated.
            valid_for_tuning=False,
            primary_metric_name="speed_delta_mph",
            primary_metric_value=segment.speed_delta_mph,
            evidence_json={
                "rank": rank,
                "avg_throttle_pct": segment.avg_throttle_pct,
                "avg_brake_pct": segment.avg_brake_pct,
                "avg_abs_steering_deg": segment.avg_abs_steering_deg,
                "min_splitter_mm": segment.min_splitter_mm,
                "drag_scrub_score": segment.drag_scrub_score,
                "detector_observation_candidate": segment.driver_input_score == 0.0,
            },
            related_setup_keys=["front_ride_height", "springs", "steering_offset", "rear_end_ratio"],
            is_proxy_based=True,
            proxy_warning=FORCE_PROXY_WARNING,
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            source_channels=[
                "lap_dist_pct",
                "speed_mph",
                "throttle_pct",
                "brake_pct",
                "abs_steering_deg",
                "yaw_rate",
            ],
            blocker_reasons=[],
        )
        for rank, segment in enumerate(ranked, start=1)
    ]
