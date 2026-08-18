from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LapSummary(BaseModel):
    lap_id: str
    run_id: str
    lap_number: int
    lap_type: str = "unknown"
    is_complete: bool = False
    is_useful: bool = False
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    lap_time: Optional[float] = None
    timing_primary_clock: Literal["session_tick", "session_time", "unavailable"] = "session_time"
    timing_clock_state: Literal["qualified", "degraded", "blocked", "unavailable"] = "degraded"
    timing_epoch_count: int = 1
    session_time_duplicate_count: int = 0
    session_time_reverse_count: int = 0
    session_time_residual_p95_s: Optional[float] = None
    simulator_lap_time_s: Optional[float] = None
    simulator_lap_time_residual_s: Optional[float] = None
    lap_time_channel_corroboration: str = "unavailable"
    lap_delta_validity_corroboration: Optional[bool] = None
    timing_blockers: list[str] = Field(default_factory=list)
    pct_min: Optional[float] = None
    pct_max: Optional[float] = None
    pct_span: Optional[float] = None
    sample_count: int = 0
    avg_speed_mph: Optional[float] = None
    max_speed_mph: Optional[float] = None
    min_speed_mph: Optional[float] = None
    avg_rpm: Optional[float] = None
    min_rpm: Optional[float] = None
    max_rpm: Optional[float] = None
    avg_throttle_pct: Optional[float] = None
    max_throttle_pct: Optional[float] = None
    avg_brake_pct: Optional[float] = None
    max_brake_pct: Optional[float] = None
    min_splitter_mm: Optional[float] = None
    min_splitter_pct: Optional[float] = None
    min_splitter_distance_m: Optional[float] = None
    min_splitter_speed_mph: Optional[float] = None
    max_abs_steering_deg: Optional[float] = None
    avg_abs_steering_deg: Optional[float] = None
    classification_tags: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)
