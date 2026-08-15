from __future__ import annotations

from datetime import UTC, datetime
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
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import engineering_learning_service as service
from racelab_engine.services.crew_chief_service import (
    _event,
    _learning_capture_blockers,
    _with_learning_capture_blockers,
)
from racelab_engine.storage.crew_chief_repository import CrewChiefRepository
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    LEARNING_CAPTURE_INTEGRITY_BLOCKER,
    EngineeringLearningIntegrityError,
    EngineeringLearningRepository,
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
        selected_scope_hash="1" * 64,
        reasoning_snapshot_sha256="2" * 64,
        p20_state_revision="3" * 64,
        p20_profile_hash="4" * 64,
        p26_graph_version="p26.graph.v1:test",
        p26_knowledge_graph_sha256="5" * 64,
        p26_reasoning_snapshot_sha256="2" * 64,
        p32_projection_sha256="9" * 64,
        run_sentinel_sha256="c" * 64,
        learning_history_revision="a" * 64,
        learning_projection_sha256="b" * 64,
        setup_id=setup_id,
        setup_snapshot_sha256=setup_sha256,
        vehicle_runtime_identity_hash=build_sha256,
        objective_id=EngineeringObjective.RACE_LONG_RUN,
        workspace_revision="8" * 64,
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
