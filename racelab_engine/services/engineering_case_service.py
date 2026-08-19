"""Assemble the P35.4.3 canonical case from existing producer-owned truth."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.knowledge.engineering_semantic_registry import (
    compile_engineering_semantic_registry,
    semantic_entry,
)
from racelab_engine.models.engineering_case import (
    CanonicalEngineeringCase,
    CaseQuantityObservability,
    CapabilityEvidenceResolution,
    EngineeringCaseCampaignCapture,
    EngineeringResponseArtifact,
    EngineeringSemanticFocusState,
    P19ResponseAdmission,
    P19ResponseCauseAssessment,
    SetupEffectReadiness,
)


def engineering_case_id(workspace_revision: str) -> str:
    return f"p3543case_{workspace_revision[:24]}"


def _producer_for_relation(relation: str) -> str:
    if relation == "disturbance_to_chassis":
        return "p35.4.surface_disturbance_response"
    if relation == "stint_migration":
        return "p35.4.stint_response_migration"
    return "p20.dynamic_response"


def build_engineering_response_artifacts(
    *,
    workspace_revision: str,
    run_id: str,
    session_id: str,
    setup_id: str,
    recording_sha256: str,
    operational_evidence: Sequence[Any],
) -> tuple[EngineeringResponseArtifact, ...]:
    case_id = engineering_case_id(workspace_revision)
    return tuple(
        EngineeringResponseArtifact.build(
            artifact_id=item.evidence_id,
            case_id=case_id,
            case_revision_sha256=workspace_revision,
            run_id=run_id,
            session_id=session_id,
            setup_id=setup_id,
            source_recording_sha256=recording_sha256,
            source_producer_id=_producer_for_relation(item.relation),
            relation=item.relation,
            lap_pct_start=item.lap_pct_start,
            lap_pct_end=item.lap_pct_end,
            phase=item.phase,
            source_lap_numbers=item.source_lap_numbers,
            reference_lap_numbers=(),
            independence_unit_ids=tuple(
                f"{recording_sha256}:lap:{lap_number}"
                for lap_number in item.source_lap_numbers
            ),
            operational_evidence=item,
        )
        for item in operational_evidence
    )


def build_p19_response_admissions(
    *,
    case_id: str,
    case_revision_sha256: str,
    p19_reasoning_snapshot_sha256: str,
    causes: Sequence[Any],
    response_artifacts: Sequence[EngineeringResponseArtifact],
    driver_demand_state: str,
    context_state: str,
    traffic_blocked: bool,
) -> tuple[P19ResponseAdmission, ...]:
    admissions: list[P19ResponseAdmission] = []
    exact_context = (
        driver_demand_state == "matched"
        and context_state == "qualified"
        and not traffic_blocked
    )
    for artifact in response_artifacts:
        semantic = semantic_entry(artifact.relation)
        if semantic is None:
            admissions.append(
                P19ResponseAdmission.build(
                    case_id=case_id,
                    case_revision_sha256=case_revision_sha256,
                    response_artifact_id=artifact.artifact_id,
                    p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
                    assessments=(),
                    state="blocked",
                    blocker_reasons=("No reviewed P19 response relationship exists.",),
                )
            )
            continue
        assessments: list[P19ResponseCauseAssessment] = []
        for cause in causes:
            matched = tuple(
                value
                for value in getattr(cause, "mechanism_keys", ())
                if value in semantic.p20_mechanism_ids
            )
            if not matched:
                continue
            if not exact_context:
                result = "blocked"
                blockers = (
                    "P19 response admission requires matched driver demand, qualified context, and clear traffic.",
                )
                basis = "The observation remains visible but cannot enter a P19 support contract."
            elif getattr(cause, "status", "unresolved") in {"likely", "possible"}:
                result = "supports_existing_contract"
                blockers = ()
                basis = (
                    "The raw response observation satisfies this existing P19 mechanism contract; "
                    "the current cause rank and terminal action are unchanged."
                )
            else:
                result = "unresolved"
                blockers = ()
                basis = (
                    "The response is mechanically related, but P19 does not admit it as support "
                    "for the current cause state."
                )
            assessments.append(
                P19ResponseCauseAssessment(
                    cause_id=cause.cause_id,
                    matched_mechanism_ids=matched,
                    result=result,
                    basis=basis,
                    blocker_reasons=blockers,
                )
            )
        if not assessments:
            state = "unresolved"
            blockers = ()
        elif all(item.result == "blocked" for item in assessments):
            state = "blocked"
            blockers = tuple(
                dict.fromkeys(
                    reason
                    for item in assessments
                    for reason in item.blocker_reasons
                )
            )
        elif any(
            item.result
            in {"supports_existing_contract", "contradicts_existing_contract"}
            for item in assessments
        ):
            state = "admitted"
            blockers = ()
        else:
            state = "unresolved"
            blockers = ()
        admissions.append(
            P19ResponseAdmission.build(
                case_id=case_id,
                case_revision_sha256=case_revision_sha256,
                response_artifact_id=artifact.artifact_id,
                p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
                assessments=tuple(assessments),
                state=state,
                blocker_reasons=blockers,
            )
        )
    return tuple(admissions)


def _relations_for_mechanisms(mechanism_ids: Iterable[str]) -> tuple[str, ...]:
    mechanisms = set(mechanism_ids)
    return tuple(
        item.relation_id
        for item in compile_engineering_semantic_registry().entries
        if mechanisms.intersection(item.p35_mechanism_ids)
    )


def build_setup_effect_readiness(
    hypotheses: Sequence[Any],
    response_artifacts: Sequence[EngineeringResponseArtifact],
    p19_admissions: Sequence[P19ResponseAdmission] = (),
) -> tuple[SetupEffectReadiness, ...]:
    admitted_or_unresolved_ids = {
        item.response_artifact_id
        for item in p19_admissions
        if item.state != "blocked"
    }
    apply_admission_gate = bool(p19_admissions)
    response_by_relation: dict[str, tuple[str, ...]] = {}
    for item in response_artifacts:
        if apply_admission_gate and item.artifact_id not in admitted_or_unresolved_ids:
            continue
        response_by_relation.setdefault(item.relation, ())
        response_by_relation[item.relation] = (
            *response_by_relation[item.relation],
            item.artifact_id,
        )
    readiness: list[SetupEffectReadiness] = []
    for hypothesis in hypotheses:
        expected_relations = _relations_for_mechanisms(hypothesis.p35_mechanism_ids)
        response_ids = tuple(
            artifact_id
            for relation in expected_relations
            for artifact_id in response_by_relation.get(relation, ())
        )
        if hypothesis.knowledge_applicability in {"blocked_by_build", "unsupported"}:
            state = "blocked"
            authority = "knowledge_only"
            setup_authorized = False
            missing = hypothesis.missing_evidence or (
                "The effect is outside reviewed current-build applicability.",
            )
        elif hypothesis.p19_control is not None:
            state = "p19_testable"
            authority = "exact_p19_projection"
            setup_authorized = True
            missing = ()
        elif response_ids:
            state = "response_evidence_ready"
            authority = "measurement_only"
            setup_authorized = False
            missing = tuple(
                dict.fromkeys(
                    (
                        *hypothesis.missing_evidence,
                        "Exact legal option and P19 authorization remain required.",
                    )
                )
            )
        elif hypothesis.level == "measurable_hypothesis":
            state = "measurement_ready"
            authority = "measurement_only"
            setup_authorized = False
            missing = hypothesis.missing_evidence
        else:
            state = "knowledge_only"
            authority = "knowledge_only"
            setup_authorized = False
            missing = hypothesis.missing_evidence
        readiness.append(
            SetupEffectReadiness(
                effect_id=hypothesis.effect_id,
                bridge_id=hypothesis.bridge_id,
                state=state,
                response_artifact_ids=tuple(dict.fromkeys(response_ids)),
                expected_response_relation_ids=expected_relations,
                exact_control_keys=(
                    (hypothesis.p19_control.control_key,)
                    if hypothesis.p19_control is not None
                    else ()
                ),
                experiment_factor_id=hypothesis.experiment_factor_id,
                countereffect_measurement_ids=hypothesis.countereffect_ids,
                missing_evidence=missing,
                authority=authority,
                setup_authorized=setup_authorized,
            )
        )
    return tuple(readiness)


def build_capability_resolutions(
    readiness: Sequence[SetupEffectReadiness],
    response_artifacts: Sequence[EngineeringResponseArtifact],
) -> tuple[CapabilityEvidenceResolution, ...]:
    available_channels = {
        channel
        for artifact in response_artifacts
        for channel in artifact.operational_evidence.source_channels
    }
    resolutions: dict[str, CapabilityEvidenceResolution] = {}
    registry = compile_engineering_semantic_registry()
    entry_by_relation = {item.relation_id: item for item in registry.entries}
    for effect in readiness:
        for missing in effect.missing_evidence:
            relations = tuple(
                entry_by_relation[relation]
                for relation in effect.expected_response_relation_ids
                if relation in entry_by_relation
            )
            required = tuple(
                dict.fromkeys(
                    channel for relation in relations for channel in relation.required_channel_ids
                )
            )
            text = missing.casefold()
            if "tire" in text and any(
                token in text for token in ("wear", "pressure", "temperature", "carcass")
            ):
                status = "pit_snapshot_only"
                recovery = "Capture the required tire state at a verified pit boundary."
            elif required and set(required) <= available_channels:
                status = "available_now"
                recovery = "Open the admitted response artifact in Telemetry Capabilities."
            elif required:
                status = "requires_new_run"
                recovery = "Record another exact-context run with the required healthy channels."
            else:
                status = "structurally_unavailable"
                recovery = "No current typed channel contract can satisfy this requirement."
            identity = canonical_json_sha256([missing, required, status, recovery])
            resolutions.setdefault(
                identity,
                CapabilityEvidenceResolution(
                    resolution_id=f"p3543cap_{identity[:24]}",
                    missing_evidence=missing,
                    required_channel_ids=required,
                    status=status,
                    recovery=recovery,
                    source_artifact_ids=tuple(
                        artifact.artifact_id
                        for artifact in response_artifacts
                        if set(artifact.operational_evidence.source_channels)
                        & set(required)
                    ),
                ),
            )
    return tuple(resolutions.values())


def build_canonical_engineering_case(
    *,
    identity: Any,
    recording_sha256: str,
    evidence_index_sha256: str,
    p351_projection: Any,
    response_artifacts: Sequence[EngineeringResponseArtifact],
    p19_admissions: Sequence[P19ResponseAdmission],
    p35: Any,
    p26: Any,
    terminal_decision: Any,
    effect_readiness: Sequence[SetupEffectReadiness],
    capability_resolutions: Sequence[CapabilityEvidenceResolution],
    investigation_id: str | None,
) -> CanonicalEngineeringCase:
    case_id = engineering_case_id(identity.workspace_revision)
    first_artifact = response_artifacts[0] if response_artifacts else None
    relation = first_artifact.relation if first_artifact is not None else None
    semantic = semantic_entry(relation) if relation is not None else None
    effect_ids = tuple(
        item.effect_id
        for item in effect_readiness
        if first_artifact is not None
        and first_artifact.artifact_id in item.response_artifact_ids
    )
    p19_cause_ids = tuple(
        item.cause_id
        for admission in p19_admissions
        if first_artifact is not None
        and admission.response_artifact_id == first_artifact.artifact_id
        for item in admission.assessments
    )
    focus = EngineeringSemanticFocusState(
        case_id=case_id,
        case_revision_sha256=identity.workspace_revision,
        artifact_id=(first_artifact.artifact_id if first_artifact else None),
        lap_numbers=(first_artifact.source_lap_numbers if first_artifact else ()),
        lap_pct_start=(first_artifact.lap_pct_start if first_artifact else None),
        lap_pct_end=(first_artifact.lap_pct_end if first_artifact else None),
        phase=(first_artifact.phase if first_artifact else None),
        mechanism_ids=(semantic.p35_mechanism_ids if semantic else ()),
        response_relation_id=relation,
        component_ids=(semantic.p26_component_family_ids if semantic else ()),
        effect_ids=effect_ids,
        control_keys=tuple(
            dict.fromkeys(
                control
                for item in effect_readiness
                if item.effect_id in effect_ids
                for control in item.exact_control_keys
            )
        ),
        p19_cause_ids=tuple(dict.fromkeys(p19_cause_ids)),
    )
    primary_opportunity_id = next(iter(p35.performance_opportunity_ids), None)
    terminal_hash = canonical_json_sha256(terminal_decision)
    quantities: dict[str, CaseQuantityObservability] = {}
    for artifact in response_artifacts:
        relation_entry = semantic_entry(artifact.relation)
        if relation_entry is None:
            continue
        for quantity_id in relation_entry.p26_quantity_ids:
            existing = quantities.get(quantity_id)
            artifact_ids = tuple(
                dict.fromkeys(
                    (
                        *((existing.response_artifact_ids) if existing else ()),
                        artifact.artifact_id,
                    )
                )
            )
            quantities[quantity_id] = CaseQuantityObservability(
                quantity_id=quantity_id,
                component_family_ids=relation_entry.p26_component_family_ids,
                response_artifact_ids=artifact_ids,
            )
    return CanonicalEngineeringCase.build(
        case_revision_sha256=identity.workspace_revision,
        run_id=identity.run_id,
        session_id=identity.session_id,
        recording_sha256=recording_sha256,
        setup_id=identity.setup_id,
        setup_snapshot_sha256=identity.setup_snapshot_sha256,
        objective_id=identity.objective_id.value,
        condition_epoch_sha256=identity.run_sentinel_sha256,
        p19_reasoning_snapshot_sha256=identity.reasoning_snapshot_sha256,
        p20_state_revision=identity.p20_state_revision,
        p26_knowledge_graph_sha256=identity.p26_knowledge_graph_sha256,
        p32_projection_sha256=identity.p32_projection_sha256,
        p35_assessment_sha256=identity.p35_assessment_sha256,
        p351_projection_sha256=p351_projection.projection_sha256,
        p33_projection_sha256=identity.learning_projection_sha256,
        evidence_index_sha256=evidence_index_sha256,
        primary_opportunity_id=primary_opportunity_id,
        response_artifacts=tuple(response_artifacts),
        p19_response_admissions=tuple(p19_admissions),
        mechanism_ids=tuple(item.mechanism_id for item in p35.mechanism_separation),
        component_ids=tuple(item.component_id for item in p26.component_states),
        effect_readiness=tuple(effect_readiness),
        active_discriminator_id=p35.next_discriminator_contract_id,
        investigation_id=investigation_id,
        workspace_revision=identity.workspace_revision,
        terminal_move_sha256=terminal_hash,
        capability_resolutions=tuple(capability_resolutions),
        quantity_observability=tuple(quantities.values()),
        semantic_focus=focus,
        campaign_capture=EngineeringCaseCampaignCapture(
            state="pending",
            blocker_reasons=(
                "P36 qualification requires a completed real-session certificate; no scientific count is credited.",
            ),
        ),
    )


__all__ = [
    "build_capability_resolutions",
    "build_canonical_engineering_case",
    "build_engineering_response_artifacts",
    "build_p19_response_admissions",
    "build_setup_effect_readiness",
    "engineering_case_id",
]
