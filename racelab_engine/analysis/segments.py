from __future__ import annotations

from statistics import mean
from typing import Any, Optional

from pydantic import BaseModel

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.platform import classify_splitter_height_mm


class SegmentSummary(BaseModel):
    segment_id: str
    run_id: str
    lap_number: Optional[int] = None
    segment_type: str = "fixed_pct"
    segment_name: str
    pct_start: float
    pct_end: float
    distance_start_m: Optional[float] = None
    distance_end_m: Optional[float] = None
    avg_speed_mph: Optional[float] = None
    min_speed_mph: Optional[float] = None
    max_speed_mph: Optional[float] = None
    speed_delta_mph: Optional[float] = None
    avg_rpm: Optional[float] = None
    rpm_delta: Optional[float] = None
    avg_throttle_pct: Optional[float] = None
    avg_brake_pct: Optional[float] = None
    avg_abs_steering_deg: Optional[float] = None
    max_abs_steering_deg: Optional[float] = None
    avg_lat_accel: Optional[float] = None
    min_splitter_mm: Optional[float] = None
    platform_risk_score: float = 0.0
    drag_scrub_score: float = 0.0
    driver_input_score: float = 0.0
    powertrain_score: float = 0.0
    confidence_score: float = 0.0


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def _values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key) is not None]


def _score_platform(splitter_mm: float | None) -> float:
    severity = classify_splitter_height_mm(splitter_mm)
    return {
        "scrape": 1.0,
        "critical": 0.9,
        "high": 0.75,
        "watch": 0.45,
        "safe": 0.1,
        "unavailable": 0.0,
    }[severity]


def build_fixed_pct_segments(table: Any, run_id: str = "unassigned", lap_number: int | None = None) -> list[SegmentSummary]:
    rows = normalize_telemetry_rows(table)
    if not rows:
        return []

    if lap_number is not None:
        rows = [row for row in rows if int(row.get("lap") or row.get("lap_number") or -1) == lap_number]
    if not rows:
        return []

    segments: list[SegmentSummary] = []
    for start in range(0, 100, 5):
        end = start + 5
        segment_rows = [row for row in rows if (pct := _pct(row.get("lap_dist_pct"))) is not None and start <= pct < end]
        if not segment_rows:
            continue

        speeds = _values(segment_rows, "speed_mph")
        rpms = _values(segment_rows, "rpm")
        throttles = _values(segment_rows, "throttle_pct")
        brakes = _values(segment_rows, "brake_pct")
        steering = _values(segment_rows, "abs_steering_deg")
        lat_accel = _values(segment_rows, "lat_accel")
        splitters = _values(segment_rows, "cfsr_height_mm")
        distances = _values(segment_rows, "lap_dist_m")

        speed_delta = speeds[-1] - speeds[0] if len(speeds) >= 2 else None
        rpm_delta = rpms[-1] - rpms[0] if len(rpms) >= 2 else None
        avg_throttle = mean(throttles) if throttles else None
        avg_brake = mean(brakes) if brakes else None
        avg_steering = mean(steering) if steering else None
        min_splitter = min(splitters) if splitters else None
        platform_score = _score_platform(min_splitter)
        driver_input_score = 1.0 if (avg_brake or 0.0) > 5.0 or (avg_throttle is not None and avg_throttle < 95.0) else 0.0
        drag_scrub_score = 0.0
        if speed_delta is not None and speed_delta < -0.5 and (avg_throttle or 0) >= 95.0 and (avg_brake or 0) <= 5.0:
            drag_scrub_score = min(1.0, abs(speed_delta) / 3.0 + (avg_steering or 0.0) / 90.0 + platform_score * 0.25)

        segments.append(
            SegmentSummary(
                segment_id=f"{run_id}:segment:{lap_number or 'all'}:{start}-{end}",
                run_id=run_id,
                lap_number=lap_number,
                segment_name=f"{start}-{end}%",
                pct_start=float(start),
                pct_end=float(end),
                distance_start_m=min(distances) if distances else None,
                distance_end_m=max(distances) if distances else None,
                avg_speed_mph=mean(speeds) if speeds else None,
                min_speed_mph=min(speeds) if speeds else None,
                max_speed_mph=max(speeds) if speeds else None,
                speed_delta_mph=speed_delta,
                avg_rpm=mean(rpms) if rpms else None,
                rpm_delta=rpm_delta,
                avg_throttle_pct=avg_throttle,
                avg_brake_pct=avg_brake,
                avg_abs_steering_deg=avg_steering,
                max_abs_steering_deg=max(steering) if steering else None,
                avg_lat_accel=mean(lat_accel) if lat_accel else None,
                min_splitter_mm=min_splitter,
                platform_risk_score=platform_score,
                drag_scrub_score=drag_scrub_score,
                driver_input_score=driver_input_score,
                powertrain_score=0.0,
                confidence_score=0.6 if len(segment_rows) >= 2 else 0.25,
            )
        )

    return segments
