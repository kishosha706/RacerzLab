from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from racelab_engine.analysis.test_director import score_test_execution
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.crew_chief import (
    CrewChiefEventPayload,
    CrewChiefInvestigation,
    CrewChiefTerminalDecision,
    CrewChiefWorkspaceIdentity,
    EngineeringObjective,
    InvestigationSubgoal,
)
from racelab_engine.models.engineering_learning import (
    EngineeringExperienceContext,
    EngineeringSourceProvenance,
    P19CauseMemory,
    P19ReasoningMemory,
    ProblemFingerprint,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import ControlledCauseOutcome
from racelab_engine.models.investigation_adaptation import (
    InvestigationDecision,
    InvestigationPolicyEvaluation,
    InvestigationOutcomeCertificate,
    NegativeControlConditionEvidence,
    P34ActivationDecision,
    P19CauseState,
    investigation_adaptation_source_snapshot_sha256,
)
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import controlled_workflow_service
from racelab_engine.services import crew_chief_service
from racelab_engine.services import engineering_learning_service as service
from racelab_engine.services import investigation_adaptation_service
from racelab_engine.services.crew_chief_service import (
    _build_p34_completed_comparison,
    _build_p34_discriminator_outcome,
    _build_p34_outcome_certificate,
    _event,
    _freeze_p34_pair_for_workspace,
    _learning_capture_blockers,
    _review_p34_terminal_capture,
    _with_learning_capture_blockers,
    continue_investigation,
)
from racelab_engine.services.investigation_adaptation_service import (
    baseline_investigation_policy,
    build_paired_investigation_comparison,
    build_paired_investigation_decision,
    evaluate_p34_repository,
    limited_attention_investigation_policy,
    memory_shadow_investigation_policy,
    p34_activation_protocol,
    persist_p34_foundation,
    resolve_effective_activation_decision,
)
from racelab_engine.storage.crew_chief_repository import (
    P34_CAPTURE_INTEGRITY_BLOCKER,
    CrewChiefIntegrityError,
    CrewChiefRepository,
    crew_chief_event_hash,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    LEARNING_CAPTURE_INTEGRITY_BLOCKER,
    EngineeringLearningIntegrityError,
    EngineeringLearningRepository,
)
from racelab_engine.storage.investigation_adaptation_repository import (
    InvestigationAdaptationIntegrityError,
    InvestigationAdaptationRepository,
)
from racelab_engine.storage.repository import RaceLabRepository
from test_engineering_memory_service import _planned_workflow, _scored_workflow
from test_p33_learning_repository import _current, _investigation_record


def _reasoning(digest: str = "2" * 64) -> P19ReasoningMemory:
    return P19ReasoningMemory(
        reasoning_snapshot_sha256=digest,
        causes=(
            P19CauseMemory(
                cause_id="cause-platform",
                status="possible",
                ordinal_rank=1,
                mechanism_family="platform",
            ),
        ),
        measurement_plan_kind="measurement_mission",
        discriminator_ids=(),
        authority_level="measurement",
        setup_authorized=False,
    )


def _workspace_identity(
    *,
    run_id: str = "run-investigation",
    session_id: str = "session-investigation",
    setup_id: str = "setup-investigation",
    setup_sha256: str = "6" * 64,
    build_sha256: str = "7" * 64,
) -> CrewChiefWorkspaceIdentity:
    return CrewChiefWorkspaceIdentity(
        run_id=run_id,
        session_id=session_id,
        selected_scope_hash=canonical_json_sha256((run_id,)),
        selected_run_ids=(run_id,),
        reasoning_snapshot_sha256="2" * 64,
        p20_state_revision="3" * 64,
        p20_profile_hash="4" * 64,
        p26_graph_version="p26.graph.v1:test",
        p26_knowledge_graph_sha256="5" * 64,
        p26_reasoning_snapshot_sha256="2" * 64,
        p32_projection_sha256="9" * 64,
        p35_assessment_sha256="d" * 64,
        run_sentinel_sha256="c" * 64,
        learning_history_revision="a" * 64,
        learning_projection_sha256="b" * 64,
        setup_id=setup_id,
        setup_snapshot_sha256=setup_sha256,
        vehicle_runtime_identity_hash=build_sha256,
        objective_id=EngineeringObjective.RACE_LONG_RUN,
        workspace_revision="8" * 64,
    )


def _exact_p34_artifact(
    identity: CrewChiefWorkspaceIdentity,
    *,
    artifact_id: str,
    evidence_state: EvidenceState,
    blocker_reasons: tuple[str, ...] = (),
    source_provenance_available: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_id=artifact_id,
        evidence_state=evidence_state,
        blocker_reasons=blocker_reasons,
        source_provenance_available=source_provenance_available,
        run_id=identity.run_id,
        session_id=identity.session_id,
        setup_id=identity.setup_id,
        workspace_run_id=identity.run_id,
        workspace_session_id=identity.session_id,
        workspace_setup_id=identity.setup_id,
        source_run_id=identity.run_id,
        source_session_id=(identity.session_id if source_provenance_available else None),
        source_setup_id=(identity.setup_id if source_provenance_available else None),
        source_setup_sha256=(
            identity.setup_snapshot_sha256 if source_provenance_available else None
        ),
        source_build_context_sha256=(
            identity.vehicle_runtime_identity_hash
            if source_provenance_available
            else None
        ),
    )


def _opening_problem(artifact_id: str = "opening-artifact") -> ProblemFingerprint:
    return ProblemFingerprint.build(
        physical_episode_id="episode-opening",
        phase="entry",
        physical_region="T1 entry",
        time_origin_class="entry",
        carry_behavior="no_measured_carry",
        driver_demand_state="matched_inputs",
        vehicle_response_state="changed_response",
        p20_mechanism_families=("platform",),
        p26_component_families=(),
        traffic_context_state="clear",
        tire_stint_state="short_run",
        objective="race_long_run",
        source_artifact_ids=(artifact_id,),
    )


def _crew_case(
    *,
    current_run_id: str = "run-investigation",
    current_session_id: str = "session-investigation",
    current_setup_id: str = "setup-investigation",
    current_setup_sha256: str = "6" * 64,
    build_sha256: str = "7" * 64,
) -> tuple[
    CrewChiefInvestigation,
    service.CurrentLearningInputs,
    CrewChiefTerminalDecision,
    tuple[Any, ...],
]:
    identity = _workspace_identity()
    problem = _opening_problem()
    opening = _reasoning()
    investigation = CrewChiefInvestigation(
        investigation_id="investigation-lifecycle",
        workspace_identity=identity,
        origin="driver_report",
        objective=EngineeringObjective.RACE_LONG_RUN,
        raw_driver_report="The car pushes on entry.",
        canonical_problem="tight on entry",
        opening_reasoning=opening,
        opening_problem=problem,
        opened_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
    )
    context = EngineeringExperienceContext.build(
        run_id=current_run_id,
        session_id=current_session_id,
        driver_id="driver-a",
        car_path="nascar-nextgen-chevy",
        car_version="2026.08",
        iracing_build="2026.08.1",
        track="atlanta",
        track_configuration="oval",
        package_type="speedway",
        setup_family=None,
        setup_snapshot_sha256=current_setup_sha256,
        objective="race_long_run",
        physical_scope_sha256="c" * 64,
        phase="entry",
        physical_region="T1 entry",
        speed_load_band="high_speed_loaded",
        fuel_state="short_run",
        tire_state="short_run",
        weather_state="recorded",
        traffic_state="clear",
        driver_execution_state="matched_inputs",
    )
    provenance = EngineeringSourceProvenance.build(
        artifact_id=problem.source_artifact_ids[0],
        producer_id="p32.performance-intelligence",
        run_id=current_run_id,
        session_id=current_session_id,
        setup_id=current_setup_id,
        setup_snapshot_sha256=current_setup_sha256,
        build_context_sha256=build_sha256,
        lap_numbers=(7, 8, 9),
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        phase="entry",
        source_channels=("speed_mps", "steering_angle_deg"),
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        polarity="support",
    )
    current = service.CurrentLearningInputs(
        context=context,
        problem=problem,
        reasoning=opening,
        source_provenance=(provenance,),
        performance_response=None,
        driver_contributions=(),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No setup call",
        instruction="Collect a qualified discriminator before assigning the cause.",
        authority="context_only",
    )
    terminal = _event(
        investigation.investigation_id,
        1,
        identity.workspace_revision,
        "decision_emitted",
        CrewChiefEventPayload(
            message="No setup call is authorized.",
            decision_kind="no_call",
        ),
    )
    return investigation, current, decision, (terminal,)


def _event_with_prediction_pair(event, pair):
    payload = event.payload.model_copy(
        update={
            "adaptation_prediction_pair_id": pair.pair_id,
            "adaptation_prediction_pair_sha256": pair.pair_sha256,
            "adaptation_prediction_source_snapshot_sha256": (
                CrewChiefRepository._p34_pair_source_snapshot_sha256(pair)
            ),
        }
    )
    draft = event.model_copy(update={"payload": payload, "event_hash": "0" * 64})
    return draft.model_copy(update={"event_hash": crew_chief_event_hash(draft)})


def _p34_terminal_unit(
    db_path,
    investigation: CrewChiefInvestigation,
    current: service.CurrentLearningInputs,
    terminal,
    experience,
    *,
    activation_decision: P34ActivationDecision | None = None,
    complete_mandatory_checks: bool = False,
):
    baseline_policy = baseline_investigation_policy()
    memory_policy = (
        limited_attention_investigation_policy()
        if activation_decision is not None
        else memory_shadow_investigation_policy()
    )
    repository = InvestigationAdaptationRepository(db_path)
    persist_p34_foundation(repository)
    decision = InvestigationDecision(
        decision_kind="no_call",
        action_id=(
            "terminal:no_call:"
            + canonical_json_sha256(
                ["no_call", terminal.payload.message]
            )[:24]
        ),
        priority_tier="terminal",
        safe_reorder_group=None,
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="The frozen baseline and memory policies reached the same boundary.",
        mandatory_check_ids=("workspace_identity", "data_integrity"),
    )
    pair = build_paired_investigation_decision(
        baseline_policy=baseline_policy,
        memory_policy=memory_policy,
        investigation_id=investigation.investigation_id,
        investigation_opened_at=investigation.opened_at,
        run_id=investigation.workspace_identity.run_id,
        session_id=investigation.workspace_identity.session_id,
        workspace_revision=terminal.workspace_revision,
        authority_revision=investigation.workspace_identity.authority_revision,
        step_number=0,
        baseline_decision=decision,
        memory_decision=decision,
        available_tool_ids=("inspect_data_quality",),
        eligible_tool_ids=(),
        completed_tool_ids=(),
        available_artifact_ids=(),
        current_truth_sha256="1" * 64,
        p19_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        current_p19_cause_ids=tuple(item.cause_id for item in current.reasoning.causes),
        current_p19_cause_states=tuple(
            P19CauseState(cause_id=item.cause_id, state=item.status)
            for item in current.reasoning.causes
        ),
        current_contradiction_ids=(),
        strongest_contradiction_id=None,
        current_objective=investigation.objective.value,
        p33_projection_sha256="0" * 64,
        p33_history_revision=investigation.workspace_identity.learning_history_revision,
        p33_ledger_head_sha256=None,
        p33_context_sha256=current.context.context_sha256,
        p33_problem_sha256=current.problem.problem_sha256,
        track=current.context.track,
        track_configuration=current.context.track_configuration,
        package_type=current.context.package_type,
        iracing_build=current.context.iracing_build,
        problem_family="entry",
        problem_orientation="combined",
        track_class="intermediate",
        phase=current.problem.phase,
        build_review_state="same_build",
        driver_drift_state="unknown",
        decision_frozen_at=terminal.created_at - timedelta(seconds=1),
        context_transfer_class="none",
        negative_control_condition="no_relevant_history",
        negative_control_evidence=NegativeControlConditionEvidence(
            condition="no_relevant_history",
            p33_projection_sha256="0" * 64,
            p33_state="insufficient_history",
            recurrence_class="new_problem",
            driver_drift_state="unknown",
        ),
        p20_projection_sha256=investigation.workspace_identity.p20_state_revision,
        p26_projection_sha256=(
            investigation.workspace_identity.p26_knowledge_graph_sha256
        ),
        p32_projection_sha256=investigation.workspace_identity.p32_projection_sha256,
        activation_decision=activation_decision,
    )
    repository.append_paired_decision(pair)
    fact = experience.investigation_outcome
    certificate = InvestigationOutcomeCertificate.build(
        activation_protocol_id=pair.activation_protocol_id,
        activation_protocol_sha256=pair.activation_protocol_sha256,
        decision_frozen_at=pair.decision_frozen_at,
        pair_id=pair.pair_id,
        pair_sha256=pair.pair_sha256,
        investigation_id=investigation.investigation_id,
        investigation_opened_at=investigation.opened_at,
        starting_workspace_revision=investigation.workspace_identity.workspace_revision,
        ending_workspace_revision=terminal.workspace_revision,
        final_p19_snapshot_sha256=(
            experience.closing_reasoning.reasoning_snapshot_sha256
        ),
        terminal_crew_decision="no_call",
        tool_request_event_ids=(),
        tool_result_event_ids=(),
        tools_actually_requested=(),
        tool_results_received=(),
        qualified_artifact_ids=(),
        qualified_artifact_evidence_states=(),
        driver_question_ids=(),
        driver_answer_event_ids=(),
        consumption_metrics_state="unavailable",
        lap_ids_consumed=None,
        measurement_mission_ids=None,
        consumption_metric_blockers=(
            "Post-open lap and completed measurement-mission consumption lineage is unavailable.",
        ),
        elapsed_wall_seconds=fact.elapsed_seconds,
        investigation_steps=terminal.sequence,
        useful_discriminator_id=None,
        dead_end_tool_ids=(),
        causes_separated=fact.eliminated_cause_ids,
        causes_left_unresolved=fact.unresolved_cause_ids,
        final_p19_cause_states=tuple(
            P19CauseState(cause_id=item.cause_id, state=item.status)
            for item in experience.closing_reasoning.causes
        ),
        strongest_contradiction_id=None,
        strongest_contradiction_handled=False,
        completed_mandatory_check_ids=(
            ("workspace_identity", "data_integrity")
            if complete_mandatory_checks
            else ("workspace_identity",)
        ),
        workflow_created=bool(fact.workflow_ids),
        workflow_scored=False,
        p19_outcome="no_call",
        outcome_validity="qualified",
        prospective=(
            investigation.opened_at > p34_activation_protocol().prospective_boundary
        ),
        synthetic=False,
        blockers=(),
        certified_at=terminal.created_at,
    )
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=terminal.created_at,
    )
    return certificate, comparison, pair


