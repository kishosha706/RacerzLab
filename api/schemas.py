from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.io.ibt_types import ImportStatus

DialInObjective = Literal["race-pace", "qualifying", "long-run", "tire-conservation", "driver-confidence"]
DialInPriority = Literal[
    "overall-pace",
    "entry-security",
    "center-rotation",
    "exit-drive",
    "tire-life",
    "platform-margin",
]


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class ImportIbtRequest(BaseModel):
    path: str


class CacheInfo(BaseModel):
    path: Optional[str] = None
    format: Optional[str] = None
    used_fallback: bool = False


class TrackMapResolution(BaseModel):
    status: str = "missing"  # matched | ambiguous | missing | manual_required
    map_id: Optional[str] = None
    map_name: Optional[str] = None
    confidence: str = "unknown"  # high | medium | low | unknown
    message: Optional[str] = None


class ImportIbtResponse(BaseModel):
    run_id: Optional[str] = None
    status: ImportStatus
    cache: Optional[CacheInfo] = None
    track_map: Optional[TrackMapResolution] = None
    analysis_status: Optional[str] = None  # imported | analyzing | ready | failed
    existing_run_updated: bool = False


class RunListItem(BaseModel):
    run_id: str
    car_name: Optional[str] = None
    track_name: Optional[str] = None
    setup_name: Optional[str] = None
    imported_at: Optional[str] = None
    best_lap_number: Optional[int] = None
    best_lap_time: Optional[float] = None
    best_lap_time_s: Optional[float] = None
    lap_count: Optional[int] = None
    has_setup_snapshot: bool = False
    primary_issue: Optional[str] = None


class DialInRequest(BaseModel):
    complaint: str
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    selected_lap: Optional[int] = Field(default=None, ge=1)
    selected_zone_start_pct: Optional[float] = Field(default=None, ge=0.0, lt=100.0)
    selected_zone_end_pct: Optional[float] = Field(default=None, gt=0.0, le=100.0)
    selected_zone_label: Optional[str] = Field(default=None, max_length=120)
    selected_phase: Optional[str] = Field(default=None, max_length=64)
    objective: DialInObjective = "race-pace"
    priority: DialInPriority = "overall-pace"
    baseline_run_id: Optional[str] = None
    test_run_id: Optional[str] = None
    car_family: Optional[str] = None
    track_family: Optional[str] = None
    package_archetype: Optional[str] = None
    limit: int = Field(default=3, ge=1, le=18)
    include_debug_evidence: bool = False


class ReportResponse(BaseModel):
    run_id: str
    markdown: str


class ChannelCatalogItem(BaseModel):
    name: str
    label: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    type: Optional[str] = None
    count: int = 1
    is_raw: bool = False
    is_calculated: bool = False
    is_canonical_alias: bool = False
    archive_column: Optional[str] = None
    provenance: Optional[str] = None
    health_status: Optional[str] = None
    health_warnings: list[str] = Field(default_factory=list)
    non_finite_sample_count: int = 0
    impossible_sample_count: int = 0
    impossible_range_rule: Optional[str] = None
    malformed_array_record_count: int = 0
    null_element_count: int = 0
    numeric_limit_hit_count: int = 0
    clipping_status: Optional[str] = None
    saturation_status: Optional[str] = None
    lower_bound_occupancy_fraction: Optional[float] = None
    upper_bound_occupancy_fraction: Optional[float] = None
    is_proxy: bool = False
    formula: Optional[str] = None
    dependencies: list[str] = Field(default_factory=list)
    used_by_charts: list[str] = Field(default_factory=list)
    used_by_events: list[str] = Field(default_factory=list)
    used_by_analyses: list[str] = Field(default_factory=list)
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    sample_value: Any = None
    missing_status: Optional[str] = None
    group: Optional[str] = None
    source: Optional[str] = None
    raw_name: Optional[str] = None
    canonical_name: Optional[str] = None
    canonical_mapping_kind: Optional[str] = None
    registry_status: Optional[str] = None
    archive_status: Optional[str] = None
    variation: Optional[str] = None
    count_as_time: bool = False
    base_sample_rate_hz: Optional[int] = None
    effective_sample_rate_hz: Optional[int] = None
    missing_fraction: Optional[float] = None


class ChannelSummaryItem(BaseModel):
    name: str
    label: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    type: Optional[str] = None
    count: int = 1
    is_raw: bool = False
    is_calculated: bool = False
    is_canonical_alias: bool = False
    archive_column: Optional[str] = None
    provenance: Optional[str] = None
    health_status: Optional[str] = None
    health_warnings: list[str] = Field(default_factory=list)
    non_finite_sample_count: int = 0
    impossible_sample_count: int = 0
    impossible_range_rule: Optional[str] = None
    malformed_array_record_count: int = 0
    null_element_count: int = 0
    numeric_limit_hit_count: int = 0
    clipping_status: Optional[str] = None
    saturation_status: Optional[str] = None
    lower_bound_occupancy_fraction: Optional[float] = None
    upper_bound_occupancy_fraction: Optional[float] = None
    is_proxy: bool = False
    missing_status: Optional[str] = None
    group: Optional[str] = None
    source: Optional[str] = None
    raw_name: Optional[str] = None
    canonical_name: Optional[str] = None
    canonical_mapping_kind: Optional[str] = None
    registry_status: Optional[str] = None
    archive_status: Optional[str] = None
    variation: Optional[str] = None
    count_as_time: bool = False
    base_sample_rate_hz: Optional[int] = None
    effective_sample_rate_hz: Optional[int] = None
    missing_fraction: Optional[float] = None


class TraceResponse(BaseModel):
    run_id: str
    lap: Optional[int] = None
    x_name: Optional[str] = None
    x_unit: Optional[str] = None
    x: Any
    x_by_name: Optional[dict[str, list[Any]]] = None
    channels: dict[str, Any]
    events: list[dict[str, Any]] = []
    sample_count: int
    downsample: int | str
    preserve_extrema: bool = False
    trace_meta: Optional[dict[str, Any]] = None


class PlatformEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    title: str
    severity: str
    confidence: str
    display_scope: str = "actionable"
    is_visible_default: bool = True
    reason_for_hidden: Optional[str] = None
    diagnostic_state: Literal["finding", "clear_check", "context"] = "finding"
    contributes_to_backend_evidence: bool = True
    lap: Optional[int] = None
    sample_index: int
    lap_dist_ft: Optional[float] = None
    lap_pct: Optional[float] = None
    track_x_ft: Optional[float] = None
    track_y_ft: Optional[float] = None
    primary_value: Optional[float] = None
    primary_unit: Optional[str] = None
    channels_used: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    is_proxy_based: bool = False
    proxy_warning: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_state: str = "needs_confirmation"
    source_channels: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)


class PlatformEventsReport(BaseModel):
    run_id: str
    lap: Optional[int] = None
    evidence_status: Literal["findings", "clear", "unavailable"]
    events: list[PlatformEventItem] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
