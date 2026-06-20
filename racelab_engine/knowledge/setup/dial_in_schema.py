from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .evidence_schema import CandidateEvidenceReadiness, RunEvidenceGroup


class DialInModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Clarification(DialInModel):
    needed: bool
    question: str | None = None
    options: list[str] = Field(default_factory=list)


class DialInSwing(DialInModel):
    id: str
    title: str
    change_this: str
    garage_lever: str
    setup_area: str
    strength_label: str
    risk_label: str
    effect: str
    counter_effect: str
    one_change_test: str
    validate_with: list[str] = Field(default_factory=list)
    validate_with_labels: list[str] = Field(default_factory=list)
    watch_for: list[str] = Field(default_factory=list)
    watch_for_labels: list[str] = Field(default_factory=list)
    readiness_label: str
    disabled_reason: str | None = None
    debug: dict[str, Any] | None = None


class HiddenEvidenceSummary(DialInModel):
    evidence_flags: list[str] = Field(default_factory=list)
    evidence_groups: list[RunEvidenceGroup] = Field(default_factory=list)
    present_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    readiness_by_candidate: list[CandidateEvidenceReadiness] = Field(default_factory=list)
    ranking_reasons: dict[str, list[str]] = Field(default_factory=dict)
    disabled_by_capability: list[dict[str, str]] = Field(default_factory=list)


class DialInResponse(DialInModel):
    run_id: str
    complaint_raw: str
    interpreted_symptom: str | None = None
    interpreted_phase: str | None = None
    balance_direction: str | None = None
    confidence_label: str
    readiness_label: str
    driver_message: str
    top_swings: list[DialInSwing] = Field(default_factory=list)
    next_step: str | None = None
    validation_summary: str | None = None
    clarification: Clarification
    hidden_evidence_summary: HiddenEvidenceSummary | None = None
    warnings: list[str] = Field(default_factory=list)