def _persist_test_p34_earned_activation(
    repository: InvestigationAdaptationRepository,
    *,
    decided_at: datetime,
) -> P34ActivationDecision:
    persist_p34_foundation(repository)
    locked = evaluate_p34_repository(
        repository,
        evaluated_at=decided_at - timedelta(seconds=1),
    )
    earned_values = locked.model_dump(
        mode="python",
        exclude={"evaluation_id", "evaluation_sha256"},
    )
    earned_values.update(
        safety=locked.safety,
        efficiency=locked.efficiency,
        quality=locked.quality,
        subgroup_results=locked.subgroup_results,
        blockers=(),
        decision="limited_attention_earned",
    )
    earned = InvestigationPolicyEvaluation.build(**earned_values)
    protocol = p34_activation_protocol()
    activation = P34ActivationDecision.build(
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.protocol_sha256,
        evaluation_id=earned.evaluation_id,
        evaluation_sha256=earned.evaluation_sha256,
        activated_policy_id=protocol.activated_policy_id,
        activated_policy_sha256=protocol.activated_policy_sha256,
        state="limited_attention",
        production_policy_kind="limited_attention",
        blockers=(),
        recovery_debt=(),
        decided_at=decided_at,
    )
    repository.append_evaluation(earned)
    repository.append_activation_decision(activation)
    return activation


def _setup_snapshots(workflow: ControlledWorkflow) -> dict[str, SetupSnapshot]:
    values = {"A": 50.0, "B": 50.5, "A2": 50.0}
    return {
        run_id: SetupSnapshot(
            setup_id=f"setup-{stage.lower()}",
            run_id=run_id,
            cross_weight_percent=values[stage],
        )
        for stage, run_id in workflow.stage_run_ids.items()
    }


def _compatibility_identity() -> dict[str, Any]:
    return {
        "driver_user_id": "driver-a",
        "car_path": "nascar-nextgen-chevy",
        "car_version": "2026.08",
        "iracing_build_version": "2026.08.1",
        "track_name": "atlanta",
        "track_configuration_name": "oval",
        "car_configuration_name": "speedway",
    }


def _workflow(
    *,
    workflow_id: str = "workflow-lifecycle",
    verdict: str = "keep",
) -> tuple[ControlledWorkflow, dict[str, SetupSnapshot]]:
    workflow = _scored_workflow(
        workflow_id=workflow_id,
        source_run_id=f"{workflow_id}-source",
    )
    execution = workflow.execution
    assert execution is not None
    if verdict == "undo":
        execution = execution.model_copy(update={"countereffect_passed": False})
    elif verdict == "invalid":
        execution = execution.model_copy(
            update={
                "phase_effect_b_vs_a_s": 0.05,
                "phase_effect_b_vs_a2_s": 0.05,
            }
        )
    quality = score_test_execution(execution)
    assert quality.verdict == verdict
    workflow = workflow.model_copy(update={"execution": execution, "quality": quality})
    setups = _setup_snapshots(workflow)
    identity = _compatibility_identity()
    stages = {
        stage: {
            "run_id": run_id,
            "compatibility_identity": identity,
            "setup_fingerprint": canonical_json_sha256(setups[run_id]),
            "eligible_lap_numbers": list(
                workflow.stage_eligible_lap_numbers[stage]
            ),
        }
        for stage, run_id in workflow.stage_run_ids.items()
    }
    snapshot = {
        **workflow.reproduction_snapshot,
        "decision_context": {"objective": "race_long_run"},
        "stages": stages,
        "p19_authority_binding": {
            "session_id": "session-workflow",
            "reasoning_snapshot_sha256": "d" * 64,
        },
        "p19_outcome_binding": {
            "workflow_id": workflow.workflow_id,
            "reasoning_snapshot_sha256": "d" * 64,
        },
    }
    workflow = workflow.model_copy(update={"reproduction_snapshot": snapshot})
    return ControlledWorkflow.model_validate(workflow.model_dump(mode="python")), setups


def _controlled_outcome(
    workflow: ControlledWorkflow,
    *,
    verdict: str,
    workflow_id: str | None = None,
    source_run_id: str | None = None,
    stage_run_ids: tuple[str, ...] | None = None,
    countereffects: tuple[str, ...] = (),
) -> ControlledCauseOutcome:
    invalid = verdict == "invalid"
    return ControlledCauseOutcome(
        workflow_id=workflow_id or workflow.workflow_id,
        outcome="invalid" if invalid else "inconclusive",
        verdict=verdict,
        source_run_id=source_run_id or workflow.source_run_id,
        stage_run_ids=(
            stage_run_ids
            if stage_run_ids is not None
            else tuple(workflow.stage_run_ids[stage] for stage in ("A", "B", "A2"))
        ),
        eligible_lap_ids=(
            ()
            if invalid
            else tuple(
                f"{stage}:{lap}"
                for stage in ("A", "B", "A2")
                for lap in workflow.stage_eligible_lap_numbers[stage]
            )
        ),
        metric="phase_time_s",
        phase="entry",
        actual_effect_s=None if invalid else -0.05,
        time_origin_phase=None if invalid else "entry",
        time_origin_pct=None if invalid else 25.0,
        downstream_carry_effect_s=None if invalid else -0.01,
        control_key="cross_weight_percent",
        countereffects=countereffects,
        blocker_reasons=("The A/B/A2 protocol was invalid.",) if invalid else (),
        diagnostic_validity="control_response_only",
        control_direction_result="invalid" if invalid else "matched",
    )


class _SetupRepository:
    def __init__(self, setups: dict[str, SetupSnapshot]) -> None:
        self.setups = setups

    def get_setup_snapshots(
        self, run_ids: tuple[str, ...]
    ) -> dict[str, SetupSnapshot]:
        return {run_id: self.setups[run_id] for run_id in run_ids}


def _patch_manifest_parts(monkeypatch, workflow: ControlledWorkflow) -> dict[str, str]:
    identity = _compatibility_identity()
    build_hashes = {
        run_id: canonical_json_sha256(
            {"canonical_runtime_build": run_id, "version": "2026.08.1"}
        )
        for run_id in workflow.stage_run_ids.values()
    }
    monkeypatch.setattr(
        service,
        "_manifest_parts",
        lambda run_id: (identity, build_hashes[run_id]),
    )
    return build_hashes


def _build_workflow_experience(
    monkeypatch,
    workflow: ControlledWorkflow,
    setups: dict[str, SetupSnapshot],
    outcome: ControlledCauseOutcome,
):
    build_hashes = _patch_manifest_parts(monkeypatch, workflow)
    experience = service.build_controlled_workflow_experience(
        workflow,
        controlled_outcome=outcome,
        closing_reasoning=_reasoning("d" * 64),
        p19_reasoning_snapshot_sha256="d" * 64,
        repository=_SetupRepository(setups),  # type: ignore[arg-type]
    )
    return experience, build_hashes


def _seed_runs(db_path, run_ids: tuple[str, ...]) -> None:
    connection = initialize_database(db_path)
    try:
        connection.executemany(
            "INSERT INTO runs (run_id, source_file, import_time, imported_at, session_json) "
            "VALUES (?, ?, '2026-08-14', '2026-08-14', '{}')",
            ((run_id, f"{run_id}.ibt") for run_id in run_ids),
        )
        connection.commit()
    finally:
        connection.close()


