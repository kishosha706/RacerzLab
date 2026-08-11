from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.models.evidence import EvidenceState


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    valid_for_tuning: bool = False
    primary_metric_name: Optional[str] = None
    primary_metric_value: Optional[float] = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    related_setup_keys: list[str] = Field(default_factory=list)
    is_proxy_based: bool = False
    proxy_warning: Optional[str] = None
    evidence_state: EvidenceState = EvidenceState.UNAVAILABLE
    source_channels: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(
        default_factory=lambda: ["Evidence provenance was not recorded for this legacy event."]
    )
