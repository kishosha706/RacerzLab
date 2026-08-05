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
    tire_stress_score: Optional[float] = None
    shock_stress_score: Optional[float] = None
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
    pace_quality_components: Optional[dict[str, Optional[float]]] = None


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
    pace_quality_components: Optional[dict[str, Optional[float]]] = None


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
    last_lap_time: Optional[float] = None
    avg_lap_time: Optional[float] = None
    best_lap_time: Optional[float] = None
    worst_lap_time: Optional[float] = None
    lap_time_std_dev: Optional[float] = None
    best_avg_by_size: dict[str, Optional[float]] = Field(default_factory=dict)
    best_average_size_flags: list[int] = Field(default_factory=list)
    is_best_fastest_lap: bool = False
    is_best_long_run: bool = False
    highlight_tags: list[str] = Field(default_factory=list)
    rolling_3_avg_best: Optional[float] = None
    rolling_5_avg_best: Optional[float] = None
    rolling_7_avg_best: Optional[float] = None
    rolling_10_avg_best: Optional[float] = None
    rolling_15_avg_best: Optional[float] = None
    rolling_20_avg_best: Optional[float] = None
    rolling_25_avg_best: Optional[float] = None
    rolling_30_avg_best: Optional[float] = None
    rolling_40_avg_best: Optional[float] = None
    rolling_50_avg_best: Optional[float] = None
    rolling_60_avg_best: Optional[float] = None
    falloff_total: Optional[float] = None
    falloff_per_lap: Optional[float] = None
    early_avg: Optional[float] = None
    middle_avg: Optional[float] = None
    late_avg: Optional[float] = None
    consistency_score: Optional[float] = None
    pace_quality_score: Optional[float] = None
    evidence_confidence_score: Optional[float] = None
    setup_usefulness_score: Optional[float] = None
    bucket_averages: list["StintBucket"] = Field(default_factory=list)
    lap_points: list["StintGraphPoint"] = Field(default_factory=list)
    is_primary_summary: bool = False
    is_best_for_size: bool = False
    display_group: str = "windows"
    display_label_short: str = "Window"
    rank_reason: Optional[str] = None
    tire_trend_label: str = "tire data limited"
    platform_trend_label: str = "platform data limited"
    shock_trend_label: str = "shock data limited"
    stint_label: str = "insufficient laps"
    warnings: list[str] = Field(default_factory=list)


class StintBucket(BaseModel):
    """Fixed lap-bucket average for timing-sheet style stint rows."""
    label: str
    start_offset: int
    end_offset: int
    avg_lap_time: Optional[float] = None
    lap_count: int = 0
    valid_lap_count: int = 0
    is_fastest_bucket: bool = False
    delta_from_best_bucket: Optional[float] = None
    warning: Optional[str] = None


class StintGraphPoint(BaseModel):
    """Lap-time point for graphing a selected stint without loading trace data."""
    stint_lap: int
    lap_number: int
    lap_time: Optional[float] = None
    valid: bool = False
    delta_to_best: Optional[float] = None
    rolling_5: Optional[float] = None
    avg_speed_mph: Optional[float] = None
    max_speed_mph: Optional[float] = None
    min_speed_mph: Optional[float] = None
    fuel: Optional[float] = None
    invalid_reason: Optional[str] = None
    warning: Optional[str] = None


class StintRunSummary(BaseModel):
    """Compact header summary for the selected imported run."""
    run_id: str
    setup_name: Optional[str] = None
    car_name: Optional[str] = None
    track_name: Optional[str] = None
    session_date: Optional[str] = None
    total_laps: int = 0
    valid_laps: int = 0
    best_lap_time: Optional[float] = None
    full_stint_avg: Optional[float] = None
    falloff_total: Optional[float] = None
    best_avg_by_size: dict[str, Optional[float]] = Field(default_factory=dict)
    best_3_avg: Optional[float] = None
    best_5_avg: Optional[float] = None
    best_7_avg: Optional[float] = None
    best_10_avg: Optional[float] = None
    best_15_avg: Optional[float] = None
    best_20_avg: Optional[float] = None
    best_25_avg: Optional[float] = None
    best_30_avg: Optional[float] = None
    best_40_avg: Optional[float] = None
    best_50_avg: Optional[float] = None
    best_60_avg: Optional[float] = None
    data_status: str = "Limited"
    warnings: list[str] = Field(default_factory=list)


class StintResponse(BaseModel):
    """Response for imported-data stint intelligence."""
    run_id: str
    stints: list[StintSummary] = Field(default_factory=list)
    stint_rows: list[StintSummary] = Field(default_factory=list)
    best_window_cards: list[StintSummary] = Field(default_factory=list)
    primary_stints: list[StintSummary] = Field(default_factory=list)
    all_windows: list[StintSummary] = Field(default_factory=list)
    run_summary: Optional[StintRunSummary] = None
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
    same_length_avg_delta: Optional[float] = None
    rolling_delta_by_size: dict[str, Optional[float]] = Field(default_factory=dict)
    comparison_warnings: list[str] = Field(default_factory=list)
    bucket_deltas: list["StintBucketDelta"] = Field(default_factory=list)
    falloff_delta: Optional[float] = None
    consistency_delta: Optional[float] = None
    tire_trend_delta: str = "limited"
    platform_trend_delta: str = "limited"
    shock_trend_delta: str = "limited"
    verdict: str = "Data is limited; need more clean laps."
    summary: str = "Stint comparison is limited by available clean lap data."


class StintBucketDelta(BaseModel):
    """Time delta for matching bucket labels between selected stints."""
    label: str
    delta: Optional[float] = None
    baseline_avg: Optional[float] = None
    test_avg: Optional[float] = None
    warning: Optional[str] = None
