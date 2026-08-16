"""Build the P35.1 current engineering-knowledge projection from canonical DTOs."""

from __future__ import annotations

from racelab_engine.knowledge.setup.engineering_knowledge import (
    compile_engineering_knowledge_coverage,
    compile_mechanism_setup_bridges,
)
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.crew_chief import CrewChiefTerminalDecision
from racelab_engine.models.engineering_learning import CrewChiefLearningPrior
from racelab_engine.models.engineering_knowledge import (
    CanonicalPerformanceOpportunityBinding,
    ControlledKnowledgeHistory,
    CanonicalPhysicalSegment,
    CurrentEngineeringKnowledgeProjection,
    CurrentKnowledgeHypothesis,
    MechanismSetupBridge,
    P19TestableControl,
)
from racelab_engine.models.engineering_projection import EngineeringAwarenessProjection
from racelab_engine.models.performance_intelligence import PerformanceIntelligenceProjection
from racelab_engine.models.vehicle_dynamics_knowledge import PerformanceMechanismAssessment
from racelab_engine.models.vehicle_systems import VehicleSystemsProjection


_POSITIVE_EVIDENCE_PRIORITY = {
    EvidenceState.CONTROLLED_TEST_EFFECT.value: 0,
    EvidenceState.OBSERVED_CORRELATION.value: 1,
    EvidenceState.MEASURED.value: 2,
    EvidenceState.CALCULATED.value: 3,
    EvidenceState.ESTIMATED_PROXY.value: 4,
}


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _component_truth(
    bridge: MechanismSetupBridge,
    p26: VehicleSystemsProjection,
) -> dict[str, tuple[str, ...]]:
    partitions: dict[str, list[str]] = {
        "candidate": [],
        "supported": [],
        "contradicted": [],
        "blocked": [],
        "unobservable": [],
        "irrelevant": [],
    }
    states = {
        state.component_id: state
        for state in p26.component_states
        if state.component_id in bridge.p26_component_family_ids
    }
    for component_id in bridge.p26_component_family_ids:
        state = states.get(component_id)
        if state is None:
            continue
        observability = {_enum_value(value) for value in state.observability_states}
        if (
            "unavailable" in observability
            or state.current_response_state == "unavailable"
        ):
            partitions["unobservable"].append(component_id)
            continue
        relevance = _enum_value(state.relevance)
        target = "supported" if relevance in {"supported", "tested"} else relevance
        if target in partitions:
            partitions[target].append(component_id)
    return {key: tuple(values) for key, values in partitions.items()}


def _runtime_evidence_state(
    *,
    support_ids: tuple[str, ...],
    matching_blocked: bool,
    p35: PerformanceMechanismAssessment,
) -> str:
    if matching_blocked:
        return "blocked_by_context"
    focus_states = {
        item.artifact_id: _enum_value(item.evidence_state)
        for item in p35.focus_artifacts
    }
    states = tuple(
        focus_states[artifact_id]
        for artifact_id in support_ids
        if artifact_id in focus_states
    )
    positive = tuple(
        state for state in states if state in _POSITIVE_EVIDENCE_PRIORITY
    )
    return (
        min(positive, key=_POSITIVE_EVIDENCE_PRIORITY.__getitem__)
        if positive
        else "unavailable"
    )


def _leading_hypotheses(
    hypotheses: list[CurrentKnowledgeHypothesis],
    *,
    next_discriminator_contract_id: str | None,
    limit: int = 8,
) -> tuple[str, ...]:
    current = [
        item
        for item in hypotheses
        if item.relevance in {"supported_candidate", "blocked_candidate"}
    ]
    selected: list[CurrentKnowledgeHypothesis] = []
    used_mechanisms: set[str] = set()
    used_components: set[str] = set()

    discriminator_owner = next(
        (
            item
            for item in current
            if next_discriminator_contract_id is not None
            and next_discriminator_contract_id in item.discriminator_contract_ids
        ),
        None,
    )
    if discriminator_owner is not None:
        selected.append(discriminator_owner)
        used_mechanisms.update(discriminator_owner.p35_mechanism_ids)
        used_components.update(discriminator_owner.p26_component_family_ids)

    for item in current:
        if item in selected:
            continue
        mechanisms = set(item.p35_mechanism_ids)
        components = set(item.p26_component_family_ids)
        if not (mechanisms - used_mechanisms or components - used_components):
            continue
        selected.append(item)
        used_mechanisms.update(mechanisms)
        used_components.update(components)
        if len(selected) == limit:
            break
    for item in current:
        if item not in selected:
            selected.append(item)
        if len(selected) == limit:
            break
    return tuple(item.effect_id for item in selected)