def _corrupt_empty_learning_head(db_path) -> None:
    connection = initialize_database(db_path)
    try:
        connection.execute(
            "UPDATE engineering_experience_stream_head "
            "SET record_count = 0, head_sha256 = ?",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize(
    "drift",
    [
        {"current_run_id": "another-run"},
        {"current_setup_id": "another-setup"},
        {"current_setup_sha256": "e" * 64},
        {"build_sha256": "e" * 64},
    ],
    ids=("run", "setup-id", "setup-snapshot", "build"),
)
def test_investigation_builder_rejects_terminal_opening_provenance_drift(
    drift: dict[str, str],
) -> None:
    investigation, current, decision, events = _crew_case(**drift)

    with pytest.raises(ValueError, match="opening.*provenance|build.*identity"):
        service.build_investigation_experience(
            investigation=investigation,
            events=events,
            current=current,
            terminal_decision=decision,
            p32_projection_sha256="9" * 64,
        )


def test_workflow_builder_preserves_canonical_build_and_hides_setup_values(
    monkeypatch,
) -> None:
    workflow, setups = _workflow()
    outcome = _controlled_outcome(workflow, verdict="keep")
    experience, build_hashes = _build_workflow_experience(
        monkeypatch, workflow, setups, outcome
    )

    assert tuple(
        item.build_context_sha256 for item in experience.source_provenance
    ) == tuple(build_hashes[run_id] for run_id in workflow.stage_run_ids.values())
    assert experience.context.setup_snapshot_sha256 == canonical_json_sha256(
        setups[workflow.stage_run_ids["B"]]
    )
    assert experience.car_response is not None
    response = experience.car_response.model_dump(mode="python")
    assert not {
        "current_value",
        "proposed_value",
        "observed_a_value",
        "observed_b_value",
        "observed_a2_value",
    } & set(response)
    assert 50.0 not in response.values()
    assert 50.5 not in response.values()
    assert experience.car_response.setup_authorized is False


def test_workflow_builder_rejects_a_b_a2_compatibility_drift(monkeypatch) -> None:
    workflow, setups = _workflow()
    snapshot = dict(workflow.reproduction_snapshot)
    stages = {
        stage: dict(value) for stage, value in snapshot["stages"].items()
    }
    stages["A2"]["compatibility_identity"] = {
        **_compatibility_identity(),
        "iracing_build_version": "2026.09.0",
    }
    snapshot["stages"] = stages
    drifted = workflow.model_copy(update={"reproduction_snapshot": snapshot})
    _patch_manifest_parts(monkeypatch, drifted)

    with pytest.raises(ValueError, match="canonical A/B/A2 compatibility"):
        service.build_controlled_workflow_experience(
            drifted,
            controlled_outcome=_controlled_outcome(drifted, verdict="keep"),
            closing_reasoning=_reasoning("d" * 64),
            p19_reasoning_snapshot_sha256="d" * 64,
            repository=_SetupRepository(setups),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("verdict", ["invalid", "undo"])
def test_workflow_builder_preserves_invalid_and_undo_axes(
    monkeypatch,
    verdict: str,
) -> None:
    workflow, setups = _workflow(verdict=verdict)
    outcome = _controlled_outcome(workflow, verdict=verdict)
    experience, _ = _build_workflow_experience(
        monkeypatch, workflow, setups, outcome
    )

    response = experience.car_response
    assert response is not None
    assert response.policy_verdict == verdict
    if verdict == "invalid":
        assert response.p19_mechanism_assessment == "invalid"
        assert response.control_response_assessment == "invalid"
        assert response.phase_time_effect_s is None
        assert response.carry_effect_s is None
    else:
        assert response.p19_mechanism_assessment == "inconclusive"
        assert response.control_response_assessment == "matched"
        assert response.countereffects == (
            "A recorded countereffect made the total controlled response unacceptable.",
        )
        assert response.setup_authorized is False


@pytest.mark.parametrize("foreign_axis", ["workflow", "source", "stages"])
def test_workflow_builder_rejects_foreign_controlled_outcome_axes(
    monkeypatch,
    foreign_axis: str,
) -> None:
    workflow, setups = _workflow()
    foreign = _controlled_outcome(
        workflow,
        verdict="keep",
        workflow_id=(
            "another-workflow" if foreign_axis == "workflow" else None
        ),
        source_run_id=(
            "another-source" if foreign_axis == "source" else None
        ),
        stage_run_ids=(
            ("another-a", "another-b", "another-a2")
            if foreign_axis == "stages"
            else None
        ),
    )
    _patch_manifest_parts(monkeypatch, workflow)

    with pytest.raises(ValueError, match="controlled outcome.*workflow"):
        service.build_controlled_workflow_experience(
            workflow,
            controlled_outcome=foreign,
            closing_reasoning=_reasoning("d" * 64),
            p19_reasoning_snapshot_sha256="d" * 64,
            repository=_SetupRepository(setups),  # type: ignore[arg-type]
        )


def test_terminal_atomic_retry_rolls_back_then_commits_once(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "terminal-retry.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(investigation)

    with monkeypatch.context() as injected:
        injected.setattr(
            EngineeringLearningRepository,
            "append_experience_in_transaction",
            lambda _connection, _record: (_ for _ in ()).throw(
                RuntimeError("injected P33 failure")
            ),
        )
        with pytest.raises(RuntimeError, match="injected P33 failure"):
            repository.append_terminal_event_and_experience(terminal, experience)

    assert repository.list_events(investigation.investigation_id) == ()
    captured = repository.append_terminal_event_and_experience(terminal, experience)
    retried = repository.append_terminal_event_and_experience(terminal, experience)

    assert captured == retried
    assert captured.payload.learning_capture_state == "captured"
    assert captured.payload.learning_capture_experience_id == experience.experience_id
    assert (
        captured.payload.learning_capture_experience_sha256
        == experience.experience_sha256
    )
    assert repository.list_events(investigation.investigation_id) == (captured,)
    assert EngineeringLearningRepository(db_path).stream_state().record_count == 1


def test_terminal_capture_commits_crew_p33_certificate_and_comparison_once(
    tmp_path,
) -> None:
    db_path = tmp_path / "terminal-p34-atomic.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    certificate, comparison, pair = _p34_terminal_unit(
        db_path,
        investigation,
        current,
        terminal,
        experience,
    )
    terminal = _event_with_prediction_pair(terminal, pair)

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )
    replay = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )

    assert replay == captured
    assert captured.payload.learning_capture_state == "captured"
    assert captured.payload.adaptation_capture_state == "captured"
    assert (
        captured.payload.adaptation_capture_certificate_id
        == certificate.certificate_id
    )
    adaptation = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=(
            "outcome_certificate",
            "paired_comparison",
            "negative_control_result",
        ),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    assert not adaptation.blockers
    assert {
        item.certificate_id
        for item in adaptation.records
        if hasattr(item, "certificate_id")
    } == {
        certificate.certificate_id
    }
    assert len(adaptation.records) == 3
    control = next(
        item
        for item in adaptation.records
        if item.schema_version == "p34.negative-control-result.v1"
    )
    assert control.control_id == "no_relevant_history"
    assert control.passed is True
    restarted_control = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("negative_control_result",),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    assert restarted_control.records == (control,)
    frozen_pair = InvestigationAdaptationRepository(db_path).get_paired_decision(
        certificate.pair_sha256
    )
    assert frozen_pair is not None
    recovery_workspace = SimpleNamespace(
        investigation=SimpleNamespace(
            investigation_id=investigation.investigation_id,
        ),
        folded_state=SimpleNamespace(status="open"),
        identity=SimpleNamespace(workspace_revision=frozen_pair.workspace_revision),
    )
    # Simulate a process crash after the atomic capture commit but before its
    # post-commit activation review. The next explicit pair-freeze mutation
    # repairs that debt; a restart/retry remains exactly idempotent.
    assert _freeze_p34_pair_for_workspace(
        recovery_workspace,
        db_path=db_path,
    ) == frozen_pair
    assert _freeze_p34_pair_for_workspace(
        recovery_workspace,
        db_path=db_path,
    ) == frozen_pair
    _review_p34_terminal_capture(captured, db_path=db_path)
    reviewed = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("policy_evaluation", "activation_decision"),
        limit=10,
    )
    assert len(reviewed.records) == 2
    reviewed_hashes = tuple(
        item.evaluation_sha256
        if item.schema_version == "p34.policy-evaluation.v1"
        else item.decision_sha256
        for item in reviewed.records
    )
    _review_p34_terminal_capture(captured, db_path=db_path)
    restarted_review = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("policy_evaluation", "activation_decision"),
        limit=10,
    )
    assert len(restarted_review.records) == 2
    assert tuple(
        item.evaluation_sha256
        if item.schema_version == "p34.policy-evaluation.v1"
        else item.decision_sha256
        for item in restarted_review.records
    ) == reviewed_hashes
    assert EngineeringLearningRepository(db_path).stream_state().record_count == 1


def test_p34_prediction_receipt_rejects_missing_swapped_and_stale_bindings(
    tmp_path,
) -> None:
    db_path = tmp_path / "p34-prediction-receipt-hostiles.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    _certificate, _comparison, pair = _p34_terminal_unit(
        db_path,
        investigation,
        current,
        terminal,
        experience,
    )
    exact = _event_with_prediction_pair(terminal, pair)
    swapped_payload = exact.payload.model_copy(
        update={"adaptation_prediction_pair_sha256": "f" * 64}
    )
    swapped_draft = exact.model_copy(
        update={"payload": swapped_payload, "event_hash": "0" * 64}
    )
    swapped = swapped_draft.model_copy(
        update={"event_hash": crew_chief_event_hash(swapped_draft)}
    )
    stale_draft = exact.model_copy(
        update={"workspace_revision": "e" * 64, "event_hash": "0" * 64}
    )
    stale = stale_draft.model_copy(
        update={"event_hash": crew_chief_event_hash(stale_draft)}
    )
    forged_source_payload = exact.payload.model_copy(
        update={"adaptation_prediction_source_snapshot_sha256": "d" * 64}
    )
    forged_source_draft = exact.model_copy(
        update={"payload": forged_source_payload, "event_hash": "0" * 64}
    )
    forged_source = forged_source_draft.model_copy(
        update={"event_hash": crew_chief_event_hash(forged_source_draft)}
    )

    connection = initialize_database(db_path)
    try:
        CrewChiefRepository._validate_p34_prediction_receipt(connection, exact)
        with pytest.raises(CrewChiefIntegrityError, match="omitted"):
            CrewChiefRepository._validate_p34_prediction_receipt(
                connection,
                terminal,
            )
        with pytest.raises(CrewChiefIntegrityError, match="stale or swapped"):
            CrewChiefRepository._validate_p34_prediction_receipt(
                connection,
                swapped,
            )
        with pytest.raises(CrewChiefIntegrityError, match="exactly follow"):
            CrewChiefRepository._validate_p34_prediction_receipt(
                connection,
                stale,
            )
        with pytest.raises(CrewChiefIntegrityError, match="exactly follow"):
            CrewChiefRepository._validate_p34_prediction_receipt(
                connection,
                forged_source,
            )
    finally:
        connection.close()


@pytest.mark.parametrize("mandatory_violation", (False, True))
def test_active_p34_terminal_keeps_clean_activation_or_persists_typed_rollback(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    mandatory_violation: bool,
) -> None:
    db_path = tmp_path / f"p34-active-{'violation' if mandatory_violation else 'clean'}.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    adaptation = InvestigationAdaptationRepository(db_path)
    activation = _persist_test_p34_earned_activation(
        adaptation,
        decided_at=terminal.created_at - timedelta(seconds=2),
    )
    certificate, comparison, pair = _p34_terminal_unit(
        db_path,
        investigation,
        current,
        terminal,
        experience,
        activation_decision=activation,
        complete_mandatory_checks=not mandatory_violation,
    )
    terminal = _event_with_prediction_pair(terminal, pair)
    assert comparison.mandatory_check_violations == int(mandatory_violation)

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )
    assert captured.payload.adaptation_capture_state == "captured"
    if not mandatory_violation:
        # Corrected v1 cannot scientifically earn activation. Inject only the
        # typed mechanics seam so a clean active terminal cannot manufacture a
        # rollback; production resolver rejection remains explicit below.
        monkeypatch.setattr(
            crew_chief_service,
            "review_p34_after_terminal_capture",
            lambda *_args, **_kwargs: None,
        )
    _review_p34_terminal_capture(captured, db_path=db_path)

    restarted = InvestigationAdaptationRepository(db_path)
    decisions = restarted.query_records(
        record_kinds=("activation_decision",),
        protocol_id=p34_activation_protocol().protocol_id,
        limit=10,
    ).records
    if mandatory_violation:
        rollback = decisions[0]
        assert rollback.state == "shadow_only"
        assert rollback.rollback_applied is True
        assert rollback.supersedes_decision_id == activation.decision_id
        assert rollback.supersedes_decision_sha256 == activation.decision_sha256
        assert rollback.recovery_debt
        assert resolve_effective_activation_decision(restarted) is None
    else:
        assert all(item.state == "limited_attention" for item in decisions)
        assert all(not item.rollback_applied for item in decisions)
        assert resolve_effective_activation_decision(restarted) is None

    # Restarting the post-terminal review cannot duplicate or reverse either
    # the retained earned state or its typed rollback debt.
    before = tuple(item.decision_sha256 for item in decisions)
    _review_p34_terminal_capture(captured, db_path=db_path)
    after = restarted.query_records(
        record_kinds=("activation_decision",),
        protocol_id=p34_activation_protocol().protocol_id,
        limit=10,
    ).records
    assert tuple(item.decision_sha256 for item in after) == before


