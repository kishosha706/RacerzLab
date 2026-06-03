from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EvidenceStatus = Literal["ready", "partially_ready", "missing", "unavailable", "unknown"]
MatcherReadiness = Literal["ready", "partially_ready", "missing_key_evidence"]


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunEvidenceGroup(EvidenceModel):
    group_id: str
    label: str
    status: EvidenceStatus
    present_items: list[str] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)
    channels_present: list[str] = Field(default_factory=list)
    channels_missing: list[str] = Field(default_factory=list)
    source: str
    notes: list[str] = Field(default_factory=list)
    confidence_boost: float = 0.0
    can_support_setup_knowledge: bool = False


class RunEvidenceContext(EvidenceModel):
    run_id: str
    car_name: str | None = None
    car_family: str
    track_name: str | None = None
    track_family: str
    setup_snapshot_status: EvidenceStatus
    evidence_groups: list[RunEvidenceGroup] = Field(default_factory=list)
    evidence_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unavailable_reasons: dict[str, str] = Field(default_factory=dict)


class CandidateEvidenceReadiness(EvidenceModel):
    effect_id: str
    readiness: MatcherReadiness
    present_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    readiness_reason: str
