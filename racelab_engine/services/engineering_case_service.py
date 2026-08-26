"""Assemble the P35.4.3 canonical case from existing producer-owned truth."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from threading import RLock
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
    DriverIntent,
    EngineeringEvidenceDeficit,
    EngineeringCaseCampaignCapture,
    EngineeringMission,
    EngineeringResponseArtifact,
    EngineeringSemanticFocusState,
    P19ResponseAdmission,
    ResponseChannelLineage,
    ResponseExpectationContract,
    ResponseExpectationEvaluation,
    SetupEffectReadiness,
)
from racelab_engine.services.p19_response_admission_service import (
    build_p19_response_evaluations_and_admissions,
)


_CASE_BUILD_LOCK = RLock()
_CASE_PROJECTION_BUILD_COUNT = 0


def engineering_case_id(*, run_id: str, session_id: str) -> str:
    identity = canonical_json_sha256(
        {
            "schema": "p3544.engineering-case-lifecycle.v1",
            "run_id": run_id,
            "session_id": session_id,
        }
    )
    return f"p3543case_{identity[:24]}"


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
    case_id = engineering_case_id(run_id=run_id, session_id=session_id)
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
            source_producer_version="p35.4.4.response-artifact.v1",
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
            physical_episode_sha256=canonical_json_sha256(
                {
                    "recording": recording_sha256,
                    "producer": _producer_for_relation(item.relation),
                    "relation": item.relation,
                    "phase": item.phase,
                    "lap_pct_start": item.lap_pct_start,
                    "lap_pct_end": item.lap_pct_end,
                    "source_artifact_ids": list(item.source_artifact_ids),
                    "independence_unit_ids": [
                        f"{recording_sha256}:lap:{lap_number}"
                        for lap_number in item.source_lap_numbers
                    ],
                }
            ),
            speed_min_mps=item.speed_min_mps,
            speed_median_mps=item.speed_median_mps,
            speed_max_mps=item.speed_max_mps,
            metric_channel_lineage=tuple(
                ResponseChannelLineage(
                    metric_id=metric.metric_id,
                    source_channel_ids=metric.source_channels,
                )
                for metric in item.metrics
            ),
            operational_evidence=item,
            evidence_state=item.evidence_state,
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
    expectation_contracts: Sequence[ResponseExpectationContract] = (),
) -> tuple[P19ResponseAdmission, ...]:
    _evaluations, admissions = build_p19_response_evaluations_and_admissions(
        case_id=case_id,
        case_revision_sha256=case_revision_sha256,
        p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
        causes=causes,
        response_artifacts=response_artifacts,
        expectation_contracts=expectation_contracts,
        driver_demand_state=driver_demand_state,
        context_state=context_state,
        traffic_blocked=traffic_blocked,
    )
    return admissions


def _relations_for_mechanisms(mechanism_ids: Iterable[str]) -> tuple[str, ...]:
    mechanisms = set(mechanism_ids)
    return tuple(
        item.relation_id
        for item in compile_engineering_semantic_registry().entries
        if mechanisms.intersection(item.p35_mechanism_ids)
    )


def build_response_expectation_contracts(
    hypotheses: Sequence[Any],
) -> tuple[ResponseExpectationContract, ...]:
    """Admit only explicit reviewed contracts already carried by producer truth.

    P35.1 currently supplies direction-neutral validation targets, not numeric
    sign/range/noise contracts.  Those hypotheses therefore remain measurable
    but cannot be promoted by manufacturing a generic response expectation.
    """

    contracts: list[ResponseExpectationContract] = []
    for hypothesis in hypotheses:
        for raw in tuple(getattr(hypothesis, "response_expectation_contracts", ())):
            contract = (
                raw
                if isinstance(raw, ResponseExpectationContract)
                else ResponseExpectationContract.model_validate(raw)
            )
            p19_control = getattr(hypothesis, "p19_control", None)
            if (
                contract.owning_effect_id != hypothesis.effect_id
                or contract.experiment_factor_id
                != getattr(hypothesis, "experiment_factor_id", None)
                or p19_control is None
                or contract.control_key != p19_control.control_key
            ):
                raise ValueError(
                    "response expectation does not match its exact P35.1/P19 bridge"
                )
            contracts.append(contract)
    identities = tuple(item.expectation_contract_id for item in contracts)
    if len(identities) != len(set(identities)):
        raise ValueError("response expectation contracts must be unique")
    return tuple(contracts)


def build_setup_effect_readiness(
    hypotheses: Sequence[Any],
    response_artifacts: Sequence[EngineeringResponseArtifact],
    p19_admissions: Sequence[P19ResponseAdmission] = (),
) -> tuple[SetupEffectReadiness, ...]:
    admitted_ids = {
        item.response_artifact_id
        for item in p19_admissions
        if item.state == "admitted"
    }
    apply_admission_gate = bool(p19_admissions)
    response_by_relation: dict[str, tuple[str, ...]] = {}
    for item in response_artifacts:
        if apply_admission_gate and item.artifact_id not in admitted_ids:
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
                deficit_ids=(),
                authority=authority,
                setup_authorized=setup_authorized,
            )
        )
    return tuple(readiness)


def build_evidence_deficits(
    readiness: Sequence[SetupEffectReadiness],
    response_artifacts: Sequence[EngineeringResponseArtifact],
) -> tuple[EngineeringEvidenceDeficit, ...]:
    """Build planner debt from typed readiness state, never from prose wording."""

    available_channels = {
        channel
        for artifact in response_artifacts
        for channel in artifact.operational_evidence.source_channels
    }
    registry = compile_engineering_semantic_registry()
    entry_by_relation = {item.relation_id: item for item in registry.entries}
    deficits: list[EngineeringEvidenceDeficit] = []

    def add(
        effect: SetupEffectReadiness,
        *,
        code: str,
        blockers: tuple[str, ...],
        required_channels: tuple[str, ...] = (),
        recovery_mode: str,
        mission_eligible: bool,
    ) -> None:
        deficits.append(
            EngineeringEvidenceDeficit.build(
                code=code,
                affected_contract_ids=effect.expected_response_relation_ids,
                affected_effect_ids=(effect.effect_id,),
                required_channel_ids=required_channels,
                current_channel_capability_ids=tuple(
                    f"channel:{channel}"
                    for channel in required_channels
                    if channel in available_channels
                ),
                blocker_reasons=blockers,
                recovery_mode=recovery_mode,
                mission_eligible=mission_eligible,
            )
        )

    for effect in readiness:
        relations = tuple(
            entry_by_relation[item]
            for item in effect.expected_response_relation_ids
            if item in entry_by_relation
        )
        required_channels = tuple(
            dict.fromkeys(
                channel
                for relation in relations
                for channel in relation.required_channel_ids
            )
        )
        missing_channels = tuple(
            channel for channel in required_channels if channel not in available_channels
        )
        if not effect.expected_response_relation_ids:
            add(
                effect,
                code="EXACT_SEMANTIC_BRIDGE_MISSING",
                blockers=("No exact reviewed response relation exists for this effect.",),
                recovery_mode="unavailable",
                mission_eligible=False,
            )
            continue
        if effect.state == "blocked":
            add(
                effect,
                code="BUILD_APPLICABILITY_BLOCKED",
                blockers=effect.missing_evidence
                or ("Reviewed car/build applicability blocks this effect.",),
                required_channels=required_channels,
                recovery_mode="unavailable",
                mission_eligible=False,
            )
            continue
        if effect.state == "p19_testable":
            continue
        if effect.state == "response_evidence_ready":
            add(
                effect,
                code="EXACT_LEGAL_OPTION_MISSING",
                blockers=("An exact adjacent legal setup option is not yet bound.",),
                required_channels=tuple(
                    dict.fromkeys(
                        channel
                        for artifact in response_artifacts
                        if artifact.artifact_id in effect.response_artifact_ids
                        for channel in artifact.operational_evidence.source_channels
                    )
                ),
                recovery_mode="controlled_test",
                mission_eligible=False,
            )
            add(
                effect,
                code="P19_AUTHORITY_REQUIRED",
                blockers=("Only the current exact P19 projection may authorize this test.",),
                recovery_mode="controlled_test",
                mission_eligible=False,
            )
        elif missing_channels:
            add(
                effect,
                code="CHANNEL_MISSING",
                blockers=(
                    "Required healthy response channels are unavailable: "
                    + ", ".join(missing_channels),
                ),
                required_channels=required_channels,
                recovery_mode="collect_new_run",
                mission_eligible=True,
            )
        elif effect.state == "measurement_ready":
            add(
                effect,
                code="INSUFFICIENT_REPETITION",
                blockers=("Independent exact-context response repetition is still required.",),
                required_channels=required_channels,
                recovery_mode="collect_more_laps",
                mission_eligible=True,
            )
    unique = {item.deficit_id: item for item in deficits}
    return tuple(unique.values())


def attach_deficits_to_readiness(
    readiness: Sequence[SetupEffectReadiness],
    deficits: Sequence[EngineeringEvidenceDeficit],
) -> tuple[SetupEffectReadiness, ...]:
    return tuple(
        item.model_copy(
            update={
                "deficit_ids": tuple(
                    deficit.deficit_id
                    for deficit in deficits
                    if item.effect_id in deficit.affected_effect_ids
                )
            }
        )
        for item in readiness
    )


def build_engineering_mission(
    terminal_decision: Any,
    *,
    response_artifacts: Sequence[EngineeringResponseArtifact],
    strongest_contradiction: str | None,
    completion_criteria: str,
) -> EngineeringMission:
    """Project one display mission by exact mirroring of the P19 terminal object."""

    artifact = response_artifacts[0] if response_artifacts else None
    where = (
        f"{artifact.phase} · {artifact.lap_pct_start:.1f}–{artifact.lap_pct_end:.1f}%"
        if artifact is not None
        else "Current exact run scope"
    )
    authority = getattr(terminal_decision, "authority", "context_only")
    source_authority = (
        "p19_exact_mirror"
        if authority == "p19_projection_only"
        else "p19_measurement_mirror"
        if authority == "measurement_only"
        else "navigation_only"
    )
    terminal_hash = canonical_json_sha256(terminal_decision)
    blockers = tuple(getattr(terminal_decision, "blocker_reasons", ()))
    return EngineeringMission(
        what=str(getattr(terminal_decision, "title", "Current engineering case")),
        where=where,
        why_it_matters=(
            "This is the current exact-scope P19 terminal decision."
            if source_authority != "navigation_only"
            else "Current evidence does not authorize a controlled setup action."
        ),
        uncertain=(
            strongest_contradiction
            or (blockers[0] if blockers else "No stronger causal claim is authorized.")
        ),
        next=str(getattr(terminal_decision, "instruction", "Hold the current setup.")),
        done_when=completion_criteria,
        source_authority=source_authority,
        terminal_move_sha256=terminal_hash,
        source_artifact_ids=tuple(
            dict.fromkeys(
                (
                    *tuple(getattr(terminal_decision, "source_event_ids", ())),
                    *(item.artifact_id for item in response_artifacts),
                )
            )
        ),
        setup_authorized=source_authority == "p19_exact_mirror",
    )


def build_capability_resolutions(
    deficits: Sequence[EngineeringEvidenceDeficit],
    response_artifacts: Sequence[EngineeringResponseArtifact],
) -> tuple[CapabilityEvidenceResolution, ...]:
    resolutions: dict[str, CapabilityEvidenceResolution] = {}
    for deficit in deficits:
        status = {
            "use_current_data": "available_now",
            "collect_more_laps": "requires_more_laps",
            "collect_new_run": "requires_new_run",
            "pit_snapshot": "pit_snapshot_only",
            "controlled_test": "controlled_test_required",
            "unavailable": "structurally_unavailable",
        }[deficit.recovery_mode]
        recovery = {
            "use_current_data": "Open the exact current artifact in Telemetry Capabilities.",
            "collect_more_laps": "Record more eligible exact-context laps with the setup unchanged.",
            "collect_new_run": "Record another exact-context run with the required healthy channels.",
            "pit_snapshot": "Capture the required state at a verified pit boundary.",
            "controlled_test": "Return to the exact P19 workflow boundary before testing.",
            "unavailable": "No current typed measurement contract can satisfy this requirement.",
        }[deficit.recovery_mode]
        identity = canonical_json_sha256(
            [deficit.deficit_id, deficit.required_channel_ids, status, recovery]
        )
        resolutions[identity] = CapabilityEvidenceResolution(
            resolution_id=f"p3543cap_{identity[:24]}",
            missing_evidence=deficit.blocker_reasons[0],
            deficit_id=deficit.deficit_id,
            deficit_code=deficit.code,
            required_channel_ids=deficit.required_channel_ids,
            status=status,
            recovery=recovery,
            recovery_mode=deficit.recovery_mode,
            source_artifact_ids=tuple(
                artifact.artifact_id
                for artifact in response_artifacts
                if set(artifact.operational_evidence.source_channels)
                & set(deficit.required_channel_ids)
            ),
        )
    return tuple(resolutions.values())


def engineering_case_projection_revision_sha256(
    *,
    identity: Any,
    recording_sha256: str,
    evidence_index_sha256: str | None = None,
    evidence_index: Any | None = None,
    p351_projection: Any,
    response_artifacts: Sequence[EngineeringResponseArtifact],
    response_expectation_contracts: Sequence[ResponseExpectationContract],
    response_expectation_evaluations: Sequence[ResponseExpectationEvaluation],
    p19_admissions: Sequence[P19ResponseAdmission],
    terminal_decision: Any,
    effect_readiness: Sequence[SetupEffectReadiness],
    evidence_deficits: Sequence[EngineeringEvidenceDeficit],
    capability_resolutions: Sequence[CapabilityEvidenceResolution],
    investigation_id: str | None,
    mission: EngineeringMission,
    driver_intent: DriverIntent | None,
    crew_event_head_sha256: str | None,
    crew_current_subgoal: str | None,
    crew_critic_state: str,
) -> str:
    """Bind every late-built case projection without a wrapper-hash cycle.

    The operational Crew workspace is identified before P35.1, the semantic
    registry, the evidence index, and the readiness/capability projections are
    assembled. Response envelopes then need the finalized case projection
    revision. Hashing their semantic payloads while excluding only revision and
    content-address wrapper fields gives the case one complete, stable identity
    that those envelopes can safely carry.
    """

    artifact_payloads = [
        item.model_dump(
            mode="json",
            exclude={"artifact_sha256", "case_revision_sha256"},
        )
        for item in response_artifacts
    ]
    admission_payloads = [
        item.model_dump(
            mode="json",
            exclude={
                "admission_id",
                "admission_sha256",
                "case_revision_sha256",
            },
        )
        for item in p19_admissions
    ]
    if evidence_index is not None:
        index_entries = []
        for entry in evidence_index.entries:
            payload = entry.model_dump(mode="json")
            typed = payload.get("typed_artifact")
            if isinstance(typed, dict) and typed.get("artifact_type") == (
                "engineering_response"
            ):
                typed.pop("case_revision_sha256", None)
                response = typed.get("response")
                if isinstance(response, dict):
                    response.pop("artifact_sha256", None)
                    response.pop("case_revision_sha256", None)
            index_entries.append(payload)
        evidence_index_identity = canonical_json_sha256(
            {
                "workspace_revision": evidence_index.workspace_revision,
                "entries": index_entries,
            }
        )
    elif evidence_index_sha256 is not None:
        # Compatibility seam for direct builders that predate the typed index.
        evidence_index_identity = evidence_index_sha256
    else:
        raise ValueError("engineering case projection requires an evidence index")
    return canonical_json_sha256(
        {
            "schema": "p3544.engineering-case-projection-revision.v1",
            "workspace_revision": identity.workspace_revision,
            "recording_sha256": recording_sha256,
            "p351_projection_sha256": p351_projection.projection_sha256,
            "semantic_registry_sha256": (
                compile_engineering_semantic_registry().registry_sha256
            ),
            "evidence_index_semantic_sha256": evidence_index_identity,
            "response_artifacts": artifact_payloads,
            "response_expectation_contracts": [
                item.model_dump(mode="json")
                for item in response_expectation_contracts
            ],
            "response_expectation_evaluations": [
                item.model_dump(mode="json")
                for item in response_expectation_evaluations
            ],
            "p19_response_admissions": admission_payloads,
            "terminal_decision": terminal_decision,
            "effect_readiness": [
                item.model_dump(mode="json") for item in effect_readiness
            ],
            "evidence_deficits": [
                item.model_dump(mode="json") for item in evidence_deficits
            ],
            "capability_resolutions": [
                item.model_dump(mode="json") for item in capability_resolutions
            ],
            "investigation_id": investigation_id,
            "mission": mission,
            "driver_intent_sha256": (
                driver_intent.intent_sha256 if driver_intent is not None else None
            ),
            "crew_event_head_sha256": crew_event_head_sha256,
            "crew_current_subgoal": crew_current_subgoal,
            "crew_critic_state": crew_critic_state,
        }
    )


def build_canonical_engineering_case(
    *,
    identity: Any,
    recording_sha256: str,
    evidence_index_sha256: str,
    p351_projection: Any,
    response_artifacts: Sequence[EngineeringResponseArtifact],
    response_expectation_contracts: Sequence[ResponseExpectationContract],
    response_expectation_evaluations: Sequence[ResponseExpectationEvaluation],
    p19_admissions: Sequence[P19ResponseAdmission],
    p35: Any,
    p26: Any,
    terminal_decision: Any,
    effect_readiness: Sequence[SetupEffectReadiness],
    evidence_deficits: Sequence[EngineeringEvidenceDeficit],
    capability_resolutions: Sequence[CapabilityEvidenceResolution],
    investigation_id: str | None,
    mission: EngineeringMission,
    driver_intent: DriverIntent | None = None,
    crew_event_head_sha256: str | None = None,
    crew_current_subgoal: str | None = None,
    crew_critic_state: str = "unavailable",
    case_revision_sha256: str | None = None,
) -> CanonicalEngineeringCase:
    global _CASE_PROJECTION_BUILD_COUNT
    with _CASE_BUILD_LOCK:
        _CASE_PROJECTION_BUILD_COUNT += 1
    case_id = engineering_case_id(run_id=identity.run_id, session_id=identity.session_id)
    projection_revision = case_revision_sha256 or identity.workspace_revision
    admitted_artifact_ids = {
        item.response_artifact_id
        for item in p19_admissions
        if item.state == "admitted"
    }
    first_artifact = next(
        (
            item
            for item in response_artifacts
            if item.artifact_id in admitted_artifact_ids
        ),
        response_artifacts[0] if response_artifacts else None,
    )
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
        case_revision_sha256=projection_revision,
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
    quantity_channel_groups: dict[str, tuple[tuple[str, ...], ...]] = {
        "quantity:brake_input": (("brake_pct",),),
        "quantity:four_corner_brake_pressure": (
            ("lf_brake_line_pressure_bar",),
            ("rf_brake_line_pressure_bar",),
            ("lr_brake_line_pressure_bar",),
            ("rr_brake_line_pressure_bar",),
        ),
        "quantity:longitudinal_acceleration": (("long_accel", "long_accel_g"),),
        "quantity:shock_deflection": (
            ("lf_shock_defl_in",),
            ("rf_shock_defl_in",),
            ("lr_shock_defl_in",),
            ("rr_shock_defl_in",),
        ),
        "quantity:shock_velocity": (
            ("lf_shock_vel_in_s",),
            ("rf_shock_vel_in_s",),
            ("lr_shock_vel_in_s",),
            ("rr_shock_vel_in_s",),
        ),
        "quantity:steering_wheel_demand": (("steering_deg", "abs_steering_deg"),),
        "quantity:throttle_input": (("throttle_pct",),),
        "quantity:vertical_acceleration": (("vert_accel_g", "vertical_accel"),),
        "quantity:yaw_rate": (("yaw_rate",),),
    }
    for artifact in response_artifacts:
        relation_entry = semantic_entry(artifact.relation)
        if relation_entry is None:
            continue
        for quantity_id in relation_entry.p26_quantity_ids:
            channel_groups = quantity_channel_groups.get(quantity_id)
            source_channels = set(artifact.operational_evidence.source_channels)
            if channel_groups is None or not all(
                source_channels.intersection(group) for group in channel_groups
            ):
                continue
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
        case_id=case_id,
        case_revision_sha256=projection_revision,
        run_id=identity.run_id,
        session_id=identity.session_id,
        selected_run_ids=(
            tuple(identity.selected_run_ids)
            if getattr(identity, "selected_run_ids", ())
            else (identity.run_id,)
        ),
        recording_sha256=recording_sha256,
        vehicle_runtime_identity_sha256=getattr(
            identity,
            "vehicle_runtime_identity_hash",
            canonical_json_sha256(
                {
                    "state": "unavailable",
                    "run_id": identity.run_id,
                    "recording_sha256": recording_sha256,
                }
            ),
        ),
        car_identity=(
            identity.vehicle_runtime_identity.car_path
            if getattr(identity, "vehicle_runtime_identity", None) is not None
            else str(getattr(p35, "car_path", "unavailable"))
        ),
        car_version=(
            identity.vehicle_runtime_identity.car_version
            if getattr(identity, "vehicle_runtime_identity", None) is not None
            else str(getattr(p35, "car_version", "unavailable"))
        ),
        iracing_build_version=(
            identity.vehicle_runtime_identity.iracing_build_version
            if getattr(identity, "vehicle_runtime_identity", None) is not None
            else str(getattr(p35, "iracing_build_version", "unavailable"))
        ),
        track_configuration=(
            identity.vehicle_runtime_identity.track_configuration_name
            if getattr(identity, "vehicle_runtime_identity", None) is not None
            else str(getattr(p35, "track_package", "unavailable"))
        ),
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
        semantic_registry_sha256=compile_engineering_semantic_registry().registry_sha256,
        evidence_index_sha256=evidence_index_sha256,
        driver_intent=driver_intent,
        crew_event_head_sha256=crew_event_head_sha256,
        crew_current_subgoal=crew_current_subgoal,
        crew_critic_state=crew_critic_state,
        active_workflow_id=getattr(identity, "active_workflow_id", None),
        active_workflow_revision=getattr(identity, "active_workflow_revision", None),
        primary_opportunity_id=primary_opportunity_id,
        response_artifacts=tuple(response_artifacts),
        response_expectation_contracts=tuple(response_expectation_contracts),
        response_expectation_evaluations=tuple(response_expectation_evaluations),
        p19_response_admissions=tuple(p19_admissions),
        mechanism_ids=tuple(item.mechanism_id for item in p35.mechanism_separation),
        component_ids=tuple(item.component_id for item in p26.component_states),
        effect_readiness=tuple(effect_readiness),
        active_discriminator_id=p35.next_discriminator_contract_id,
        investigation_id=investigation_id,
        workspace_revision=identity.workspace_revision,
        terminal_move_sha256=terminal_hash,
        mission=mission,
        evidence_deficits=tuple(evidence_deficits),
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


def engineering_case_projection_stats() -> dict[str, int]:
    with _CASE_BUILD_LOCK:
        return {"build_count": _CASE_PROJECTION_BUILD_COUNT}


__all__ = [
    "attach_deficits_to_readiness",
    "build_capability_resolutions",
    "build_canonical_engineering_case",
    "build_evidence_deficits",
    "build_engineering_mission",
    "build_engineering_response_artifacts",
    "build_p19_response_admissions",
    "build_response_expectation_contracts",
    "build_setup_effect_readiness",
    "engineering_case_id",
    "engineering_case_projection_revision_sha256",
    "engineering_case_projection_stats",
]