def test_cold_get_matches_execution_and_active_pair_honors_durable_rollback(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "p34-active-pair-rollback.sqlite"
    investigation, current_learning, _decision, _events = _crew_case()
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    adaptation = InvestigationAdaptationRepository(db_path)
    prior = _investigation_record(707)
    EngineeringLearningRepository(db_path).append_experience(prior)
    p33_state = EngineeringLearningRepository(db_path).stream_state()
    activated_at = investigation.opened_at + timedelta(minutes=1)
    activation = _persist_test_p34_earned_activation(
        adaptation,
        decided_at=activated_at,
    )
    mandatory = ("workspace_identity", "driver_car_separation")
    baseline = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Deterministic current-evidence inspection.",
        mandatory_check_ids=mandatory,
    )
    memory = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_time_loss_origin",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=2,
        selected_ordinal=1,
        reason="Previously earned limited attention promoted one adjacent inspection.",
        mandatory_check_ids=mandatory,
        source_memory_record_ids=(prior.experience_id,),
    )
    identity = investigation.workspace_identity
    active_pair = build_paired_investigation_decision(
        baseline_policy=baseline_investigation_policy(),
        memory_policy=limited_attention_investigation_policy(),
        investigation_id=investigation.investigation_id,
        investigation_opened_at=investigation.opened_at,
        run_id=identity.run_id,
        session_id=identity.session_id,
        workspace_revision=identity.workspace_revision,
        authority_revision=identity.authority_revision,
        step_number=0,
        baseline_decision=baseline,
        memory_decision=memory,
        available_tool_ids=(
            "inspect_lap_time_opportunity",
            "inspect_time_loss_origin",
        ),
        eligible_tool_ids=(
            "inspect_lap_time_opportunity",
            "inspect_time_loss_origin",
        ),
        completed_tool_ids=(),
        available_artifact_ids=(),
        current_truth_sha256="1" * 64,
        p19_snapshot_sha256=identity.reasoning_snapshot_sha256,
        current_p19_cause_ids=("cause-platform",),
        current_p19_cause_states=(
            P19CauseState(cause_id="cause-platform", state="possible"),
        ),
        current_contradiction_ids=(),
        strongest_contradiction_id=None,
        current_objective=identity.objective_id.value,
        p33_projection_sha256=identity.learning_projection_sha256,
        p33_history_revision=p33_state.history_revision,
        p33_ledger_head_sha256=p33_state.head_sha256,
        p33_context_sha256=current_learning.context.context_sha256,
        p33_problem_sha256=current_learning.problem.problem_sha256,
        track=current_learning.context.track,
        track_configuration=current_learning.context.track_configuration,
        package_type=current_learning.context.package_type,
        iracing_build=current_learning.context.iracing_build,
        problem_family="entry",
        problem_orientation="combined",
        track_class="intermediate",
        phase=current_learning.problem.phase,
        build_review_state="same_build",
        driver_drift_state="stable",
        decision_frozen_at=activated_at + timedelta(minutes=1),
        context_transfer_class="exact",
        p20_projection_sha256=identity.p20_state_revision,
        p26_projection_sha256=identity.p26_knowledge_graph_sha256,
        p32_projection_sha256=identity.p32_projection_sha256,
        activation_decision=activation,
    )
    adaptation.append_paired_decision(active_pair)
    blocker = "A mandatory authority invariant failed after activation."
    protocol = p34_activation_protocol()
    rollback = P34ActivationDecision.build(
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.protocol_sha256,
        evaluation_id=activation.evaluation_id,
        evaluation_sha256=activation.evaluation_sha256,
        activated_policy_id=protocol.activated_policy_id,
        activated_policy_sha256=protocol.activated_policy_sha256,
        state="shadow_only",
        production_policy_kind="deterministic_baseline",
        blockers=(blocker,),
        recovery_debt=(blocker,),
        supersedes_decision_id=activation.decision_id,
        supersedes_decision_sha256=activation.decision_sha256,
        rollback_applied=True,
        decided_at=active_pair.decision_frozen_at + timedelta(minutes=1),
    )
    baseline_subgoal = InvestigationSubgoal(
        subgoal_id="subgoal-baseline-a",
        title="Inspect lap time opportunity",
        selected_tool=baseline.action_id,
        why_this_tool="Deterministic current-evidence inspection.",
        distinguishes_cause_ids=("cause-platform",),
        required_evidence=("exact current evidence",),
        stop_condition="Stop after the canonical artifact is attached.",
        priority_rank=1,
    )
    workspace = SimpleNamespace(
        identity=identity,
        investigation=investigation,
        folded_state=SimpleNamespace(
            status="open",
            pending_driver_question_id=None,
            driver_answers=("entry",),
            last_sequence=0,
            completed_tool_ids=(),
            investigation_id=investigation.investigation_id,
        ),
        current_subgoal=baseline_subgoal,
        learning_prior=SimpleNamespace(
            state="available",
            context_transfer_level="exact",
            driver_tendencies=(),
            useful_prior_investigations=(
                SimpleNamespace(
                    experience_id=prior.experience_id,
                    outcome=SimpleNamespace(completed_at=activated_at),
                ),
            ),
            context_transfers=(
                SimpleNamespace(
                    experience_id=prior.experience_id,
                    level="exact",
                    drift_reasons=(),
                    blocker_reasons=(),
                ),
            ),
            recommended_attention_order=(
                SimpleNamespace(
                    tool_id=memory.action_id,
                    safety_band="performance_measurement",
                    transfer_level="exact",
                    source_experience_ids=(prior.experience_id,),
                    baseline_rank_within_band=2,
                    learned_rank_within_band=1,
                    reason="Exact prior exposed the discriminator earlier.",
                ),
            ),
        ),
    )
    captured_events: list[tuple[object, ...]] = []

    class _CrewRepository:
        def __init__(self, _db_path=None) -> None:
            pass

        def append_events(self, events) -> None:
            captured_events.append(tuple(events))

        def mutation_receipt(self, *_args, **_kwargs):
            return None

        def record_continue_action_in_transaction(self, *_args) -> None:
            return None

        def validate_inspection_trace(self, _events) -> None:
            return None

        def append_events_in_transaction(self, _connection, events) -> None:
            captured_events.append(tuple(events))

    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_crew_chief_workspace",
        lambda *_args, **_kwargs: workspace,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.CrewChiefRepository",
        _CrewRepository,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._select_tool_entries",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._commit_crew_case_mutation",
        lambda **values: (values["apply"](object()), workspace)[1],
    )

    # A caller-authored empty-ledger artifact is deliberately not production
    # activation proof. Inject it only to exercise Crew's future activation
    # mechanics and then replay the durable rollback fallback.
    assert (
        resolve_effective_activation_decision(
            InvestigationAdaptationRepository(db_path)
        )
        is None
    )
    mechanics_active = True
    mutation_verified = False

    def injected_mechanics_activation(_repository):
        return activation if mechanics_active and mutation_verified else None

    def injected_mutation_restore(_repository):
        nonlocal mutation_verified
        mutation_verified = True
        return activation if mechanics_active else None

    monkeypatch.setattr(
        crew_chief_service,
        "resolve_effective_activation_decision",
        injected_mechanics_activation,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "restore_effective_activation_on_mutation",
        injected_mutation_restore,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_source_snapshot_sha256",
        lambda _workspace: CrewChiefRepository._p34_pair_source_snapshot_sha256(
            active_pair
        ),
    )
    # A cold GET exposes the deterministic baseline. The mutation may verify
    # the durable activation, but must execute that same baseline for this
    # revision; limited attention begins only on the following revision.
    assert injected_mechanics_activation(adaptation) is None
    cold_get = crew_chief_service.build_crew_chief_workspace(
        identity.run_id,
        session_id=identity.session_id,
        investigation_id=investigation.investigation_id,
        db_path=db_path,
    )
    displayed_next_action = cold_get.current_subgoal.selected_tool
    assert displayed_next_action == baseline.action_id
    continue_investigation(
        identity.run_id,
        investigation.investigation_id,
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
        db_path=db_path,
    )
    cold_invocation, cold_result = captured_events[0][:2]
    assert cold_invocation.payload.tool_id == displayed_next_action
    assert cold_result.payload.tool_id == baseline.action_id
    assert cold_invocation.payload.adaptation_prediction_pair_id is None

    continue_investigation(
        identity.run_id,
        investigation.investigation_id,
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
        db_path=db_path,
    )
    active_invocation, active_result = captured_events[1][:2]
    assert active_invocation.payload.tool_id == memory.action_id
    assert active_result.payload.tool_id == memory.action_id
    assert active_invocation.payload.adaptation_prediction_pair_id == active_pair.pair_id
    assert (
        active_invocation.payload.adaptation_prediction_source_snapshot_sha256
        == CrewChiefRepository._p34_pair_source_snapshot_sha256(active_pair)
    )

    adaptation.append_activation_decision(rollback)
    mechanics_active = False
    assert resolve_effective_activation_decision(
        InvestigationAdaptationRepository(db_path)
    ) is None
    assert _freeze_p34_pair_for_workspace(workspace, db_path=db_path) is None
    continue_investigation(
        identity.run_id,
        investigation.investigation_id,
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
        db_path=db_path,
    )

    invocation, result = captured_events[2][:2]
    assert invocation.payload.tool_id == baseline.action_id
    assert result.payload.tool_id == baseline.action_id
    assert invocation.payload.adaptation_prediction_pair_id is None
    assert all(
        event.payload.tool_id != memory.action_id for event in (invocation, result)
    )
    restarted = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("activation_decision",),
        protocol_id=protocol.protocol_id,
        limit=10,
    )
    assert restarted.records[0] == rollback


def test_post_terminal_p34_review_failure_cannot_veto_captured_truth(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "p34-review-fail-contained.sqlite"
    _seed_runs(db_path, ("run-investigation",))
    _investigation_value, _current_value, _decision_value, events = _crew_case()
    terminal = events[-1]
    captured = terminal.model_copy(
        update={
            "payload": terminal.payload.model_copy(
                update={"adaptation_capture_state": "captured"}
            )
        }
    )
    attempts: list[datetime] = []

    def fail_review(_repository, *, captured_at: datetime):
        attempts.append(captured_at)
        raise RuntimeError("injected post-terminal review failure")

    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.review_p34_after_terminal_capture",
        fail_review,
    )

    _review_p34_terminal_capture(captured, db_path=db_path)

    assert attempts == [captured.created_at]
    assert InvestigationAdaptationRepository(db_path).stream_state().record_count == 0


