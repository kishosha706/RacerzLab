from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.engineering_knowledge import (
    CurrentEngineeringKnowledgeProjection,
)
from racelab_engine.models.crew_chief import CrewChiefTerminalDecision

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
    current_relevance: Literal[
        "supported_candidate", "blocked_candidate", "knowledge_only", "inapplicable"
    ]
    p32_opportunity_id: str | None = None
    knowledge_level: Literal[
        "educational_knowledge",
        "measurable_hypothesis",
        "p19_testable_control",
        "unsupported_remove",
    ]
    bridge_id: str
    bridge_sha256: str
    direction_sign: Literal[-1, 0, 1]
    experiment_factor_id: str | None = None
    p35_mechanism_ids: list[str] = Field(default_factory=list)
    p20_mechanism_ids: list[str] = Field(default_factory=list)
    possible_component_family_ids: list[str] = Field(default_factory=list)
    p26_component_family_ids: list[str] = Field(default_factory=list)
    current_candidate_component_ids: list[str] = Field(default_factory=list)
    current_supported_component_ids: list[str] = Field(default_factory=list)
    contradicted_component_ids: list[str] = Field(default_factory=list)
    blocked_component_ids: list[str] = Field(default_factory=list)
    unobservable_component_ids: list[str] = Field(default_factory=list)
    irrelevant_component_ids: list[str] = Field(default_factory=list)
    p32_performance_mechanism_ids: list[str] = Field(default_factory=list)
    inspection_tool_ids: list[str] = Field(default_factory=list)
    discriminator_contract_ids: list[str] = Field(default_factory=list)
    expected_vehicle_state_ids: list[str] = Field(default_factory=list)
    validation_metric_ids: list[str] = Field(default_factory=list)
    countereffect_state_ids: list[str] = Field(default_factory=list)
    protected_performance_outcome_ids: list[str] = Field(default_factory=list)
    rollback_condition_ids: list[str] = Field(default_factory=list)
    knowledge_applicability: Literal[
        "applicable", "educational_only", "blocked_by_build", "unsupported"
    ]
    runtime_evidence_state: EvidenceState
    knowledge_version: str
    knowledge_graph_sha256: str
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
    engineering_knowledge: CurrentEngineeringKnowledgeProjection | None = None
    p19_terminal_decision: CrewChiefTerminalDecision | None = None

    @classmethod
    def from_internal(
        cls,
        response: DialInResponse,
        *,
        engineering_knowledge: CurrentEngineeringKnowledgeProjection | None = None,
        p19_terminal_decision: CrewChiefTerminalDecision | None = None,
        limit: int | None = None,
    ) -> DialInHypothesisResponse:
        from .engineering_knowledge import compile_mechanism_setup_bridges
        from .loader import load_setup_knowledge

        bridges = {
            item.effect_id: item for item in compile_mechanism_setup_bridges()
        }
        current_by_effect = {
            item.effect_id: item
            for item in (
                engineering_knowledge.hypotheses
                if engineering_knowledge is not None
                else ()
            )
        }
        authority_blocker = (
            "This Dial-In response is measurement guidance only. Only the controlled "
            "P19 workflow may authorize one exact setup target, Keep/Undo, or stop-testing."
        )
        swings = [
            DialInHypothesisSwing(
                **(
                    {
                        # This route has no current P19 decision to mirror.  A
                        # structurally controllable catalog effect therefore
                        # remains a measurable hypothesis here; level three is
                        # reserved for the atomic Crew/P19 projection.
                        "knowledge_level": (
                            current_by_effect[swing.id].level
                            if swing.id in current_by_effect
                            else "measurable_hypothesis"
                            if bridges[swing.id].catalog_classification
                            == "p19_testable_control"
                            else bridges[swing.id].catalog_classification
                        ),
                        "current_relevance": (
                            current_by_effect[swing.id].relevance
                            if swing.id in current_by_effect
                            else "knowledge_only"
                        ),
                        "p32_opportunity_id": (
                            current_by_effect[swing.id].p32_opportunity_id
                            if swing.id in current_by_effect
                            else None
                        ),
                        "bridge_id": bridges[swing.id].bridge_id,
                        "bridge_sha256": bridges[swing.id].bridge_sha256,
                        "direction_sign": bridges[swing.id].direction_sign,
                        "experiment_factor_id": bridges[swing.id].experiment_factor_id,
                        "p35_mechanism_ids": list(
                            current_by_effect[swing.id].p35_mechanism_ids
                            if swing.id in current_by_effect
                            else bridges[swing.id].p35_mechanism_ids
                        ),
                        "p20_mechanism_ids": list(
                            current_by_effect[swing.id].p20_mechanism_ids
                            if swing.id in current_by_effect
                            else bridges[swing.id].p20_mechanism_ids
                        ),
                        "possible_component_family_ids": list(
                            current_by_effect[swing.id].possible_component_family_ids
                            if swing.id in current_by_effect
                            else bridges[swing.id].p26_component_family_ids
                        ),
                        "p26_component_family_ids": list(
                            current_by_effect[swing.id].p26_component_family_ids
                            if swing.id in current_by_effect
                            else bridges[swing.id].p26_component_family_ids
                        ),
                        "current_candidate_component_ids": list(
                            current_by_effect[swing.id].current_candidate_component_ids
                            if swing.id in current_by_effect
                            else ()
                        ),
                        "current_supported_component_ids": list(
                            current_by_effect[swing.id].current_supported_component_ids
                            if swing.id in current_by_effect
                            else ()
                        ),
                        "contradicted_component_ids": list(
                            current_by_effect[swing.id].contradicted_component_ids
                            if swing.id in current_by_effect
                            else ()
                        ),
                        "blocked_component_ids": list(
                            current_by_effect[swing.id].blocked_component_ids
                            if swing.id in current_by_effect
                            else ()
                        ),
                        "unobservable_component_ids": list(
                            current_by_effect[swing.id].unobservable_component_ids
                            if swing.id in current_by_effect
                            else ()
                        ),
                        "irrelevant_component_ids": list(
                            current_by_effect[swing.id].irrelevant_component_ids
                            if swing.id in current_by_effect
                            else ()
                        ),
                        "p32_performance_mechanism_ids": list(
                            bridges[swing.id].p32_performance_mechanism_ids
                        ),
                        "inspection_tool_ids": list(
                            current_by_effect[swing.id].inspection_tool_ids
                            if swing.id in current_by_effect
                            else bridges[swing.id].inspection_tool_ids
                        ),
                        "discriminator_contract_ids": list(
                            current_by_effect[swing.id].discriminator_contract_ids
                            if swing.id in current_by_effect
                            else bridges[swing.id].discriminator_contract_ids
                        ),
                        "expected_vehicle_state_ids": list(
                            bridges[swing.id].expected_vehicle_state_ids
                        ),
                        "validation_metric_ids": list(
                            bridges[swing.id].validation_metric_ids
                        ),
                        "countereffect_state_ids": list(
                            bridges[swing.id].countereffect_state_ids
                        ),
                        "protected_performance_outcome_ids": list(
                            bridges[swing.id].protected_performance_outcome_ids
                        ),
                        "rollback_condition_ids": list(
                            bridges[swing.id].rollback_condition_ids
                        ),
                        "knowledge_applicability": (
                            current_by_effect[swing.id].knowledge_applicability
                            if swing.id in current_by_effect
                            else "unsupported"
                            if bridges[swing.id].catalog_classification
                            == "unsupported_remove"
                            else "educational_only"
                        ),
                        "runtime_evidence_state": (
                            EvidenceState(
                                current_by_effect[swing.id].runtime_evidence_state
                            )
                            if swing.id in current_by_effect
                            else EvidenceState.UNAVAILABLE
                        ),
                        "knowledge_version": bridges[swing.id].knowledge_version,
                        "knowledge_graph_sha256": (
                            bridges[swing.id].p35_knowledge_graph_sha256
                        ),
                    }
                ),
                id=swing.id,
                title=" ".join(swing.setup_area.replace("_", " ").split()).title(),
                setup_area=swing.setup_area,
                candidate_control_label=swing.garage_lever,
                related_control_keys=list(swing.control_keys),
                influence_label=swing.influence_label,
                strength_label=swing.strength_label,
                risk_label=swing.risk_label,
                mechanism_to_verify=(
                    "Separate current evidence for "
                    + ", ".join(
                        item.removeprefix("mechanism:").replace("_", " ")
                        for item in bridges[swing.id].p35_mechanism_ids
                    )
                    if bridges[swing.id].p35_mechanism_ids
                    else "This effect is not applicable to the current Next Gen control set."
                ),
                counter_effect_to_watch=(
                    "Protect "
                    + ", ".join(
                        item.replace("_", " ")
                        for item in bridges[swing.id].countereffect_targets
                    )
                    + " during controlled measurement."
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
                evidence_state=(
                    EvidenceState(current_by_effect[swing.id].runtime_evidence_state)
                    if swing.id in current_by_effect
                    else EvidenceState.UNAVAILABLE
                ),
                source_channels=list(swing.source_channels),
                observed_evidence_flags=list(swing.observed_evidence_flags),
                supporting_event_ids=list(swing.supporting_event_ids),
                blocker_reasons=list(dict.fromkeys((*swing.blocker_reasons, authority_blocker))),
            )
            for swing in response.top_swings
        ]
        if engineering_knowledge is not None:
            existing_ids = {item.id for item in swings}
            effects = {
                item.effect_id: item
                for item in load_setup_knowledge().setup_effects
            }
            for effect_id in engineering_knowledge.leading_hypothesis_ids:
                if effect_id in existing_ids:
                    continue
                current = current_by_effect[effect_id]
                bridge = bridges[effect_id]
                effect = effects[effect_id]
                swings.append(
                    DialInHypothesisSwing(
                        id=effect_id,
                        title=" ".join(current.setup_area.replace("_", " ").split()).title(),
                        setup_area=current.setup_area,
                        current_relevance=current.relevance,
                        p32_opportunity_id=current.p32_opportunity_id,
                        knowledge_level=current.level,
                        bridge_id=bridge.bridge_id,
                        bridge_sha256=bridge.bridge_sha256,
                        direction_sign=current.direction_sign,
                        experiment_factor_id=current.experiment_factor_id,
                        p35_mechanism_ids=list(current.p35_mechanism_ids),
                        p20_mechanism_ids=list(current.p20_mechanism_ids),
                        possible_component_family_ids=list(
                            current.possible_component_family_ids
                        ),
                        p26_component_family_ids=list(
                            current.p26_component_family_ids
                        ),
                        current_candidate_component_ids=list(
                            current.current_candidate_component_ids
                        ),
                        current_supported_component_ids=list(
                            current.current_supported_component_ids
                        ),
                        contradicted_component_ids=list(
                            current.contradicted_component_ids
                        ),
                        blocked_component_ids=list(current.blocked_component_ids),
                        unobservable_component_ids=list(
                            current.unobservable_component_ids
                        ),
                        irrelevant_component_ids=list(
                            current.irrelevant_component_ids
                        ),
                        p32_performance_mechanism_ids=list(
                            bridge.p32_performance_mechanism_ids
                        ),
                        inspection_tool_ids=list(current.inspection_tool_ids),
                        discriminator_contract_ids=list(
                            current.discriminator_contract_ids
                        ),
                        expected_vehicle_state_ids=list(
                            current.expected_vehicle_state_ids
                        ),
                        validation_metric_ids=list(current.validation_metric_ids),
                        countereffect_state_ids=list(
                            current.countereffect_state_ids
                        ),
                        protected_performance_outcome_ids=list(
                            current.protected_performance_outcome_ids
                        ),
                        rollback_condition_ids=list(current.rollback_condition_ids),
                        knowledge_applicability=current.knowledge_applicability,
                        runtime_evidence_state=EvidenceState(
                            current.runtime_evidence_state
                        ),
                        knowledge_version=bridge.knowledge_version,
                        knowledge_graph_sha256=bridge.p35_knowledge_graph_sha256,
                        candidate_control_label=" ".join(
                            current.setup_area.replace("_", " ").split()
                        ).title(),
                        related_control_keys=list(bridge.related_control_keys),
                        influence_label="Current mechanism relationship",
                        strength_label="Canonical P35 candidate",
                        risk_label=f"{effect.coupling_risk.title()} coupling",
                        mechanism_to_verify=current.physical_role,
                        counter_effect_to_watch=(
                            "Protect "
                            + ", ".join(current.protected_outcomes)
                            + " during controlled measurement."
                        ),
                        validate_with=list(current.expected_vehicle_response_ids),
                        validate_with_labels=[
                            item.replace("_", " ").title()
                            for item in current.expected_vehicle_response_ids
                        ],
                        watch_for=list(current.countereffect_ids),
                        watch_for_labels=[
                            item.replace("_", " ").title()
                            for item in current.countereffect_ids
                        ],
                        readiness_label="Measurement required",
                        measurement_needed=(
                            current.missing_evidence[0]
                            if current.missing_evidence
                            else "Use the candidate-owned bounded discriminator before any setup action."
                        ),
                        evidence_state=EvidenceState(current.runtime_evidence_state),
                        blocker_reasons=list(current.missing_evidence),
                    )
                )
            current_order = {
                effect_id: index
                for index, effect_id in enumerate(
                    engineering_knowledge.leading_hypothesis_ids
                )
            }
            swings.sort(
                key=lambda item: (
                    current_order.get(item.id, len(current_order)),
                    {
                        "supported_candidate": 0,
                        "blocked_candidate": 1,
                        "knowledge_only": 2,
                        "inapplicable": 3,
                    }[item.current_relevance],
                    item.setup_area,
                    item.id,
                )
            )
        if limit is not None:
            swings = swings[:limit]
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
            engineering_knowledge=engineering_knowledge,
            p19_terminal_decision=p19_terminal_decision,
        )
