from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from time import perf_counter
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import racelab_engine.services.crew_chief_service as crew_chief_service
import racelab_engine.services.investigation_adaptation_service as adaptation_service
import racelab_engine.storage.investigation_adaptation_repository as adaptation_storage
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    CrewChiefEvent,
    CrewChiefEventPayload,
    CrewChiefInvestigation,
    CrewChiefWorkspaceIdentity,
    EngineeringObjective,
)
from racelab_engine.models.engineering_learning import (
    DriverFingerprintContribution,
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    EngineeringSourceProvenance,
    InvestigationPathFact,
    P19CauseMemory,
    P19ReasoningMemory,
    ProblemFingerprint,
)
from racelab_engine.models.investigation_adaptation import (
    InvestigationAdaptationContext,
    InvestigationDecision,
    InvestigationPolicyEvaluation,
    NegativeControlConditionEvidence,
    P19CauseChange,
    P19CauseState,
    P34ActivationDecision,
    P34NegativeControlResult,
    PairedInvestigationComparison,
    PairedInvestigationDecision,
    investigation_adaptation_source_snapshot_sha256,
)
from racelab_engine.services.engineering_learning_service import (
    CurrentLearningInputs,
    build_crew_chief_learning_prior,
    clear_learning_cache,
)
from racelab_engine.services.investigation_adaptation_service import (
    assess_investigation_improvement_readiness,
    assess_p34_repository_readiness,
    baseline_investigation_policy,
    build_discriminator_outcome,
    build_discriminator_outcome_from_crew_events,
    build_investigation_improvement_projection,
    build_investigation_negative_transfer,
    build_investigation_outcome_certificate,
    build_investigation_outcome_followup,
    build_p34_activation_decision,
    build_p34_negative_control_result,
    build_paired_investigation_comparison,
    build_paired_investigation_decision,
    canonical_investigation_evaluation_pair,
    evaluate_investigation_policies,
    evaluate_p34_repository,
    memory_shadow_investigation_policy,
    p34_activation_protocol,
    pending_p34_scored_workflow_ids,
    persist_p34_foundation,
    resolve_effective_activation_decision,
)
from racelab_engine.storage.crew_chief_repository import (
    CrewChiefRepository,
    crew_chief_event_hash,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    EngineeringLearningRepository,
)
from racelab_engine.storage.investigation_adaptation_repository import (
    InvestigationAdaptationIntegrityError,
    InvestigationAdaptationRepository,
)

_FROZEN = datetime(2026, 8, 15, 8, 12, 47, tzinfo=timezone.utc)


def _empty_p33_history_revision() -> str:
    return canonical_json_sha256(
        {
            "schema_version": "p33.engineering-experience.v1",
            "record_count": 0,
            "head_sha256": None,
        }
    )


def _fixture_context(
    *,
    track: str,
    track_configuration: str,
    package_type: str,
    phase: str,
    objective: str,
) -> EngineeringExperienceContext:
    return EngineeringExperienceContext.build(
        run_id="run-1",
        session_id="session-1",
        driver_id="driver-1",
        car_path="fixture-car",
        car_version="fixture-version",
        iracing_build="build-1",
        track=track,
        track_configuration=track_configuration,
        package_type=package_type,
        setup_family="fixture-setup",
        setup_snapshot_sha256="6" * 64,
        objective=objective,
        physical_scope_sha256=canonical_json_sha256(
            [track, track_configuration, phase, objective]
        ),
        phase=phase,
        physical_region="run scope",
        speed_load_band="recorded",
        fuel_state="recorded",
        tire_state="recorded",
        weather_state="recorded",
        traffic_state="clear",
        driver_execution_state="stable",
    )


def _fixture_problem(
    *,
    investigation_id: str,
    phase: str,
    objective: str,
) -> ProblemFingerprint:
    return ProblemFingerprint.build(
        physical_episode_id=f"episode-{investigation_id}",
        phase=phase,
        physical_region="run scope",
        time_origin_class="unavailable",
        carry_behavior="unavailable",
        driver_demand_state="unresolved",
        vehicle_response_state="unresolved",
        traffic_context_state="unresolved",
        tire_stint_state="unresolved",
        objective=objective,
        source_artifact_ids=(f"terminal-artifact-{investigation_id}",),
    )


def _fixture_workspace_identity(
    *,
    investigation_id: str,
    workspace_revision: str,
    objective: str,
    p19_sha256: str,
    p20_sha256: str,
    p26_sha256: str,
    p32_sha256: str,
    p33_projection_sha256: str,
    p33_history_revision: str,
    p33_ledger_head_sha256: str | None,
) -> CrewChiefWorkspaceIdentity:
    return CrewChiefWorkspaceIdentity(
        run_id="run-1",
        session_id="session-1",
        selected_scope_hash=canonical_json_sha256(("run-1",)),
        selected_run_ids=("run-1",),
        reasoning_snapshot_sha256=p19_sha256,
        p20_state_revision=p20_sha256,
        p20_profile_hash=None,
        p26_graph_version="p26.graph.v1:fixture",
        p26_knowledge_graph_sha256=p26_sha256,
        p26_reasoning_snapshot_sha256=p19_sha256,
        p32_projection_sha256=p32_sha256,
        p35_assessment_sha256="d" * 64,
        run_sentinel_sha256="c" * 64,
        learning_history_revision=p33_history_revision,
        learning_ledger_head_sha256=p33_ledger_head_sha256,
        learning_projection_sha256=p33_projection_sha256,
        setup_id="setup-1",
        setup_snapshot_sha256="6" * 64,
        vehicle_runtime_identity_hash="7" * 64,
        objective_id=EngineeringObjective(objective),
        investigation_id=investigation_id,
        workspace_revision=workspace_revision,
    )


def _decision(
    action_id: str,
    *,
    baseline_ordinal: int,
    selected_ordinal: int,
    memory_ids: tuple[str, ...] = (),
) -> InvestigationDecision:
    return InvestigationDecision(
        decision_kind="inspect_tool",
        action_id=action_id,
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=baseline_ordinal,
        selected_ordinal=selected_ordinal,
        reason="Inspect the next bounded current-evidence discriminator.",
        mandatory_check_ids=("workspace_identity", "data_integrity"),
        source_memory_record_ids=memory_ids,
    )


def _pair(
    *,
    investigation_id: str = "inv-1",
    step_number: int = 1,
    frozen_at: datetime = _FROZEN,
    memory_action: str = "inspect_time_loss_origin",
    transfer: str = "exact",
    investigation_opened_at: datetime | None = None,
    negative_control_condition: str | None = None,
    future_memory_record_ids: tuple[str, ...] = (),
    track: str = "Atlanta",
    track_configuration: str = "oval",
    package_type: str = "intermediate",
    problem_family: str = "entry",
    problem_orientation: str = "unresolved",
    track_class: str = "intermediate",
    objective: str = "race_long_run",
    build_review_state: str = "same_build",
    driver_drift_state: str = "stable",
    available_artifact_ids: tuple[str, ...] = (),
    qualified_available_artifact_ids: tuple[str, ...] | None = None,
    current_evidence_pinned_tool_ids: tuple[str, ...] = (),
    activation_decision: P34ActivationDecision | None = None,
    negative_control_p33_state: str | None = None,
    p33_history_revision: str | None = None,
    p33_ledger_head_sha256: str | None = None,
) -> PairedInvestigationDecision:
    baseline = _decision(
        "inspect_lap_time_opportunity",
        baseline_ordinal=1,
        selected_ordinal=1,
    )
    same = memory_action == baseline.action_id
    memory = _decision(
        memory_action,
        baseline_ordinal=1 if same else 2,
        selected_ordinal=1,
        memory_ids=(
            ()
            if transfer in {"none", "weak", "blocked"}
            else ("p33x_" + "a" * 24,)
        ),
    )
    proof: NegativeControlConditionEvidence | None = None
    if negative_control_condition is not None:
        transfer_id = "p33x_" + "c" * 24
        proof_values: dict[str, object] = {
            "condition": negative_control_condition,
            "p33_projection_sha256": "0" * 64,
            "p33_state": "available",
            "context_transfer_record_ids": (),
            "context_transfer_levels": (),
            "useful_prior_experience_ids": (),
            "component_history_experience_ids": (),
            "physical_scope_mismatch_dimensions": (),
            "recurrence_class": "new_problem",
            "corruption_blocker_sha256s": (),
            "future_memory_record_ids": future_memory_record_ids,
            "future_memory_record_completed_ats": tuple(
                frozen_at + timedelta(seconds=1)
                for _ in future_memory_record_ids
            ),
            "driver_drift_state": driver_drift_state,
        }
        if negative_control_condition == "no_relevant_history":
            proof_values["p33_state"] = "insufficient_history"
        elif negative_control_condition == "incompatible_history":
            proof_values.update(
                context_transfer_record_ids=(transfer_id,),
                context_transfer_levels=("blocked",),
            )
        elif negative_control_condition == "corrupt_history":
            proof_values.update(
                p33_state="blocked",
                corruption_blocker_sha256s=("d" * 64,),
            )
        elif negative_control_condition == "generic_component_knowledge_only":
            proof_values.update(
                context_transfer_record_ids=(transfer_id,),
                context_transfer_levels=("weak",),
                component_history_experience_ids=("p33x_" + "d" * 24,),
            )
        elif negative_control_condition == "same_words_different_physical_scope":
            proof_values.update(
                context_transfer_record_ids=(transfer_id,),
                context_transfer_levels=("weak",),
                physical_scope_mismatch_dimensions=("physical_region",),
                recurrence_class="possible_recurrence",
            )
        if negative_control_p33_state is not None:
            proof_values["p33_state"] = negative_control_p33_state
        proof = NegativeControlConditionEvidence(**proof_values)
    qualified_artifact_ids = (
        available_artifact_ids
        if qualified_available_artifact_ids is None
        else qualified_available_artifact_ids
    )
    if p33_history_revision is None:
        if (
            transfer in {"exact", "compatible"}
            or future_memory_record_ids
            or negative_control_condition is not None
        ):
            p33_history_revision = "e" * 64
            p33_ledger_head_sha256 = p33_ledger_head_sha256 or "f" * 64
        else:
            p33_history_revision = _empty_p33_history_revision()
    context = _fixture_context(
        track=track,
        track_configuration=track_configuration,
        package_type=package_type,
        phase=problem_family,
        objective=objective,
    )
    problem = _fixture_problem(
        investigation_id=investigation_id,
        phase=problem_family,
        objective=objective,
    )
    workspace_revision = "a" * 64
    p19_sha256 = "d" * 64
    p20_sha256 = "3" * 64
    p26_sha256 = "4" * 64
    p32_sha256 = "5" * 64
    p33_projection_sha256 = "0" * 64
    identity = _fixture_workspace_identity(
        investigation_id=investigation_id,
        workspace_revision=workspace_revision,
        objective=objective,
        p19_sha256=p19_sha256,
        p20_sha256=p20_sha256,
        p26_sha256=p26_sha256,
        p32_sha256=p32_sha256,
        p33_projection_sha256=p33_projection_sha256,
        p33_history_revision=p33_history_revision,
        p33_ledger_head_sha256=p33_ledger_head_sha256,
    )
    return build_paired_investigation_decision(
        baseline_policy=baseline_investigation_policy(),
        memory_policy=(
            adaptation_service.limited_attention_investigation_policy()
            if activation_decision is not None
            else memory_shadow_investigation_policy()
        ),
        investigation_id=investigation_id,
        investigation_opened_at=(
            investigation_opened_at
            or p34_activation_protocol().prospective_boundary
            + timedelta(seconds=1)
        ),
        run_id="run-1",
        session_id="session-1",
        workspace_revision=workspace_revision,
        authority_revision=identity.authority_revision,
        step_number=step_number,
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
        available_artifact_ids=available_artifact_ids,
        qualified_available_artifact_ids=qualified_artifact_ids,
        qualified_available_artifact_evidence_states=tuple(
            "measured" for _ in qualified_artifact_ids
        ),
        qualified_available_artifact_provenance_sha256s=tuple(
            canonical_json_sha256(
                {"artifact_id": artifact_id, "source": "frozen-fixture"}
            )
            for artifact_id in qualified_artifact_ids
        ),
        current_evidence_pinned_tool_ids=current_evidence_pinned_tool_ids,
        current_truth_sha256="c" * 64,
        p19_snapshot_sha256=p19_sha256,
        current_p19_cause_ids=("cause-1",),
        current_p19_cause_states=(
            P19CauseState(cause_id="cause-1", state="possible"),
        ),
        current_contradiction_ids=("contradiction-1", "contradiction-2"),
        strongest_contradiction_id="contradiction-1",
        current_objective=objective,
        p33_projection_sha256=p33_projection_sha256,
        p33_history_revision=p33_history_revision,
        p33_ledger_head_sha256=p33_ledger_head_sha256,
        p33_context_sha256=context.context_sha256,
        p33_problem_sha256=problem.problem_sha256,
        track=track,
        track_configuration=track_configuration,
        package_type=package_type,
        iracing_build="build-1",
        problem_family=problem_family,
        problem_orientation=problem_orientation,
        track_class=track_class,
        phase=problem_family,
        build_review_state=build_review_state,
        driver_drift_state=driver_drift_state,
        decision_frozen_at=frozen_at,
        context_transfer_class=transfer,
        negative_control_condition=negative_control_condition,
        negative_control_evidence=proof,
        future_memory_record_ids=future_memory_record_ids,
        p20_projection_sha256=p20_sha256,
        p26_projection_sha256=p26_sha256,
        p32_projection_sha256=p32_sha256,
        activation_decision=activation_decision,
    )