def test_scored_workflow_p34_followup_runs_after_score_and_is_fail_contained(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "p34-workflow-followup.sqlite"
    workflow = _scored_workflow(
        workflow_id="p34-followup-workflow",
        source_run_id="p34-followup-source",
    )
    previous = _scored_workflow(
        workflow_id="p34-followup-crash-recovery",
        source_run_id="p34-followup-prior-source",
    )
    scope = (
        workflow.source_run_id,
        *workflow.stage_run_ids.values(),
        previous.source_run_id,
        *previous.stage_run_ids.values(),
    )
    _seed_runs(db_path, scope)
    repository = RaceLabRepository(db_path)
    repository.save_controlled_workflow(previous)
    repository.save_controlled_workflow(workflow)
    pending_ids = (previous.workflow_id, workflow.workflow_id)
    monkeypatch.setattr(
        investigation_adaptation_service,
        "pending_p34_scored_workflow_ids",
        lambda _repository, *, limit: (
            pending_ids if limit == 512 else pytest.fail("unexpected recovery bound")
        ),
    )
    monkeypatch.setattr(
        repository,
        "list_controlled_workflows",
        lambda *_args, **_kwargs: pytest.fail(
            "P34 recovery must not scan the workflow catalog"
        ),
    )
    captured: list[str] = []

    monkeypatch.setattr(
        controlled_workflow_service,
        "record_workflow_outcome",
        lambda *_args, **_kwargs: None,
    )

    def capture_followup(_repository, *, workflow: ControlledWorkflow):
        assert repository.get_controlled_workflow(workflow.workflow_id) == workflow
        captured.append(workflow.workflow_id)
        return None

    monkeypatch.setattr(
        investigation_adaptation_service,
        "capture_p34_controlled_workflow_followup",
        capture_followup,
    )
    controlled_workflow_service.record_scored_workflow_side_effects(
        workflow,
        repository=repository,
    )
    assert set(captured) == {workflow.workflow_id, previous.workflow_id}

    real_get_workflow = repository.get_controlled_workflow
    lookup_recovery: list[str] = []

    def corrupt_first_lookup(workflow_id: str):
        if workflow_id == previous.workflow_id:
            raise ValueError("injected corrupt pending workflow")
        return real_get_workflow(workflow_id)

    monkeypatch.setattr(repository, "get_controlled_workflow", corrupt_first_lookup)
    monkeypatch.setattr(
        investigation_adaptation_service,
        "capture_p34_controlled_workflow_followup",
        lambda _repository, *, workflow: lookup_recovery.append(
            workflow.workflow_id
        ),
    )
    controlled_workflow_service.recover_p34_scored_workflow_followups(repository)
    assert lookup_recovery == [workflow.workflow_id]
    monkeypatch.setattr(repository, "get_controlled_workflow", real_get_workflow)

    recovery_attempts: list[str] = []

    def fail_one_followup(_repository, *, workflow: ControlledWorkflow):
        recovery_attempts.append(workflow.workflow_id)
        if workflow.workflow_id == previous.workflow_id:
            raise RuntimeError("injected P34 follow-up failure")
        return None

    monkeypatch.setattr(
        investigation_adaptation_service,
        "capture_p34_controlled_workflow_followup",
        fail_one_followup,
    )
    controlled_workflow_service.record_scored_workflow_side_effects(
        workflow,
        repository=repository,
    )
    assert repository.get_controlled_workflow(workflow.workflow_id) == workflow
    assert set(recovery_attempts) == {workflow.workflow_id, previous.workflow_id}


def test_scored_workflow_p34_recovery_drains_513_in_bounded_restart_pages(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "p34-workflow-bounded-restart.sqlite"
    repository = RaceLabRepository(db_path)
    template = _scored_workflow(
        workflow_id="p34-bounded-template",
        source_run_id="p34-bounded-source",
    )
    pending = [f"p34-pending-{index:03d}" for index in range(513)]
    workflows = {
        workflow_id: template.model_copy(update={"workflow_id": workflow_id})
        for workflow_id in pending
    }
    inventory_calls: list[tuple[str, int]] = []

    def pending_page(adaptation, *, limit: int):
        assert adaptation.db_path == db_path
        inventory_calls.append((p34_activation_protocol().protocol_id, limit))
        return tuple(pending[:limit])

    def capture_page(_adaptation, *, workflow: ControlledWorkflow):
        pending.remove(workflow.workflow_id)
        return None

    monkeypatch.setattr(
        investigation_adaptation_service,
        "pending_p34_scored_workflow_ids",
        pending_page,
    )
    monkeypatch.setattr(
        investigation_adaptation_service,
        "capture_p34_controlled_workflow_followup",
        capture_page,
    )
    monkeypatch.setattr(
        repository,
        "get_controlled_workflow",
        lambda workflow_id: workflows.get(workflow_id),
    )

    controlled_workflow_service.recover_p34_scored_workflow_followups(repository)
    assert pending == ["p34-pending-512"]

    restarted = RaceLabRepository(db_path)
    monkeypatch.setattr(
        restarted,
        "get_controlled_workflow",
        lambda workflow_id: workflows.get(workflow_id),
    )
    controlled_workflow_service.recover_p34_scored_workflow_followups(restarted)

    assert pending == []
    assert inventory_calls == [
        (p34_activation_protocol().protocol_id, 512),
        (p34_activation_protocol().protocol_id, 512),
    ]


def test_typed_p34_failure_commits_crew_and_p33_as_blocked_without_backfill(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "terminal-p34-blocked.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    certificate, comparison, pair = _p34_terminal_unit(
        db_path,
        investigation,
        current,
        terminal,
        experience,
    )
    terminal = _event_with_prediction_pair(terminal, pair)
    with monkeypatch.context() as injected:
        injected.setattr(
            InvestigationAdaptationRepository,
            "append_comparison_in_transaction",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                InvestigationAdaptationIntegrityError("injected P34 corruption")
            ),
        )
        captured = crew.append_terminal_event_and_experience(
            terminal,
            experience,
            outcome_certificate=certificate,
            outcome_comparison=comparison,
        )

    replay = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )

    assert replay == captured
    assert captured.payload.learning_capture_state == "captured"
    assert captured.payload.adaptation_capture_state == "blocked"
    assert (
        captured.payload.adaptation_capture_certificate_id
        == certificate.certificate_id
    )
    assert (
        captured.payload.adaptation_capture_blocker_reason
        == P34_CAPTURE_INTEGRITY_BLOCKER
    )
    adaptation = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("outcome_certificate", "paired_comparison"),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    assert not adaptation.records
    assert EngineeringLearningRepository(db_path).stream_state().record_count == 1


def test_foreign_protocol_payload_corruption_cannot_hide_current_p34_capture(
    tmp_path,
) -> None:
    db_path = tmp_path / "terminal-p34-foreign-corrupt.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    certificate, comparison, pair = _p34_terminal_unit(
        db_path,
        investigation,
        current,
        terminal,
        experience,
    )
    terminal = _event_with_prediction_pair(terminal, pair)
    foreign = P34ActivationDecision.build(
        protocol_id="p34proto_" + "f" * 24,
        protocol_sha256="f" * 64,
        evaluation_id="p34eval_" + "e" * 24,
        evaluation_sha256="e" * 64,
        activated_policy_id="p34pol_" + "d" * 24,
        activated_policy_sha256="d" * 64,
        state="shadow_only",
        production_policy_kind="deterministic_baseline",
        blockers=("A foreign protocol remains locked.",),
        recovery_debt=("A foreign protocol remains locked.",),
        decided_at=terminal.created_at - timedelta(microseconds=1),
    )
    adaptation = InvestigationAdaptationRepository(db_path)
    adaptation.append_activation_decision(foreign)
    connection = initialize_database(db_path)
    try:
        connection.execute(
            "DROP TRIGGER investigation_adaptation_records_no_update"
        )
        connection.execute(
            "UPDATE investigation_adaptation_records SET record_json = '{}' "
            "WHERE record_id = ?",
            (foreign.decision_id,),
        )
        connection.commit()
    finally:
        connection.close()

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )

    assert captured.payload.learning_capture_state == "captured"
    assert captured.payload.adaptation_capture_state == "captured"
    persisted = adaptation.query_records(
        record_kinds=("outcome_certificate", "paired_comparison"),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    assert {item.schema_version for item in persisted.records} == {
        "p34.investigation-outcome.v1",
        "p34.paired-investigation-comparison.v1",
    }
    adaptation.stream_state(validate_chain=True, validate_payloads=False)
    with pytest.raises(
        InvestigationAdaptationIntegrityError,
        match="payload is corrupt",
    ):
        adaptation.stream_state(validate_chain=True)


def test_unrelated_p33_payload_corruption_cannot_hide_current_terminal_truth(
    tmp_path,
) -> None:
    db_path = tmp_path / "terminal-p33-unrelated-corrupt.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    learning = EngineeringLearningRepository(db_path)
    unrelated = _investigation_record(87)
    learning.append_experience(unrelated)
    certificate, comparison, pair = _p34_terminal_unit(
        db_path,
        investigation,
        current,
        terminal,
        experience,
    )
    terminal = _event_with_prediction_pair(terminal, pair)
    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER engineering_experiences_no_update")
        connection.execute(
            "UPDATE engineering_experiences SET record_json = '{}' "
            "WHERE experience_id = ?",
            (unrelated.experience_id,),
        )
        connection.commit()
    finally:
        connection.close()

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )

    assert captured.payload.learning_capture_state == "captured"
    assert captured.payload.adaptation_capture_state == "captured"
    relevant = learning.query_relevant(
        experience.context,
        problem=experience.problem,
    )
    assert tuple(item.experience_id for item in relevant.records) == (
        experience.experience_id,
    )
    assert relevant.blockers == ()
    learning.stream_state(validate_chain=True, validate_payloads=False)
    with pytest.raises(
        EngineeringLearningIntegrityError,
        match="payload is corrupt",
    ):
        learning.stream_state(validate_chain=True)


