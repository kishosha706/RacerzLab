from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    CrewChiefEvent,
    CrewChiefEventPayload,
    CrewChiefInvestigation,
    CrewChiefTerminalDecision,
    CrewChiefWorkspaceIdentity,
)
from racelab_engine.models.engineering_learning import (
    CarResponseFact,
    DeadEndFact,
    DriverFingerprintContribution,
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    EngineeringSourceProvenance,
    InvestigationPathFact,
    MindChangeFact,
    P19CauseMemory,
    P19ReasoningMemory,
    ProblemFingerprint,
)
from racelab_engine.services import engineering_learning_service as service
from racelab_engine.services.session_service import (
    add_run_to_session,
    create_session,
    remove_run_from_session,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    EngineeringLearningRepository,
)
from racelab_engine.storage.repository import RaceLabRepository
from test_engineering_memory_service import _scored_workflow
from test_p19_release_proofs import _run as _imported_run


def _context(
    index: int,
    *,
    build: str = "2026.08.1",
    objective: str = "race_long_run",
    setup_hash: str = "a" * 64,
    run_id: str | None = None,
    session_id: str | None = None,
    driver_execution_state: str = "matched_inputs",
) -> EngineeringExperienceContext:
    return EngineeringExperienceContext.build(
        run_id=run_id or f"run-{index}",
        session_id=session_id or f"session-{index}",
        driver_id="driver-a",
        car_path="nascar-nextgen-chevy",
        car_version="2026.08",
        iracing_build=build,
        track="atlanta",
        track_configuration="oval",
        package_type="speedway",
        setup_family=None,
        setup_snapshot_sha256=setup_hash,
        objective=objective,
        physical_scope_sha256="b" * 64,
        phase="center",
        physical_region="T1-T2",
        speed_load_band="high_speed_loaded",
        fuel_state="short_run",
        tire_state="short_run",
        weather_state="recorded",
        traffic_state="clear",
        driver_execution_state=driver_execution_state,
    )


def _problem(index: int, *, stable_source_ids: bool = True) -> ProblemFingerprint:
    suffix = "shared" if stable_source_ids else str(index)
    return ProblemFingerprint.build(
        physical_episode_id=f"episode-{suffix}",
        performance_opportunity_id=f"opportunity-{suffix}",
        phase="center",
        physical_region="T1-T2",
        time_origin_class="local_loss",
        carry_behavior="following_straight_carry",
        driver_demand_state="matched_inputs",
        vehicle_response_state="changed_response",
        p20_mechanism_families=("platform", "tire_state"),
        p26_component_families=("rf_tire",),
        traffic_context_state="clear",
        tire_stint_state="short_run",
        objective="race_long_run",
        source_artifact_ids=(f"problem-artifact-{suffix}",),
    )


def _reasoning(index: int, *, leading: str = "platform") -> P19ReasoningMemory:
    other = "tire_state" if leading == "platform" else "platform"
    return P19ReasoningMemory(
        reasoning_snapshot_sha256=f"{index % 10}" * 64,
        causes=(
            P19CauseMemory(
                cause_id=f"cause-{leading}",
                status="likely",
                ordinal_rank=1,
                mechanism_family=leading,
            ),
            P19CauseMemory(
                cause_id=f"cause-{other}",
                status="possible",
                ordinal_rank=2,
                mechanism_family=other,
            ),
        ),
        measurement_plan_kind="discriminator",
        discriminator_ids=("inspect_tire_state",),
        authority_level="measurement",
        setup_authorized=False,
    )


def _provenance(
    context: EngineeringExperienceContext,
    artifact_id: str,
    *,
    state: str = "observed_correlation",
    setup_id: str | None = None,
    build_context_sha256: str = "4" * 64,
) -> EngineeringSourceProvenance:
    return EngineeringSourceProvenance.build(
        artifact_id=artifact_id,
        producer_id="p33.test-source",
        run_id=context.run_id,
        session_id=context.session_id,
        setup_id=setup_id or f"setup-{context.run_id}",
        setup_snapshot_sha256=context.setup_snapshot_sha256,
        build_context_sha256=build_context_sha256,
        lap_numbers=(7,),
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        phase="center",
        source_channels=("speed_mps",),
        evidence_state=state,
        polarity="support",
    )


def _current(
    *,
    context: EngineeringExperienceContext | None = None,
    problem: ProblemFingerprint | None = None,
) -> service.CurrentLearningInputs:
    context = context or _context(99)
    problem = problem or _problem(99)
    artifact_id = problem.source_artifact_ids[0]
    return service.CurrentLearningInputs(
        context=context,
        problem=problem,
        reasoning=_reasoning(9),
        source_provenance=(_provenance(context, artifact_id),),
        performance_response=None,
        driver_contributions=(),
    )