def _certificate(
    pair: PairedInvestigationDecision,
    *,
    synthetic: bool = False,
    prospective: bool | None = None,
):
    derived_prospective = (
        pair.investigation_opened_at
        > p34_activation_protocol().prospective_boundary
    )
    return build_investigation_outcome_certificate(
        pair,
        starting_workspace_revision=pair.workspace_revision,
        ending_workspace_revision="8" * 64,
        final_p19_snapshot_sha256="7" * 64,
        terminal_crew_decision="no_call",
        tool_request_event_ids=(f"request-{pair.investigation_id}",),
        tool_result_event_ids=(f"result-{pair.investigation_id}",),
        tools_actually_requested=(pair.baseline_decision.action_id,),
        tool_results_received=(pair.baseline_decision.action_id,),
        qualified_artifact_ids=("artifact-1",),
        qualified_artifact_evidence_states=("measured",),
        driver_question_ids=(),
        driver_answer_event_ids=(),
        consumption_metrics_state="observed",
        lap_ids_consumed=("lap-1",),
        measurement_mission_ids=(),
        consumption_metric_blockers=(),
        elapsed_wall_seconds=10,
        investigation_steps=1,
        useful_discriminator_id=None,
        dead_end_tool_ids=(),
        repeated_no_finding_tool_ids=(),
        causes_separated=(),
        causes_left_unresolved=("cause-1",),
        final_p19_cause_states=(
            P19CauseState(cause_id="cause-1", state="unresolved"),
        ),
        strongest_contradiction_id="contradiction-1",
        strongest_contradiction_handled=True,
        completed_mandatory_check_ids=("workspace_identity", "data_integrity"),
        workflow_created=False,
        workflow_scored=False,
        p19_outcome="no_call",
        outcome_validity="qualified",
        prospective=(derived_prospective if prospective is None else prospective),
        synthetic=synthetic,
        blockers=(),
        certified_at=pair.decision_frozen_at + timedelta(seconds=10),
    )


def _context(pair: PairedInvestigationDecision) -> InvestigationAdaptationContext:
    proof_sha256 = (
        canonical_json_sha256(
            pair.negative_control_evidence.model_dump(mode="json")
        )
        if pair.negative_control_evidence is not None
        else None
    )
    return InvestigationAdaptationContext.build(
        run_id=pair.run_id,
        session_id=pair.session_id,
        workspace_revision=pair.workspace_revision,
        current_truth_sha256=pair.current_truth_sha256,
        p19_snapshot_sha256=pair.p19_snapshot_sha256,
        p20_projection_sha256=pair.p20_projection_sha256,
        p26_projection_sha256=pair.p26_projection_sha256,
        p32_projection_sha256=pair.p32_projection_sha256,
        p33_projection_sha256=pair.p33_projection_sha256,
        p33_context_sha256=pair.p33_context_sha256,
        p33_problem_sha256=pair.p33_problem_sha256,
        qualified_available_artifact_ids=(
            pair.qualified_available_artifact_ids
        ),
        qualified_available_artifact_evidence_states=(
            pair.qualified_available_artifact_evidence_states
        ),
        qualified_available_artifact_provenance_sha256s=(
            pair.qualified_available_artifact_provenance_sha256s
        ),
        current_evidence_pinned_tool_ids=pair.current_evidence_pinned_tool_ids,
        track=pair.track,
        track_configuration=pair.track_configuration,
        package_type=pair.package_type,
        iracing_build=pair.iracing_build,
        problem_family=pair.problem_family,
        problem_orientation=pair.problem_orientation,
        track_class=pair.track_class,
        phase=pair.phase,
        current_objective=pair.current_objective,
        build_review_state=pair.build_review_state,
        driver_drift_state=pair.driver_drift_state,
        context_subgroup_keys=pair.context_subgroup_keys,
        negative_control_condition=pair.negative_control_condition,
        negative_control_evidence_sha256=proof_sha256,
    )


def _event(**values: object) -> CrewChiefEvent:
    draft = CrewChiefEvent(event_hash="0" * 64, **values)
    return draft.model_copy(update={"event_hash": crew_chief_event_hash(draft)})


