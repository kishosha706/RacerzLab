from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from racelab_engine.io.ibt_types import ImportStatus


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
    baseline_run_id: Optional[str] = None
    test_run_id: Optional[str] = None
    car_family: Optional[str] = None
    track_family: Optional[str] = None
    package_archetype: Optional[str] = None
    limit: int = Field(default=3, ge=1, le=10)
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
    is_proxy: bool = False
    formula: Optional[str] = None
    dependencies: list[str] = []
    used_by_charts: list[str] = []
    used_by_events: list[str] = []
    used_by_recommendations: list[str] = []
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    sample_value: Any = None
    missing_status: Optional[str] = None
    group: Optional[str] = None
    source: Optional[str] = None


class ChannelSummaryItem(BaseModel):
    name: str
    label: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    type: Optional[str] = None
    count: int = 1
    is_raw: bool = False
    is_calculated: bool = False
    is_proxy: bool = False
    missing_status: Optional[str] = None
    group: Optional[str] = None
    source: Optional[str] = None


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


class PlatformEventItem(BaseModel):
    event_id: str
    event_type: str
    title: str
    severity: str
    confidence: str
    display_scope: str = "actionable"
    is_visible_default: bool = True
    reason_for_hidden: Optional[str] = None
    contributes_to_backend_evidence: bool = True
    lap: Optional[int] = None
    sample_index: int
    lap_dist_ft: Optional[float] = None
    lap_pct: Optional[float] = None
    track_x_ft: Optional[float] = None
    track_y_ft: Optional[float] = None
    primary_value: Optional[float] = None
    primary_unit: Optional[str] = None
    channels_used: list[str] = []
    evidence: list[str] = []
    recommended_action: Optional[str] = None
    is_proxy_based: bool = False
    proxy_warning: Optional[str] = None
    metadata: dict[str, Any] = {}
