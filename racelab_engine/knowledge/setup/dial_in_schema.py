from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.models.evidence import EvidenceState

from .evidence_schema import CandidateEvidenceReadiness, RunEvidenceGroup


class DialInModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Clarification(DialInModel):
    needed: bool
    question: str | None = None
    options: list[str] = Field(default_factory=list)


class EvidenceStrengthSignal(DialInModel):
    level: Literal["unavailable", "capability_only", "observed_mechanism"]
    readiness: Literal["blocked", "measurement_required", "test_hypothesis_ready"]
    setup_test_ready: bool
    requires_controlled_test: bool = True
    capability_flags: list[str] = Field(default_factory=list)
    observed_mechanism_flags: list[str] = Field(default_factory=list)
    supporting_event_ids: list[str] = Field(default_factory=list)
    reason: str


class DialInSwing(DialInModel):
    id: str
    title: str
    change_this: str
    garage_lever: str
    control_keys: list[str] = Field(default_factory=list)
    direction_sign: Literal[-1, 1]
    setup_area: str
    change_size_label: str
    change_size_explanation: str
    influence_label: str
    control_expectation: str
    control_guardrail: str
    current_value_label: str | None = None
    proposed_value_label: str | None = None
    strength_label: str
    risk_label: str
    effect: str
    counter_effect: str
    one_change_test: str
    validate_with: list[str] = Field(default_factory=list)
    validate_with_labels: list[str] = Field(default_factory=list)
    watch_for: list[str] = Field(default_factory=list)
    watch_for_labels: list[str] = Field(default_factory=list)
    keep_if: str
    undo_if: str
    readiness_label: str
    disabled_reason: str | None = None
    evidence_state: EvidenceState = EvidenceState.NEEDS_CONFIRMATION
    source_channels: list[str] = Field(default_factory=list)
    observed_evidence_flags: list[str] = Field(default_factory=list)
    supporting_event_ids: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class HiddenEvidenceSummary(DialInModel):
    evidence_flags: list[str] = Field(default_factory=list)
    evidence_groups: list[RunEvidenceGroup] = Field(default_factory=list)
    present_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    readiness_by_candidate: list[CandidateEvidenceReadiness] = Field(default_factory=list)
    ranking_reasons: dict[str, list[str]] = Field(default_factory=dict)
    disabled_by_capability: list[dict[str, str]] = Field(default_factory=list)
    capability_flags: list[str] = Field(default_factory=list)
    observed_mechanism_flags: list[str] = Field(default_factory=list)
    supporting_event_ids: list[str] = Field(default_factory=list)


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
    evidence_state: EvidenceState = EvidenceState.NEEDS_CONFIRMATION
    source_channels: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrengthSignal | None = None