def _resolve_p19_bridge(
    *,
    bridges: tuple[MechanismSetupBridge, ...],
    p26: VehicleSystemsProjection,
    active_mechanism_ids: set[str],
    decision: CrewChiefTerminalDecision,
) -> MechanismSetupBridge:
    eligible = tuple(
        bridge
        for bridge in bridges
        if bridge.effect_id == decision.setup_effect_id
        and decision.control_key in bridge.related_control_keys
        and bridge.direction_sign == decision.direction_sign
        and bridge.experiment_factor_id == decision.experiment_factor_id
        and any(
            factor.factor_id == bridge.experiment_factor_id
            and decision.control_key
            in (*factor.primary_controls, *factor.coordinated_controls)
            for factor in p26.experiment_factors
        )
        and any(
            mechanism_id in active_mechanism_ids
            for mechanism_id in bridge.p35_mechanism_ids
        )
    )
    if len(eligible) != 1:
        raise ValueError(
            "The exact P19 action does not resolve to one effect, direction, "
            "experiment factor, and active mechanism bridge."
        )
    return eligible[0]


def _history_for_bridge(
    bridge: MechanismSetupBridge,
    prior: CrewChiefLearningPrior,
) -> tuple[ControlledKnowledgeHistory, ...]:
    records: list[ControlledKnowledgeHistory] = []
    for fingerprint in prior.car_response_history:
        if fingerprint.transfer_level not in {"exact", "compatible"}:
            continue
        response = fingerprint.response
        if (
            response.component not in bridge.p26_component_family_ids
            or response.control not in bridge.related_control_keys
        ):
            continue
        for index, experience_id in enumerate(fingerprint.source_experience_ids):
            workflow_id = fingerprint.source_workflow_ids[
                min(index, len(fingerprint.source_workflow_ids) - 1)
            ]
            records.append(
                ControlledKnowledgeHistory(
                    experience_id=experience_id,
                    workflow_id=workflow_id,
                    component_family_id=response.component,
                    control_key=response.control,
                    transfer_level=fingerprint.transfer_level,
                    mechanism_assessment=response.p19_mechanism_assessment,
                    control_response=response.control_response_assessment,
                    policy_verdict=response.policy_verdict,
                    countereffects=response.countereffects,
                    source_artifact_ids=response.source_artifact_ids,
                )
            )
    return tuple(records)


