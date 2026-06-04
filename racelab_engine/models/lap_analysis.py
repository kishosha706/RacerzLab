"""Lap analysis models for the Laps intelligence system."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LapQualitySummary(BaseModel):
    """Extended lap summary with quality and risk metrics."""
    run_id: str
    lap_number: int
    lap_time: Optional[float] = None
    lap_type: str = "unknown"
    is_complete: bool = False
    is_useful: bool = False
    classification_tags: list[str] = Field(default_factory=list)
    valid_for_compare: bool = False
    invalid_reasons: list[str] = Field(default_factory=list)
    avg_speed_mph: Optional[float] = None
    max_speed_mph: Optional[float] = None
    min_speed_mph: Optional[float] = None
    min_splitter_mm: Optional[float] = None
    min_rear_ride_height_mm: Optional[float] = None
    front_platform_risk_score: Optional[float] = None
    rear_platform_risk_score: Optional[float] = None
    whole_car_bottoming_risk: Optional[float] = None
    drag_scrub_suspicion_peak: Optional[float] = None
    shock_activity_index_avg: Optional[float] = None
    tire_temp_spread_avg: Optional[float] = None
    tire_pressure_gain_avg: Optional[float] = None
    camber_bias_max: Optional[float] = None
    grade_context_label: Optional[str] = None
    setup_name: Optional[str] = None
    track_name: Optional[str] = None
    car_name: Optional[str] = None
    session_date: Optional[str] = None


class LapWindowSummary(BaseModel):
    """Summary of a consecutive lap window."""
    window_id: str
    run_id: str
    car_name: Optional[str] = None
    track_name: Optional[str] = None
    start_lap: int
    end_lap: int
    window_size: int
    total_time: Optional[float] = None
    average_lap_time: Optional[float] = None
    fastest_lap_time: Optional[float] = None
    slowest_lap_time: Optional[float] = None
    lap_time_std_dev: Optional[float] = None
    falloff_sec: Optional[float] = None
    falloff_sec_per_lap: Optional[float] = None
    consistency_score: float = 0.0
    valid_lap_count: int = 0
    excluded_laps: list[dict[str, Any]] = Field(default_factory=list)
    classification_tags: list[str] = Field(default_factory=list)
    platform_risk_peak: Optional[float] = None
    rear_platform_risk_peak: Optional[float] = None
    whole_car_bottoming_peak: Optional[float] = None
    tire_stress_score: float = 0.0
    shock_stress_score: float = 0.0
    confidence_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    pace_quality_score: Optional[float] = None
    pace_quality_label: Optional[str] = None
    evidence_confidence_score: Optional[float] = None
    evidence_confidence_label: Optional[str] = None
    setup_usefulness_score: Optional[float] = None
    setup_usefulness_label: Optional[str] = None
    pace_quality_warnings: list[str] = Field(default_factory=list)
    pace_quality_components: Optional[dict[str, float]] = None


class LapDegradationSummary(BaseModel):
    """Degradation/falloff analysis for a stint."""
    run_id: str
    lap_count: int
    early_window_laps: int = 0
    middle_window_laps: int = 0
    late_window_laps: int = 0
    early_avg_lap_time: Optional[float] = None
    middle_avg_lap_time: Optional[float] = None
    late_avg_lap_time: Optional[float] = None
    falloff_early_to_late: Optional[float] = None
    falloff_slope_sec_per_lap: Optional[float] = None
    tire_stress_trend: str = "unknown"
    platform_stress_trend: str = "unknown"
    cooling_stress_trend: str = "unknown"
    confidence_score: float = 0.0
    coaching_message: Optional[str] = None


class LapCompareSelection(BaseModel):
    """Validates a lap pair for comparison."""
    baseline_run_id: str
    baseline_lap: int
    test_run_id: str
    test_lap: int
    comparison_warnings: list[str] = Field(default_factory=list)
    can_compare_cleanly: bool = False
    reason: Optional[str] = None


class FastestLapGroup(BaseModel):
    """Group of fastest individual N laps."""
    label: str
    lap_count: int
    laps: list[LapQualitySummary] = Field(default_factory=list)
    average_lap_time: Optional[float] = None
    fastest_lap_time: Optional[float] = None
    slowest_lap_time: Optional[float] = None
    is_available: bool = False
    warning: Optional[str] = None
    pace_quality_score: Optional[float] = None
    pace_quality_label: Optional[str] = None
    evidence_confidence_score: Optional[float] = None
    evidence_confidence_label: Optional[str] = None
    setup_usefulness_score: Optional[float] = None
    setup_usefulness_label: Optional[str] = None
    pace_quality_warnings: list[str] = Field(default_factory=list)
    pace_quality_components: Optional[dict[str, float]] = None


class BestWindowGroup(BaseModel):
    """Best consecutive N-lap window."""
    label: str
    window_size: int
    windows: list[LapWindowSummary] = Field(default_factory=list)
    best_window: Optional[LapWindowSummary] = None
    is_available: bool = False
    warning: Optional[str] = None


class LapWindowsResponse(BaseModel):
    """Response for lap windows endpoint."""
    run_id: str
    fastest_groups: list[FastestLapGroup] = Field(default_factory=list)
    best_windows: list[BestWindowGroup] = Field(default_factory=list)
    degradation: Optional[LapDegradationSummary] = None
    total_valid_laps: int = 0
    total_laps: int = 0
    warnings: list[str] = Field(default_factory=list)


class StintSummary(BaseModel):
    """Table-ready summary of a run stint or consecutive lap window."""
    stint_id: str
    run_id: str
    setup_name: Optional[str] = None
    car_name: Optional[str] = None
    track_name: Optional[str] = None
    session_date: Optional[str] = None
    start_lap: int
    end_lap: int
    lap_count: int
    valid_lap_count: int
    avg_lap_time: Optional[float] = None
    best_lap_time: Optional[float] = None
    worst_lap_time: Optional[float] = None
    lap_time_std_dev: Optional[float] = None
    rolling_5_avg_best: Optional[float] = None
    rolling_10_avg_best: Optional[float] = None
    rolling_20_avg_best: Optional[float] = None
    rolling_30_avg_best: Optional[float] = None
    falloff_total: Optional[float] = None
    falloff_per_lap: Optional[float] = None
    early_avg: Optional[float] = None
    middle_avg: Optional[float] = None
    late_avg: Optional[float] = None
    consistency_score: Optional[float] = None
    pace_quality_score: Optional[float] = None
    evidence_confidence_score: Optional[float] = None
    setup_usefulness_score: Optional[float] = None
    tire_trend_label: str = "tire data limited"
    platform_trend_label: str = "platform data limited"
    shock_trend_label: str = "shock data limited"
    stint_label: str = "insufficient laps"
    warnings: list[str] = Field(default_factory=list)


class StintResponse(BaseModel):
    """Response for imported-data stint intelligence."""
    run_id: str
    stints: list[StintSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StintCompareRequest(BaseModel):
    """Request for comparing two computed stint summaries."""
    baseline_run_id: str
    baseline_stint_id: str
    test_run_id: str
    test_stint_id: str


class StintCompareResult(BaseModel):
    """Delta summary for two selected stints."""
    baseline_stint: StintSummary
    test_stint: StintSummary
    avg_delta: Optional[float] = None
    best_delta: Optional[float] = None
    rolling_5_delta: Optional[float] = None
    rolling_10_delta: Optional[float] = None
    rolling_20_delta: Optional[float] = None
    falloff_delta: Optional[float] = None
    consistency_delta: Optional[float] = None
    tire_trend_delta: str = "limited"
    platform_trend_delta: str = "limited"
    shock_trend_delta: str = "limited"
    verdict: str = "Data is limited; need more clean laps."
    summary: str = "Stint comparison is limited by available clean lap data."