def _investigation_experience(
    index: int,
    *,
    problem: ProblemFingerprint | None = None,
    context: EngineeringExperienceContext | None = None,
    driver_tendency: str = "repeatable_tendency",
) -> EngineeringExperienceRecord:
    context = context or _context(index)
    problem = problem or _problem(index)
    problem_artifact = problem.source_artifact_ids[0]
    result_artifact = f"investigation-artifact-{index}"
    opening = _reasoning(index + 3, leading="platform")
    closing = _reasoning(index + 5, leading="tire_state")
    contribution = DriverFingerprintContribution(
        contribution_id=f"driver-contribution-{index}",
        metric="brake_release_timing_consistency",
        tendency=driver_tendency,
        statement=(
            "Brake release timing remained repeatable in this physical region."
            if driver_tendency == "repeatable_tendency"
            else "Brake release timing differed from prior qualified execution."
        ),
        physical_episode_ids=(problem.physical_episode_id,),
        source_artifact_ids=(result_artifact,),
        source_lap_count=3,
    )
    outcome = InvestigationPathFact(
        investigation_id=f"investigation-{index}",
        started_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
        + timedelta(minutes=index),
        completed_at=datetime(2026, 8, 14, 12, 5, tzinfo=timezone.utc)
        + timedelta(minutes=index),
        initial_cause_ids=("cause-platform", "cause-tire_state"),
        tools_inspected=(
            "inspect_time_loss_origin",
            "inspect_track_demand",
        ),
        driver_question_ids=(f"question-{index}",),
        driver_answers=("Inputs felt consistent.",),
        requested_measurement_ids=(
            "inspect_time_loss_origin",
            "inspect_track_demand",
        ),
        completed_measurement_ids=(
            "inspect_time_loss_origin",
            "inspect_track_demand",
        ),
        strongest_contradiction="Tire-state evidence contradicted the platform-only explanation.",
        eliminated_cause_ids=("cause-platform",),
        unresolved_cause_ids=(),
        terminal_decision="measurement_only",
        workflow_ids=(),
        elapsed_seconds=300.0,
        laps_consumed=3,
        tool_steps_consumed=2,
        driver_questions_consumed=1,
        successful_discriminator_ids=("inspect_track_demand",),
        source_artifact_ids=(result_artifact,),
        historical_retrieval_used=index > 1,
        historical_match_confirmed=True if index > 1 else None,
    )
    mind_change = MindChangeFact(
        mind_change_id=f"mind-change-{index}",
        before_reasoning=opening,
        after_reasoning=closing,
        new_artifact_ids=(result_artifact,),
        new_evidence_states=("measured",),
        causes_promoted=("cause-tire_state",),
        causes_demoted=("cause-platform",),
        measurement_discriminator_id="inspect_track_demand",
        evidence_discriminated=True,
        driver_question_involved=True,
        controlled_evidence_involved=False,
        context_gate_involved=False,
    )
    dead_end = DeadEndFact(
        dead_end_id=f"dead-end-{index}",
        kind="repeated_no_finding_tool",
        tool_id="inspect_time_loss_origin",
        statement="This inspection did not separate the competing mechanisms.",
        source_artifact_ids=(result_artifact,),
    )
    return EngineeringExperienceRecord.build(
        source_kind="resolved_investigation",
        source_investigation_id=f"investigation-{index}",
        created_at=outcome.completed_at,
        context=context,
        problem=problem,
        source_p19_reasoning_snapshot_sha256=closing.reasoning_snapshot_sha256,
        source_p32_projection_sha256="f" * 64,
        opening_reasoning=opening,
        closing_reasoning=closing,
        driver_contributions=(contribution,),
        investigation_outcome=outcome,
        mind_change=mind_change,
        dead_ends=(dead_end,),
        source_event_ids=(f"event-{index}",),
        source_artifact_ids=(problem_artifact, result_artifact),
        source_provenance=(
            _provenance(context, problem_artifact),
            _provenance(context, result_artifact),
        ),
    )


def _workflow_experience(
    index: int,
    *,
    verdict: str,
    direction: str,
    problem: ProblemFingerprint,
) -> EngineeringExperienceRecord:
    context = _context(index)
    problem_artifact = problem.source_artifact_ids[0]
    result_artifact = f"workflow-artifact-{index}"
    reasoning = _reasoning(index + 1)
    response = CarResponseFact(
        response_id=f"response-{index}",
        component="vehicle_balance",
        control="cross_weight_percent",
        direction=direction,
        magnitude_class="small",
        expected_vehicle_response="More center rotation was the recorded expectation.",
        observed_vehicle_response="Center rotation increased in the controlled comparison.",
        p32_time_origin="center",
        phase_time_effect_s=-0.08,
        carry_effect_s=0.03 if verdict == "undo" else -0.02,
        recovery_surrender="exit countereffect recorded"
        if verdict == "undo"
        else "gain carried to exit",
        countereffects=("Exit instability increased.",) if verdict == "undo" else (),
        p19_mechanism_assessment="unchanged",
        control_response_assessment="matched",
        policy_verdict=verdict,
        source_workflow_id=f"workflow-{index}",
        source_artifact_ids=(result_artifact,),
    )
    return EngineeringExperienceRecord.build(
        source_kind="controlled_workflow",
        source_workflow_id=f"workflow-{index}",
        created_at=datetime(2026, 8, 14, 14, tzinfo=timezone.utc)
        + timedelta(minutes=index),
        context=context,
        problem=problem,
        source_p19_reasoning_snapshot_sha256=reasoning.reasoning_snapshot_sha256,
        source_p32_projection_sha256="f" * 64,
        closing_reasoning=reasoning,
        car_response=response,
        source_response_record_ids=(f"response-{index}",),
        source_artifact_ids=(problem_artifact, result_artifact),
        source_provenance=(
            _provenance(context, problem_artifact),
            _provenance(
                context,
                result_artifact,
                state="controlled_test_effect",
            ),
        ),
    )


def _prior(current, repository, db_path):
    service.clear_learning_cache()
    return service.build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="f" * 64,
        repository=repository,
        db_path=db_path,
    )


def _crew_event(
    investigation_id: str,
    sequence: int,
    event_type: str,
    payload: CrewChiefEventPayload,
    *,
    workspace_revision: str = "8" * 64,
) -> CrewChiefEvent:
    return CrewChiefEvent(
        event_id=f"event-{investigation_id}-{sequence}",
        investigation_id=investigation_id,
        sequence=sequence,
        event_type=event_type,
        workspace_revision=workspace_revision,
        created_at=datetime(2026, 8, 14, 16, tzinfo=timezone.utc)
        + timedelta(seconds=sequence),
        event_hash=f"{sequence % 10}" * 64,
        payload=payload,
    )


def _crew_investigation(
    current: service.CurrentLearningInputs,
    investigation_id: str,
    *,
    opening_problem: ProblemFingerprint | None = None,
) -> CrewChiefInvestigation:
    source = next(
        item
        for item in current.source_provenance
        if item.run_id == current.context.run_id
    )
    identity = CrewChiefWorkspaceIdentity(
        run_id=current.context.run_id,
        session_id=current.context.session_id,
        selected_scope_hash="1" * 64,
        reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p20_state_revision="2" * 64,
        p20_profile_hash=None,
        p26_graph_version="p26.v1",
        p26_knowledge_graph_sha256="3" * 64,
        p26_reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="5" * 64,
        learning_history_revision="6" * 64,
        learning_projection_sha256="7" * 64,
        setup_id=source.setup_id,
        setup_snapshot_sha256=source.setup_snapshot_sha256,
        vehicle_runtime_identity_hash=source.build_context_sha256,
        active_workflow_id=None,
        active_workflow_revision=None,
        objective_id=current.context.objective,
        investigation_id=None,
        workspace_revision="8" * 64,
    )
    return CrewChiefInvestigation(
        investigation_id=investigation_id,
        workspace_identity=identity,
        origin="manual_review",
        objective=current.context.objective,
        raw_driver_report="The balance changed in the measured region.",
        canonical_problem="balance changed in the measured region",
        opening_reasoning=current.reasoning,
        opening_problem=opening_problem or current.problem,
        opened_at=datetime(2026, 8, 14, 16, tzinfo=timezone.utc),
    )


