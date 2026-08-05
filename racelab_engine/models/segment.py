from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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
    drag_scrub_score: Optional[float] = None
    driver_input_score: float = 0.0
    powertrain_score: float = 0.0
    confidence_score: float = 0.0