def test_same_decision_pair_cannot_claim_direct_observation_when_next_event_skips_it(
    tmp_path,
) -> None:
    db_path = tmp_path / "p34-skipped-next-event.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    adaptation = InvestigationAdaptationRepository(db_path)
    persist_p34_foundation(adaptation)
    skipped = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_data_quality",
        priority_tier="identity_integrity",
        safe_reorder_group=None,
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="The frozen next action was a data-quality inspection.",
        mandatory_check_ids=(
            "workspace_identity",
            "vehicle_condition_epoch",
            "applied_control_state",
            "strongest_contradiction",
        ),
    )
    pair = build_paired_investigation_decision(
        baseline_policy=baseline_investigation_policy(),
        memory_policy=memory_shadow_investigation_policy(),
        investigation_id=investigation.investigation_id,
        investigation_opened_at=investigation.opened_at,
        run_id=current.context.run_id,
        session_id=current.context.session_id,
        workspace_revision=terminal.workspace_revision,
        authority_revision=investigation.workspace_identity.authority_revision,
        step_number=0,
        baseline_decision=skipped,
        memory_decision=skipped,
        available_tool_ids=("inspect_data_quality",),
        eligible_tool_ids=("inspect_data_quality",),
        completed_tool_ids=(),
        available_artifact_ids=(),
        current_truth_sha256="1" * 64,
        p19_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        current_p19_cause_ids=tuple(
            item.cause_id for item in current.reasoning.causes
        ),
        current_p19_cause_states=tuple(
            P19CauseState(cause_id=item.cause_id, state=item.status)
            for item in current.reasoning.causes
        ),
        current_contradiction_ids=(),
        strongest_contradiction_id=None,
        current_objective=investigation.objective.value,
        p33_projection_sha256="0" * 64,
        p33_history_revision=investigation.workspace_identity.learning_history_revision,
        p33_ledger_head_sha256=None,
        p33_context_sha256=current.context.context_sha256,
        p33_problem_sha256=current.problem.problem_sha256,
        track=current.context.track,
        track_configuration=current.context.track_configuration,
        package_type=current.context.package_type,
        iracing_build=current.context.iracing_build,
        problem_family="entry",
        problem_orientation="combined",
        track_class="intermediate",
        phase=current.problem.phase,
        build_review_state="same_build",
        driver_drift_state="unknown",
        decision_frozen_at=terminal.created_at - timedelta(seconds=1),
        context_transfer_class="none",
        p20_projection_sha256=investigation.workspace_identity.p20_state_revision,
        p26_projection_sha256=(
            investigation.workspace_identity.p26_knowledge_graph_sha256
        ),
        p32_projection_sha256=investigation.workspace_identity.p32_projection_sha256,
    )
    adaptation.append_paired_decision(pair)
    terminal_workspace = SimpleNamespace(
        learning_prior=SimpleNamespace(state="available"),
        terminal_decision=decision,
        critique=SimpleNamespace(passed=True),
        evidence_index=SimpleNamespace(entries=()),
    )
    certificate = _build_p34_outcome_certificate(
        terminal_workspace,
        investigation=investigation,
        terminal_events=events,
        terminal_event=terminal,
        experience=experience,
        pair=pair,
    )
    comparison = _build_p34_completed_comparison(
        (pair,),
        certificate,
        compared_at=terminal.created_at,
    )
    assert certificate is not None
    assert comparison is not None
    assert comparison.observability == "directly_observed"

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )

    assert captured.payload.learning_capture_state == "captured"
    assert captured.payload.adaptation_capture_state == "blocked"
    assert InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("outcome_certificate", "paired_comparison"),
        investigation_id=investigation.investigation_id,
        limit=10,
    ).records == ()


def test_multi_revision_terminal_capture_persists_unobservable_canonical_comparison(
    tmp_path,
) -> None:
    db_path = tmp_path / "terminal-p34-multi-revision.sqlite"
    investigation, current, decision, _events = _crew_case()
    tool_revision = "a" * 64
    terminal_revision = "b" * 64
    invocation = _event(
        investigation.investigation_id,
        1,
        tool_revision,
        "tool_invoked",
        CrewChiefEventPayload(
            message="Requested lap-time opportunity.",
            tool_id="inspect_lap_time_opportunity",
            requested_measurement_ids=("inspect_lap_time_opportunity",),
        ),
    )
    result = _event(
        investigation.investigation_id,
        2,
        tool_revision,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="Attached the exact current artifact.",
            tool_id="inspect_lap_time_opportunity",
            artifact_ids=("opening-artifact",),
            completed_measurement_ids=("inspect_lap_time_opportunity",),
        ),
    )
    terminal = _event(
        investigation.investigation_id,
        3,
        terminal_revision,
        "decision_emitted",
        CrewChiefEventPayload(
            message="No setup call is authorized.",
            decision_kind="no_call",
        ),
    )
    events = (invocation, result, terminal)
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    adaptation = InvestigationAdaptationRepository(db_path)
    baseline_policy = baseline_investigation_policy()
    memory_policy = memory_shadow_investigation_policy()
    for record in (baseline_policy, memory_policy, p34_activation_protocol()):
        adaptation.append_record(record)
    mandatory = (
        "workspace_identity",
        "data_integrity",
        "telemetry_health",
        "context_comparability",
        "traffic_contamination",
        "vehicle_condition_epoch",
        "applied_control_state",
        "strongest_contradiction",
        "driver_car_separation",
    )
    baseline_tool = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Deterministic first inspection.",
        mandatory_check_ids=mandatory,
    )
    shadow_tool = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_time_loss_origin",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=2,
        selected_ordinal=1,
        reason="Exact memory moved the next safe inspection by one slot.",
        mandatory_check_ids=mandatory,
        source_memory_record_ids=("p33x_" + "a" * 24,),
    )

    def paired(
        *,
        workspace_revision: str,
        authority_seed: str,
        step_number: int,
        baseline_decision: InvestigationDecision,
        memory_decision: InvestigationDecision,
        frozen_at: datetime,
        transfer: str,
        driver_state: str,
    ):
        return build_paired_investigation_decision(
            baseline_policy=baseline_policy,
            memory_policy=memory_policy,
            investigation_id=investigation.investigation_id,
            investigation_opened_at=investigation.opened_at,
            run_id=current.context.run_id,
            session_id=current.context.session_id,
            workspace_revision=workspace_revision,
            authority_revision=canonical_json_sha256([authority_seed]),
            step_number=step_number,
            baseline_decision=baseline_decision,
            memory_decision=memory_decision,
            available_tool_ids=(
                "inspect_lap_time_opportunity",
                "inspect_time_loss_origin",
            ),
            eligible_tool_ids=tuple(
                dict.fromkeys(
                    decision.action_id
                    for decision in (baseline_decision, memory_decision)
                    if decision.decision_kind == "inspect_tool"
                )
            ),
            completed_tool_ids=(),
            available_artifact_ids=("opening-artifact",),
            current_truth_sha256=canonical_json_sha256(
                ["truth", workspace_revision]
            ),
            p19_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
            current_p19_cause_ids=tuple(
                item.cause_id for item in current.reasoning.causes
            ),
            current_p19_cause_states=tuple(
                P19CauseState(cause_id=item.cause_id, state=item.status)
                for item in current.reasoning.causes
            ),
            current_contradiction_ids=(),
            strongest_contradiction_id=None,
            current_objective=investigation.objective.value,
            p33_projection_sha256="0" * 64,
            p33_history_revision=investigation.workspace_identity.learning_history_revision,
            p33_ledger_head_sha256=(
                "f" * 64 if memory_decision.source_memory_record_ids else None
            ),
            p33_context_sha256=current.context.context_sha256,
            p33_problem_sha256=current.problem.problem_sha256,
            track=current.context.track,
            track_configuration=current.context.track_configuration,
            package_type=current.context.package_type,
            iracing_build=current.context.iracing_build,
            problem_family="entry",
            problem_orientation="combined",
            track_class="intermediate",
            phase=current.problem.phase,
            build_review_state="same_build",
            driver_drift_state=driver_state,
            decision_frozen_at=frozen_at,
            context_transfer_class=transfer,
            p20_projection_sha256=investigation.workspace_identity.p20_state_revision,
            p26_projection_sha256=(
                investigation.workspace_identity.p26_knowledge_graph_sha256
            ),
            p32_projection_sha256=(
                investigation.workspace_identity.p32_projection_sha256
            ),
        )

    opening_pair = paired(
        workspace_revision=tool_revision,
        authority_seed="tool-authority",
        step_number=0,
        baseline_decision=baseline_tool,
        memory_decision=shadow_tool,
        frozen_at=invocation.created_at - timedelta(seconds=1),
        transfer="exact",
        driver_state="stable",
    )
    terminal_choice = InvestigationDecision(
        decision_kind="no_call",
        action_id=(
            "terminal:no_call:"
            + canonical_json_sha256(["no_call", terminal.payload.message])[:24]
        ),
        priority_tier="terminal",
        safe_reorder_group=None,
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Both policies preserve the exact terminal boundary.",
        mandatory_check_ids=mandatory,
    )
    terminal_pair = paired(
        workspace_revision=terminal_revision,
        authority_seed="terminal-authority",
        step_number=2,
        baseline_decision=terminal_choice,
        memory_decision=terminal_choice,
        frozen_at=terminal.created_at - timedelta(microseconds=1),
        transfer="none",
        driver_state="unknown",
    )
    adaptation.append_paired_decision(opening_pair)
    adaptation.append_paired_decision(terminal_pair)
    invocation = _event_with_prediction_pair(invocation, opening_pair)
    terminal = _event_with_prediction_pair(terminal, terminal_pair)
    events = (invocation, result, terminal)
    crew.append_events((invocation, result))
    assert invocation.payload.adaptation_prediction_pair_id == opening_pair.pair_id
    assert (
        invocation.payload.adaptation_prediction_pair_sha256
        == opening_pair.pair_sha256
    )
    assert terminal.payload.adaptation_prediction_pair_id == terminal_pair.pair_id
    terminal_workspace = SimpleNamespace(
        identity=investigation.workspace_identity,
        learning_prior=SimpleNamespace(state="available"),
        terminal_decision=decision,
        critique=SimpleNamespace(passed=True),
        evidence_index=SimpleNamespace(
            entries=(
                _exact_p34_artifact(
                    investigation.workspace_identity,
                    artifact_id="opening-artifact",
                    evidence_state=EvidenceState.MEASURED,
                ),
            )
        ),
    )
    certificate = _build_p34_outcome_certificate(
        terminal_workspace,
        investigation=investigation,
        terminal_events=events,
        terminal_event=terminal,
        experience=experience,
        pair=opening_pair,
    )
    assert certificate is not None
    assert {
        "workspace_identity",
        "vehicle_condition_epoch",
        "applied_control_state",
    }.issubset(certificate.completed_mandatory_check_ids)
    assert certificate.consumption_metrics_state == "unavailable"
    assert certificate.lap_ids_consumed is None
    assert certificate.measurement_mission_ids is None
    comparison = _build_p34_completed_comparison(
        (opening_pair, terminal_pair),
        certificate,
        compared_at=terminal.created_at,
    )
    assert comparison is not None

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
    )

    assert captured.payload.adaptation_capture_state == "captured"
    assert certificate.starting_workspace_revision != terminal.workspace_revision
    assert comparison.pair_id == opening_pair.pair_id
    assert comparison.pair_id != terminal_pair.pair_id
    assert comparison.observability == "counterfactual_unobservable"
    restarted_event = CrewChiefRepository(db_path).list_events(
        investigation.investigation_id
    )[-1]
    assert restarted_event.payload.adaptation_capture_state == "captured"
    assert (
        restarted_event.payload.adaptation_capture_certificate_sha256
        == certificate.certificate_sha256
    )
    persisted = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("paired_comparison",),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    assert persisted.records == (comparison,)
    assert persisted.records[0].comparison_sha256 == comparison.comparison_sha256
    restarted_outcome = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("outcome_certificate",),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    assert restarted_outcome.records == (certificate,)
    assert (
        restarted_outcome.records[0].certificate_sha256
        == certificate.certificate_sha256
    )