def _transition_case(
    artifact_id: str,
    *,
    state: str = "measured",
) -> tuple[service.CurrentLearningInputs, CrewChiefInvestigation]:
    base = _current()
    closing = _reasoning(9, leading="tire_state")
    current = service.CurrentLearningInputs(
        context=base.context,
        problem=base.problem,
        reasoning=closing,
        source_provenance=(
            *base.source_provenance,
            _provenance(base.context, artifact_id, state=state),
        ),
        performance_response=base.performance_response,
        driver_contributions=base.driver_contributions,
    )
    opening = _reasoning(8, leading="platform").model_copy(
        update={"discriminator_ids": ()}
    )
    draft = _crew_investigation(current, f"investigation-{artifact_id}")
    identity = draft.workspace_identity.model_copy(
        update={"reasoning_snapshot_sha256": opening.reasoning_snapshot_sha256}
    )
    investigation = CrewChiefInvestigation.model_validate(
        {
            **draft.model_dump(mode="python"),
            "workspace_identity": identity,
            "opening_reasoning": opening,
        }
    )
    return current, investigation


def _rebuilt_record(
    record: EngineeringExperienceRecord,
    **updates: object,
) -> EngineeringExperienceRecord:
    excluded = {"experience_id", "experience_sha256", "source_identity_sha256"}
    payload = {
        field: getattr(record, field)
        for field in type(record).model_fields
        if field not in excluded
    }
    payload.update(updates)
    return EngineeringExperienceRecord.build(**payload)


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            child for nested in value.values() for child in _nested_keys(nested)
        }
    if isinstance(value, (list, tuple)):
        return {child for nested in value for child in _nested_keys(nested)}
    return set()


def test_public_projection_surfaces_recurrence_driver_car_process_and_dead_ends(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99, stable_source_ids=False)
    for record in (
        _investigation_experience(1, problem=_problem(1, stable_source_ids=False)),
        _investigation_experience(2, problem=_problem(2, stable_source_ids=False)),
        _workflow_experience(3, verdict="keep", direction="increase", problem=problem),
        _workflow_experience(4, verdict="undo", direction="decrease", problem=problem),
    ):
        repository.append_experience(record)

    prior = _prior(_current(problem=problem), repository, db_path)

    assert prior.state == "available"
    assert prior.recurrence.classification == "exact_context_recurrence"
    assert len(prior.useful_prior_investigations) == 2
    assert all(item.useful for item in prior.useful_prior_investigations)
    assert len(prior.mind_change_history) == 2
    assert all(
        item.fact.before_reasoning.causes[0].cause_id == "cause-platform"
        and item.fact.after_reasoning.causes[0].cause_id == "cause-tire_state"
        and item.fact.evidence_discriminated is True
        for item in prior.mind_change_history
    )
    assert len(prior.driver_tendencies) == 1
    assert prior.driver_tendencies[0].state == "repeatable_tendency"
    assert len(prior.car_response_history) == 2
    assert {item.response.policy_verdict for item in prior.car_response_history} == {
        "keep",
        "undo",
    }
    undo = next(
        item
        for item in prior.car_response_history
        if item.response.policy_verdict == "undo"
    )
    assert undo.response.control_response_assessment == "matched"
    assert undo.response.countereffects == ("Exit instability increased.",)
    assert len(prior.known_dead_ends) == 1
    assert prior.known_dead_ends[0].counts.independent_episode_count == 2
    assert prior.known_dead_ends[0].may_deprioritize_within_band is True
    assert prior.known_dead_ends[0].may_veto_current_evidence is False
    assert tuple(item.tool_id for item in prior.recommended_attention_order) == (
        "inspect_track_demand",
    )
    assert all(
        item.authority == "attention_only" for item in prior.recommended_attention_order
    )
    assert prior.ledger.investigations_resolved == 2
    assert prior.ledger.keep_outcomes == 1
    assert prior.ledger.undo_outcomes == 1
    assert prior.authority == "attention_only"
    assert prior.setup_authorized is False
    assert prior.p19_rank_modified is False
    assert not {
        "probability",
        "probability_percent",
        "recommended_setup_action",
        "setup_action",
    } & _nested_keys(prior.model_dump(mode="json"))


def test_scenario_e_credits_only_the_successful_discriminator_not_the_dead_end(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-scenario-e.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99, stable_source_ids=False)
    for index in (1, 2):
        repository.append_experience(
            _investigation_experience(
                index,
                problem=_problem(index, stable_source_ids=False),
            )
        )

    prior = _prior(_current(problem=problem), repository, db_path)

    assert prior.ledger.successful_discriminators == ("inspect_track_demand",)
    assert len(prior.known_dead_ends) == 1
    dead_end = prior.known_dead_ends[0]
    assert dead_end.fact.tool_id == "inspect_time_loss_origin"
    assert dead_end.may_deprioritize_within_band is True
    assert dead_end.may_veto_current_evidence is False
    assert tuple(item.tool_id for item in prior.recommended_attention_order) == (
        "inspect_track_demand",
    )


def test_exact_attention_precedes_compatible_attention_before_tool_position(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-attention-transfer-order.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99, stable_source_ids=False)
    for index in (1, 2):
        original = _investigation_experience(
            index,
            problem=_problem(index, stable_source_ids=False),
            context=_context(index),
        )
        assert original.investigation_outcome is not None
        exact_outcome = original.investigation_outcome.model_copy(
            update={
                "tools_inspected": (
                    "inspect_lap_time_opportunity",
                    "inspect_time_loss_origin",
                ),
                "successful_discriminator_ids": ("inspect_time_loss_origin",),
            }
        )
        repository.append_experience(
            _rebuilt_record(
                original,
                investigation_outcome=exact_outcome,
                mind_change=original.mind_change.model_copy(
                    update={"measurement_discriminator_id": "inspect_time_loss_origin"}
                ),
                dead_ends=(),
            )
        )
    for index in (3, 4):
        original = _investigation_experience(
            index,
            problem=_problem(index, stable_source_ids=False),
            context=_context(index, setup_hash="c" * 64),
        )
        assert original.investigation_outcome is not None
        compatible_outcome = original.investigation_outcome.model_copy(
            update={
                "tools_inspected": ("inspect_track_demand",),
                "tool_steps_consumed": 1,
                "successful_discriminator_ids": ("inspect_track_demand",),
            }
        )
        repository.append_experience(
            _rebuilt_record(
                original,
                investigation_outcome=compatible_outcome,
                dead_ends=(),
            )
        )

    prior = _prior(_current(problem=problem), repository, db_path)

    assert tuple(
        (item.tool_id, item.transfer_level)
        for item in prior.recommended_attention_order
    ) == (
        ("inspect_time_loss_origin", "exact"),
        ("inspect_track_demand", "compatible"),
    )


