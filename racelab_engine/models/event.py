from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    event_id: str
    run_id: str
    lap_number: Optional[int] = None
    event_type: str
    event_subtype: Optional[str] = None
    lap_pct_start: Optional[float] = None
    lap_pct_end: Optional[float] = None
    lap_pct_peak: Optional[float] = None
    distance_m_peak: Optional[float] = None
    zone_name: Optional[str] = None
    severity: str = "info"
    confidence_score: float = 0.0
    valid_for_tuning: bool = False
    primary_metric_name: Optional[str] = None
    primary_metric_value: Optional[float] = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    related_setup_keys: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
