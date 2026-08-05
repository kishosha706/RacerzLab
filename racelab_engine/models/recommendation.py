from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from racelab_engine.models.evidence import EvidenceState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Recommendation(BaseModel):
    recommendation_id: str
    run_id: str
    priority_rank: int = 1
    issue: str
    cause_bucket: str = "unknown"
    recommendation_text: str
    confidence_score: float = 0.0
    evidence_strength: str = "unknown"
    success_metric: Optional[str] = None
    required_next_data: list[str] = Field(default_factory=list)
    do_not_change_warnings: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_state: EvidenceState = EvidenceState.UNAVAILABLE
    source_channels: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(
        default_factory=lambda: ["Evidence provenance was not recorded for this legacy recommendation."]
    )
    confidence_limit_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