@pytest.mark.parametrize("after_rebase", (False, True), ids=("opening", "rebased"))
@pytest.mark.parametrize("relevant_transition", (True, False))
def test_real_a_to_b_shadow_lineage_earns_only_relevant_discriminator(
    tmp_path,
    relevant_transition: bool,
    after_rebase: bool,
) -> None:
    db_path = tmp_path / f"p34-a-to-b-{relevant_transition}-{after_rebase}.sqlite"
    investigation, opening_current, decision, _ = _crew_case()
    cause_id = "cause-platform"
    first_revision = (
        "a" * 64
        if after_rebase
        else investigation.workspace_identity.workspace_revision
    )
    second_revision = "b" * 64
    terminal_revision = "c" * 64
    sequence_offset = 1 if after_rebase else 0
    accepted_rebase = (
        _event(
            investigation.investigation_id,
            1,
            first_revision,
            "workspace_rebased",
            CrewChiefEventPayload(
                message="Accepted the current workspace before either P34 prediction.",
                previous_workspace_revision=(
                    investigation.workspace_identity.workspace_revision
                ),
                new_workspace_revision=first_revision,
                previous_authority_revision=(
                    investigation.workspace_identity.authority_revision
                ),
                new_authority_revision=(
                    investigation.workspace_identity.authority_revision
                ),
                adaptation_rebase_source_snapshot_sha256=(
                    investigation_adaptation_source_snapshot_sha256(
                        run_id=opening_current.context.run_id,
                        session_id=opening_current.context.session_id,
                        workspace_revision=first_revision,
                        authority_revision=(
                            investigation.workspace_identity.authority_revision
                        ),
                        current_truth_sha256="d" * 64,
                        p19_snapshot_sha256=(
                            investigation.opening_reasoning.reasoning_snapshot_sha256
                        ),
                        p20_projection_sha256=(
                            investigation.workspace_identity.p20_state_revision
                        ),
                        p26_projection_sha256=(
                            investigation.workspace_identity.p26_knowledge_graph_sha256
                        ),
                        p32_projection_sha256=(
                            investigation.workspace_identity.p32_projection_sha256
                        ),
                    )
                ),
            ),
        )
        if after_rebase
        else None
    )
    first_request = _event(
        investigation.investigation_id,
        1 + sequence_offset,
        first_revision,
        "tool_invoked",
        CrewChiefEventPayload(
            message="Requested baseline inspection A.",
            tool_id="inspect_lap_time_opportunity",
            cause_ids=(cause_id,),
            requested_measurement_ids=("inspect_lap_time_opportunity",),
        ),
    )
    first_result = _event(
        investigation.investigation_id,
        2 + sequence_offset,
        first_revision,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="Baseline inspection A returned contextual evidence.",
            tool_id="inspect_lap_time_opportunity",
            cause_ids=(cause_id,),
            artifact_ids=("opening-artifact",),
            completed_measurement_ids=("inspect_lap_time_opportunity",),
        ),
    )
    second_request = _event(
        investigation.investigation_id,
        3 + sequence_offset,
        second_revision,
        "tool_invoked",
        CrewChiefEventPayload(
            message="Requested shadow-predicted inspection B.",
            tool_id="inspect_time_loss_origin",
            cause_ids=(cause_id,),
            requested_measurement_ids=("inspect_time_loss_origin",),
        ),
    )
    second_result = _event(
        investigation.investigation_id,
        4 + sequence_offset,
        second_revision,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="Inspection B returned qualified evidence.",
            tool_id="inspect_time_loss_origin",
            cause_ids=(cause_id if relevant_transition else "unrelated-cause",),
            artifact_ids=("artifact-b",),
            completed_measurement_ids=("inspect_time_loss_origin",),
        ),
    )
    terminal = _event(
        investigation.investigation_id,
        5 + sequence_offset,
        terminal_revision,
        "decision_emitted",
        CrewChiefEventPayload(
            message="No setup call is authorized.",
            decision_kind="no_call",
        ),
    )
    events = (
        *((accepted_rebase,) if accepted_rebase is not None else ()),
        first_request,
        first_result,
        second_request,
        second_result,
        terminal,
    )
    opening_provenance = opening_current.source_provenance[0]
    qualified_provenance = EngineeringSourceProvenance.build(
        artifact_id="artifact-b",
        producer_id="p32.time-loss-origin",
        run_id=opening_provenance.run_id,
        session_id=opening_provenance.session_id,
        setup_id=opening_provenance.setup_id,
        setup_snapshot_sha256=opening_provenance.setup_snapshot_sha256,
        build_context_sha256=opening_provenance.build_context_sha256,
        lap_numbers=(7, 8, 9),
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        phase="entry",
        source_channels=("speed_mps", "lap_dist_pct"),
        evidence_state=EvidenceState.MEASURED,
        polarity="contradiction",
    )
    closing_reasoning = P19ReasoningMemory(
        reasoning_snapshot_sha256="e" * 64,
        causes=(
            P19CauseMemory(
                cause_id=cause_id,
                status="ruled_out",
                ordinal_rank=1,
                mechanism_family="platform",
            ),
        ),
        measurement_plan_kind="measurement_mission",
        authority_level="measurement",
        setup_authorized=False,
    )
    current = service.CurrentLearningInputs(
        context=opening_current.context,
        problem=opening_current.problem,
        reasoning=closing_reasoning,
        source_provenance=(opening_provenance, qualified_provenance),
        performance_response=None,
        driver_contributions=(),
    )
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    expected_useful = (
        ("inspect_time_loss_origin",) if relevant_transition else ()
    )
    assert experience.investigation_outcome is not None
    assert experience.investigation_outcome.successful_discriminator_ids == (
        expected_useful
    )

    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    adaptation = InvestigationAdaptationRepository(db_path)
    persist_p34_foundation(adaptation)
    prior = _investigation_record(99)
    EngineeringLearningRepository(db_path).append_experience(prior)
    p33_state = EngineeringLearningRepository(db_path).stream_state()
    baseline_policy = baseline_investigation_policy()
    memory_policy = memory_shadow_investigation_policy()
    mandatory = (
        "workspace_identity",
        "vehicle_condition_epoch",
        "applied_control_state",
        "strongest_contradiction",
    )
    baseline_a = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Deterministic baseline inspection A.",
        mandatory_check_ids=mandatory,
    )
    memory_b = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_time_loss_origin",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=2,
        selected_ordinal=1,
        reason="Exact prior moved inspection B by one safe position.",
        mandatory_check_ids=mandatory,
        source_memory_record_ids=(prior.experience_id,),
    )
    baseline_b = memory_b.model_copy(
        update={
            "baseline_ordinal": 2,
            "selected_ordinal": 2,
            "reason": "Deterministic baseline reached inspection B.",
            "source_memory_record_ids": (),
        }
    )

    def pair(
        *,
        workspace_revision: str,
        step_number: int,
        baseline_decision: InvestigationDecision,
        memory_decision: InvestigationDecision,
        frozen_at: datetime,
        transfer: str,
        driver_state: str,
    ):
        return build_paired_investigation_decision(
            baseline_policy=baseline_policy,
            memory_policy=memory_policy,
            investigation_id=investigation.investigation_id,
            investigation_opened_at=investigation.opened_at,
            run_id=opening_current.context.run_id,
            session_id=opening_current.context.session_id,
            workspace_revision=workspace_revision,
            authority_revision=investigation.workspace_identity.authority_revision,
            step_number=step_number,
            baseline_decision=baseline_decision,
            memory_decision=memory_decision,
            available_tool_ids=(
                "inspect_lap_time_opportunity",
                "inspect_time_loss_origin",
            ),
            eligible_tool_ids=tuple(
                dict.fromkeys(
                    decision.action_id
                    for decision in (baseline_decision, memory_decision)
                    if decision.decision_kind == "inspect_tool"
                )
            ),
            completed_tool_ids=(),
            available_artifact_ids=("opening-artifact",),
            current_truth_sha256=canonical_json_sha256(
                ["a-to-b", workspace_revision]
            ),
            p19_snapshot_sha256=investigation.opening_reasoning.reasoning_snapshot_sha256,
            current_p19_cause_ids=(cause_id,),
            current_p19_cause_states=(
                P19CauseState(cause_id=cause_id, state="possible"),
            ),
            current_contradiction_ids=(),
            strongest_contradiction_id=None,
            current_objective=investigation.objective.value,
            p33_projection_sha256="0" * 64,
            p33_history_revision=p33_state.history_revision,
            p33_ledger_head_sha256=p33_state.head_sha256,
            p33_context_sha256=opening_current.context.context_sha256,
            p33_problem_sha256=opening_current.problem.problem_sha256,
            track=opening_current.context.track,
            track_configuration=opening_current.context.track_configuration,
            package_type=opening_current.context.package_type,
            iracing_build=opening_current.context.iracing_build,
            problem_family="entry",
            problem_orientation="combined",
            track_class="intermediate",
            phase=opening_current.problem.phase,
            build_review_state="same_build",
            driver_drift_state=driver_state,
            decision_frozen_at=frozen_at,
            context_transfer_class=transfer,
            p20_projection_sha256=investigation.workspace_identity.p20_state_revision,
            p26_projection_sha256=(
                investigation.workspace_identity.p26_knowledge_graph_sha256
            ),
            p32_projection_sha256=(
                investigation.workspace_identity.p32_projection_sha256
            ),
        )

    prediction_pair = pair(
        workspace_revision=first_revision,
        step_number=sequence_offset,
        baseline_decision=baseline_a,
        memory_decision=memory_b,
        frozen_at=first_request.created_at - timedelta(seconds=1),
        transfer="exact",
        driver_state="stable",
    )
    source_pair = pair(
        workspace_revision=second_revision,
        step_number=2 + sequence_offset,
        baseline_decision=baseline_b,
        memory_decision=baseline_b,
        frozen_at=second_request.created_at - timedelta(microseconds=1),
        transfer="none",
        driver_state="unknown",
    )
    adaptation.append_paired_decision(prediction_pair)
    adaptation.append_paired_decision(source_pair)
    first_request = _event_with_prediction_pair(first_request, prediction_pair)
    second_request = _event_with_prediction_pair(second_request, source_pair)
    events = (
        *((accepted_rebase,) if accepted_rebase is not None else ()),
        first_request,
        first_result,
        second_request,
        second_result,
        terminal,
    )
    crew.append_events(events[:-1])
    assert (
        second_request.payload.adaptation_prediction_pair_id
        == source_pair.pair_id
    )
    assert (
        second_request.payload.adaptation_prediction_pair_sha256
        == source_pair.pair_sha256
    )
    terminal_workspace = SimpleNamespace(
        identity=investigation.workspace_identity,
        learning_prior=SimpleNamespace(state="available"),
        terminal_decision=decision,
        critique=SimpleNamespace(passed=True),
        evidence_index=SimpleNamespace(
            entries=(
                _exact_p34_artifact(
                    investigation.workspace_identity,
                    artifact_id="opening-artifact",
                    evidence_state=EvidenceState.OBSERVED_CORRELATION,
                ),
                _exact_p34_artifact(
                    investigation.workspace_identity,
                    artifact_id="artifact-b",
                    evidence_state=EvidenceState.MEASURED,
                ),
            )
        ),
    )
    certificate = _build_p34_outcome_certificate(
        terminal_workspace,
        investigation=investigation,
        terminal_events=events,
        terminal_event=terminal,
        experience=experience,
        pair=prediction_pair,
    )
    assert certificate is not None
    p34_relevant_transition = relevant_transition and not after_rebase
    if p34_relevant_transition:
        for hostile_artifact in (
            _exact_p34_artifact(
                investigation.workspace_identity,
                artifact_id="artifact-b",
                evidence_state=EvidenceState.MEASURED,
                blocker_reasons=("Traffic contaminated the measured window.",),
            ),
            _exact_p34_artifact(
                investigation.workspace_identity,
                artifact_id="artifact-b",
                evidence_state=EvidenceState.MEASURED,
                source_provenance_available=False,
            ),
        ):
            hostile_workspace = SimpleNamespace(
                identity=investigation.workspace_identity,
                learning_prior=terminal_workspace.learning_prior,
                terminal_decision=decision,
                critique=terminal_workspace.critique,
                evidence_index=SimpleNamespace(entries=(hostile_artifact,)),
            )
            hostile_certificate = _build_p34_outcome_certificate(
                hostile_workspace,
                investigation=investigation,
                terminal_events=events,
                terminal_event=terminal,
                experience=experience,
                pair=prediction_pair,
            )
            assert hostile_certificate is not None
            assert "artifact-b" not in hostile_certificate.qualified_artifact_ids
            hostile_discriminator = _build_p34_discriminator_outcome(
                (prediction_pair, source_pair),
                hostile_certificate,
                terminal_events=events,
                evaluated_at=terminal.created_at,
            )
            assert (
                hostile_discriminator is None
                or hostile_discriminator.credit_state != "earned"
            )
    discriminator = _build_p34_discriminator_outcome(
        (prediction_pair, source_pair),
        certificate,
        terminal_events=events,
        evaluated_at=terminal.created_at,
    )
    comparison = _build_p34_completed_comparison(
        (prediction_pair, source_pair),
        certificate,
        discriminator_outcome=discriminator,
        compared_at=terminal.created_at,
    )
    assert comparison is not None

    captured = crew.append_terminal_event_and_experience(
        terminal,
        experience,
        outcome_certificate=certificate,
        outcome_comparison=comparison,
        discriminator_outcome=discriminator,
    )

    assert captured.payload.adaptation_capture_state == "captured"
    assert captured.payload.decision_kind == "no_call"
    assert certificate.setup_authorized is False
    assert prediction_pair.p19_rank_unchanged is True
    assert prediction_pair.p19_terminal_action_unchanged is True
    persisted = InvestigationAdaptationRepository(db_path).query_records(
        record_kinds=("discriminator_outcome", "paired_comparison"),
        investigation_id=investigation.investigation_id,
        limit=10,
    )
    if p34_relevant_transition:
        assert discriminator is not None
        assert discriminator.credit_state == "earned"
        assert comparison.useful_discriminator_hit is True
        assert comparison.bounded_reorder_observed is True
        assert comparison.bounded_discriminator_step_advance == 1
        assert comparison.memory_path_metrics_observed is False
        assert comparison.memory_tool_steps is None
        assert {
            item.outcome_id
            for item in persisted.records
            if item.schema_version == "p34.discriminator-outcome.v1"
        } == {
            discriminator.outcome_id
        }
        restarted = InvestigationAdaptationRepository(db_path).query_records(
            record_kinds=("discriminator_outcome",),
            investigation_id=investigation.investigation_id,
            limit=10,
        )
        assert restarted.records == (discriminator,)
    else:
        assert discriminator is None or discriminator.credit_state != "earned"
        if after_rebase and relevant_transition:
            assert discriminator is not None
            assert discriminator.credit_state in {"rejected", "unobservable"}
            assert discriminator.exact_workspace_match is False
            assert comparison.useful_discriminator_hit is False
            assert comparison.bounded_reorder_observed is False
            persisted_discriminators = tuple(
                item
                for item in persisted.records
                if item.schema_version == "p34.discriminator-outcome.v1"
            )
            assert persisted_discriminators == (
                (discriminator,) if discriminator is not None else ()
            )


