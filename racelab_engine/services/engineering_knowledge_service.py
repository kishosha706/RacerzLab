"""Build the P35.1 current engineering-knowledge projection from canonical DTOs."""

from __future__ import annotations

from racelab_engine.knowledge.setup.engineering_knowledge import (
    compile_engineering_knowledge_coverage,
    compile_mechanism_setup_bridges,
)
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import CrewChiefTerminalDecision
from racelab_engine.models.engineering_learning import CrewChiefLearningPrior
from racelab_engine.models.engineering_knowledge import (
    CanonicalPerformanceOpportunityBinding,
    ControlledKnowledgeHistory,
    CurrentEngineeringKnowledgeProjection,
    CurrentKnowledgeHypothesis,
    MechanismSetupBridge,
    P19TestableControl,
)
from racelab_engine.models.engineering_projection import EngineeringAwarenessProjection
from racelab_engine.models.performance_intelligence import PerformanceIntelligenceProjection
from racelab_engine.models.vehicle_dynamics_knowledge import PerformanceMechanismAssessment
from racelab_engine.models.vehicle_systems import VehicleSystemsProjection


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
        eligible = tuple(
            bridge
            for bridge in bridges
            if p19_terminal_decision.control_key in bridge.related_control_keys
            and any(
                mechanism_id in supported_mechanisms | blocked_mechanisms
                for mechanism_id in bridge.p35_mechanism_ids
            )
        )
        if eligible:
            p19_bridge_id = eligible[0].bridge_id

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
                control_key=decision.control_key,
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
                p26_component_family_ids=tuple(
                    component_id
                    for component_id in bridge.p26_component_family_ids
                    if component_id in {state.component_id for state in p26.component_states}
                ),
                response_regimes=bridge.response_regimes,
                relevant_phases=bridge.relevant_phases,
                expected_vehicle_response_ids=bridge.validation_targets,
                countereffect_ids=bridge.countereffect_targets,
                protected_outcomes=bridge.protected_outcomes,
                inspection_tool_ids=bridge.inspection_tool_ids,
                support_artifact_ids=support_ids,
                contradiction_artifact_ids=contradiction_ids,
                discriminator_contract_ids=discriminator_ids,
                missing_evidence=missing_evidence,
                controlled_history=_history_for_bridge(bridge, p33),
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
    leading = tuple(
        item.effect_id
        for item in hypotheses
        if item.relevance in {"supported_candidate", "blocked_candidate"}
    )[:8]
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
    body = {
        "schema_version": "p351.workflow-performance-opportunity.v1",
        "p32_projection_sha256": p32.projection_sha256,
        "p32_opportunity_id": opportunity_id,
        "engineering_knowledge_projection_sha256": knowledge.projection_sha256,
        "start_pct": canonical.start_pct,
        "end_pct": canonical.end_pct,
        "phase": canonical.phase,
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