def build_current_engineering_knowledge(
    *,
    run_id: str,
    session_id: str,
    complaint_prior: str | None,
    p20: EngineeringAwarenessProjection,
    p26: VehicleSystemsProjection,
    p32: PerformanceIntelligenceProjection,
    p35: PerformanceMechanismAssessment,
    p33: CrewChiefLearningPrior,
    p19_terminal_decision: CrewChiefTerminalDecision,
) -> CurrentEngineeringKnowledgeProjection:
    """Compile one shared view without reinterpreting producer-owned evidence."""

    if (
        p20.run_id != run_id
        or p20.session_id != session_id
        or getattr(p26, "run_id", run_id) != run_id
        or getattr(p26, "session_id", session_id) != session_id
        or p32.run_id != run_id
        or p32.session_id != session_id
        or p35.run_id != run_id
        or p35.session_id != session_id
        or p33.run_id != run_id
        or p33.session_id != session_id
    ):
        raise ValueError("P35.1 inputs must share one exact run/session")
    if (
        p20.reasoning_snapshot_id != p35.p19_reasoning_snapshot_sha256
        or p20.state_revision != p35.p20_state_revision
        or p26.reasoning_snapshot_sha256 != p35.p19_reasoning_snapshot_sha256
        or p26.knowledge_graph_sha256 != p35.p26_knowledge_graph_sha256
        or p32.projection_sha256 != p35.p32_projection_sha256
        or p32.p19_reasoning_snapshot_sha256 != p35.p19_reasoning_snapshot_sha256
        or p33.p19_reasoning_snapshot_sha256 != p35.p19_reasoning_snapshot_sha256
        or p33.p32_projection_sha256 != p35.p32_projection_sha256
    ):
        raise ValueError("P35.1 canonical producer identities do not form one truth")

    coverage = compile_engineering_knowledge_coverage()
    bridges = compile_mechanism_setup_bridges()
    candidates = {item.mechanism_id: item for item in p35.candidates}
    supported_mechanisms = {
        item.mechanism_id for item in p35.candidates if item.relevance == "candidate"
    }
    blocked_mechanisms = {
        item.mechanism_id for item in p35.candidates if item.relevance == "blocked"
    }
    p32_opportunity_id = (
        p35.performance_opportunity_ids[0]
        if p35.performance_opportunity_ids
        else None
    )

    p19_bridge_id: str | None = None
    if (
        p19_terminal_decision.kind == "controlled_test"
        and p19_terminal_decision.control_key is not None
    ):
        p19_bridge_id = _resolve_p19_bridge(
            bridges=bridges,
            p26=p26,
            active_mechanism_ids=supported_mechanisms | blocked_mechanisms,
            decision=p19_terminal_decision,
        ).bridge_id

    hypotheses: list[CurrentKnowledgeHypothesis] = []
    for bridge in bridges:
        current_mechanism_ids = tuple(
            mechanism_id
            for mechanism_id in bridge.p35_mechanism_ids
            if mechanism_id in candidates
        )
        support_ids = tuple(
            artifact_id
            for mechanism_id in current_mechanism_ids
            for artifact_id in candidates[mechanism_id].support_artifact_ids
        )
        contradiction_ids = tuple(
            artifact_id
            for mechanism_id in current_mechanism_ids
            for artifact_id in candidates[mechanism_id].contradiction_artifact_ids
        )
        discriminator_ids = tuple(
            dict.fromkeys(
                contract_id
                for mechanism_id in current_mechanism_ids
                for contract_id in candidates[mechanism_id].discriminator_contract_ids
            )
        )
        matching_supported = any(
            mechanism_id in supported_mechanisms for mechanism_id in current_mechanism_ids
        )
        matching_blocked = any(
            mechanism_id in blocked_mechanisms for mechanism_id in current_mechanism_ids
        )
        if bridge.catalog_classification == "unsupported_remove":
            level = "unsupported_remove"
            relevance = "inapplicable"
            authority = "knowledge_only"
        elif matching_supported:
            level = "measurable_hypothesis"
            relevance = "supported_candidate"
            authority = "measurement_only"
        elif matching_blocked:
            level = "measurable_hypothesis"
            relevance = "blocked_candidate"
            authority = "measurement_only"
        else:
            level = "educational_knowledge"
            relevance = "knowledge_only"
            authority = "knowledge_only"

        component_truth = _component_truth(bridge, p26)
        current_component_ids = tuple(
            dict.fromkeys(
                (*component_truth["candidate"], *component_truth["supported"])
            )
        )
        knowledge_applicability = (
            "unsupported"
            if bridge.catalog_classification == "unsupported_remove"
            else "blocked_by_build"
            if p35.applicability_state != "ready"
            else "applicable"
            if relevance in {"supported_candidate", "blocked_candidate"}
            else "educational_only"
        )
        runtime_evidence_state = _runtime_evidence_state(
            support_ids=support_ids,
            matching_blocked=matching_blocked,
            p35=p35,
        )

        p19_control = None
        setup_authorized = False
        if bridge.bridge_id == p19_bridge_id:
            decision = p19_terminal_decision
            if (
                decision.control_key is None
                or decision.current_value is None
                or decision.proposed_value is None
                or decision.workflow_id is None
                or decision.workflow_revision is None
            ):
                raise ValueError("P35.1 cannot mirror an incomplete P19 controlled test")
            p19_control = P19TestableControl(
                effect_id=bridge.effect_id,
                control_key=decision.control_key,
                direction_sign=bridge.direction_sign,
                experiment_factor_id=bridge.experiment_factor_id,
                current_value=decision.current_value,
                proposed_value=decision.proposed_value,
                workflow_id=decision.workflow_id,
                workflow_revision=decision.workflow_revision,
                source_event_ids=decision.source_event_ids,
            )
            level = "p19_testable_control"
            authority = "exact_p19_projection"
            setup_authorized = True

        candidate_blockers = tuple(
            dict.fromkeys(
                blocker
                for mechanism_id in current_mechanism_ids
                for blocker in candidates[mechanism_id].blocker_reasons
            )
        )
        missing_evidence = candidate_blockers or (
            bridge.evidence_requirements
            if level in {"educational_knowledge", "measurable_hypothesis"}
            and not support_ids
            else ()
        )
        hypotheses.append(
            CurrentKnowledgeHypothesis(
                bridge_id=bridge.bridge_id,
                effect_id=bridge.effect_id,
                setup_area=bridge.setup_area,
                physical_role=bridge.physical_role,
                direction_sign=bridge.direction_sign,
                experiment_factor_id=bridge.experiment_factor_id,
                level=level,
                relevance=relevance,
                p32_opportunity_id=(
                    p32_opportunity_id
                    if relevance in {"supported_candidate", "blocked_candidate"}
                    else None
                ),
                p35_mechanism_ids=current_mechanism_ids,
                p20_mechanism_ids=tuple(
                    mechanism_id
                    for mechanism_id in bridge.p20_mechanism_ids
                    if mechanism_id
                    in {
                        state.mechanism.value
                        for state in p20.subsystem_states
                        if state.status == "ready"
                    }
                ),
                possible_component_family_ids=bridge.p26_component_family_ids,
                p26_component_family_ids=current_component_ids,
                current_candidate_component_ids=component_truth["candidate"],
                current_supported_component_ids=component_truth["supported"],
                contradicted_component_ids=component_truth["contradicted"],
                blocked_component_ids=component_truth["blocked"],
                unobservable_component_ids=component_truth["unobservable"],
                irrelevant_component_ids=component_truth["irrelevant"],
                response_regimes=bridge.response_regimes,
                relevant_phases=bridge.relevant_phases,
                expected_vehicle_response_ids=bridge.validation_targets,
                expected_vehicle_state_ids=bridge.expected_vehicle_state_ids,
                validation_metric_ids=bridge.validation_metric_ids,
                countereffect_ids=bridge.countereffect_targets,
                countereffect_state_ids=bridge.countereffect_state_ids,
                protected_outcomes=bridge.protected_outcomes,
                protected_performance_outcome_ids=(
                    bridge.protected_performance_outcome_ids
                ),
                rollback_condition_ids=bridge.rollback_condition_ids,
                inspection_tool_ids=bridge.inspection_tool_ids,
                support_artifact_ids=support_ids,
                contradiction_artifact_ids=contradiction_ids,
                discriminator_contract_ids=discriminator_ids,
                missing_evidence=missing_evidence,
                controlled_history=_history_for_bridge(bridge, p33),
                knowledge_applicability=knowledge_applicability,
                runtime_evidence_state=runtime_evidence_state,
                p19_control=p19_control,
                authority=authority,
                setup_authorized=setup_authorized,
            )
        )

    ordering = {
        "p19_testable_control": 0,
        "supported_candidate": 1,
        "blocked_candidate": 2,
        "knowledge_only": 3,
        "inapplicable": 4,
    }
    hypotheses.sort(
        key=lambda item: (
            ordering.get(item.level, ordering[item.relevance]),
            item.setup_area,
            item.effect_id,
        )
    )
    leading = _leading_hypotheses(
        hypotheses,
        next_discriminator_contract_id=p35.next_discriminator_contract_id,
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *p35.applicability_blockers,
                *p35.blocker_reasons,
                *p33.blocker_reasons,
            )
        )
    )
    return CurrentEngineeringKnowledgeProjection.build(
        run_id=run_id,
        session_id=session_id,
        complaint_prior=(
            " ".join(complaint_prior.split()) if complaint_prior else None
        ),
        p19_reasoning_snapshot_sha256=p35.p19_reasoning_snapshot_sha256,
        p20_state_revision=p20.state_revision,
        p26_knowledge_graph_sha256=p26.knowledge_graph_sha256,
        p32_projection_sha256=p32.projection_sha256,
        p35_assessment_sha256=p35.p35_assessment_sha256,
        p33_projection_sha256=p33.projection_sha256,
        bridge_coverage_sha256=coverage.report_sha256,
        p32_opportunity_id=p32_opportunity_id,
        hypotheses=tuple(hypotheses),
        leading_hypothesis_ids=leading,
        next_discriminator_contract_id=p35.next_discriminator_contract_id,
        blocker_reasons=blockers,
    )