def _persist_authoritative_lineage(
    db_path,
    pair: PairedInvestigationDecision,
    certificate,
    *,
    executed_tool_id: str | None = None,
    skip_before_request: bool = False,
    attach_prediction_receipt: bool = True,
) -> None:
    connection = initialize_database(db_path)
    connection.execute(
        "INSERT OR IGNORE INTO runs "
        "(run_id, source_file, import_time, imported_at, session_json) "
        "VALUES (?, 'fixture.ibt', '2026-01-01', '2026-01-01', '{}')",
        (pair.run_id,),
    )
    connection.commit()
    connection.close()
    identity = _fixture_workspace_identity(
        investigation_id=pair.investigation_id,
        workspace_revision=certificate.starting_workspace_revision,
        objective=pair.current_objective,
        p19_sha256=pair.p19_snapshot_sha256,
        p20_sha256=pair.p20_projection_sha256,
        p26_sha256=pair.p26_projection_sha256,
        p32_sha256=pair.p32_projection_sha256,
        p33_projection_sha256=pair.p33_projection_sha256,
        p33_history_revision=pair.p33_history_revision,
        p33_ledger_head_sha256=pair.p33_ledger_head_sha256,
    )
    opening_reasoning = P19ReasoningMemory(
        reasoning_snapshot_sha256=pair.p19_snapshot_sha256,
        causes=(
            P19CauseMemory(
                cause_id="cause-1",
                status="possible",
                ordinal_rank=1,
                mechanism_family="unresolved",
            ),
        ),
        measurement_plan_kind="measurement_mission",
        authority_level="measurement",
        setup_authorized=False,
    )
    investigation = CrewChiefInvestigation(
        investigation_id=pair.investigation_id,
        workspace_identity=identity,
        origin="driver_report",
        objective=EngineeringObjective.RACE_LONG_RUN,
        raw_driver_report="Loose on entry.",
        canonical_problem="loose on entry.",
        opening_reasoning=opening_reasoning,
        opening_problem=_fixture_problem(
            investigation_id=pair.investigation_id,
            phase=pair.phase,
            objective=pair.current_objective,
        ),
        opened_at=pair.investigation_opened_at,
    )
    crew = CrewChiefRepository(db_path)
    crew.save_investigation(investigation)
    prefix = tuple(
        _event(
            event_id=f"prefix-{pair.investigation_id}-{sequence}",
            investigation_id=pair.investigation_id,
            sequence=sequence,
            event_type="problem_interpreted",
            workspace_revision=pair.workspace_revision,
            created_at=pair.decision_frozen_at
            - timedelta(seconds=pair.step_number - sequence + 1),
            payload=CrewChiefEventPayload(message="Frozen pre-decision context."),
        )
        for sequence in range(1, pair.step_number + 1)
    )
    actual_tool_id = executed_tool_id or pair.baseline_decision.action_id
    skipped = (
        (
            _event(
                event_id=f"skipped-{pair.investigation_id}",
                investigation_id=pair.investigation_id,
                sequence=pair.step_number + 1,
                event_type="hypothesis_inspected",
                workspace_revision=pair.workspace_revision,
                created_at=pair.decision_frozen_at + timedelta(milliseconds=500),
                payload=CrewChiefEventPayload(message="Skipped the frozen next action."),
            ),
        )
        if skip_before_request
        else ()
    )
    request_sequence = pair.step_number + 1 + len(skipped)
    request = _event(
        event_id=certificate.tool_request_event_ids[0],
        investigation_id=pair.investigation_id,
        sequence=request_sequence,
        event_type="tool_invoked",
        workspace_revision=pair.workspace_revision,
        created_at=pair.decision_frozen_at + timedelta(seconds=1),
        payload=CrewChiefEventPayload(
            message="Inspect.",
            tool_id=actual_tool_id,
            requested_measurement_ids=(actual_tool_id,),
            adaptation_prediction_pair_id=(
                pair.pair_id if attach_prediction_receipt else None
            ),
            adaptation_prediction_pair_sha256=(
                pair.pair_sha256 if attach_prediction_receipt else None
            ),
            adaptation_prediction_source_snapshot_sha256=(
                investigation_adaptation_source_snapshot_sha256(
                    run_id=pair.run_id,
                    session_id=pair.session_id,
                    workspace_revision=pair.workspace_revision,
                    authority_revision=pair.authority_revision,
                    current_truth_sha256=pair.current_truth_sha256,
                    p19_snapshot_sha256=pair.p19_snapshot_sha256,
                    p20_projection_sha256=pair.p20_projection_sha256,
                    p26_projection_sha256=pair.p26_projection_sha256,
                    p32_projection_sha256=pair.p32_projection_sha256,
                )
                if attach_prediction_receipt
                else None
            ),
        ),
    )
    result = _event(
        event_id=certificate.tool_result_event_ids[0],
        investigation_id=pair.investigation_id,
        sequence=request_sequence + 1,
        event_type="tool_result_attached",
        workspace_revision=pair.workspace_revision,
        created_at=pair.decision_frozen_at + timedelta(seconds=2),
        payload=CrewChiefEventPayload(
            message="Result.",
            tool_id=actual_tool_id,
            artifact_ids=certificate.qualified_artifact_ids,
            completed_measurement_ids=(actual_tool_id,),
        ),
    )
    crew.append_events((*prefix, *skipped, request, result))
    terminal_id = f"terminal-{pair.investigation_id}"
    terminal_artifact_id = f"terminal-artifact-{pair.investigation_id}"
    terminal_context = _fixture_context(
        track=pair.track,
        track_configuration=pair.track_configuration,
        package_type=pair.package_type,
        phase=pair.phase,
        objective=pair.current_objective,
    )
    terminal_provenance = EngineeringSourceProvenance.build(
        artifact_id=terminal_artifact_id,
        producer_id="p27.crew-chief.fixture",
        run_id=pair.run_id,
        session_id=pair.session_id,
        setup_id=identity.setup_id,
        setup_snapshot_sha256=identity.setup_snapshot_sha256,
        build_context_sha256=identity.vehicle_runtime_identity_hash,
        phase=pair.phase,
        evidence_state="measured",
        polarity="neutral",
    )
    source_event_ids = tuple(
        item.event_id for item in (*prefix, *skipped, request, result)
    ) + (terminal_id,)
    experience = EngineeringExperienceRecord.build(
        source_kind="resolved_investigation",
        source_investigation_id=pair.investigation_id,
        created_at=certificate.certified_at,
        context=terminal_context,
        problem=investigation.opening_problem,
        source_p19_reasoning_snapshot_sha256=opening_reasoning.reasoning_snapshot_sha256,
        source_p32_projection_sha256=pair.p32_projection_sha256,
        opening_reasoning=opening_reasoning,
        closing_reasoning=opening_reasoning,
        investigation_outcome=InvestigationPathFact(
            investigation_id=pair.investigation_id,
            started_at=pair.investigation_opened_at,
            completed_at=certificate.certified_at,
            initial_cause_ids=pair.current_p19_cause_ids,
            tools_inspected=(actual_tool_id,),
            requested_measurement_ids=(actual_tool_id,),
            completed_measurement_ids=(actual_tool_id,),
            strongest_contradiction="No contradiction changed the frozen cause state.",
            unresolved_cause_ids=pair.current_p19_cause_ids,
            terminal_decision="no_call",
            elapsed_seconds=(
                certificate.certified_at - pair.investigation_opened_at
            ).total_seconds(),
            laps_consumed=0,
            tool_steps_consumed=1,
            driver_questions_consumed=0,
            source_artifact_ids=(terminal_artifact_id,),
            historical_retrieval_used=bool(pair.memory_records_consulted),
        ),
        source_event_ids=source_event_ids,
        source_artifact_ids=(terminal_artifact_id,),
        source_provenance=(terminal_provenance,),
    )
    EngineeringLearningRepository(db_path).append_experience(experience)
    terminal = _event(
        event_id=terminal_id,
        investigation_id=pair.investigation_id,
        sequence=request_sequence + 2,
        event_type="decision_emitted",
        workspace_revision=certificate.ending_workspace_revision,
        created_at=certificate.certified_at,
        payload=CrewChiefEventPayload(
            message="No call.",
            decision_kind="no_call",
            learning_capture_state="captured",
            learning_capture_experience_id=experience.experience_id,
            learning_capture_experience_sha256=experience.experience_sha256,
            adaptation_capture_state="captured",
            adaptation_capture_certificate_id=certificate.certificate_id,
            adaptation_capture_certificate_sha256=certificate.certificate_sha256,
        ),
    )
    connection = initialize_database(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        CrewChiefRepository._append_event(connection, terminal)
        connection.commit()
    finally:
        connection.close()


def test_frozen_policies_and_protocol_are_content_addressed_and_honest() -> None:
    baseline = baseline_investigation_policy()
    shadow = memory_shadow_investigation_policy()
    protocol = p34_activation_protocol()

    assert baseline.kind == "deterministic_baseline"
    assert baseline.maximum_reorder_distance == 0
    assert shadow.kind == "memory_informed_shadow"
    assert protocol.memory_policy_id == shadow.policy_id
    assert protocol.prospective_boundary == datetime(
        2026, 8, 15, 8, 12, 46, tzinfo=timezone.utc
    )
    assert protocol.historical_only_activation_allowed is False
    assert protocol.synthetic_cases_count_toward_activation is False


def test_shadow_pair_keeps_production_baseline_and_binds_exact_context() -> None:
    pair = _pair()

    assert pair.production_policy_kind == "deterministic_baseline"
    assert pair.production_decision == pair.baseline_decision
    assert pair.memory_decision.action_id == "inspect_time_loss_origin"
    assert pair.activation_protocol_id == p34_activation_protocol().protocol_id
    assert pair.problem_family == "entry"
    assert pair.track == "Atlanta"
    assert pair.setup_authorized is False


def test_forged_ordinal_cannot_bypass_one_position_ceiling() -> None:
    baseline = _decision(
        "inspect_lap_time_opportunity", baseline_ordinal=1, selected_ordinal=1
    )
    forged = _decision(
        "inspect_time_loss_origin",
        baseline_ordinal=7,
        selected_ordinal=1,
        memory_ids=("p33x_" + "a" * 24,),
    )
    values = _pair().model_dump(mode="python")
    values.update(
        baseline_decision=baseline,
        memory_decision=forged,
        production_decision=baseline,
    )

    with pytest.raises(ValidationError, match="one safe position"):
        PairedInvestigationDecision.model_validate(values)


def test_frozen_policy_rejects_a_content_valid_forged_canonical_ordinal(
    tmp_path,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    valid = _pair(investigation_id="forged-canonical")
    forged_memory = _decision(
        "inspect_time_loss_origin",
        baseline_ordinal=1,
        selected_ordinal=1,
        memory_ids=("p33x_" + "a" * 24,),
    )
    values = valid.model_dump(
        mode="python", exclude={"pair_id", "pair_sha256"}
    )
    values["baseline_decision"] = valid.baseline_decision
    values["memory_decision"] = forged_memory
    values["production_decision"] = valid.production_decision
    values["current_p19_cause_states"] = valid.current_p19_cause_states
    forged = PairedInvestigationDecision.build(**values)
    certificate = _certificate(forged)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(forged,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    repository.append_paired_decision(forged)
    repository.append_outcome(certificate)
    repository.append_comparison(comparison)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 0
    assert any("Orphan or swapped-parent" in item for item in evaluation.blockers)


def test_memory_provenance_identity_and_evidence_are_mandatory() -> None:
    with pytest.raises(ValidationError, match="exact P33 experience IDs"):
        _decision(
            "inspect_time_loss_origin",
            baseline_ordinal=2,
            selected_ordinal=1,
            memory_ids=("p33x_a",),
        )
    values = _pair().model_dump(mode="python", exclude={"pair_id", "pair_sha256"})
    source = _pair()
    values["baseline_decision"] = source.baseline_decision
    values["memory_decision"] = _decision(
        "inspect_time_loss_origin",
        baseline_ordinal=2,
        selected_ordinal=1,
    )
    values["memory_records_consulted"] = ()
    values["production_decision"] = source.production_decision
    values["current_p19_cause_states"] = source.current_p19_cause_states
    with pytest.raises(ValidationError, match="qualified P33 provenance"):
        PairedInvestigationDecision.build(**values)

    for pair in (
        _pair(investigation_id="consulted-head"),
        _pair(
            investigation_id="future-head",
            memory_action="inspect_lap_time_opportunity",
            transfer="blocked",
            negative_control_condition="future_memory_record",
            future_memory_record_ids=("p33x_" + "e" * 24,),
        ),
    ):
        without_head = pair.model_dump(
            mode="python",
            exclude={"pair_id", "pair_sha256"},
        )
        without_head["p33_ledger_head_sha256"] = None
        with pytest.raises(ValidationError, match="frozen ledger head"):
            PairedInvestigationDecision.build(**without_head)


@pytest.mark.parametrize("strongest", [None, "contradiction-2"])
def test_strongest_contradiction_is_canonical_rank_one(strongest: str | None) -> None:
    values = _pair().model_dump(mode="python")
    values["strongest_contradiction_id"] = strongest

    with pytest.raises(ValidationError, match="canonical current rank one"):
        PairedInvestigationDecision.model_validate(values)


@pytest.mark.parametrize("state", ["estimated_proxy", "observed_correlation"])
def test_proxy_or_correlation_cannot_earn_discriminator_credit(state: str) -> None:
    outcome = build_discriminator_outcome(
        activation_protocol_id=p34_activation_protocol().protocol_id,
        activation_protocol_sha256=p34_activation_protocol().protocol_sha256,
        investigation_id="inv-1",
        prediction_pair_id="p34pair_" + "a" * 24,
        prediction_pair_sha256="a" * 64,
        source_pair_id="p34pair_" + "b" * 24,
        source_pair_sha256="b" * 64,
        source_authority_revision="c" * 64,
        workspace_revision="a" * 64,
        tool_id="inspect_time_loss_origin",
        request_event_id="request-1",
        request_sequence=1,
        request_recorded_at=_FROZEN + timedelta(seconds=1),
        result_event_id="result-1",
        result_sequence=2,
        result_recorded_at=_FROZEN + timedelta(seconds=2),
        transition_sequence=3,
        lineage_event_ids=("request-1", "result-1", "transition-1"),
        artifact_ids=("artifact-1",),
        qualified_evidence_states=(state,),
        before_p19_snapshot_sha256="1" * 64,
        after_p19_snapshot_sha256="2" * 64,
        relevant_ambiguity_ids=("cause-1",),
        cause_changes=(
            P19CauseChange(
                cause_id="cause-1", before_state="possible", after_state="ruled_out"
            ),
        ),
        resolved_blocker_ids=(),
        artifact_available_before_transition=True,
        exact_workspace_match=True,
        evaluated_at=_FROZEN + timedelta(seconds=5),
    )

    assert outcome.credit_state == "rejected"


def test_canonical_pair_uses_earliest_differing_inspection() -> None:
    first_same = _pair(
        step_number=1,
        frozen_at=_FROZEN,
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
    )
    first_different = _pair(step_number=2, frozen_at=_FROZEN + timedelta(seconds=1))
    later_different = _pair(step_number=3, frozen_at=_FROZEN + timedelta(seconds=2))

    assert canonical_investigation_evaluation_pair(
        (later_different, first_same, first_different)
    ) == first_different


def test_comparison_keeps_unperformed_shadow_tool_unobservable() -> None:
    pair = _pair()
    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )

    assert comparison.observability == "counterfactual_unobservable"
    assert comparison.memory_path_metrics_observed is False
    assert comparison.memory_tool_steps is None
    assert comparison.qualified is True


def test_empty_real_inventory_is_shadow_only_with_exact_deficits(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)
    readiness = assess_investigation_improvement_readiness(evaluation)
    projection = build_investigation_improvement_projection(
        run_id="run-1",
        session_id="session-1",
        workspace_revision="a" * 64,
        readiness=readiness,
        current_pair=None,
        current_context=None,
    )

    assert evaluation.decision == "no_activation_earned"
    assert readiness.production_policy == "deterministic_baseline"
    assert readiness.historical_deficit == 20
    assert readiness.prospective_deficit == 12
    assert readiness.context_deficit == 3
    assert readiness.problem_family_deficit == 4
    assert readiness.objective_deficit == 2
    assert len(readiness.remaining_collection_missions) >= 7
    assert projection.state == "unavailable"
    assert projection.current_pair is None
    assert resolve_effective_activation_decision(repository) is None


def test_default_repository_resolves_the_runtime_database_path(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "default-runtime.sqlite"
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    connection = initialize_database()
    connection.close()
    repository = InvestigationAdaptationRepository()

    evaluation = evaluate_p34_repository(repository)
    readiness = assess_p34_repository_readiness(repository)

    assert evaluation.decision == "no_activation_earned"
    assert readiness.production_policy == "deterministic_baseline"
    assert readiness.memory_policy_state == "shadow_only"
    assert readiness.setup_authorized is False
    assert not any("NoneType" in blocker for blocker in readiness.blockers)


def test_projection_requires_independent_exact_current_context(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-context.sqlite")
    persist_p34_foundation(repository)
    readiness = assess_investigation_improvement_readiness(
        evaluate_p34_repository(repository, evaluated_at=_FROZEN)
    )
    pair = _pair(
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
    )
    context = _context(pair)
    projection = build_investigation_improvement_projection(
        run_id=pair.run_id,
        session_id=pair.session_id,
        workspace_revision=pair.workspace_revision,
        readiness=readiness,
        current_pair=pair,
        current_context=context,
    )
    assert projection.current_context == context

    values = context.model_dump(
        mode="python", exclude={"context_binding_sha256"}
    )
    values["track"] = "Talladega"
    forged = InvestigationAdaptationContext.build(**values)
    with pytest.raises(ValidationError, match="independently bind"):
        build_investigation_improvement_projection(
            run_id=pair.run_id,
            session_id=pair.session_id,
            workspace_revision=pair.workspace_revision,
            readiness=readiness,
            current_pair=pair,
            current_context=forged,
        )


def test_first_zero_ledger_readiness_is_pure_and_requires_no_foundation_write(
    tmp_path,
) -> None:
    db_path = tmp_path / "p34-read-only.sqlite"
    initializer = initialize_database(db_path)
    before_rows = initializer.execute(
        "SELECT COUNT(*) AS count FROM investigation_adaptation_records"
    ).fetchone()["count"]
    initializer.close()
    before_mtime = os.stat(db_path).st_mtime_ns
    connection = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    before_changes = connection.total_changes
    repository = InvestigationAdaptationRepository(db_path)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)
    readiness = assess_investigation_improvement_readiness(evaluation)

    try:
        assert connection.total_changes == before_changes
        assert before_rows == 0
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM investigation_adaptation_records"
        ).fetchone()["count"] == 0
    finally:
        connection.close()
    assert os.stat(db_path).st_mtime_ns == before_mtime
    assert evaluation.ledger_record_count == 0
    assert evaluation.ledger_head_sha256 is None
    assert readiness.historical_deficit == 20
    assert readiness.prospective_deficit == 12
    assert readiness.exact_recurrence_deficit == 5
    assert readiness.compatible_recurrence_deficit == 5


def test_repository_is_idempotent_restart_safe_and_append_only(tmp_path) -> None:
    db_path = tmp_path / "p34.sqlite"
    first = InvestigationAdaptationRepository(db_path)
    pair = _pair()
    first.append_paired_decision(pair)
    first.append_paired_decision(pair)

    restarted = InvestigationAdaptationRepository(db_path)
    assert restarted.get_paired_decision(pair.pair_sha256) == pair
    assert restarted.stream_state(validate_chain=True).record_count == 1
    connection = initialize_database(db_path)
    try:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE investigation_adaptation_records SET record_json = '{}'"
            )
    finally:
        connection.close()


def test_foundation_can_share_pair_transaction_without_partial_registry(
    tmp_path,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-atomic.sqlite")
    connection = initialize_database(repository.db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        persist_p34_foundation(repository, connection=connection)
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM investigation_adaptation_records"
        ).fetchone()["count"] == 4
        connection.rollback()
    finally:
        connection.close()

    assert repository.stream_state(validate_chain=True).record_count == 0


def test_crash_recovery_is_scoped_to_the_frozen_protocol(
    tmp_path,
    monkeypatch,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-recovery.sqlite")
    persist_p34_foundation(repository)
    locked = evaluate_p34_repository(
        repository,
        evaluated_at=_FROZEN + timedelta(minutes=1),
    )
    pair = _pair(investigation_id="recover-current")
    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    repository.append_comparison(comparison)

    foreign_protocol_id = "p34proto_" + "6" * 24
    foreign_protocol_sha256 = "6" * 64
    foreign_evaluation_values = locked.model_dump(
        mode="python",
        exclude={"evaluation_id", "evaluation_sha256"},
    )
    foreign_evaluation_values.update(
        protocol_id=foreign_protocol_id,
        protocol_sha256=foreign_protocol_sha256,
    )
    repository.append_evaluation(
        InvestigationPolicyEvaluation.build(**foreign_evaluation_values)
    )

    calls: list[datetime] = []
    sentinel = object()

    def fake_review(_repository, *, captured_at):
        calls.append(captured_at)
        return sentinel

    monkeypatch.setattr(
        adaptation_service,
        "review_p34_after_terminal_capture",
        fake_review,
    )
    assert (
        adaptation_service.recover_unreviewed_p34_terminal_capture(repository)
        is sentinel
    )
    assert calls == [comparison.compared_at]

    repository.append_evaluation(locked)
    foreign_comparison_values = comparison.model_dump(
        mode="python",
        exclude={"comparison_id", "comparison_sha256"},
    )
    foreign_comparison_values.update(
        investigation_id="foreign-comparison",
        activation_protocol_id=foreign_protocol_id,
        activation_protocol_sha256=foreign_protocol_sha256,
    )
    repository.append_comparison(
        PairedInvestigationComparison.build(**foreign_comparison_values)
    )

    assert (
        adaptation_service.recover_unreviewed_p34_terminal_capture(repository)
        is None
    )
    assert calls == [comparison.compared_at]


def test_workflow_followup_search_is_scoped_to_the_frozen_protocol(
    tmp_path,
    monkeypatch,
) -> None:
    class Quality:
        protocol_valid = True
        verdict = "keep"

    class Candidate:
        workflow_id = "workflow-current"
        status = "scored"
        execution = object()
        quality = Quality()
        updated_at = _FROZEN + timedelta(hours=1)

        def model_dump(self, *, mode):
            assert mode == "json"
            return {
                "workflow_id": self.workflow_id,
                "status": self.status,
                "updated_at": self.updated_at.isoformat(),
            }

    candidate = Candidate()

    class SourceRepository:
        def get_controlled_workflow(self, workflow_id):
            assert workflow_id == candidate.workflow_id
            return candidate

    class AdaptationRepository:
        db_path = tmp_path / "followup.sqlite"

        def __init__(self):
            self.certificate_kwargs = None

        def get_outcome_certificate_for_workflow(self, **kwargs):
            self.certificate_kwargs = kwargs
            return None

    repository = AdaptationRepository()
    monkeypatch.setattr(
        "racelab_engine.models.controlled_workflow.ControlledWorkflow.model_validate",
        classmethod(lambda _cls, _value: candidate),
    )
    monkeypatch.setattr(
        "racelab_engine.storage.repository.RaceLabRepository",
        lambda _db_path: SourceRepository(),
    )
    monkeypatch.setattr(
        "racelab_engine.analysis.test_director.score_test_execution",
        lambda _execution: candidate.quality,
    )
    monkeypatch.setattr(
        "racelab_engine.services.controlled_workflow_service.validate_p19_workflow_origin",
        lambda _workflow, *, repository: {
            "reasoning_snapshot_sha256": "1" * 64,
            "source_event_ids": ["event-1"],
        },
    )

    assert (
        adaptation_service.capture_p34_controlled_workflow_followup(
            repository,
            workflow=candidate,
        )
        is None
    )
    assert repository.certificate_kwargs == {
        "protocol_id": p34_activation_protocol().protocol_id,
        "workflow_id": "workflow-current",
    }


def test_pending_workflow_recovery_uses_exact_protocol_anti_join(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "pending-followup.sqlite")

    def certificate_with_workflow(pair, workflow_id):
        base = _certificate(pair)
        values = base.model_dump(
            mode="python",
            exclude={"certificate_id", "certificate_sha256"},
        )
        values.update(
            created_workflow_ids=(workflow_id,),
            workflow_created=True,
        )
        return type(base).build(**values)

    connection = initialize_database(repository.db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO runs "
            "(run_id, source_file, import_time, imported_at, session_json) "
            "VALUES ('run-1', 'fixture.ibt', '2026-01-01', '2026-01-01', '{}')"
        )
        for index in range(513):
            no_workflow_pair = _pair(
                investigation_id=f"no-workflow-{index:03d}"
            )
            repository.append_outcome_in_transaction(
                connection,
                _certificate(no_workflow_pair),
            )
            planned_workflow_id = f"workflow-planned-{index:03d}"
            planned_pair = _pair(
                investigation_id=f"planned-workflow-{index:03d}"
            )
            repository.append_outcome_in_transaction(
                connection,
                certificate_with_workflow(planned_pair, planned_workflow_id),
            )
            connection.execute(
                "INSERT INTO controlled_test_workflows "
                "(workflow_id, created_at, updated_at, status, source_run_id, "
                "complaint, packet_json) VALUES (?, ?, ?, 'planned', 'run-1', ?, '{}')",
                (
                    planned_workflow_id,
                    _FROZEN.isoformat(),
                    _FROZEN.isoformat(),
                    "Planned recovery fixture.",
                ),
            )
        pair = _pair(investigation_id="pending-followup")
        certificate = certificate_with_workflow(pair, "workflow-pending")
        repository.append_outcome_in_transaction(connection, certificate)
        connection.execute(
            "INSERT INTO controlled_test_workflows "
            "(workflow_id, created_at, updated_at, status, source_run_id, "
            "complaint, packet_json) VALUES (?, ?, ?, 'scored', 'run-1', ?, '{}')",
            (
                "workflow-pending",
                _FROZEN.isoformat(),
                (_FROZEN + timedelta(hours=1)).isoformat(),
                "Scored recovery fixture.",
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    followup = build_investigation_outcome_followup(
        certificate,
        observed_p19_snapshot_sha256="6" * 64,
        observed_p19_outcome="keep",
        source_workflow_id="workflow-pending",
        source_workflow_revision_sha256="5" * 64,
        source_event_ids=("workflow-event",),
        source_artifact_ids=(),
        observed_at=certificate.certified_at + timedelta(seconds=1),
    )
    foreign_values = followup.model_dump(
        mode="python",
        exclude={"followup_id", "followup_sha256"},
    )
    foreign_values.update(
        activation_protocol_id="p34proto_" + "6" * 24,
        activation_protocol_sha256="6" * 64,
    )
    repository.append_outcome_followup(type(followup).build(**foreign_values))
    swapped_values = followup.model_dump(
        mode="python",
        exclude={"followup_id", "followup_sha256"},
    )
    swapped_values.update(
        certificate_id="p34out_" + "7" * 24,
        certificate_sha256="7" * 64,
    )
    repository.append_outcome_followup(type(followup).build(**swapped_values))

    assert pending_p34_scored_workflow_ids(
        repository,
        limit=1,
    ) == ("workflow-pending",)

    repository.append_outcome_followup(followup)
    assert pending_p34_scored_workflow_ids(repository) == ()


def test_full_audit_detects_deleted_middle_record(tmp_path) -> None:
    db_path = tmp_path / "p34.sqlite"
    repository = InvestigationAdaptationRepository(db_path)
    persist_p34_foundation(repository)
    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER investigation_adaptation_records_no_delete")
        connection.execute(
            "DELETE FROM investigation_adaptation_records WHERE sequence = 2"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(InvestigationAdaptationIntegrityError, match="deleted"):
        repository.stream_state(validate_chain=True)


def test_wal_tamper_cannot_reuse_evaluation_or_activation_cache(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-cache-tamper.sqlite")
    persist_p34_foundation(repository)
    locked = evaluate_p34_repository(repository)
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
    limited = P34ActivationDecision.build(
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
        decided_at=_FROZEN + timedelta(minutes=1),
    )
    repository.append_evaluation(earned)
    repository.append_activation_decision(limited)
    evaluate_p34_repository(repository)
    # A self-consistent caller-authored evaluation is not activation proof.
    assert resolve_effective_activation_decision(repository) is None

    tamper = sqlite3.connect(repository.db_path)
    try:
        assert tamper.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tamper.execute("DROP TRIGGER investigation_adaptation_records_no_update")
        tamper.execute(
            "UPDATE investigation_adaptation_records SET record_json = '{}' "
            "WHERE sequence = 2"
        )
        tamper.commit()
    finally:
        tamper.close()

    with pytest.raises(InvestigationAdaptationIntegrityError):
        evaluate_p34_repository(repository, strict_integrity=True)
    assert resolve_effective_activation_decision(repository) is None


def test_authoritative_crew_tamper_invalidates_cached_evaluation(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "crew-cache-tamper.sqlite")
    persist_p34_foundation(repository)
    pair, certificate, _comparison = _append_case(
        repository,
        investigation_id="crew-cache-tamper",
    )
    initial = evaluate_p34_repository(repository)
    assert initial.independent_investigation_count == 1

    tamper = sqlite3.connect(repository.db_path)
    try:
        assert tamper.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tamper.execute(
            "UPDATE crew_chief_events SET event_json = '{}' WHERE event_id = ?",
            (certificate.tool_request_event_ids[0],),
        )
        tamper.commit()
    finally:
        tamper.close()

    refreshed = evaluate_p34_repository(repository)
    assert refreshed.independent_investigation_count == 0
    assert refreshed.invalid_comparisons >= 1
    assert pair.investigation_id == "crew-cache-tamper"


def test_concurrent_source_commit_cannot_poison_the_evaluation_cache(
    tmp_path,
    monkeypatch,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-cache-race.sqlite")
    persist_p34_foundation(repository)
    _pair_record, certificate, _comparison = _append_case(
        repository,
        investigation_id="crew-cache-race",
    )
    initial = evaluate_p34_repository(repository)
    assert initial.independent_investigation_count == 1

    writer = sqlite3.connect(repository.db_path)
    original_boundary = adaptation_service._verified_p34_stream_boundary
    committed = False

    def commit_after_snapshot(*args, **kwargs):
        nonlocal committed
        boundary = original_boundary(*args, **kwargs)
        if not committed:
            writer.execute(
                "UPDATE crew_chief_events SET event_json = '{}' WHERE event_id = ?",
                (certificate.tool_request_event_ids[0],),
            )
            writer.commit()
            committed = True
        return boundary

    monkeypatch.setattr(
        adaptation_service,
        "_verified_p34_stream_boundary",
        commit_after_snapshot,
    )
    try:
        # This call may truthfully finish its already-open old snapshot, but it
        # must never cache that snapshot under the newly committed source state.
        evaluate_p34_repository(repository)
    finally:
        writer.close()
        monkeypatch.setattr(
            adaptation_service,
            "_verified_p34_stream_boundary",
            original_boundary,
        )

    refreshed = evaluate_p34_repository(repository)
    replayed = evaluate_p34_repository(repository)
    assert refreshed.independent_investigation_count == 0
    assert refreshed.invalid_comparisons >= 1
    assert replayed == refreshed


def test_strict_evaluation_contains_unrelated_p33_payload_corruption(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-p33-scope.sqlite")
    persist_p34_foundation(repository)
    _append_case(repository, investigation_id="clean-p33-scope")
    connection = initialize_database(repository.db_path)
    try:
        source_row = connection.execute(
            "SELECT * FROM engineering_experiences ORDER BY sequence LIMIT 1"
        ).fetchone()
        source = EngineeringLearningRepository._validate_row(source_row)
    finally:
        connection.close()
    unrelated_values = source.model_dump(
        mode="python",
        exclude={"experience_id", "experience_sha256", "source_identity_sha256"},
    )
    unrelated_values.update(
        source_kind="controlled_workflow",
        source_investigation_id=None,
        source_workflow_id="unrelated-workflow",
        created_at=source.created_at + timedelta(seconds=1),
        context=_fixture_context(
            track="Unrelated Track",
            track_configuration="road",
            package_type="road_course",
            phase="center",
            objective="driver_confidence",
        ),
        problem=ProblemFingerprint.build(
            physical_episode_id="episode-unrelated-workflow",
            phase="center",
            physical_region="unrelated region",
            time_origin_class="unavailable",
            carry_behavior="unavailable",
            driver_demand_state="unresolved",
            vehicle_response_state="unresolved",
            traffic_context_state="unresolved",
            tire_stint_state="unresolved",
            objective="driver_confidence",
            source_artifact_ids=source.source_artifact_ids,
        ),
        opening_reasoning=None,
        closing_reasoning=source.closing_reasoning,
        investigation_outcome=None,
        source_provenance=source.source_provenance,
    )
    unrelated = EngineeringExperienceRecord.build(**unrelated_values)
    EngineeringLearningRepository(repository.db_path).append_experience(unrelated)
    tamper = initialize_database(repository.db_path)
    try:
        tamper.execute("DROP TRIGGER engineering_experiences_no_update")
        tamper.execute(
            "UPDATE engineering_experiences SET record_json = '{}' "
            "WHERE experience_id = ?",
            (unrelated.experience_id,),
        )
        tamper.commit()
    finally:
        tamper.close()

    evaluation = evaluate_p34_repository(repository, strict_integrity=True)
    assert evaluation.independent_investigation_count == 1
    assert evaluation.invalid_comparisons == 0


def test_strict_evaluation_contains_foreign_protocol_payload_corruption(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-foreign-scope.sqlite")
    persist_p34_foundation(repository)
    _append_case(repository, investigation_id="clean-foreign-scope")
    foreign_protocol_id, _foreign_sha256 = _bulk_seed_foreign_protocol_controls(
        repository,
        count=1,
    )
    tamper = initialize_database(repository.db_path)
    try:
        tamper.execute("DROP TRIGGER investigation_adaptation_records_no_update")
        tamper.execute(
            "UPDATE investigation_adaptation_records SET record_json = '{}' "
            "WHERE protocol_id = ?",
            (foreign_protocol_id,),
        )
        tamper.commit()
    finally:
        tamper.close()

    evaluation = evaluate_p34_repository(repository, strict_integrity=True)
    assert evaluation.independent_investigation_count == 1
    assert evaluation.invalid_comparisons == 0


def _producer_control_experience(
    index: int,
    *,
    context: EngineeringExperienceContext,
    problem: ProblemFingerprint,
    driver_tendency: str | None = None,
) -> EngineeringExperienceRecord:
    artifact_id = f"producer-control-artifact-{index}"
    reasoning = P19ReasoningMemory(
        reasoning_snapshot_sha256=f"{index}" * 64,
        causes=(
            P19CauseMemory(
                cause_id="cause-1",
                status="possible",
                ordinal_rank=1,
                mechanism_family="unresolved",
            ),
        ),
        measurement_plan_kind="measurement_mission",
        authority_level="measurement",
        setup_authorized=False,
    )
    outcome = InvestigationPathFact(
        investigation_id=f"producer-control-{index}",
        started_at=_FROZEN - timedelta(hours=index + 2),
        completed_at=_FROZEN - timedelta(hours=index + 1),
        initial_cause_ids=("cause-1",),
        tools_inspected=("inspect_lap_time_opportunity",),
        requested_measurement_ids=("inspect_lap_time_opportunity",),
        completed_measurement_ids=("inspect_lap_time_opportunity",),
        strongest_contradiction="The prior comparison remained unresolved.",
        unresolved_cause_ids=("cause-1",),
        terminal_decision="no_call",
        elapsed_seconds=60.0,
        laps_consumed=0,
        tool_steps_consumed=1,
        driver_questions_consumed=0,
        successful_discriminator_ids=("inspect_lap_time_opportunity",),
        source_artifact_ids=(artifact_id,),
        historical_retrieval_used=False,
    )
    contribution = (
        (
            DriverFingerprintContribution(
                contribution_id=f"producer-driver-drift-{index}",
                metric="controlled_test_execution_consistency",
                tendency=driver_tendency,
                statement="Driver execution changed in this physical region.",
                physical_episode_ids=(problem.physical_episode_id,),
                source_artifact_ids=(artifact_id,),
                source_lap_count=3,
            ),
        )
        if driver_tendency is not None
        else ()
    )

    def provenance(source_artifact_id: str) -> EngineeringSourceProvenance:
        return EngineeringSourceProvenance.build(
            artifact_id=source_artifact_id,
            producer_id="p33.producer-control.fixture",
            run_id=context.run_id,
            session_id=context.session_id,
            setup_id="setup-1",
            setup_snapshot_sha256=context.setup_snapshot_sha256,
            build_context_sha256="7" * 64,
            phase=context.phase,
            evidence_state="measured",
            polarity="neutral",
        )

    return EngineeringExperienceRecord.build(
        source_kind="resolved_investigation",
        source_investigation_id=outcome.investigation_id,
        created_at=outcome.completed_at,
        context=context,
        problem=problem,
        source_p19_reasoning_snapshot_sha256=reasoning.reasoning_snapshot_sha256,
        source_p32_projection_sha256="5" * 64,
        opening_reasoning=reasoning,
        closing_reasoning=reasoning,
        driver_contributions=contribution,
        investigation_outcome=outcome,
        source_event_ids=(f"producer-control-event-{index}",),
        source_artifact_ids=(*problem.source_artifact_ids, artifact_id),
        source_provenance=tuple(
            provenance(source_artifact_id)
            for source_artifact_id in (*problem.source_artifact_ids, artifact_id)
        ),
    )


@pytest.mark.parametrize(
    ("condition", "expected_prior_state", "expected_driver_state"),
    (
        ("material_driver_drift", "available", "material_drift"),
        ("incompatible_history", "insufficient_history", "stable"),
    ),
)
def test_real_producer_control_pair_counts_under_strict_evaluation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
    expected_prior_state: str,
    expected_driver_state: str,
) -> None:
    db_path = tmp_path / f"p34-real-{condition}.sqlite"
    investigation_id = f"real-{condition}"
    context = _fixture_context(
        track="Atlanta",
        track_configuration="oval",
        package_type="intermediate",
        phase="entry",
        objective="race_long_run",
    )
    problem = _fixture_problem(
        investigation_id=investigation_id,
        phase="entry",
        objective="race_long_run",
    )
    current_reasoning = P19ReasoningMemory(
        reasoning_snapshot_sha256="d" * 64,
        causes=(
            P19CauseMemory(
                cause_id="cause-1",
                status="possible",
                ordinal_rank=1,
                mechanism_family="unresolved",
            ),
        ),
        measurement_plan_kind="measurement_mission",
        authority_level="measurement",
        setup_authorized=False,
    )
    current_provenance = EngineeringSourceProvenance.build(
        artifact_id=problem.source_artifact_ids[0],
        producer_id="p33.producer-control.current",
        run_id=context.run_id,
        session_id=context.session_id,
        setup_id="setup-1",
        setup_snapshot_sha256=context.setup_snapshot_sha256,
        build_context_sha256="7" * 64,
        phase=context.phase,
        evidence_state="measured",
        polarity="neutral",
    )
    current = CurrentLearningInputs(
        context=context,
        problem=problem,
        reasoning=current_reasoning,
        source_provenance=(current_provenance,),
        performance_response=None,
        driver_contributions=(),
    )
    learning = EngineeringLearningRepository(db_path)
    if condition == "material_driver_drift":
        shifted_values = context.model_dump(
            mode="python", exclude={"context_sha256"}
        )
        shifted_values["driver_execution_state"] = "changed_inputs"
        shifted_context = EngineeringExperienceContext.build(**shifted_values)
        for index in (1, 2):
            learning.append_experience(
                _producer_control_experience(
                    index,
                    context=shifted_context,
                    problem=_fixture_problem(
                        investigation_id=f"material-prior-{index}",
                        phase="entry",
                        objective="race_long_run",
                    ),
                    driver_tendency="changed_behavior",
                )
            )
    else:
        incompatible_values = context.model_dump(
            mode="python", exclude={"context_sha256"}
        )
        incompatible_values["car_path"] = "foreign-car"
        learning.append_experience(
            _producer_control_experience(
                1,
                context=EngineeringExperienceContext.build(**incompatible_values),
                problem=problem,
            )
        )
    clear_learning_cache()
    prior = build_crew_chief_learning_prior(
        current,
        scope_run_ids=(context.run_id,),
        p19_reasoning_snapshot_sha256=current_reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="5" * 64,
        repository=learning,
        db_path=db_path,
    )
    p33_state = learning.stream_state()
    identity = _fixture_workspace_identity(
        investigation_id=investigation_id,
        workspace_revision="a" * 64,
        objective="race_long_run",
        p19_sha256=current_reasoning.reasoning_snapshot_sha256,
        p20_sha256="3" * 64,
        p26_sha256="4" * 64,
        p32_sha256="5" * 64,
        p33_projection_sha256=prior.projection_sha256,
        p33_history_revision=p33_state.history_revision,
        p33_ledger_head_sha256=p33_state.head_sha256,
    )
    investigation = CrewChiefInvestigation(
        investigation_id=investigation_id,
        workspace_identity=identity,
        origin="driver_report",
        objective=EngineeringObjective.RACE_LONG_RUN,
        raw_driver_report="Loose on entry.",
        canonical_problem="loose on entry.",
        opening_reasoning=current_reasoning,
        opening_problem=problem,
        opened_at=p34_activation_protocol().prospective_boundary
        + timedelta(seconds=1),
    )
    baseline = _decision(
        "inspect_lap_time_opportunity",
        baseline_ordinal=1,
        selected_ordinal=1,
    )
    workspace = SimpleNamespace(
        identity=identity,
        investigation=investigation,
        folded_state=SimpleNamespace(
            status="open",
            last_sequence=0,
            completed_tool_ids=(),
            hypotheses=(),
            driver_answers=(),
        ),
        current_subgoal=SimpleNamespace(),
        learning_prior=prior,
        available_tools=(
            SimpleNamespace(tool_id="inspect_lap_time_opportunity"),
            SimpleNamespace(tool_id="inspect_time_loss_origin"),
        ),
        evidence_index=SimpleNamespace(entries=()),
        p19_cause_ids=("cause-1",),
        p19_contradiction_artifact_ids=(),
        blocker_reasons=(),
        terminal_decision=SimpleNamespace(),
    )
    frozen_at = p34_activation_protocol().prospective_boundary + timedelta(hours=1)
    monkeypatch.setattr(crew_chief_service, "_now", lambda: frozen_at)
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_decisions_for_workspace",
        lambda *_args, **_kwargs: (baseline, baseline, "none"),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_learning_inputs_for_workspace",
        lambda *_args, **_kwargs: current,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_qualified_current_evidence_tool_ids",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_current_truth_sha256",
        lambda *_args, **_kwargs: "c" * 64,
    )

    pair = crew_chief_service._freeze_p34_pair_for_workspace(
        workspace,
        db_path=db_path,
    )

    assert pair is not None
    assert prior.state == expected_prior_state
    assert pair.negative_control_condition == condition
    assert pair.context_transfer_class == "blocked"
    assert pair.driver_drift_state == expected_driver_state
    assert pair.production_decision == pair.baseline_decision
    assert pair.memory_records_consulted == ()
    if condition == "incompatible_history":
        assert pair.negative_control_evidence is not None
        assert pair.negative_control_evidence.p33_state == "insufficient_history"

    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    adaptation = InvestigationAdaptationRepository(db_path)
    adaptation.append_outcome(certificate)
    adaptation.append_comparison(comparison)
    _persist_authoritative_lineage(db_path, pair, certificate)

    evaluation = evaluate_p34_repository(
        adaptation,
        strict_integrity=True,
        evaluated_at=certificate.certified_at + timedelta(hours=1),
    )

    assert evaluation.independent_investigation_count == 1
    assert evaluation.invalid_comparisons == 0


def test_real_negative_control_requires_exact_fallback() -> None:
    pair = _pair(memory_action="inspect_lap_time_opportunity", transfer="none")
    control = P34NegativeControlResult.build(
        protocol_id=p34_activation_protocol().protocol_id,
        protocol_sha256=p34_activation_protocol().protocol_sha256,
        control_id="no_relevant_history",
        investigation_id=pair.investigation_id,
        pair_id=pair.pair_id,
        pair_sha256=pair.pair_sha256,
        observed_exact_fallback=True,
        passed=True,
        source_artifact_ids=("artifact-1",),
        blockers=(),
        evaluated_at=_FROZEN + timedelta(seconds=1),
    )

    assert control.passed is True


def test_no_relevant_history_allows_unrelated_available_p33_facts() -> None:
    pair = _pair(
        investigation_id="available-but-unrelated",
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
        negative_control_condition="no_relevant_history",
        negative_control_p33_state="available",
    )
    control = build_p34_negative_control_result(
        pair,
        control_id="no_relevant_history",
        evaluated_at=pair.decision_frozen_at + timedelta(seconds=1),
    )

    assert pair.negative_control_evidence is not None
    assert pair.negative_control_evidence.p33_state == "available"
    assert control.passed is True


def test_qualified_current_evidence_pin_is_an_authoritative_blocked_fallback(
    tmp_path,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-pin.sqlite")
    persist_p34_foundation(repository)
    pair = _pair(
        investigation_id="current-evidence-pin",
        memory_action="inspect_lap_time_opportunity",
        transfer="blocked",
        driver_drift_state="unknown",
        available_artifact_ids=("current-artifact",),
        qualified_available_artifact_ids=("current-artifact",),
        current_evidence_pinned_tool_ids=("inspect_lap_time_opportunity",),
    )
    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    repository.append_paired_decision(pair)
    repository.append_outcome(certificate)
    repository.append_comparison(comparison)
    _persist_authoritative_lineage(repository.db_path, pair, certificate)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert pair.negative_control_condition is None
    assert pair.production_decision == pair.baseline_decision
    assert evaluation.independent_investigation_count == 1
    assert evaluation.invalid_comparisons == 0


@pytest.mark.parametrize(
    "pair_kwargs",
    (
        {"problem_orientation": "combined"},
        {"track_class": "short_track"},
    ),
)
def test_pair_cannot_self_certify_source_context_subgroups(
    tmp_path,
    pair_kwargs: dict[str, str],
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-source-group.sqlite")
    persist_p34_foundation(repository)
    pair = _pair(
        investigation_id="forged-source-subgroup",
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
        negative_control_condition="no_relevant_history",
        driver_drift_state="unknown",
        **pair_kwargs,
    )
    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    repository.append_paired_decision(pair)
    repository.append_outcome(certificate)
    repository.append_comparison(comparison)
    _persist_authoritative_lineage(repository.db_path, pair, certificate)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 0
    assert evaluation.invalid_comparisons >= 1


def test_current_evidence_pin_cannot_name_the_unused_candidate() -> None:
    pair = _pair()
    values = pair.model_dump(mode="python", exclude={"pair_id", "pair_sha256"})
    values["baseline_decision"] = pair.baseline_decision
    values["memory_decision"] = pair.memory_decision
    values["production_decision"] = pair.production_decision
    values["current_p19_cause_states"] = pair.current_p19_cause_states
    values["current_evidence_pinned_tool_ids"] = ("inspect_time_loss_origin",)

    with pytest.raises(ValidationError, match="exact deterministic baseline"):
        PairedInvestigationDecision.build(**values)


def _append_case(
    repository: InvestigationAdaptationRepository,
    *,
    investigation_id: str,
    prospective: bool = True,
    synthetic: bool = False,
):
    p33_repository = EngineeringLearningRepository(repository.db_path)
    p33_state = p33_repository.stream_state()
    connection = initialize_database(repository.db_path)
    try:
        latest_p33_created_at = connection.execute(
            "SELECT MAX(created_at) AS value FROM engineering_experiences"
        ).fetchone()["value"]
    finally:
        connection.close()
    frozen_at = (
        max(
            _FROZEN,
            datetime.fromisoformat(latest_p33_created_at) + timedelta(seconds=1),
        )
        if latest_p33_created_at is not None
        else _FROZEN
    )
    pair = _pair(
        investigation_id=investigation_id,
        frozen_at=frozen_at,
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
        investigation_opened_at=(
            p34_activation_protocol().prospective_boundary - timedelta(seconds=1)
            if not prospective
            else None
        ),
        p33_history_revision=p33_state.history_revision,
        p33_ledger_head_sha256=p33_state.head_sha256,
        negative_control_condition=(
            "no_relevant_history" if p33_state.record_count == 0 else None
        ),
        driver_drift_state=(
            "unknown" if p33_state.record_count == 0 else "stable"
        ),
    )
    certificate = _certificate(
        pair,
        prospective=prospective,
        synthetic=synthetic,
    )
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    repository.append_paired_decision(pair)
    repository.append_outcome(certificate)
    repository.append_comparison(comparison)
    _persist_authoritative_lineage(repository.db_path, pair, certificate)
    return pair, certificate, comparison


def _rebuild_comparison(
    comparison: PairedInvestigationComparison,
    **updates: object,
) -> PairedInvestigationComparison:
    values = comparison.model_dump(
        mode="python",
        exclude={"comparison_id", "comparison_sha256"},
    )
    values.update(updates)
    return PairedInvestigationComparison.build(**values)


def test_synthetic_case_is_mechanics_only_and_cannot_count(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    _append_case(repository, investigation_id="synthetic", synthetic=True)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 0
    assert evaluation.prospective_count == 0
    assert evaluation.decision == "no_activation_earned"


def test_repeated_processing_of_one_investigation_counts_once(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    pair, certificate, comparison = _append_case(
        repository, investigation_id="one-investigation"
    )
    repository.append_paired_decision(pair)
    repository.append_outcome(certificate)
    repository.append_comparison(comparison)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 1
    assert evaluation.prospective_count == 1


@pytest.mark.parametrize(
    ("executed_tool_id", "skip_before_request"),
    [
        ("inspect_time_loss_origin", False),
        (None, True),
    ],
)
def test_authoritative_case_requires_the_exact_frozen_next_action(
    tmp_path,
    executed_tool_id: str | None,
    skip_before_request: bool,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-next.sqlite")
    persist_p34_foundation(repository)
    pair = _pair(
        investigation_id="next-action",
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
    )
    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    repository.append_paired_decision(pair)
    repository.append_outcome(certificate)
    repository.append_comparison(comparison)
    _persist_authoritative_lineage(
        repository.db_path,
        pair,
        certificate,
        executed_tool_id=executed_tool_id,
        skip_before_request=skip_before_request,
        attach_prediction_receipt=False,
    )

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 0
    assert any("Orphan or swapped-parent" in item for item in evaluation.blockers)


def test_selected_tool_must_be_live_and_all_projection_digests_are_required() -> None:
    pair = _pair()
    values = pair.model_dump(mode="python", exclude={"pair_id", "pair_sha256"})
    values["baseline_decision"] = pair.baseline_decision
    values["memory_decision"] = pair.memory_decision
    values["production_decision"] = pair.production_decision
    values["current_p19_cause_states"] = pair.current_p19_cause_states
    values["eligible_tool_ids"] = ("inspect_time_loss_origin",)
    values["completed_tool_ids"] = ("inspect_lap_time_opportunity",)
    with pytest.raises(ValidationError, match="eligible at freeze"):
        PairedInvestigationDecision.build(**values)

    missing = pair.model_dump(mode="python")
    missing.pop("p26_projection_sha256")
    with pytest.raises(ValidationError, match="p26_projection_sha256"):
        PairedInvestigationDecision.model_validate(missing)


def test_orphan_or_swapped_parent_comparison_is_withheld(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    pair, certificate, comparison = _append_case(
        repository, investigation_id="bound"
    )
    other = _pair(investigation_id="other")
    swapped = _rebuild_comparison(
        comparison,
        pair_id=other.pair_id,
        pair_sha256=other.pair_sha256,
    )
    connection = initialize_database(repository.db_path)
    try:
        connection.execute("DROP TRIGGER investigation_adaptation_records_no_delete")
        connection.execute(
            "DELETE FROM investigation_adaptation_records "
            "WHERE record_kind = 'paired_comparison'"
        )
        connection.execute(
            "UPDATE investigation_adaptation_stream_head "
            "SET record_count = record_count - 1, head_sha256 = ("
            "SELECT entry_sha256 FROM investigation_adaptation_records "
            "ORDER BY sequence DESC LIMIT 1)"
        )
        connection.commit()
    finally:
        connection.close()
    # A clean append-only repository would reject replacement. This hostile
    # fixture simulates an independently received, validly hashed orphan body.
    repository.append_comparison(swapped)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 0
    assert any("Orphan or swapped-parent" in item for item in evaluation.blockers)
    assert pair.pair_id != other.pair_id
    assert certificate.pair_id == pair.pair_id


def test_caller_authored_authority_violation_is_rebuilt_and_withheld(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    pair = _pair(
        investigation_id="unsafe",
        memory_action="inspect_lap_time_opportunity",
        transfer="none",
    )
    certificate = _certificate(pair)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(pair,),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )
    unsafe = _rebuild_comparison(
        comparison,
        authority_violations=1,
        qualified=False,
        blockers=("Recorded authority violation.",),
    )
    repository.append_paired_decision(pair)
    repository.append_outcome(certificate)
    repository.append_comparison(unsafe)
    _persist_authoritative_lineage(repository.db_path, pair, certificate)

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 0
    assert evaluation.safety.authority_violations == 0
    assert any("Orphan or swapped-parent" in item for item in evaluation.blockers)


def test_historical_inventory_alone_cannot_activate(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    for index in range(20):
        _append_case(
            repository,
            investigation_id=f"historical-{index}",
            prospective=False,
        )

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.historical_count == 20
    assert evaluation.prospective_count == 0
    assert evaluation.decision == "no_activation_earned"
    assert any("prospective" in item for item in evaluation.blockers)


def test_same_track_runs_do_not_inflate_track_package_contexts(tmp_path) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34.sqlite")
    persist_p34_foundation(repository)
    for index in range(3):
        _append_case(repository, investigation_id=f"same-track-{index}")

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 3
    assert evaluation.context_count == 1


def test_same_recording_does_not_increment_p34_independent_investigations(
    tmp_path,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-source-identity.sqlite")
    persist_p34_foundation(repository)
    _append_case(repository, investigation_id="same-recording-a")
    _append_case(repository, investigation_id="same-recording-b")
    connection = initialize_database(repository.db_path)
    try:
        connection.execute(
            "UPDATE runs SET file_hash = ? WHERE run_id = 'run-1'",
            ("8" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    evaluation = evaluate_p34_repository(repository, evaluated_at=_FROZEN)

    assert evaluation.independent_investigation_count == 1
    assert any(
        "same physical recording" in blocker
        for blocker in evaluation.blockers
    )
    assert evaluation.context_count < p34_activation_protocol().minimum_contexts


def test_pre_freeze_claim_cannot_become_prospective() -> None:
    pair = _pair(
        investigation_id="pre-freeze",
        investigation_opened_at=(
            p34_activation_protocol().prospective_boundary - timedelta(seconds=1)
        ),
    )
    with pytest.raises(ValueError, match="prospective status"):
        _certificate(pair, prospective=True)


def test_later_pair_cannot_replace_canonical_earliest_differing_pair() -> None:
    earliest = _pair(investigation_id="canonical", step_number=1)
    later = _pair(
        investigation_id="canonical",
        step_number=2,
        frozen_at=_FROZEN + timedelta(seconds=1),
    )
    certificate = _certificate(later)
    # The certificate selected the later pair, but the cohort owns an earlier
    # differing inspection. The builder must fail it closed instead of
    # cherry-picking the outcome-selected revision.
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(earliest, later),
        certificate=certificate,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )

    assert comparison.pair_id == earliest.pair_id
    assert comparison.qualified is False
    assert any("exact frozen pair" in item for item in comparison.blockers)


def _bounded_a_then_b_fixture(
    prediction: PairedInvestigationDecision | None = None,
):
    prediction = prediction or _pair(
        investigation_id="a-then-b",
        step_number=0,
    )
    source_baseline = _decision(
        "inspect_time_loss_origin",
        baseline_ordinal=2,
        selected_ordinal=2,
    )
    source = build_paired_investigation_decision(
        baseline_policy=baseline_investigation_policy(),
        memory_policy=memory_shadow_investigation_policy(),
        investigation_id=prediction.investigation_id,
        investigation_opened_at=prediction.investigation_opened_at,
        run_id=prediction.run_id,
        session_id=prediction.session_id,
        workspace_revision="3" * 64,
        authority_revision=prediction.authority_revision,
        step_number=2,
        baseline_decision=source_baseline,
        memory_decision=source_baseline,
        available_tool_ids=(
            "inspect_lap_time_opportunity",
            "inspect_time_loss_origin",
        ),
        eligible_tool_ids=("inspect_time_loss_origin",),
        completed_tool_ids=("inspect_lap_time_opportunity",),
        available_artifact_ids=("artifact-a",),
        qualified_available_artifact_ids=("artifact-a",),
        qualified_available_artifact_evidence_states=("measured",),
        qualified_available_artifact_provenance_sha256s=("6" * 64,),
        current_truth_sha256="4" * 64,
        p19_snapshot_sha256=prediction.p19_snapshot_sha256,
        current_p19_cause_ids=prediction.current_p19_cause_ids,
        current_p19_cause_states=prediction.current_p19_cause_states,
        current_contradiction_ids=prediction.current_contradiction_ids,
        strongest_contradiction_id=prediction.strongest_contradiction_id,
        current_objective=prediction.current_objective,
        p33_projection_sha256=prediction.p33_projection_sha256,
        p33_history_revision=prediction.p33_history_revision,
        p33_ledger_head_sha256=prediction.p33_ledger_head_sha256,
        p33_context_sha256=prediction.p33_context_sha256,
        p33_problem_sha256=prediction.p33_problem_sha256,
        track=prediction.track,
        track_configuration=prediction.track_configuration,
        package_type=prediction.package_type,
        iracing_build=prediction.iracing_build,
        problem_family=prediction.problem_family,
        problem_orientation=prediction.problem_orientation,
        track_class=prediction.track_class,
        phase=prediction.phase,
        build_review_state=prediction.build_review_state,
        driver_drift_state=prediction.driver_drift_state,
        decision_frozen_at=_FROZEN + timedelta(seconds=2, milliseconds=500),
        context_transfer_class="none",
        p20_projection_sha256=prediction.p20_projection_sha256,
        p26_projection_sha256=prediction.p26_projection_sha256,
        p32_projection_sha256=prediction.p32_projection_sha256,
    )
    event_specs = (
        (1, "tool_invoked", prediction.workspace_revision, "inspect_lap_time_opportunity", ()),
        (2, "tool_result_attached", prediction.workspace_revision, "inspect_lap_time_opportunity", ("artifact-a",)),
        (3, "tool_invoked", source.workspace_revision, "inspect_time_loss_origin", ()),
        (4, "tool_result_attached", source.workspace_revision, "inspect_time_loss_origin", ("artifact-b",)),
    )
    events = []
    for sequence, event_type, revision, tool_id, artifacts in event_specs:
        receipt_pair = (
            prediction
            if sequence == 1
            else source
            if sequence == 3
            else None
        )
        events.append(
            _event(
                event_id=f"a-then-b-{sequence}",
                investigation_id=prediction.investigation_id,
                sequence=sequence,
                event_type=event_type,
                workspace_revision=revision,
                created_at=_FROZEN + timedelta(seconds=sequence),
                payload=CrewChiefEventPayload(
                    message="Inspect current evidence.",
                    tool_id=tool_id,
                    artifact_ids=artifacts,
                    requested_measurement_ids=(
                        (tool_id,) if event_type == "tool_invoked" else ()
                    ),
                    completed_measurement_ids=(
                        (tool_id,) if event_type == "tool_result_attached" else ()
                    ),
                    adaptation_prediction_pair_id=(
                        receipt_pair.pair_id if receipt_pair is not None else None
                    ),
                    adaptation_prediction_pair_sha256=(
                        receipt_pair.pair_sha256 if receipt_pair is not None else None
                    ),
                    adaptation_prediction_source_snapshot_sha256=(
                        investigation_adaptation_source_snapshot_sha256(
                            run_id=receipt_pair.run_id,
                            session_id=receipt_pair.session_id,
                            workspace_revision=receipt_pair.workspace_revision,
                            authority_revision=receipt_pair.authority_revision,
                            current_truth_sha256=receipt_pair.current_truth_sha256,
                            p19_snapshot_sha256=receipt_pair.p19_snapshot_sha256,
                            p20_projection_sha256=receipt_pair.p20_projection_sha256,
                            p26_projection_sha256=receipt_pair.p26_projection_sha256,
                            p32_projection_sha256=receipt_pair.p32_projection_sha256,
                        )
                        if receipt_pair is not None
                        else None
                    ),
                ),
            )
        )
    events.append(
        _event(
            event_id="a-then-b-5",
            investigation_id=prediction.investigation_id,
            sequence=5,
            event_type="hypothesis_inspected",
            workspace_revision=source.workspace_revision,
            created_at=_FROZEN + timedelta(seconds=5),
            payload=CrewChiefEventPayload(
                message="Current evidence changed the P19 ambiguity.",
                cause_ids=("cause-1",),
                artifact_ids=("artifact-b",),
            ),
        )
    )
    certificate = build_investigation_outcome_certificate(
        prediction,
        starting_workspace_revision="9" * 64,
        ending_workspace_revision="8" * 64,
        final_p19_snapshot_sha256="7" * 64,
        terminal_crew_decision="no_call",
        tool_request_event_ids=(events[0].event_id, events[2].event_id),
        tool_result_event_ids=(events[1].event_id, events[3].event_id),
        tools_actually_requested=(
            "inspect_lap_time_opportunity",
            "inspect_time_loss_origin",
        ),
        tool_results_received=(
            "inspect_lap_time_opportunity",
            "inspect_time_loss_origin",
        ),
        qualified_artifact_ids=("artifact-b",),
        qualified_artifact_evidence_states=("measured",),
        driver_question_ids=(),
        driver_answer_event_ids=(),
        consumption_metrics_state="observed",
        lap_ids_consumed=("lap-1",),
        measurement_mission_ids=(),
        consumption_metric_blockers=(),
        elapsed_wall_seconds=10,
        investigation_steps=5,
        useful_discriminator_id="inspect_time_loss_origin",
        dead_end_tool_ids=("inspect_lap_time_opportunity",),
        repeated_no_finding_tool_ids=(),
        causes_separated=("cause-1",),
        causes_left_unresolved=(),
        final_p19_cause_states=(
            P19CauseState(cause_id="cause-1", state="ruled_out"),
        ),
        strongest_contradiction_id="contradiction-1",
        strongest_contradiction_handled=True,
        completed_mandatory_check_ids=("workspace_identity", "data_integrity"),
        created_workflow_ids=(),
        workflow_created=False,
        workflow_scored=False,
        p19_outcome="no_call",
        outcome_validity="qualified",
        prospective=(
            prediction.investigation_opened_at
            > p34_activation_protocol().prospective_boundary
        ),
        synthetic=False,
        blockers=(),
        certified_at=_FROZEN + timedelta(seconds=10),
    )
    return prediction, source, tuple(events), certificate


def test_real_a_then_b_lineage_proves_only_discriminator_position() -> None:
    prediction, source, events, certificate = _bounded_a_then_b_fixture()
    discriminator = build_discriminator_outcome_from_crew_events(
        prediction_pair=prediction,
        source_pair=source,
        certificate=certificate,
        request_event=events[2],
        result_event=events[3],
        investigation_events=events,
        transition_sequence=5,
        evaluated_at=certificate.certified_at,
    )
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(prediction, source),
        certificate=certificate,
        discriminator_outcome=discriminator,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )

    assert discriminator.credit_state == "earned"
    assert discriminator.source_pair_id == source.pair_id
    assert comparison.bounded_reorder_observed is True
    assert comparison.bounded_discriminator_step_advance == 1
    assert comparison.baseline_useful_discriminator_step == 2
    assert comparison.memory_useful_discriminator_step == 1
    assert comparison.memory_tool_steps is None
    assert comparison.memory_dead_ends is None
    assert comparison.memory_path_metrics_observed is False
    assert comparison.memory_elapsed_seconds is None


def test_unrelated_transition_cannot_earn_discriminator_credit() -> None:
    prediction, source, events, certificate = _bounded_a_then_b_fixture()
    unrelated = certificate.model_dump(
        mode="python", exclude={"certificate_id", "certificate_sha256"}
    )
    unrelated["useful_discriminator_id"] = "inspect_lap_time_opportunity"
    unrelated["final_p19_cause_states"] = certificate.final_p19_cause_states
    unrelated_certificate = type(certificate).build(**unrelated)

    discriminator = build_discriminator_outcome_from_crew_events(
        prediction_pair=prediction,
        source_pair=source,
        certificate=unrelated_certificate,
        request_event=events[2],
        result_event=events[3],
        investigation_events=events,
        transition_sequence=5,
        evaluated_at=unrelated_certificate.certified_at,
    )

    assert discriminator.credit_state == "rejected"
    assert discriminator.relevant_ambiguity_ids == ()


def test_artifact_unqualified_at_freeze_cannot_prove_equal_consumption() -> None:
    prediction = _pair(
        investigation_id="late-qualified-artifact",
        step_number=0,
        available_artifact_ids=("artifact-b",),
        qualified_available_artifact_ids=(),
    )
    prediction, source, events, certificate = _bounded_a_then_b_fixture(
        prediction
    )
    discriminator = build_discriminator_outcome_from_crew_events(
        prediction_pair=prediction,
        source_pair=source,
        certificate=certificate,
        request_event=events[2],
        result_event=events[3],
        investigation_events=events,
        transition_sequence=5,
        evaluated_at=certificate.certified_at,
    )
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(prediction, source),
        certificate=certificate,
        discriminator_outcome=discriminator,
        compared_at=certificate.certified_at + timedelta(seconds=1),
    )

    assert comparison.bounded_reorder_observed is True
    assert comparison.memory_consumption_metrics_observed is False
    assert comparison.memory_laps is None
    assert comparison.memory_measurement_missions is None


def test_bounded_dead_end_promotion_records_delay_without_fake_path_cost() -> None:
    prediction, source, _events, certificate = _bounded_a_then_b_fixture()
    values = certificate.model_dump(
        mode="python",
        exclude={"certificate_id", "certificate_sha256"},
    )
    values.update(
        useful_discriminator_id=prediction.baseline_decision.action_id,
        dead_end_tool_ids=(prediction.memory_decision.action_id,),
        final_p19_cause_states=certificate.final_p19_cause_states,
    )
    harmful_certificate = type(certificate).build(**values)
    comparison = build_paired_investigation_comparison(
        investigation_pairs=(prediction, source),
        certificate=harmful_certificate,
        compared_at=harmful_certificate.certified_at + timedelta(seconds=1),
    )
    transfer = build_investigation_negative_transfer(
        comparison,
        detected_at=comparison.compared_at,
    )

    assert comparison.bounded_discriminator_step_delay == 1
    assert comparison.bounded_dead_end_promoted is True
    assert comparison.memory_useful_discriminator_step == 2
    assert transfer is not None
    assert "dead_end_promoted" in transfer.kinds
    assert "useful_current_evidence_delayed" in transfer.kinds
    assert transfer.memory_tool_steps is None
    assert transfer.baseline_useful_discriminator_step == 1
    assert transfer.memory_useful_discriminator_step == 2
    assert transfer.material_efficiency_degradation_pct == 0

    evaluation = evaluate_investigation_policies(
        protocol=p34_activation_protocol(),
        comparisons=(comparison,),
        pairs=(prediction, source),
        certificates=(harmful_certificate,),
        policy_records=(
            baseline_investigation_policy(),
            memory_shadow_investigation_policy(),
            adaptation_service.limited_attention_investigation_policy(),
        ),
        protocol_records=(p34_activation_protocol(),),
        negative_transfers=(transfer,),
        authoritative_case_ids=frozenset((prediction.investigation_id,)),
        registry_identity_sha256="9" * 64,
        ledger_record_count=8,
        ledger_head_sha256="8" * 64,
        evaluated_at=_FROZEN + timedelta(hours=1),
    )
    entry = next(
        item for item in evaluation.subgroup_results if item.subgroup_key == "entry"
    )
    assert entry.material_efficiency_degradation_pct == 0
    assert entry.passed is True


def _frozen_gate_evaluation(
    *,
    prospective_benefit: bool,
) -> InvestigationPolicyEvaluation:
    protocol = p34_activation_protocol()
    pairs: list[PairedInvestigationDecision] = []
    certificates = []
    discriminators = []
    comparisons = []
    controls = []
    authoritative_cases: set[str] = set()
    authoritative_discriminators: set[str] = set()
    conditions = (
        ("no_relevant_history", "none", "combined", "stable", ()),
        ("incompatible_history", "blocked", "driver", "stable", ()),
        ("corrupt_history", "blocked", "combined", "stable", ()),
        (
            "generic_component_knowledge_only",
            "weak",
            "vehicle",
            "stable",
            (),
        ),
        (
            "same_words_different_physical_scope",
            "weak",
            "combined",
            "stable",
            (),
        ),
        ("material_driver_drift", "blocked", "driver", "material_drift", ()),
        (
            "future_memory_record",
            "blocked",
            "combined",
            "stable",
            ("p33x_" + "e" * 24,),
        ),
    )
    for index, (condition, transfer, orientation, driver_state, future_ids) in enumerate(
        conditions
    ):
        pair = _pair(
            investigation_id=f"earned-control-{index}",
            step_number=0,
            memory_action="inspect_lap_time_opportunity",
            transfer=transfer,
            investigation_opened_at=protocol.prospective_boundary
            - timedelta(hours=1),
            negative_control_condition=condition,
            future_memory_record_ids=future_ids,
            problem_family=("braking", "entry", "center", "exit", "straight", "long_run", "entry")[index],
            problem_orientation=orientation,
            driver_drift_state=driver_state,
        )
        certificate = _certificate(pair, prospective=False)
        comparison = build_paired_investigation_comparison(
            investigation_pairs=(pair,),
            certificate=certificate,
            compared_at=certificate.certified_at + timedelta(seconds=1),
        )
        control = build_p34_negative_control_result(
            pair,
            control_id=condition,
            evaluated_at=certificate.certified_at + timedelta(seconds=2),
        )
        pairs.append(pair)
        certificates.append(certificate)
        comparisons.append(comparison)
        controls.append(control)
        authoritative_cases.add(pair.investigation_id)

    tracks = (
        ("Bristol", "oval", "short_track"),
        ("Atlanta", "oval", "intermediate"),
        ("Daytona", "oval", "superspeedway"),
    )
    families = ("braking", "entry", "center", "exit", "straight", "long_run")
    orientations = ("driver", "vehicle", "combined")
    objectives = ("qualifying_peak", "race_long_run", "driver_confidence")
    for index in range(25):
        investigation_id = f"earned-benefit-{index}"
        track, configuration, track_class = tracks[index % len(tracks)]
        prediction = _pair(
            investigation_id=investigation_id,
            step_number=0,
            transfer="compatible" if index < 5 else "exact",
            investigation_opened_at=(
                protocol.prospective_boundary - timedelta(hours=1)
                if index < 13
                else protocol.prospective_boundary + timedelta(seconds=1)
            ),
            track=track,
            track_configuration=configuration,
            package_type=track_class,
            problem_family=families[index % len(families)],
            problem_orientation=orientations[index % len(orientations)],
            track_class=track_class,
            objective=objectives[index % len(objectives)],
            build_review_state=(
                "reviewed_compatible_build" if index % 4 == 0 else "same_build"
            ),
            available_artifact_ids=("artifact-b",),
            memory_action=(
                "inspect_time_loss_origin"
                if prospective_benefit or index < 13
                else "inspect_lap_time_opportunity"
            ),
        )
        if not prospective_benefit and index >= 13:
            certificate = _certificate(prediction, prospective=True)
            comparison = build_paired_investigation_comparison(
                investigation_pairs=(prediction,),
                certificate=certificate,
                compared_at=certificate.certified_at + timedelta(seconds=1),
            )
            pairs.append(prediction)
            certificates.append(certificate)
            comparisons.append(comparison)
            authoritative_cases.add(investigation_id)
            continue
        prediction, source, events, certificate = _bounded_a_then_b_fixture(
            prediction
        )
        discriminator = build_discriminator_outcome_from_crew_events(
            prediction_pair=prediction,
            source_pair=source,
            certificate=certificate,
            request_event=events[2],
            result_event=events[3],
            investigation_events=events,
            transition_sequence=5,
            evaluated_at=certificate.certified_at,
        )
        comparison = build_paired_investigation_comparison(
            investigation_pairs=(prediction, source),
            certificate=certificate,
            discriminator_outcome=discriminator,
            compared_at=certificate.certified_at + timedelta(seconds=1),
        )
        assert comparison.memory_consumption_metrics_observed is True
        pairs.extend((prediction, source))
        certificates.append(certificate)
        discriminators.append(discriminator)
        comparisons.append(comparison)
        authoritative_cases.add(investigation_id)
        authoritative_discriminators.add(discriminator.outcome_id)

    return evaluate_investigation_policies(
        protocol=protocol,
        comparisons=comparisons,
        pairs=pairs,
        certificates=certificates,
        policy_records=(
            baseline_investigation_policy(),
            memory_shadow_investigation_policy(),
            adaptation_service.limited_attention_investigation_policy(),
        ),
        protocol_records=(protocol,),
        discriminator_outcomes=discriminators,
        negative_control_results=controls,
        authoritative_case_ids=frozenset(authoritative_cases),
        authoritative_discriminator_ids=frozenset(
            authoritative_discriminators
        ),
        registry_identity_sha256="9" * 64,
        ledger_record_count=128,
        ledger_head_sha256="8" * 64,
        evaluated_at=_FROZEN + timedelta(hours=1),
    )


def test_shadow_discriminator_timing_does_not_fake_full_path_efficiency() -> None:
    evaluation = _frozen_gate_evaluation(prospective_benefit=True)

    assert evaluation.historical_count == 20
    assert evaluation.prospective_count == 12
    assert evaluation.paired_observable_comparisons == 32
    assert evaluation.efficiency.earlier_useful_discriminator_rate == 1
    assert evaluation.efficiency.median_tool_step_difference == 0
    assert evaluation.efficiency.relative_tool_step_reduction == 0
    assert evaluation.efficiency.dead_end_reduction_rate == 0
    assert evaluation.decision == "no_activation_earned"
    assert "Frozen investigation-efficiency thresholds are not met." in (
        evaluation.blockers
    )


def test_historical_success_cannot_hide_a_failed_prospective_gate() -> None:
    evaluation = _frozen_gate_evaluation(prospective_benefit=False)

    assert evaluation.historical_count == 20
    assert evaluation.prospective_count == 12
    assert evaluation.decision == "no_activation_earned"
    assert any(
        "prospective safety and investigation-efficiency" in blocker
        for blocker in evaluation.blockers
    )


def test_per_case_fallback_does_not_revoke_and_equal_time_rollback_wins(
    tmp_path,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-activation.sqlite")
    persist_p34_foundation(repository)
    locked = evaluate_p34_repository(repository, evaluated_at=_FROZEN)
    earned_values = locked.model_dump(
        mode="python", exclude={"evaluation_id", "evaluation_sha256"}
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
    timestamp = _FROZEN + timedelta(minutes=2)
    limited = P34ActivationDecision.build(
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
        decided_at=timestamp,
    )
    repository.append_evaluation(earned)
    repository.append_activation_decision(limited)

    current_local_debt = evaluate_p34_repository(
        repository,
        evaluated_at=timestamp + timedelta(seconds=1),
    )
    unchanged = build_p34_activation_decision(
        current_local_debt,
        repository=repository,
        decided_at=timestamp + timedelta(seconds=1),
    )
    assert unchanged == limited

    rollback_evaluation_values = current_local_debt.model_dump(
        mode="python", exclude={"evaluation_id", "evaluation_sha256"}
    )
    rollback_evaluation_values.update(
        safety=current_local_debt.safety.model_copy(
            update={"authority_violations": 1}
        ),
        efficiency=current_local_debt.efficiency,
        quality=current_local_debt.quality,
        subgroup_results=current_local_debt.subgroup_results,
        blockers=("One or more frozen safety gates failed.",),
        decision="no_activation_earned",
    )
    rollback_evaluation = InvestigationPolicyEvaluation.build(
        **rollback_evaluation_values
    )
    rollback = P34ActivationDecision.build(
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.protocol_sha256,
        evaluation_id=rollback_evaluation.evaluation_id,
        evaluation_sha256=rollback_evaluation.evaluation_sha256,
        activated_policy_id=protocol.activated_policy_id,
        activated_policy_sha256=protocol.activated_policy_sha256,
        state="shadow_only",
        production_policy_kind="deterministic_baseline",
        blockers=("A post-activation authority or mandatory safety gate failed.",),
        recovery_debt=(
            "A post-activation authority or mandatory safety gate failed.",
        ),
        supersedes_decision_id=limited.decision_id,
        supersedes_decision_sha256=limited.decision_sha256,
        rollback_applied=True,
        decided_at=timestamp,
    )
    repository.append_evaluation(rollback_evaluation)
    repository.append_activation_decision(rollback)

    restarted = InvestigationAdaptationRepository(repository.db_path)
    decisions = restarted.query_records(
        record_kinds=("activation_decision",),
        protocol_id=protocol.protocol_id,
    ).records
    assert decisions[0] == rollback
    assert resolve_effective_activation_decision(restarted) is None


def test_warm_pair_activation_and_projection_paths_meet_latency_budget(
    tmp_path,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-warm.sqlite")
    persist_p34_foundation(repository)
    pair = _pair(investigation_id="warm-path")
    context = _context(pair)
    evaluation = evaluate_p34_repository(repository)
    readiness = assess_investigation_improvement_readiness(evaluation)
    build_investigation_improvement_projection(
        run_id=pair.run_id,
        session_id=pair.session_id,
        workspace_revision=pair.workspace_revision,
        readiness=readiness,
        current_pair=pair,
        current_context=context,
    )
    resolve_effective_activation_decision(repository)

    iterations = 20
    started = perf_counter()
    for _ in range(iterations):
        _pair(investigation_id="warm-path")
    pair_average = (perf_counter() - started) / iterations

    started = perf_counter()
    for _ in range(iterations):
        resolve_effective_activation_decision(repository)
    activation_average = (perf_counter() - started) / iterations

    started = perf_counter()
    for _ in range(iterations):
        evaluate_p34_repository(repository)
    evaluation_average = (perf_counter() - started) / iterations

    started = perf_counter()
    for _ in range(iterations):
        build_investigation_improvement_projection(
            run_id=pair.run_id,
            session_id=pair.session_id,
            workspace_revision=pair.workspace_revision,
            readiness=readiness,
            current_pair=pair,
            current_context=context,
        )
    projection_average = (perf_counter() - started) / iterations

    assert pair_average < 0.05
    assert activation_average < 0.05
    assert evaluation_average < 0.10
    assert projection_average < 0.10


def _bulk_seed_independent_pair_revisions(
    repository: InvestigationAdaptationRepository,
    *,
    investigation_count: int,
    revisions: int,
) -> None:
    template = _pair(investigation_id="bulk-template", step_number=1)
    body = template.model_dump(mode="python", exclude={"pair_id", "pair_sha256"})
    body.update(
        baseline_decision=template.baseline_decision,
        memory_decision=template.memory_decision,
        production_decision=template.production_decision,
        current_p19_cause_states=template.current_p19_cause_states,
    )
    connection = initialize_database(repository.db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = repository.stream_state(connection=connection)
        sequence = state.record_count
        previous = state.head_sha256
        for investigation_index in range(investigation_count):
            for revision_index in range(revisions):
                values = dict(body)
                values.update(
                    investigation_id=f"bounded-{investigation_index:05d}",
                    step_number=revision_index + 1,
                    decision_frozen_at=(
                        _FROZEN + timedelta(microseconds=revision_index)
                    ),
                )
                pair = PairedInvestigationDecision.build(**values)
                metadata = adaptation_storage._metadata(pair)
                indexed = adaptation_storage._indexed_identity(metadata)
                sequence += 1
                entry_sha256 = adaptation_storage._entry_sha256(
                    sequence,
                    previous,
                    indexed,
                )
                connection.execute(
                    """
                    INSERT INTO investigation_adaptation_records (
                      sequence, record_id, record_sha256, record_kind,
                      previous_entry_sha256, entry_sha256, recorded_at,
                      investigation_id, workspace_revision, step_number,
                      policy_id, protocol_id, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        metadata.record_id,
                        metadata.record_sha256,
                        metadata.record_kind,
                        previous,
                        entry_sha256,
                        metadata.recorded_at,
                        metadata.investigation_id,
                        metadata.workspace_revision,
                        metadata.step_number,
                        metadata.policy_id,
                        metadata.protocol_id,
                        pair.model_dump_json(),
                    ),
                )
                previous = entry_sha256
        connection.execute(
            "UPDATE investigation_adaptation_stream_head "
            "SET record_count = ?, head_sha256 = ? WHERE stream_id = ?",
            (sequence, previous, "p34.investigation-adaptation.v1"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _bulk_seed_foreign_protocol_controls(
    repository: InvestigationAdaptationRepository,
    *,
    count: int,
) -> tuple[str, str]:
    protocol_id = "p34proto_" + "6" * 24
    protocol_sha256 = "6" * 64
    connection = initialize_database(repository.db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = repository.stream_state(connection=connection)
        sequence = state.record_count
        previous = state.head_sha256
        for index in range(count):
            pair_id = "p34pair_" + f"{index:024x}"
            record = P34NegativeControlResult.build(
                protocol_id=protocol_id,
                protocol_sha256=protocol_sha256,
                control_id="no_relevant_history",
                investigation_id=f"foreign-{index:05d}",
                pair_id=pair_id,
                pair_sha256=f"{index:064x}",
                observed_exact_fallback=True,
                passed=True,
                source_artifact_ids=(pair_id,),
                blockers=(),
                evaluated_at=_FROZEN,
            )
            metadata = adaptation_storage._metadata(record)
            indexed = adaptation_storage._indexed_identity(metadata)
            sequence += 1
            entry_sha256 = adaptation_storage._entry_sha256(
                sequence,
                previous,
                indexed,
            )
            connection.execute(
                """
                INSERT INTO investigation_adaptation_records (
                  sequence, record_id, record_sha256, record_kind,
                  previous_entry_sha256, entry_sha256, recorded_at,
                  investigation_id, workspace_revision, step_number,
                  policy_id, protocol_id, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    metadata.record_id,
                    metadata.record_sha256,
                    metadata.record_kind,
                    previous,
                    entry_sha256,
                    metadata.recorded_at,
                    metadata.investigation_id,
                    metadata.workspace_revision,
                    metadata.step_number,
                    metadata.policy_id,
                    metadata.protocol_id,
                    record.model_dump_json(),
                ),
            )
            previous = entry_sha256
        connection.execute(
            "UPDATE investigation_adaptation_stream_head "
            "SET record_count = ?, head_sha256 = ? WHERE stream_id = ?",
            (sequence, previous, "p34.investigation-adaptation.v1"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return protocol_id, protocol_sha256


def test_10000_independent_multi_revision_pairs_are_bounded_and_10001_blocks(
    tmp_path,
    monkeypatch,
) -> None:
    repository = InvestigationAdaptationRepository(tmp_path / "p34-10k.sqlite")
    persist_p34_foundation(repository)
    _bulk_seed_independent_pair_revisions(
        repository,
        investigation_count=10_000,
        revisions=2,
    )
    evaluation_statements: list[str] = []
    original_connect_read_only = adaptation_service.connect_read_only

    def traced_read_only(db_path):
        traced = original_connect_read_only(db_path)
        traced.set_trace_callback(evaluation_statements.append)
        return traced

    monkeypatch.setattr(
        adaptation_service,
        "connect_read_only",
        traced_read_only,
    )
    adaptation_service._REPOSITORY_EVALUATION_CACHE.clear()
    adaptation_service._EFFECTIVE_ACTIVATION_CACHE.clear()
    adaptation_service._VERIFIED_P34_CHAIN_KEYS.clear()
    cold_pair = _pair(investigation_id="bounded-cold-projection")
    started = perf_counter()
    cold_readiness = assess_p34_repository_readiness(repository)
    build_investigation_improvement_projection(
        run_id=cold_pair.run_id,
        session_id=cold_pair.session_id,
        workspace_revision=cold_pair.workspace_revision,
        readiness=cold_readiness,
        current_pair=cold_pair,
        current_context=_context(cold_pair),
    )
    cold_projection_elapsed = perf_counter() - started

    assert cold_projection_elapsed < 0.10
    assert not any(
        token in statement.lower()
        for statement in evaluation_statements
        for token in (
            " from laps",
            " from segments",
            "telemetry_samples",
            "normalized_telemetry",
        )
    )

    connection = initialize_database(repository.db_path)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    started = perf_counter()
    pairs = repository.query_canonical_pairs(
        protocol_id=p34_activation_protocol().protocol_id,
        limit=10_000,
        connection=connection,
    )
    elapsed = perf_counter() - started
    overflow_at_limit = repository.evaluation_capacity_overflow(
        protocol_id=p34_activation_protocol().protocol_id,
        record_kinds=("paired_comparison",),
        connection=connection,
    )
    connection.close()

    assert len(pairs) == 10_000
    assert len({item.investigation_id for item in pairs}) == 10_000
    assert all(item.step_number == 1 for item in pairs)
    assert overflow_at_limit == ()
    assert elapsed < 10
    assert not any(
        token in statement.lower()
        for statement in statements
        for token in (" from laps", " from segments", "telemetry_samples")
    )

    foreign_protocol_id, _foreign_protocol_sha256 = (
        _bulk_seed_foreign_protocol_controls(repository, count=10_001)
    )
    scoped = initialize_database(repository.db_path)
    try:
        assert repository.evaluation_capacity_overflow(
            protocol_id=p34_activation_protocol().protocol_id,
            record_kinds=("negative_control_result",),
            connection=scoped,
        ) == ()
        assert repository.evaluation_capacity_overflow(
            protocol_id=foreign_protocol_id,
            record_kinds=("negative_control_result",),
            connection=scoped,
        ) == ("negative_control_result",)
        repository.stream_state(connection=scoped, validate_chain=True)
    finally:
        scoped.close()

    overflow_pair = _pair(
        investigation_id="bounded-overflow-10001",
        step_number=1,
    )
    repository.append_paired_decision(overflow_pair)
    evaluation_statements.clear()
    evaluation = evaluate_p34_repository(
        repository,
        evaluated_at=_FROZEN + timedelta(minutes=1),
    )

    assert evaluation.decision == "no_activation_earned"
    assert any("10000-unit retrieval bound" in item for item in evaluation.blockers)
    assert not any(
        token in statement.lower()
        for statement in evaluation_statements
        for token in (
            " from laps",
            " from segments",
            "telemetry_samples",
            "normalized_telemetry",
        )
    )

    # Prime one full, protocol-scoped restart audit, then prove the immutable
    # revision cache keeps the normal workspace path inside its warm budget.
    evaluate_p34_repository(repository)
    started = perf_counter()
    readiness = assess_p34_repository_readiness(repository)
    build_investigation_improvement_projection(
        run_id=overflow_pair.run_id,
        session_id=overflow_pair.session_id,
        workspace_revision=overflow_pair.workspace_revision,
        readiness=readiness,
        current_pair=overflow_pair,
        current_context=_context(overflow_pair),
    )
    warm_projection_elapsed = perf_counter() - started

    started = perf_counter()
    _pair(investigation_id="bounded-warm-new")
    warm_pair_elapsed = perf_counter() - started

    assert warm_pair_elapsed < 0.05
    assert warm_projection_elapsed < 0.10