def test_two_investigations_of_one_physical_episode_cannot_teach_attention(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-one-episode-attention.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99)
    for index in (1, 2):
        original = _investigation_experience(index, problem=problem)
        repository.append_experience(_rebuilt_record(original, dead_ends=()))

    prior = _prior(_current(problem=problem), repository, db_path)

    assert prior.counts.independent_episode_count == 1
    assert prior.recommended_attention_order == ()


def test_compatible_dead_ends_cannot_erase_exact_successful_attention(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-attention-tiered-dead-end.sqlite"
    repository = EngineeringLearningRepository(db_path)
    current_problem = _problem(99, stable_source_ids=False)
    for index in (1, 2):
        original = _investigation_experience(
            index,
            problem=_problem(index, stable_source_ids=False),
            context=_context(index),
        )
        assert original.investigation_outcome is not None
        success = original.investigation_outcome.model_copy(
            update={
                "tools_inspected": ("inspect_track_demand",),
                "tool_steps_consumed": 1,
                "successful_discriminator_ids": ("inspect_track_demand",),
            }
        )
        repository.append_experience(
            _rebuilt_record(
                original,
                investigation_outcome=success,
                dead_ends=(),
            )
        )
    for index in (3, 4):
        original = _investigation_experience(
            index,
            problem=_problem(index, stable_source_ids=False),
            context=_context(index, setup_hash="c" * 64),
        )
        assert original.investigation_outcome is not None
        no_finding = original.investigation_outcome.model_copy(
            update={
                "tools_inspected": ("inspect_track_demand",),
                "tool_steps_consumed": 1,
                "successful_discriminator_ids": (),
            }
        )
        dead_end = original.dead_ends[0].model_copy(
            update={"tool_id": "inspect_track_demand"}
        )
        repository.append_experience(
            _rebuilt_record(
                original,
                investigation_outcome=no_finding,
                mind_change=original.mind_change.model_copy(
                    update={
                        "measurement_discriminator_id": None,
                        "evidence_discriminated": False,
                    }
                ),
                dead_ends=(dead_end,),
            )
        )

    prior = _prior(
        _current(problem=current_problem),
        repository,
        db_path,
    )

    assert tuple(
        (item.tool_id, item.transfer_level)
        for item in prior.recommended_attention_order
    ) == (("inspect_track_demand", "exact"),)
    assert prior.known_dead_ends[0].transfer_level == "compatible"
    assert prior.known_dead_ends[0].may_veto_current_evidence is False


def test_attention_rank_restarts_inside_each_safety_band(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "learning-attention-band-ranks.sqlite"
    repository = EngineeringLearningRepository(db_path)
    current_problem = _problem(99, stable_source_ids=False)
    monkeypatch.setitem(
        service._ATTENTION_TOOLS,
        "inspect_other_band",
        ("other_safe_band", 1),
    )
    for index in (1, 2):
        original = _investigation_experience(
            index,
            problem=_problem(index, stable_source_ids=False),
        )
        assert original.investigation_outcome is not None
        outcome = original.investigation_outcome.model_copy(
            update={
                "tools_inspected": (
                    "inspect_track_demand",
                    "inspect_other_band",
                ),
                "successful_discriminator_ids": (
                    "inspect_track_demand",
                    "inspect_other_band",
                ),
                "requested_measurement_ids": (
                    "inspect_track_demand",
                    "inspect_other_band",
                ),
                "completed_measurement_ids": (
                    "inspect_track_demand",
                    "inspect_other_band",
                ),
            }
        )
        repository.append_experience(
            _rebuilt_record(
                original,
                investigation_outcome=outcome,
                dead_ends=(),
            )
        )

    prior = _prior(
        _current(problem=current_problem),
        repository,
        db_path,
    )

    assert {
        (item.safety_band, item.learned_rank_within_band)
        for item in prior.recommended_attention_order
    } == {
        ("performance_measurement", 1),
        ("other_safe_band", 1),
    }


def test_semantically_same_independent_problem_ids_still_recur(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    first_problem = _problem(1, stable_source_ids=False)
    second_problem = _problem(2, stable_source_ids=False)
    current_problem = _problem(99, stable_source_ids=False)
    assert first_problem.physical_episode_id != second_problem.physical_episode_id
    assert first_problem.source_artifact_ids != second_problem.source_artifact_ids
    assert first_problem.problem_sha256 == second_problem.problem_sha256
    assert second_problem.problem_sha256 == current_problem.problem_sha256
    repository.append_experience(_investigation_experience(1, problem=first_problem))
    repository.append_experience(_investigation_experience(2, problem=second_problem))

    prior = _prior(
        _current(problem=current_problem),
        repository,
        db_path,
    )

    assert prior.recurrence.classification in {
        "strong_recurrence",
        "exact_context_recurrence",
    }
    assert prior.recurrence.counts.independent_episode_count == 2


def test_grouped_learning_uses_worst_qualified_transfer_level(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99, stable_source_ids=False)
    repository.append_experience(
        _investigation_experience(
            1,
            context=_context(1),
            problem=_problem(1, stable_source_ids=False),
        )
    )
    repository.append_experience(
        _investigation_experience(
            2,
            context=_context(2, setup_hash="c" * 64),
            problem=_problem(2, stable_source_ids=False),
        )
    )

    prior = _prior(
        _current(context=_context(99), problem=problem),
        repository,
        db_path,
    )

    assert {item.level for item in prior.context_transfers} == {
        "exact",
        "compatible",
    }
    assert prior.context_transfer_level == "exact"
    assert prior.driver_tendencies[0].transfer_level == "compatible"
    assert prior.known_dead_ends[0].transfer_level == "compatible"
    assert prior.known_dead_ends[0].may_deprioritize_within_band is True
    assert prior.recommended_attention_order[0].transfer_level == "compatible"


def test_duplicate_semantic_dead_ends_in_one_experience_are_projected_once(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-duplicate-dead-end.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99, stable_source_ids=False)
    original = _investigation_experience(1, problem=problem)
    first = original.dead_ends[0]
    duplicate = first.model_copy(update={"dead_end_id": "same-semantic-dead-end"})
    repository.append_experience(
        _rebuilt_record(original, dead_ends=(first, duplicate))
    )

    prior = _prior(_current(problem=problem), repository, db_path)

    assert len(prior.known_dead_ends) == 1
    projected = prior.known_dead_ends[0]
    assert len(projected.experience_ids) == 1
    assert projected.counts.observation_count == 1
    assert projected.counts.independent_episode_count == 1
    assert projected.may_deprioritize_within_band is False


def test_failed_investigations_do_not_teach_attention_order(tmp_path) -> None:
    db_path = tmp_path / "learning-failed-attention.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99)
    for index in (1, 2):
        original = _investigation_experience(index, problem=problem)
        assert original.investigation_outcome is not None
        failed = original.investigation_outcome.model_copy(
            update={
                "successful_discriminator_ids": (),
                "completed_measurement_ids": (),
                "terminal_decision": "no_call",
            }
        )
        repository.append_experience(
            _rebuilt_record(
                original,
                investigation_outcome=failed,
                mind_change=original.mind_change.model_copy(
                    update={
                        "measurement_discriminator_id": None,
                        "evidence_discriminated": False,
                    }
                ),
            )
        )

    prior = _prior(_current(problem=problem), repository, db_path)

    assert prior.useful_prior_investigations == ()
    assert prior.recommended_attention_order == ()
    assert prior.setup_authorized is False
    assert prior.p19_rank_modified is False


def test_abandoned_investigation_is_opened_but_not_resolved_or_timed(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-abandoned-ledger.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99)
    resolved = _investigation_experience(1, problem=problem)
    abandoned = _investigation_experience(2, problem=problem)
    assert abandoned.investigation_outcome is not None
    abandoned_outcome = abandoned.investigation_outcome.model_copy(
        update={"terminal_decision": "abandoned", "laps_consumed": 99}
    )
    repository.append_experience(resolved)
    repository.append_experience(
        _rebuilt_record(abandoned, investigation_outcome=abandoned_outcome)
    )

    prior = _prior(_current(problem=problem), repository, db_path)

    assert prior.ledger.investigations_opened == 2
    assert prior.ledger.investigations_resolved == 1
    assert prior.ledger.laps_consumed_before_resolution == 3
    assert prior.ledger.average_tool_steps_before_resolution == 2.0
    assert prior.ledger.recurrence_resolved_faster_count == 0


def test_historical_retrieval_is_not_recorded_as_match_confirmation() -> None:
    current = _current()
    investigation_id = "investigation-retrieval-only"
    investigation = _crew_investigation(current, investigation_id)
    events = (
        _crew_event(
            investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Historical inspection was requested.",
                tool_id="inspect_time_loss_origin",
                requested_measurement_ids=("inspect_time_loss_origin",),
            ),
        ),
        _crew_event(
            investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Historical reference was inspected.",
                tool_id="inspect_time_loss_origin",
                artifact_ids=("p33ref_" + "1" * 24,),
                completed_measurement_ids=("inspect_time_loss_origin",),
            ),
        ),
        _crew_event(
            investigation_id,
            3,
            "decision_emitted",
            CrewChiefEventPayload(
                message="No discriminating call was available.",
                decision_kind="no_call",
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Acquire a discriminator before making a setup call.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.investigation_outcome is not None
    assert record.investigation_outcome.historical_retrieval_used is True
    assert record.investigation_outcome.historical_match_confirmed is None
    assert "p33ref_" not in " ".join(record.source_artifact_ids)


def test_terminal_builder_records_an_exact_no_finding_tool_dead_end() -> None:
    current = _current()
    investigation_id = "investigation-no-finding-tool"
    investigation = _crew_investigation(current, investigation_id)
    events = (
        _crew_event(
            investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Current inspection was requested.",
                tool_id="inspect_time_loss_origin",
                requested_measurement_ids=("inspect_time_loss_origin",),
            ),
        ),
        _crew_event(
            investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="No canonical artifact matched this inspection.",
                tool_id="inspect_time_loss_origin",
                completed_measurement_ids=("inspect_time_loss_origin",),
            ),
        ),
        _crew_event(
            investigation_id,
            3,
            "decision_emitted",
            CrewChiefEventPayload(
                message="No discriminating call was available.",
                decision_kind="no_call",
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Acquire a discriminator before making a setup call.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    no_finding = tuple(
        item for item in record.dead_ends if item.kind == "repeated_no_finding_tool"
    )
    assert len(no_finding) == 1
    assert no_finding[0].tool_id == "inspect_time_loss_origin"
    assert no_finding[0].current_evidence_may_override is True


def test_unproven_event_artifact_cannot_be_substituted_into_mind_change() -> None:
    current = _current()
    investigation_id = "investigation-unproven-mind-change"
    base = _crew_investigation(current, investigation_id)
    opening = _reasoning(8)
    opening_identity = base.workspace_identity.model_copy(
        update={
            "reasoning_snapshot_sha256": opening.reasoning_snapshot_sha256,
        }
    )
    investigation = CrewChiefInvestigation.model_validate(
        {
            **base.model_dump(mode="python"),
            "workspace_identity": opening_identity,
            "opening_reasoning": opening,
        }
    )
    foreign_artifact = "p19-new-artifact-without-provenance"
    events = (
        _crew_event(
            investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Current P19 inspection was requested.",
                tool_id="inspect_p19_causes",
                requested_measurement_ids=("inspect_p19_causes",),
            ),
        ),
        _crew_event(
            investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Current P19 evidence was inspected.",
                tool_id="inspect_p19_causes",
                artifact_ids=(foreign_artifact,),
                completed_measurement_ids=("inspect_p19_causes",),
            ),
        ),
        _crew_event(
            investigation_id,
            3,
            "decision_emitted",
            CrewChiefEventPayload(
                message="Driver evidence remains the next inspection.",
                decision_kind="driver_focus",
                artifact_ids=(foreign_artifact,),
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="driver_focus",
        title="Inspect driver execution",
        instruction="Inspect current execution before considering setup authority.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.mind_change is None
    assert foreign_artifact not in record.source_artifact_ids
    assert record.investigation_outcome is not None
    assert "withheld" in record.investigation_outcome.strongest_contradiction
    assert record.dead_ends == ()


def test_exact_event_provenance_preserves_the_real_mind_change_artifact() -> None:
    current = _current()
    artifact_id = "p19-new-artifact-with-exact-provenance"
    hydrated = service.CurrentLearningInputs(
        context=current.context,
        problem=current.problem,
        reasoning=current.reasoning,
        source_provenance=(
            *current.source_provenance,
            _provenance(current.context, artifact_id, state="measured"),
        ),
        performance_response=current.performance_response,
        driver_contributions=current.driver_contributions,
    )
    investigation_id = "investigation-exact-mind-change"
    base = _crew_investigation(hydrated, investigation_id)
    opening = _reasoning(8)
    opening_identity = base.workspace_identity.model_copy(
        update={
            "reasoning_snapshot_sha256": opening.reasoning_snapshot_sha256,
        }
    )
    investigation = CrewChiefInvestigation.model_validate(
        {
            **base.model_dump(mode="python"),
            "workspace_identity": opening_identity,
            "opening_reasoning": opening,
        }
    )
    events = (
        _crew_event(
            investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Exact current P19 inspection was requested.",
                tool_id="inspect_p19_causes",
                requested_measurement_ids=("inspect_p19_causes",),
            ),
        ),
        _crew_event(
            investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Exact current P19 evidence was inspected.",
                tool_id="inspect_p19_causes",
                artifact_ids=(artifact_id,),
                completed_measurement_ids=("inspect_p19_causes",),
            ),
        ),
        _crew_event(
            investigation_id,
            3,
            "decision_emitted",
            CrewChiefEventPayload(
                message="Driver evidence remains the next inspection.",
                decision_kind="driver_focus",
                artifact_ids=(artifact_id,),
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="driver_focus",
        title="Inspect driver execution",
        instruction="Inspect current execution before considering setup authority.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=hydrated,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.mind_change is not None
    assert record.mind_change.new_artifact_ids == (artifact_id,)
    assert record.mind_change.new_evidence_states == ("measured",)
    assert record.mind_change.measurement_discriminator_id is None
    assert record.mind_change.evidence_discriminated is False
    assert artifact_id in record.source_artifact_ids
    assert record.dead_ends == ()


def test_new_p19_criterion_without_a_completed_tool_result_cannot_claim_success() -> (
    None
):
    artifact_id = "p19-new-criterion-without-tool-result"
    current, investigation = _transition_case(artifact_id)
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Acquire a typed completed discriminator before assigning cause.",
        authority="context_only",
    )
    terminal = _crew_event(
        investigation.investigation_id,
        1,
        "decision_emitted",
        CrewChiefEventPayload(
            message="No completed tool result exists.",
            decision_kind="no_call",
            artifact_ids=(artifact_id,),
        ),
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=(terminal,),
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.investigation_outcome is not None
    assert record.investigation_outcome.successful_discriminator_ids == ()
    assert record.investigation_outcome.requested_measurement_ids == ()
    assert record.investigation_outcome.completed_measurement_ids == ()
    assert record.mind_change is not None
    assert record.mind_change.measurement_discriminator_id is None
    assert record.mind_change.evidence_discriminated is False


def test_exact_completed_tool_result_can_earn_one_successful_discriminator() -> None:
    artifact_id = "p19-exact-completed-tool-result"
    current, investigation = _transition_case(artifact_id)
    tool_id = "inspect_tire_state"
    events = (
        _crew_event(
            investigation.investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Tire-state inspection requested.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                requested_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Exact measured tire-state evidence attached.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                artifact_ids=(artifact_id,),
                completed_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            3,
            "decision_emitted",
            CrewChiefEventPayload(
                message="The measured result changed the cause ordering.",
                decision_kind="no_call",
                artifact_ids=(artifact_id,),
            ),
            workspace_revision="9" * 64,
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No setup call",
        instruction="Retain the evidence result without creating setup authority.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.investigation_outcome is not None
    assert record.investigation_outcome.tools_inspected == (tool_id,)
    assert record.investigation_outcome.requested_measurement_ids == (tool_id,)
    assert record.investigation_outcome.completed_measurement_ids == (tool_id,)
    assert record.investigation_outcome.successful_discriminator_ids == (tool_id,)
    assert record.mind_change is not None
    assert record.mind_change.measurement_discriminator_id == tool_id
    assert record.mind_change.evidence_discriminated is True


def test_intervening_workspace_rebase_blocks_prior_tool_success_credit() -> None:
    artifact_id = "p19-tool-result-before-rebase"
    current, investigation = _transition_case(artifact_id)
    tool_id = "inspect_tire_state"
    events = (
        _crew_event(
            investigation.investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Tire-state inspection requested.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                requested_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Exact measured tire-state evidence attached.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                artifact_ids=(artifact_id,),
                completed_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            3,
            "workspace_rebased",
            CrewChiefEventPayload(
                message="Authority was explicitly rebased after the tool result.",
                previous_workspace_revision="8" * 64,
                new_workspace_revision="9" * 64,
                previous_authority_revision="a" * 64,
                new_authority_revision="b" * 64,
            ),
            workspace_revision="9" * 64,
        ),
        _crew_event(
            investigation.investigation_id,
            4,
            "decision_emitted",
            CrewChiefEventPayload(
                message="No pre-rebase result may receive learned success.",
                decision_kind="no_call",
                artifact_ids=(artifact_id,),
            ),
            workspace_revision="c" * 64,
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Reinspect under the accepted authority revision.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.investigation_outcome is not None
    assert record.investigation_outcome.requested_measurement_ids == (tool_id,)
    assert record.investigation_outcome.completed_measurement_ids == (tool_id,)
    assert record.investigation_outcome.successful_discriminator_ids == ()
    assert record.mind_change is not None
    assert record.mind_change.measurement_discriminator_id is None
    assert record.mind_change.evidence_discriminated is False


def test_terminal_builder_rejects_an_orphan_completed_tool_result() -> None:
    artifact_id = "p19-orphan-completed-tool-result"
    current, investigation = _transition_case(artifact_id)
    tool_id = "inspect_tire_state"
    events = (
        _crew_event(
            investigation.investigation_id,
            1,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Result has no durable request.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                artifact_ids=(artifact_id,),
                completed_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            2,
            "decision_emitted",
            CrewChiefEventPayload(
                message="No call.",
                decision_kind="no_call",
                artifact_ids=(artifact_id,),
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Do not learn from an orphan completion.",
        authority="context_only",
    )

    with pytest.raises(ValueError, match="no exact preceding measurement request"):
        service.build_investigation_experience(
            investigation=investigation,
            events=events,
            current=current,
            terminal_decision=decision,
            p32_projection_sha256="f" * 64,
        )


def test_mind_change_discriminator_must_bind_the_investigation_success() -> None:
    original = _investigation_experience(91)
    assert original.mind_change is not None
    mismatched = original.mind_change.model_copy(
        update={"measurement_discriminator_id": "inspect_time_loss_origin"}
    )
    with pytest.raises(
        ValidationError,
        match="bind a successful investigation discriminator",
    ):
        _rebuilt_record(original, mind_change=mismatched)

    false_with_identity = original.mind_change.model_copy(
        update={"evidence_discriminated": False}
    )
    with pytest.raises(
        ValidationError,
        match="non-discriminating mind change cannot claim",
    ):
        _rebuilt_record(original, mind_change=false_with_identity)


@pytest.mark.parametrize(
    ("update", "message"),
    (
        (
            {
                "tools_inspected": ("inspect_time_loss_origin",),
                "tool_steps_consumed": 1,
            },
            "successful discriminators must be inspected tools",
        ),
        (
            {"completed_measurement_ids": ("inspect_time_loss_origin",)},
            "successful discriminators must be completed measurements",
        ),
    ),
)
def test_successful_discriminator_requires_the_same_tool_and_completion(
    update: dict[str, object],
    message: str,
) -> None:
    outcome = _investigation_experience(92).investigation_outcome
    assert outcome is not None
    payload = {**outcome.model_dump(mode="python"), **update}
    with pytest.raises(ValidationError, match=message):
        InvestigationPathFact.model_validate(payload)


@pytest.mark.parametrize(
    "state",
    (
        "estimated_proxy",
        "observed_correlation",
        "unavailable",
        "blocked_by_context",
        "needs_confirmation",
    ),
)
def test_nonqualifying_artifact_state_cannot_earn_discriminator_success(
    state: str,
) -> None:
    artifact_id = f"p19-nonqualifying-tool-result-{state}"
    current, investigation = _transition_case(artifact_id, state=state)
    tool_id = "inspect_tire_state"
    events = (
        _crew_event(
            investigation.investigation_id,
            1,
            "tool_invoked",
            CrewChiefEventPayload(
                message="Tire-state inspection requested.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                requested_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            2,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="Nonqualifying evidence state attached.",
                tool_id=tool_id,
                cause_ids=("cause-tire_state",),
                artifact_ids=(artifact_id,),
                completed_measurement_ids=(tool_id,),
            ),
        ),
        _crew_event(
            investigation.investigation_id,
            3,
            "decision_emitted",
            CrewChiefEventPayload(
                message="No qualifying discriminator was established.",
                decision_kind="no_call",
                artifact_ids=(artifact_id,),
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Do not promote weak or blocked evidence into learned success.",
        authority="context_only",
    )

    record = service.build_investigation_experience(
        investigation=investigation,
        events=events,
        current=current,
        terminal_decision=decision,
        p32_projection_sha256="f" * 64,
    )

    assert record.investigation_outcome is not None
    assert record.investigation_outcome.completed_measurement_ids == (tool_id,)
    assert record.investigation_outcome.successful_discriminator_ids == ()
    assert record.mind_change is not None
    assert record.mind_change.measurement_discriminator_id is None
    assert record.mind_change.evidence_discriminated is False


def test_terminal_memory_rejects_a_changed_opening_problem() -> None:
    current = _current()
    opening_problem = ProblemFingerprint.build(
        physical_episode_id="different-opening-episode",
        performance_opportunity_id="different-opening-opportunity",
        phase="entry",
        physical_region="T3-T4",
        time_origin_class="local_loss",
        carry_behavior="no_measured_carry",
        driver_demand_state="unresolved",
        vehicle_response_state="unresolved",
        p20_mechanism_families=("platform",),
        p26_component_families=(),
        traffic_context_state="clear",
        tire_stint_state="short_run",
        objective="race_long_run",
        source_artifact_ids=current.problem.source_artifact_ids,
    )
    investigation_id = "investigation-stale-opening"
    investigation = _crew_investigation(
        current,
        investigation_id,
        opening_problem=opening_problem,
    )
    events = (
        _crew_event(
            investigation_id,
            1,
            "decision_emitted",
            CrewChiefEventPayload(
                message="No call.",
                decision_kind="no_call",
            ),
        ),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Rebase before recording terminal memory.",
        authority="context_only",
    )

    with pytest.raises(ValueError, match="exact immutable opening problem"):
        service.build_investigation_experience(
            investigation=investigation,
            events=events,
            current=current,
            terminal_decision=decision,
            p32_projection_sha256="f" * 64,
        )


def test_controlled_history_navigation_binds_canonical_build_and_session_membership(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "learning-controlled-navigation.sqlite"
    run_repository = RaceLabRepository(db_path)
    learning_repository = EngineeringLearningRepository(db_path)
    workflow = _scored_workflow(
        workflow_id="p33-navigation-workflow",
        source_run_id="history-source",
    )
    stage_run_ids = tuple(workflow.stage_run_ids[stage] for stage in ("A", "B", "A2"))
    overviews = {}
    for index, run_id in enumerate(stage_run_ids, start=1):
        overview = _imported_run(
            run_id,
            cross_weight=50.5 if index == 2 else 50.0,
            started_at=datetime(2026, 8, 14, 18, tzinfo=timezone.utc)
            + timedelta(hours=index),
            file_hash=f"{index}" * 64,
        )
        run_repository.save_import(overview)
        overviews[run_id] = overview

    session = create_session("P33 historical navigation", db_path=db_path)
    for run_id in stage_run_ids:
        assert add_run_to_session(session.session_id, run_id, db_path=db_path)

    compatibility_identity = {
        "driver_user_id": "driver-a",
        "car_path": "nascar-nextgen-chevy",
        "car_version": "2026.08",
        "iracing_build_version": "2026.08.1",
        "track_name": "atlanta",
        "track_configuration_name": "oval",
        "car_configuration_name": "speedway",
    }
    runtime_identities = {
        run_id: {
            "run_id": run_id,
            "compatibility_identity": compatibility_identity,
            "available_telemetry_channels": ["speed_mps", "lap_dist_pct_100"],
            "source": "verified_telemetry_artifact",
        }
        for run_id in stage_run_ids
    }
    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        lambda _run_id: {
            "compatibility_identity": compatibility_identity,
            "compatibility_fingerprint": "a" * 64,
            "source_file_sha256": "b" * 64,
            "cache_version": "p33-navigation-test",
        },
    )
    monkeypatch.setattr(
        "racelab_engine.services.vehicle_systems_service.vehicle_systems_runtime_identity",
        lambda run_id: SimpleNamespace(
            model_dump=lambda **_kwargs: runtime_identities[run_id]
        ),
    )
    stages = {
        stage: {
            "run_id": run_id,
            "compatibility_identity": compatibility_identity,
            "setup_fingerprint": canonical_json_sha256(
                overviews[run_id].setup_snapshot
            ),
            "eligible_lap_numbers": [3, 4, 5],
        }
        for stage, run_id in zip(("A", "B", "A2"), stage_run_ids, strict=True)
    }
    workflow = workflow.model_copy(
        update={
            "reproduction_snapshot": {
                **workflow.reproduction_snapshot,
                "stages": stages,
                "p19_authority_binding": {"session_id": session.session_id},
            }
        }
    )
    closing = _reasoning(9)
    experience = service.build_controlled_workflow_experience(
        workflow,
        controlled_outcome=SimpleNamespace(
            workflow_id=workflow.workflow_id,
            source_run_id=workflow.source_run_id,
            stage_run_ids=stage_run_ids,
            outcome="supported",
            control_direction_result="matched",
            verdict="keep",
            countereffects=(),
            actual_effect_s=-0.05,
            downstream_carry_effect_s=-0.02,
            phase="entry",
        ),
        closing_reasoning=closing,
        p19_reasoning_snapshot_sha256=closing.reasoning_snapshot_sha256,
        repository=run_repository,
    )
    assert {
        item.run_id: item.build_context_sha256 for item in experience.source_provenance
    } == {
        run_id: canonical_json_sha256(runtime_identities[run_id])
        for run_id in stage_run_ids
    }
    learning_repository.append_experience(experience)
    current = service.CurrentLearningInputs(
        context=experience.context,
        problem=experience.problem,
        reasoning=experience.closing_reasoning,
        source_provenance=experience.source_provenance,
        performance_response=None,
        driver_contributions=(),
    )

    available = _prior(current, learning_repository, db_path)

    assert len(available.evidence_references) == 3
    assert {item.state for item in available.evidence_references} == {"available"}
    assert all(not item.blocker_reasons for item in available.evidence_references)

    missing_run_id = stage_run_ids[-1]
    assert remove_run_from_session(session.session_id, missing_run_id, db_path=db_path)
    unavailable = _prior(current, learning_repository, db_path)
    missing = next(
        item
        for item in unavailable.evidence_references
        if item.provenance.run_id == missing_run_id
    )
    assert missing.state == "unavailable"
    assert missing.blocker_reasons == (
        "The historical source session is unavailable or no longer contains this run.",
    )


def test_driver_changed_state_requires_independent_qualified_history(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99)
    repository.append_experience(
        _investigation_experience(
            1,
            problem=_problem(1, stable_source_ids=False),
            driver_tendency="repeatable_tendency",
        )
    )
    repository.append_experience(
        _investigation_experience(
            2,
            problem=_problem(2, stable_source_ids=False),
            driver_tendency="changed_behavior",
        )
    )

    prior = _prior(_current(problem=problem), repository, db_path)

    assert len(prior.driver_tendencies) == 1
    fingerprint = prior.driver_tendencies[0]
    assert fingerprint.state == "changed_behavior"
    assert fingerprint.tendencies[0].tendency == "changed_behavior"
    assert fingerprint.counts.independent_episode_count == 2
    assert fingerprint.transfer_level == "exact"
    assert prior.authority == "attention_only"
    assert prior.setup_authorized is False
    assert prior.p19_rank_modified is False


def test_scenario_c_current_driver_drift_downgrades_old_repeatable_tendency(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-driver-drift.sqlite"
    repository = EngineeringLearningRepository(db_path)
    current_problem = _problem(99, stable_source_ids=False)
    for index in (1, 2):
        repository.append_experience(
            _investigation_experience(
                index,
                context=_context(index),
                problem=_problem(index, stable_source_ids=False),
                driver_tendency="repeatable_tendency",
            )
        )
    current_context = _context(
        99,
        driver_execution_state="materially_changed_release",
    )

    prior = _prior(
        _current(context=current_context, problem=current_problem),
        repository,
        db_path,
    )

    assert {item.level for item in prior.context_transfers} == {"weak"}
    assert len(prior.driver_tendencies) == 1
    fingerprint = prior.driver_tendencies[0]
    assert fingerprint.state == "changed_behavior"
    assert fingerprint.transfer_level == "weak"
    assert fingerprint.tendencies[0].tendency == "changed_behavior"
    assert fingerprint.contradictions == (
        "Current driver execution differs from the qualified historical tendency.",
    )
    assert fingerprint.authority == "driver_context_only"
    assert fingerprint.setup_authorized is False
    assert prior.recommended_attention_order == ()
    assert prior.p19_rank_modified is False


def test_build_and_objective_drift_downgrade_without_leaking_authority(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99)
    repository.append_experience(_investigation_experience(1, problem=problem))

    blocked_context = _context(99, build="2026.09.0")
    blocked = _prior(
        _current(context=blocked_context, problem=problem),
        repository,
        db_path,
    )
    assert blocked.context_transfer_level == "blocked"
    assert blocked.recommended_attention_order == ()
    assert blocked.setup_authorized is False

    objective_context = _context(99, objective="qualifying_peak")
    objective_shift = _prior(
        _current(context=objective_context, problem=problem),
        repository,
        db_path,
    )
    assert objective_shift.context_transfer_level == "weak"
    assert objective_shift.recommended_attention_order == ()
    assert objective_shift.p19_rank_modified is False


def test_relevant_corruption_is_contained_and_stream_head_corruption_blocks(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    problem = _problem(99)
    valid = _investigation_experience(1, problem=problem)
    corrupt = _investigation_experience(2, problem=problem)
    weak_corrupt = _investigation_experience(
        3,
        context=_context(3, objective="qualifying_peak"),
        problem=problem,
    )
    repository.append_experience(valid)
    repository.append_experience(corrupt)
    repository.append_experience(weak_corrupt)
    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER engineering_experiences_no_update")
        connection.execute(
            "UPDATE engineering_experiences SET record_json = '{}' "
            "WHERE experience_id IN (?, ?)",
            (corrupt.experience_id, weak_corrupt.experience_id),
        )
        connection.commit()
    finally:
        connection.close()

    contained = _prior(_current(problem=problem), repository, db_path)
    assert contained.state == "available"
    assert len(contained.useful_prior_investigations) == 1
    assert any(corrupt.experience_id in item for item in contained.blocker_reasons)
    assert any(weak_corrupt.experience_id in item for item in contained.blocker_reasons)

    connection = initialize_database(db_path)
    try:
        connection.execute(
            "UPDATE engineering_experience_stream_head SET head_sha256 = ?",
            ("0" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    blocked = _prior(_current(problem=problem), repository, db_path)
    assert blocked.state == "blocked"
    assert blocked.recommended_attention_order == ()
    assert "stream tail is corrupt" in blocked.blocker_reasons[0]
