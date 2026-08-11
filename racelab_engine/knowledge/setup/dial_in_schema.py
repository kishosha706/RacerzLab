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


class DialInHypothesisSwing(DialInModel):
    """Public, non-authorizing projection of an internal setup-effect candidate."""

    id: str
    title: str
    setup_area: str
    candidate_control_label: str
    related_control_keys: list[str] = Field(default_factory=list)
    influence_label: str
    strength_label: str
    risk_label: str
    mechanism_to_verify: str
    counter_effect_to_watch: str
    validate_with: list[str] = Field(default_factory=list)
    validate_with_labels: list[str] = Field(default_factory=list)
    watch_for: list[str] = Field(default_factory=list)
    watch_for_labels: list[str] = Field(default_factory=list)
    readiness_label: str
    measurement_needed: str
    evidence_state: EvidenceState
    source_channels: list[str] = Field(default_factory=list)
    observed_evidence_flags: list[str] = Field(default_factory=list)
    supporting_event_ids: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)


class DialInHypothesisResponse(DialInModel):
    """Public Dial-In contract: engineering hypotheses, never setup targets."""

    run_id: str
    complaint_raw: str
    interpreted_symptom: str | None = None
    interpreted_phase: str | None = None
    balance_direction: str | None = None
    confidence_label: str
    readiness_label: str
    driver_message: str
    top_swings: list[DialInHypothesisSwing] = Field(default_factory=list)
    next_step: str | None = None
    clarification: Clarification
    hidden_evidence_summary: HiddenEvidenceSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    evidence_state: EvidenceState = EvidenceState.NEEDS_CONFIRMATION
    source_channels: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrengthSignal | None = None

    @classmethod
    def from_internal(cls, response: DialInResponse) -> DialInHypothesisResponse:
        authority_blocker = (
            "This Dial-In response is measurement guidance only. Only the controlled "
            "P19 workflow may authorize one exact setup target, Keep/Undo, or stop-testing."
        )
        swings = [
            DialInHypothesisSwing(
                id=swing.id,
                title=" ".join(swing.setup_area.replace("_", " ").split()).title(),
                setup_area=swing.setup_area,
                candidate_control_label=swing.garage_lever,
                related_control_keys=list(swing.control_keys),
                influence_label=swing.influence_label,
                strength_label=swing.strength_label,
                risk_label=swing.risk_label,
                mechanism_to_verify=(
                    "Determine whether this control area's measured response contributes "
                    "to the selected symptom."
                ),
                counter_effect_to_watch=(
                    "Watch for a protected-phase regression or driver-execution change "
                    "during controlled measurement."
                ),
                validate_with=list(swing.validate_with),
                validate_with_labels=list(swing.validate_with_labels),
                watch_for=list(swing.watch_for),
                watch_for_labels=list(swing.watch_for_labels),
                readiness_label="Measurement required",
                measurement_needed=(
                    swing.blocker_reasons[0]
                    if swing.blocker_reasons
                    else "Repeat the selected symptom and phase on eligible, matched laps with the setup unchanged."
                ),
                evidence_state=swing.evidence_state,
                source_channels=list(swing.source_channels),
                observed_evidence_flags=list(swing.observed_evidence_flags),
                supporting_event_ids=list(swing.supporting_event_ids),
                blocker_reasons=list(dict.fromkeys((*swing.blocker_reasons, authority_blocker))),
            )
            for swing in response.top_swings
        ]
        strength = response.evidence_strength
        if strength is not None:
            strength = strength.model_copy(update={
                "setup_test_ready": False,
                "requires_controlled_test": True,
                "reason": f"{strength.reason} {authority_blocker}",
            })
        return cls(
            run_id=response.run_id,
            complaint_raw=response.complaint_raw,
            interpreted_symptom=response.interpreted_symptom,
            interpreted_phase=response.interpreted_phase,
            balance_direction=response.balance_direction,
            confidence_label=response.confidence_label,
            readiness_label="Measurement required",
            driver_message="Engineering hypotheses only; no setup change is authorized from this response.",
            top_swings=swings,
            next_step=(
                "Collect matched, eligible repeats for the selected phase, then use the "
                "controlled P19 workflow to decide whether one setup test is justified."
            ),
            clarification=response.clarification,
            hidden_evidence_summary=response.hidden_evidence_summary,
            warnings=list(dict.fromkeys((*response.warnings, authority_blocker))),
            evidence_state=response.evidence_state,
            source_channels=list(response.source_channels),
            blocker_reasons=list(dict.fromkeys((*response.blocker_reasons, authority_blocker))),
            evidence_strength=strength,
        )