def test_scored_workflow_atomic_retry_rolls_back_then_commits_once(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workflow-retry.sqlite"
    workflow, setups = _workflow()
    experience, _ = _build_workflow_experience(
        monkeypatch,
        workflow,
        setups,
        _controlled_outcome(workflow, verdict="keep"),
    )
    original = _planned_workflow(
        workflow_id=workflow.workflow_id,
        source_run_id=workflow.source_run_id,
    )
    scope = (workflow.source_run_id, *workflow.stage_run_ids.values())
    _seed_runs(db_path, scope)
    repository = RaceLabRepository(db_path)
    repository.save_controlled_workflow(original)

    with monkeypatch.context() as injected:
        injected.setattr(
            EngineeringLearningRepository,
            "append_experience_in_transaction",
            lambda _connection, _record: (_ for _ in ()).throw(
                RuntimeError("injected P33 failure")
            ),
        )
        with pytest.raises(RuntimeError, match="injected P33 failure"):
            repository.save_scored_workflow_with_experience_if_scope_exclusive(
                workflow,
                scope,
                experience,
            )

    assert repository.get_controlled_workflow(workflow.workflow_id) == original
    captured = repository.save_scored_workflow_with_experience_if_scope_exclusive(
        workflow,
        scope,
        experience,
    )
    retried = repository.save_scored_workflow_with_experience_if_scope_exclusive(
        workflow,
        scope,
        experience,
    )

    assert captured == retried
    assert captured.learning_capture_state == "captured"
    assert captured.learning_capture_experience_id == experience.experience_id
    assert captured.learning_capture_experience_sha256 == experience.experience_sha256
    assert repository.get_controlled_workflow(workflow.workflow_id) == captured
    assert EngineeringLearningRepository(db_path).stream_state().record_count == 1


def test_corrupt_learning_ledger_commits_terminal_truth_as_capture_blocked(
    tmp_path,
) -> None:
    db_path = tmp_path / "terminal-corrupt-learning.sqlite"
    investigation, current, decision, events = _crew_case()
    terminal = events[-1]
    experience = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="9" * 64,
    )
    _seed_runs(db_path, (investigation.workspace_identity.run_id,))
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(investigation)
    _corrupt_empty_learning_head(db_path)

    finalized = repository.append_terminal_event_and_experience(
        terminal,
        experience,
    )

    assert finalized.event_type == "decision_emitted"
    assert finalized.payload.decision_kind == "no_call"
    assert finalized.payload.learning_capture_state == "blocked"
    assert finalized.payload.learning_capture_experience_id == experience.experience_id
    assert (
        finalized.payload.learning_capture_experience_sha256
        == experience.experience_sha256
    )
    assert (
        finalized.payload.learning_capture_blocker_reason
        == LEARNING_CAPTURE_INTEGRITY_BLOCKER
    )
    restarted = CrewChiefRepository(db_path)
    assert restarted.list_events(investigation.investigation_id) == (finalized,)
    connection = initialize_database(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM engineering_experiences"
        ).fetchone()[0] == 0
    finally:
        connection.close()
    with pytest.raises(EngineeringLearningIntegrityError):
        EngineeringLearningRepository(db_path).stream_state()


@pytest.mark.parametrize(
    "corruption",
    ("inconsistent_digest", "non_integer_count"),
)
def test_corrupt_learning_ledger_commits_final_p19_workflow_as_capture_blocked(
    tmp_path,
    monkeypatch,
    corruption: str,
) -> None:
    db_path = tmp_path / "workflow-corrupt-learning.sqlite"
    workflow, setups = _workflow()
    experience, _ = _build_workflow_experience(
        monkeypatch,
        workflow,
        setups,
        _controlled_outcome(workflow, verdict="keep"),
    )
    original = _planned_workflow(
        workflow_id=workflow.workflow_id,
        source_run_id=workflow.source_run_id,
    )
    scope = (workflow.source_run_id, *workflow.stage_run_ids.values())
    _seed_runs(db_path, scope)
    repository = RaceLabRepository(db_path)
    repository.save_controlled_workflow(original)
    if corruption == "inconsistent_digest":
        _corrupt_empty_learning_head(db_path)
    else:
        connection = initialize_database(db_path)
        try:
            connection.execute(
                "UPDATE engineering_experience_stream_head "
                "SET record_count = 'not-an-integer', head_sha256 = NULL"
            )
            connection.commit()
        finally:
            connection.close()

    finalized = repository.save_scored_workflow_with_experience_if_scope_exclusive(
        workflow,
        scope,
        experience,
    )

    assert finalized.status == "scored"
    assert finalized.quality == workflow.quality
    assert finalized.execution == workflow.execution
    assert finalized.reproduction_snapshot == workflow.reproduction_snapshot
    assert finalized.learning_capture_state == "blocked"
    assert finalized.learning_capture_experience_id == experience.experience_id
    assert finalized.learning_capture_experience_sha256 == experience.experience_sha256
    assert (
        finalized.learning_capture_blocker_reason
        == LEARNING_CAPTURE_INTEGRITY_BLOCKER
    )
    restarted = RaceLabRepository(db_path)
    assert restarted.get_controlled_workflow(workflow.workflow_id) == finalized
    connection = initialize_database(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM engineering_experiences"
        ).fetchone()[0] == 0
    finally:
        connection.close()
    with pytest.raises(EngineeringLearningIntegrityError):
        EngineeringLearningRepository(db_path).stream_state()


def test_blocked_capture_forces_visible_prior_block_and_removes_reorder(
    tmp_path,
) -> None:
    db_path = tmp_path / "capture-blocked-prior.sqlite"
    learning = EngineeringLearningRepository(db_path)
    learning.append_experience(_investigation_record(1))
    learning.append_experience(_investigation_record(2))
    current = _current(11)
    prior = service.build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=(
            current.reasoning.reasoning_snapshot_sha256
        ),
        p32_projection_sha256="9" * 64,
        repository=learning,
    )
    assert prior.recommended_attention_order
    workflow = _scored_workflow(workflow_id="capture-blocked-workflow")
    blocked_workflow = ControlledWorkflow.model_validate(
        {
            **workflow.model_dump(mode="python"),
            "learning_capture_state": "blocked",
            "learning_capture_experience_id": "p33x_" + "a" * 24,
            "learning_capture_experience_sha256": "b" * 64,
            "learning_capture_blocker_reason": LEARNING_CAPTURE_INTEGRITY_BLOCKER,
        }
    )

    blockers = _learning_capture_blockers((blocked_workflow,), ())
    contained = _with_learning_capture_blockers(prior, blockers)

    assert contained.state == "blocked"
    assert contained.recommended_attention_order == ()
    assert contained.context_transfer_level == "blocked"
    assert contained.post_run_brief.state == "blocked"
    assert contained.history_revision == prior.history_revision
    assert contained.projection_sha256 != prior.projection_sha256
    assert contained.authority == "attention_only"
    assert contained.setup_authorized is False
    assert contained.p19_rank_modified is False
    assert "capture-blocked-workflow" in contained.blocker_reasons[-1]
    assert "p33x_" + "a" * 24 in contained.blocker_reasons[-1]


def test_learning_capture_models_reject_partial_or_nonterminal_claims() -> None:
    planned = _planned_workflow(workflow_id="invalid-capture-state")
    with pytest.raises(ValueError, match="exclusive to final scored truth"):
        ControlledWorkflow.model_validate(
            {
                **planned.model_dump(mode="python"),
                "learning_capture_state": "captured",
                "learning_capture_experience_id": "p33x_" + "a" * 24,
                "learning_capture_experience_sha256": "b" * 64,
            }
        )
    scored = _scored_workflow(workflow_id="partial-capture-state")
    with pytest.raises(ValueError, match="identity must be complete"):
        ControlledWorkflow.model_validate(
            {
                **scored.model_dump(mode="python"),
                "learning_capture_state": "blocked",
                "learning_capture_experience_id": "p33x_" + "a" * 24,
                "learning_capture_blocker_reason": LEARNING_CAPTURE_INTEGRITY_BLOCKER,
            }
        )
    with pytest.raises(ValueError, match="exclusive to terminal Crew events"):
        _event(
            "investigation-lifecycle",
            1,
            "8" * 64,
            "problem_interpreted",
            CrewChiefEventPayload(
                message="Forged capture.",
                learning_capture_state="blocked",
                learning_capture_experience_id="p33x_" + "a" * 24,
                learning_capture_experience_sha256="b" * 64,
                learning_capture_blocker_reason=LEARNING_CAPTURE_INTEGRITY_BLOCKER,
            ),
        )