def build_canonical_performance_opportunity_binding(
    *,
    p32: PerformanceIntelligenceProjection,
    knowledge: CurrentEngineeringKnowledgeProjection,
    workflow_opportunity: object,
) -> CanonicalPerformanceOpportunityBinding:
    """Bind a workflow to P32 without allowing its legacy analyzer a second truth."""

    opportunity_id = knowledge.p32_opportunity_id
    if opportunity_id is None or knowledge.p32_projection_sha256 != p32.projection_sha256:
        raise ValueError("P19 workflow requires one canonical P32 opportunity")
    matches = tuple(
        item
        for item in p32.opportunity_map.opportunities
        if item.opportunity_id == opportunity_id
    )
    if len(matches) != 1:
        raise ValueError("P35.1 canonical P32 opportunity identity is unavailable")
    canonical = matches[0]
    observed = canonical.local_delta_s
    packet_observed = getattr(workflow_opportunity, "observed_time_loss_s", None)
    if observed is None or observed <= 0.0:
        raise ValueError("P19 workflow requires a measured positive P32 time consequence")
    if (
        getattr(workflow_opportunity, "start_pct", None) != canonical.start_pct
        or getattr(workflow_opportunity, "end_pct", None) != canonical.end_pct
        or getattr(workflow_opportunity, "phase", None) != canonical.phase
        or packet_observed is None
        or abs(float(packet_observed) - observed) > 0.0001
    ):
        raise ValueError(
            "The workflow opportunity does not equal the canonical P32 opportunity; "
            "no parallel performance reality may reach P19."
        )
    source_channels = tuple(getattr(workflow_opportunity, "source_channels", ()))
    if not source_channels or not set(source_channels).issubset(canonical.source_channels):
        raise ValueError("Workflow evidence channels are not owned by the P32 opportunity")
    segment = CanonicalPhysicalSegment(
        start_pct=canonical.start_pct,
        end_pct=canonical.end_pct,
    )
    segment_body = {
        "schema_version": "p352.physical-segment-set.v1",
        "segments": [segment.model_dump(mode="json")],
        "circular_scope": False,
        "independence_unit": "one_contiguous_physical_window",
    }
    body = {
        "schema_version": "p352.workflow-performance-opportunity.v1",
        "p32_projection_sha256": p32.projection_sha256,
        "p32_opportunity_id": opportunity_id,
        "engineering_knowledge_projection_sha256": knowledge.projection_sha256,
        "start_pct": canonical.start_pct,
        "end_pct": canonical.end_pct,
        "phase": canonical.phase,
        "physical_segment_set_sha256": canonical_json_sha256(segment_body),
        "segments": segment_body["segments"],
        "circular_scope": False,
        "independence_unit": "one_contiguous_physical_window",
        "observed_time_effect_s": observed,
        "authority": "observation_only",
        "setup_authorized": False,
    }
    return CanonicalPerformanceOpportunityBinding.model_validate(
        {**body, "binding_sha256": canonical_json_sha256(body)}
    )


__all__ = [
    "build_canonical_performance_opportunity_binding",
    "build_current_engineering_knowledge",
]
