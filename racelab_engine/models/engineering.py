"""Structural evidence contracts shared by phase-aware engineering engines."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.evidence import EvidenceState


class EngineeringModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EngineeringConclusion(EngineeringModel):
    key: str
    summary: str
    evidence_state: EvidenceState
    confidence_score: float = Field(ge=0.0, le=1.0)
    source_channels: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
    recommendation: str | None = None

    @model_validator(mode="after")
    def require_structural_evidence(self) -> EngineeringConclusion:
        if self.evidence_state in {EvidenceState.UNAVAILABLE, EvidenceState.BLOCKED_BY_CONTEXT}:
            if not self.blocker_reasons:
                raise ValueError("blocked conclusions require blocker_reasons")
        elif not self.source_channels or not self.supporting_evidence:
            raise ValueError("evidence-bearing conclusions require sources and supporting evidence")
        return self


class EngineGate(EngineeringModel):
    contract_key: str
    eligible: bool
    confidence_cap: float = Field(ge=0.0, le=1.0)
    blocker_reasons: list[str] = Field(default_factory=list)
    needed_measurements: list[str] = Field(default_factory=list)


__all__ = ["EngineGate", "EngineeringConclusion", "EngineeringModel"]
