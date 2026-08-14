from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.main import app
from api.routes_crew_chief import OpenInvestigationRequest, RevisionRequest
from racelab_engine.models.crew_chief import (
    ComponentResponseRecord,
    CrewChiefEventPayload,
    CrewChiefInvestigation,
    CrewChiefTerminalDecision,
    CrewChiefWorkspaceIdentity,
    DriverKnowledgeRecord,
    EngineeringObjective,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.engineering_learning import (
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    EngineeringSourceProvenance,
    InvestigationPathFact,
    P19CauseMemory,
    P19ReasoningMemory,
    ProblemFingerprint,
)
from racelab_engine.models.intelligence import EvidenceCitation
from racelab_engine.services.crew_chief_service import (
    _authority_revision,
    _authority_stale_reasons,
    _accepted_workspace_revision,
    _evidence_index,
    _event,
    _sentinel,
    _subgoal,
    _workspace_cache_key,
    build_crew_chief_workspace,
    continue_investigation,
    fold_investigation,
    rebase_investigation,
)
from racelab_engine.services.session_service import create_session, delete_session
from racelab_engine.storage.crew_chief_repository import (
    CrewChiefIntegrityError,
    CrewChiefRepository,
)
from racelab_engine.storage import db as storage_db
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    EngineeringLearningRepository,
)


def _identity() -> CrewChiefWorkspaceIdentity:
    return CrewChiefWorkspaceIdentity(
        run_id="run-1",
        session_id="session-1",
        selected_scope_hash="1" * 64,
        reasoning_snapshot_sha256="2" * 64,
        p20_state_revision="3" * 64,
        p20_profile_hash="4" * 64,
        p26_graph_version="p26.graph.v1:555555555555",
        p26_knowledge_graph_sha256="5" * 64,
        p26_reasoning_snapshot_sha256="2" * 64,
        p32_projection_sha256="9" * 64,
        learning_history_revision="a" * 64,
        learning_projection_sha256="b" * 64,
        setup_id="setup-1",
        setup_snapshot_sha256="6" * 64,
        vehicle_runtime_identity_hash="7" * 64,
        objective_id=EngineeringObjective.RACE_LONG_RUN,
        workspace_revision="8" * 64,
    )


def _seed_run(db_path: str) -> None:
    connection = initialize_database(db_path)
    connection.execute(
        """
        INSERT INTO runs (
          run_id, source_file, import_time, imported_at, session_json
        ) VALUES ('run-1', 'fixture.ibt', '2026-01-01', '2026-01-01', '{}')
        """
    )
    connection.commit()
    connection.close()


def _investigation() -> CrewChiefInvestigation:
    return CrewChiefInvestigation(
        investigation_id="investigation-1",
        workspace_identity=_identity(),
        origin="driver_report",
        objective=EngineeringObjective.RACE_LONG_RUN,
        raw_driver_report="Loose on entry.",
        canonical_problem="loose on entry.",
        opening_reasoning=P19ReasoningMemory(
            reasoning_snapshot_sha256="2" * 64,
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
        ),
        opening_problem=ProblemFingerprint.build(
            phase="entry",
            physical_region="run scope",
            time_origin_class="unavailable",
            carry_behavior="unavailable",
            driver_demand_state="unresolved",
            vehicle_response_state="unresolved",
            traffic_context_state="unresolved",
            tire_stint_state="unresolved",
            objective="race_long_run",
        ),
        opened_at=datetime.now(UTC),
    )


def _terminal_experience(event) -> EngineeringExperienceRecord:
    investigation = _investigation()
    context = EngineeringExperienceContext.build(
        run_id="run-1",
        session_id="session-1",
        driver_id="driver-1",
        car_path="test-car",
        car_version="2026.08",
        iracing_build="2026.08.1",
        track="test-track",
        track_configuration="oval",
        package_type="test-package",
        setup_family=None,
        setup_snapshot_sha256="6" * 64,
        objective="race_long_run",
        physical_scope_sha256="1" * 64,
        phase="entry",
        physical_region="run scope",
        speed_load_band="unresolved",
        fuel_state="unresolved",
        tire_state="unresolved",
        weather_state="unresolved",
        traffic_state="unresolved",
        driver_execution_state="unresolved",
    )
    provenance = EngineeringSourceProvenance.build(
        artifact_id=event.event_id,
        producer_id="p27.crew_chief_event",
        run_id="run-1",
        session_id="session-1",
        setup_id="setup-1",
        setup_snapshot_sha256="6" * 64,
        build_context_sha256="7" * 64,
        phase="entry",
        evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        polarity="neutral",
    )
    return EngineeringExperienceRecord.build(
        source_kind="resolved_investigation",
        source_investigation_id="investigation-1",
        created_at=event.created_at,
        context=context,
        problem=investigation.opening_problem,
        source_p19_reasoning_snapshot_sha256="2" * 64,
        opening_reasoning=investigation.opening_reasoning,
        closing_reasoning=investigation.opening_reasoning,
        investigation_outcome=InvestigationPathFact(
            investigation_id="investigation-1",
            started_at=event.created_at,
            completed_at=event.created_at,
            strongest_contradiction="No qualified discriminator resolved the mechanism.",
            terminal_decision="no_call",
            elapsed_seconds=0.0,
            laps_consumed=0,
            tool_steps_consumed=0,
            driver_questions_consumed=0,
            source_artifact_ids=(event.event_id,),
            historical_retrieval_used=False,
        ),
        source_event_ids=(event.event_id,),
        source_artifact_ids=(event.event_id,),
        source_provenance=(provenance,),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("control_key", "cross_weight_percent"),
        ("current_value", "51.5%"),
        ("proposed_value", "52.0%"),
        ("workflow_id", "workflow-1"),
        ("workflow_revision", "2026-01-01T00:00:00Z"),
    ],
)
def test_non_p19_terminal_decisions_reject_setup_or_workflow_authority(
    field: str, value: str
) -> None:
    payload = {
        "kind": "measurement_mission",
        "title": "Measure first",
        "instruction": "Collect three eligible laps.",
        "authority": "measurement_only",
        field: value,
    }
    with pytest.raises(ValidationError):
        CrewChiefTerminalDecision.model_validate(payload)


def test_controlled_decision_requires_complete_p19_workflow_projection() -> None:
    with pytest.raises(ValidationError, match="exclusive to controlled tests"):
        CrewChiefTerminalDecision(
            kind="measurement_mission",
            title="Measure first",
            instruction="Collect three eligible laps.",
            authority="p19_projection_only",
        )
    with pytest.raises(ValidationError, match="complete P19 projection"):
        CrewChiefTerminalDecision(
            kind="controlled_test",
            title="Controlled test",
            instruction="Use the exact P19 card.",
            authority="p19_projection_only",
        )
    decision = CrewChiefTerminalDecision(
        kind="controlled_test",
        title="Controlled test",
        instruction="Use the exact P19 card.",
        authority="p19_projection_only",
        control_key="cross_weight_percent",
        current_value="51.5%",
        proposed_value="52.0%",
        source_event_ids=("event-1",),
        workflow_id="workflow-1",
        workflow_revision="revision-1",
    )
    assert decision.control_key == "cross_weight_percent"
    with pytest.raises(ValidationError, match="evidence identities must be unique"):
        CrewChiefTerminalDecision.model_validate(
            {
                **decision.model_dump(),
                "source_event_ids": ["event-1", "event-1"],
            }
        )


def test_investigation_opening_truth_is_immutable_and_exact() -> None:
    payload = _investigation().model_dump(mode="json")
    payload["opening_reasoning"]["reasoning_snapshot_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="immutable workspace truth"):
        CrewChiefInvestigation.model_validate(payload)


def test_terminal_event_requires_exact_controlled_workflow_identity() -> None:
    with pytest.raises(ValidationError, match="exact workflow identity"):
        _event(
            "investigation-1",
            1,
            "8" * 64,
            "decision_emitted",
            CrewChiefEventPayload(
                message="Run the exact controlled test.",
                decision_kind="controlled_test",
            ),
        )
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "decision_emitted",
        CrewChiefEventPayload(
            message="Run the exact controlled test.",
            decision_kind="controlled_test",
            workflow_ids=("workflow-1",),
        ),
    )
    assert event.payload.workflow_ids == ("workflow-1",)


@pytest.mark.parametrize(
    "field",
    ("requested_measurement_ids", "completed_measurement_ids"),
)
def test_event_measurement_identities_are_strictly_unique(field: str) -> None:
    with pytest.raises(ValidationError, match="measurement.*unique"):
        CrewChiefEventPayload.model_validate(
            {
                "message": "Duplicate measurement identity.",
                field: ["inspect_track_demand", "inspect_track_demand"],
            }
        )


def test_tool_measurement_completion_requires_an_exact_ordered_request() -> None:
    tool_id = "inspect_track_demand"
    invocation = _event(
        "investigation-1",
        1,
        "8" * 64,
        "tool_invoked",
        CrewChiefEventPayload(
            message="Track-demand inspection requested.",
            tool_id=tool_id,
            requested_measurement_ids=(tool_id,),
        ),
    )
    result = _event(
        "investigation-1",
        2,
        "8" * 64,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="Track-demand inspection completed.",
            tool_id=tool_id,
            completed_measurement_ids=(tool_id,),
        ),
    )

    folded = fold_investigation(_investigation(), (invocation, result), ())
    assert folded.completed_tool_ids == (tool_id,)

    orphan = result.model_copy(update={"sequence": 1})
    with pytest.raises(ValueError, match="no exact preceding measurement request"):
        fold_investigation(_investigation(), (orphan,), ())

    other_result = _event(
        "investigation-1",
        2,
        "8" * 64,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="Different inspection completed.",
            tool_id="inspect_time_loss_origin",
            completed_measurement_ids=("inspect_time_loss_origin",),
        ),
    )
    with pytest.raises(ValueError, match="complete immediately"):
        fold_investigation(_investigation(), (invocation, other_result), ())

    intervening = _event(
        "investigation-1",
        2,
        "8" * 64,
        "driver_question_asked",
        CrewChiefEventPayload(
            message="This event cannot split the tool pair.",
            question_id="question-between-tool-events",
        ),
    )
    delayed_result = result.model_copy(update={"sequence": 3})
    with pytest.raises(ValueError, match="complete immediately"):
        fold_investigation(
            _investigation(),
            (invocation, intervening, delayed_result),
            (),
        )

    drifted_result = result.model_copy(update={"workspace_revision": "9" * 64})
    with pytest.raises(ValueError, match="complete immediately"):
        fold_investigation(_investigation(), (invocation, drifted_result), ())


@pytest.mark.integration
def test_event_store_survives_restart_and_rejects_tampering(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief.sqlite")
    _seed_run(db_path)
    first = CrewChiefRepository(db_path)
    investigation = _investigation()
    first.save_investigation(investigation)
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    first.append_event(event)

    restarted = CrewChiefRepository(db_path)
    assert restarted.get_investigation("investigation-1") == investigation
    assert restarted.list_events("investigation-1") == (event,)

    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE crew_chief_events SET event_hash = ? WHERE event_id = ?",
        ("f" * 64, event.event_id),
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="corrupt"):
        restarted.list_events("investigation-1")


@pytest.mark.integration
def test_terminal_event_and_learning_experience_roll_back_together(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "crew-chief-terminal-atomic.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "decision_emitted",
        CrewChiefEventPayload(
            message="No setup call.",
            decision_kind="no_call",
        ),
    )
    experience = _terminal_experience(event)

    def fail_after_event_append(connection, record):
        raise RuntimeError("injected P33 append failure")

    monkeypatch.setattr(
        EngineeringLearningRepository,
        "append_experience_in_transaction",
        fail_after_event_append,
    )
    with pytest.raises(RuntimeError, match="injected P33 append failure"):
        repository.append_terminal_event_and_experience(event, experience)

    assert repository.list_events("investigation-1") == ()
    connection = initialize_database(db_path)
    try:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM engineering_experiences"
            ).fetchone()[0]
            == 0
        )
        stream = connection.execute(
            "SELECT record_count, head_sha256 FROM engineering_experience_stream_head"
        ).fetchone()
        assert tuple(stream) == (0, None)
    finally:
        connection.close()


def test_terminal_lifecycle_uses_only_the_atomic_event_and_experience_path(
    monkeypatch,
) -> None:
    identity = _identity()
    investigation = _investigation()
    prior_event = _event(
        investigation.investigation_id,
        1,
        identity.workspace_revision,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No call",
        instruction="Keep observing until a qualified discriminator appears.",
        authority="context_only",
    )
    current = SimpleNamespace(
        identity=identity,
        investigation=investigation,
        folded_state=SimpleNamespace(
            status="open",
            pending_driver_question_id=None,
            driver_answers=("The balance changed only in traffic.",),
            last_sequence=1,
        ),
        current_subgoal=None,
        terminal_decision=decision,
        p19_cause_ids=("cause-1",),
        performance_intelligence=SimpleNamespace(projection_sha256="9" * 64),
    )
    learning_inputs = object()
    experience = object()
    captured: dict[str, object] = {}

    class AtomicOnlyRepository:
        def __init__(self, _db_path=None) -> None:
            pass

        def list_events(self, investigation_id: str):
            assert investigation_id == investigation.investigation_id
            return (prior_event,)

        def append_event(self, _event) -> None:
            pytest.fail(
                "terminal events must not be appended outside the P33 transaction"
            )

        def save_effectiveness(self, *_args, **_kwargs) -> None:
            pytest.fail("the dormant effectiveness store must not receive P33 writes")

        def append_terminal_event_and_experience(self, event, record) -> None:
            captured["event"] = event
            captured["experience"] = record

    def build_experience(**kwargs):
        captured["builder"] = kwargs
        return experience

    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_crew_chief_workspace",
        lambda *_args, **_kwargs: current,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.CrewChiefRepository",
        AtomicOnlyRepository,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._learning_inputs_for_workspace",
        lambda *_args, **_kwargs: learning_inputs,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._with_event_source_provenance",
        lambda inputs, *_args, **_kwargs: inputs,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_investigation_experience",
        build_experience,
    )
    cache_clears: list[bool] = []
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.clear_learning_cache",
        lambda: cache_clears.append(True),
    )

    result = continue_investigation(
        identity.run_id,
        investigation.investigation_id,
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
    )

    terminal_event = captured["event"]
    assert terminal_event.event_type == "decision_emitted"
    assert terminal_event.sequence == 2
    assert terminal_event.payload.decision_kind == "no_call"
    assert captured["experience"] is experience
    assert captured["builder"] == {
        "investigation": investigation,
        "events": (prior_event, terminal_event),
        "current": learning_inputs,
        "terminal_decision": decision,
        "p32_projection_sha256": "9" * 64,
    }
    assert cache_clears == [True]
    assert result is current


def test_continue_emits_one_atomic_tool_request_and_completion_pair(
    monkeypatch,
) -> None:
    identity = _identity()
    subgoal = SimpleNamespace(
        selected_tool="inspect_track_demand",
        distinguishes_cause_ids=("cause-1",),
    )
    current = SimpleNamespace(
        identity=identity,
        folded_state=SimpleNamespace(
            status="open",
            pending_driver_question_id=None,
            driver_answers=(),
            last_sequence=4,
        ),
        current_subgoal=subgoal,
    )
    captured: dict[str, object] = {}

    class PairOnlyRepository:
        def __init__(self, _db_path=None) -> None:
            pass

        def append_event(self, _event) -> None:
            pytest.fail("tool request/result must commit as one event unit")

        def append_events(self, events) -> None:
            captured["events"] = events

    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_crew_chief_workspace",
        lambda *_args, **_kwargs: current,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.CrewChiefRepository",
        PairOnlyRepository,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._select_tool_entries",
        lambda *_args, **_kwargs: (
            SimpleNamespace(artifact_id="track-demand-artifact", component_ids=()),
        ),
    )

    result = continue_investigation(
        identity.run_id,
        "investigation-1",
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
    )

    invocation, tool_result = captured["events"]
    assert (invocation.sequence, tool_result.sequence) == (5, 6)
    assert invocation.event_type == "tool_invoked"
    assert invocation.payload.requested_measurement_ids == ("inspect_track_demand",)
    assert invocation.payload.completed_measurement_ids == ()
    assert tool_result.event_type == "tool_result_attached"
    assert tool_result.payload.requested_measurement_ids == ()
    assert tool_result.payload.completed_measurement_ids == ("inspect_track_demand",)
    assert invocation.workspace_revision == tool_result.workspace_revision
    assert result is current


def test_terminal_measurement_decision_requests_the_exact_p19_contract(
    monkeypatch,
) -> None:
    identity = _identity()
    investigation = _investigation()
    decision = CrewChiefTerminalDecision(
        kind="measurement_mission",
        title="Measure first",
        instruction="Run the exact P19 collection mission.",
        authority="measurement_only",
    )
    current = SimpleNamespace(
        identity=identity,
        investigation=investigation,
        folded_state=SimpleNamespace(
            status="open",
            pending_driver_question_id=None,
            driver_answers=("The issue repeats at center.",),
            last_sequence=0,
        ),
        current_subgoal=None,
        terminal_decision=decision,
        p19_mission_contract=SimpleNamespace(contract_id="p19-mission-contract-1"),
        p19_cause_ids=("cause-1",),
        performance_intelligence=SimpleNamespace(projection_sha256="9" * 64),
    )
    captured: dict[str, object] = {}

    class TerminalRepository:
        def __init__(self, _db_path=None) -> None:
            pass

        def list_events(self, _investigation_id: str):
            return ()

        def append_terminal_event_and_experience(self, event, experience) -> None:
            captured["event"] = event
            captured["experience"] = experience

    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_crew_chief_workspace",
        lambda *_args, **_kwargs: current,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.CrewChiefRepository",
        TerminalRepository,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._learning_inputs_for_workspace",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service._with_event_source_provenance",
        lambda inputs, *_args, **_kwargs: inputs,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_investigation_experience",
        lambda **_kwargs: "experience",
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.clear_learning_cache",
        lambda: None,
    )

    result = continue_investigation(
        identity.run_id,
        investigation.investigation_id,
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
    )

    terminal = captured["event"]
    assert terminal.payload.decision_kind == "measurement_mission"
    assert terminal.payload.requested_measurement_ids == ("p19-mission-contract-1",)
    assert terminal.payload.completed_measurement_ids == ()
    assert captured["experience"] == "experience"
    assert result is current


def test_normal_learning_revision_read_checks_metadata_without_loading_payloads(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "learning-head-tail.sqlite")
    _seed_run(db_path)
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "decision_emitted",
        CrewChiefEventPayload(message="No setup call.", decision_kind="no_call"),
    )
    learning = EngineeringLearningRepository(db_path)
    learning.append_experience(_terminal_experience(event))
    connection = initialize_database(db_path)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        state = learning.stream_state(connection=connection)
    finally:
        connection.close()

    assert state.record_count == 1
    normalized = tuple(statement.upper() for statement in statements)
    assert any("COUNT(" in statement for statement in normalized)
    assert not any(
        "SELECT * FROM ENGINEERING_EXPERIENCES" in statement for statement in normalized
    )


def test_event_contract_rejects_semantically_mismatched_payload() -> None:
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    with pytest.raises(ValidationError, match="driver-answer events require"):
        event.__class__.model_validate(
            {**event.model_dump(), "event_type": "driver_answer_recorded"}
        )


def test_investigation_store_rejects_tampered_ordering_metadata(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief-investigation-tamper.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE crew_chief_investigations SET opened_at = ? WHERE investigation_id = ?",
        ("2099-01-01T00:00:00+00:00", "investigation-1"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="corrupt"):
        repository.latest_investigation("run-1", "session-1")


def test_event_store_rejects_tampered_workspace_metadata(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief-event-metadata.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    repository.append_event(event)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE crew_chief_events SET workspace_revision = ? WHERE event_id = ?",
        ("f" * 64, event.event_id),
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="corrupt"):
        repository.list_events("investigation-1")


def test_event_store_rejects_silent_tail_deletion(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief-event-deletion.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    repository.append_event(event)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "DELETE FROM crew_chief_events WHERE event_id = ?", (event.event_id,)
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="stream head is corrupt"):
        repository.list_events("investigation-1")


def test_restart_migration_does_not_silently_repair_tampered_stream_head(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "crew-chief-stream-head-tamper.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    repository.append_event(
        _event(
            "investigation-1",
            1,
            "8" * 64,
            "problem_interpreted",
            CrewChiefEventPayload(message="Driver report normalized."),
        )
    )
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE crew_chief_investigations SET event_count = 0, event_head_hash = NULL"
    )
    connection.commit()
    connection.close()
    storage_db._INITIALIZED_DATABASES.pop(
        str((tmp_path / "crew-chief-stream-head-tamper.sqlite").resolve()), None
    )
    with pytest.raises(CrewChiefIntegrityError, match="stream head is corrupt"):
        CrewChiefRepository(db_path).list_events("investigation-1")


def test_driver_memory_rejects_cross_session_row_relabeling(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief-memory-tamper.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    record = DriverKnowledgeRecord(
        record_id="memory-1",
        investigation_id="investigation-1",
        session_id="session-1",
        complaint_phrase="Loose on entry.",
        recorded_at=datetime.now(UTC),
    )
    repository.save_driver_memory(record)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE crew_chief_driver_memory SET session_id = 'foreign-session'"
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="corrupt"):
        repository.list_driver_memory("foreign-session")


def test_response_atlas_rejects_context_row_relabeling(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief-response-tamper.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    record = ComponentResponseRecord(
        record_id="response-1",
        component_id="weight_distribution",
        control_key="cross_weight_percent",
        direction="increase",
        magnitude_class="adjacent",
        car_path="stockcars chevycamarozl12022",
        car_version="2022",
        iracing_build="2026.08",
        track_package="atlanta oval",
        objective=EngineeringObjective.RACE_LONG_RUN,
        target_phase="center",
        physical_window="phase:center",
        mechanism_result="supported",
        control_response_result="matched",
        policy_verdict="keep",
        source_workflow_id="workflow-1",
        source_run_ids=("run-a", "run-b", "run-1"),
        evidence_identity="a" * 64,
        context_identity="b" * 64,
    )
    repository.save_response_record(record)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE component_response_records SET context_identity = ?",
        ("c" * 64,),
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="corrupt"):
        repository.list_response_records("c" * 64)


def test_terminal_decision_closes_the_folded_investigation() -> None:
    event = _event(
        "investigation-1",
        1,
        "8" * 64,
        "decision_emitted",
        CrewChiefEventPayload(
            message="Bounded measurement decision emitted.",
            decision_kind="measurement_mission",
            requested_measurement_ids=("mission-contract-1",),
        ),
    )
    folded = fold_investigation(_investigation(), (event,), ())
    assert folded.status == "complete"
    assert folded.last_decision_kind == "measurement_mission"


def test_event_store_rejects_gaps_and_cascades_run_deletion(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())
    with pytest.raises(CrewChiefIntegrityError, match="does not follow"):
        repository.append_event(
            _event(
                "investigation-1",
                2,
                "8" * 64,
                "problem_interpreted",
                CrewChiefEventPayload(message="Out of order."),
            )
        )
    connection = initialize_database(db_path)
    connection.execute("DELETE FROM runs WHERE run_id = 'run-1'")
    connection.commit()
    assert (
        connection.execute("SELECT COUNT(*) FROM crew_chief_investigations").fetchone()[
            0
        ]
        == 0
    )
    connection.close()


def test_session_deletion_cascades_crew_chief_state(tmp_path) -> None:
    db_path = str(tmp_path / "crew-chief.sqlite")
    _seed_run(db_path)
    session = create_session("Crew Chief test", db_path)
    identity = _identity().model_copy(update={"session_id": session.session_id})
    investigation = _investigation().model_copy(
        update={
            "investigation_id": "investigation-session-delete",
            "workspace_identity": identity,
        }
    )
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(investigation)
    assert delete_session(session.session_id, db_path) is True
    assert repository.get_investigation(investigation.investigation_id) is None


def test_run_sentinel_rejects_missing_context_instead_of_treating_it_clean() -> None:
    mission = SimpleNamespace(
        required_laps_or_passes=2,
        controlled_variables=("setup",),
        acceptance_thresholds=("repeatable response",),
        stop_rule="Stop on contamination.",
    )
    plan = SimpleNamespace(
        kind="measurement_mission",
        measurement_mission=mission,
        controlled_test=None,
        title="Measure center response",
        instruction="Collect two eligible laps.",
        blocker_reasons=(),
    )
    report = SimpleNamespace(
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Two repeatable laps."),
        data_quality=SimpleNamespace(eligible_lap_ids=("lap-1",), issues=()),
        lap_context=SimpleNamespace(contexts=()),
        smart_guidance=None,
    )
    overview = SimpleNamespace(
        laps=(SimpleNamespace(lap_id="lap-1", lap_number=1, classification_tags=[]),)
    )
    state = _sentinel(SimpleNamespace(report=report), overview)
    assert state.accepted_laps == 0
    assert state.laps[0].status == "rejected"
    assert state.laps[0].reasons == ("exact-lap context coverage is unavailable",)


def test_run_sentinel_uses_exact_a2_stage_and_rejects_reusing_stage_b_run() -> None:
    card = SimpleNamespace(
        do_not_change=("all non-target controls",),
        success_metrics=("repeatable center response",),
        stop_rule="Stop on contamination.",
        stages=(
            SimpleNamespace(stage="A", required_flying_laps=2),
            SimpleNamespace(stage="B", required_flying_laps=2),
            SimpleNamespace(stage="A2", required_flying_laps=3),
        ),
    )
    plan = SimpleNamespace(
        kind="controlled_test",
        measurement_mission=None,
        controlled_test=card,
        title="Restore baseline",
        instruction="Collect Stage A2.",
        blocker_reasons=(),
    )
    report = SimpleNamespace(
        run_id="run-1",
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Baseline restores."),
        data_quality=SimpleNamespace(eligible_lap_ids=("lap-1",), issues=()),
        lap_context=SimpleNamespace(
            contexts=(SimpleNamespace(lap_number=1, blocker_reasons=()),)
        ),
        smart_guidance=SimpleNamespace(
            test_preflight=SimpleNamespace(stage="A2", blocker_reasons=()),
            next_trustworthy_move=SimpleNamespace(
                kind="controlled_test",
                workflow_id="workflow-1",
                workflow_updated_at=datetime.now(UTC),
            ),
        ),
    )
    overview = SimpleNamespace(
        laps=(SimpleNamespace(lap_id="lap-1", lap_number=1, classification_tags=[]),)
    )
    workflow = SimpleNamespace(stage_run_ids={"A": "run-a", "B": "run-1"})
    state = _sentinel(SimpleNamespace(report=report), overview, workflow)
    assert state.stage == "A2"
    assert state.required_laps == 3
    assert state.accepted_laps == 0
    assert state.laps[0].reasons == (
        "current run is already bound to Stage B; Stage A2 requires a new exact run",
    )


def test_one_physical_artifact_merges_memberships_without_multiplying_votes() -> None:
    first = EvidenceCitation(
        citation_id="citation-1",
        event_id="event-1",
        run_id="run-1",
        lap_number=4,
        lap_pct_start=25.0,
        lap_pct_end=30.0,
        workspace="platform",
        phase="center",
        channels=("SteeringWheelAngle",),
        evidence_state=EvidenceState.MEASURED,
        valid_for_tuning=True,
        summary="Steering demand increased.",
    )
    second = first.model_copy(
        update={
            "citation_id": "citation-2",
            "channels": ("SteeringWheelAngle", "YawRate"),
        }
    )
    causes = (
        SimpleNamespace(
            cause_id="cause-a",
            mechanism_keys=("corner_rotation",),
            related_control_keys=("front_arb_diameter",),
            supporting_evidence=(first,),
            contradicting_evidence=(),
        ),
        SimpleNamespace(
            cause_id="cause-b",
            mechanism_keys=("platform_response",),
            related_control_keys=("rf_spring_rate",),
            supporting_evidence=(second,),
            contradicting_evidence=(),
        ),
    )
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot=SimpleNamespace(causes=causes, mechanism_episodes=())
        )
    )
    index = _evidence_index(
        bundle,
        _identity(),
        EngineeringObjective.RACE_LONG_RUN,
        SimpleNamespace(component_states=()),
    )
    assert len(index.entries) == 1
    entry = index.entries[0]
    assert entry.lap_numbers == (4,)
    assert set(entry.mechanism_ids) == {
        "corner_rotation",
        "platform_response",
    }
    assert entry.control_keys == ("front_arb_diameter", "rf_spring_rate")
    assert entry.source_channels == ("SteeringWheelAngle", "YawRate")


def test_learning_evidence_index_exposes_only_available_exact_provenance() -> None:
    source = SimpleNamespace(
        run_id="historical-run",
        session_id="historical-session",
        setup_id="historical-setup",
        setup_snapshot_sha256="a" * 64,
        build_context_sha256="b" * 64,
        lap_numbers=(7,),
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        phase="center",
        source_channels=("speed_mps",),
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        polarity="support",
    )
    learning_prior = SimpleNamespace(
        evidence_references=(
            SimpleNamespace(
                reference_id="p33ref_" + "1" * 24,
                state="available",
                provenance=source,
            ),
            SimpleNamespace(
                reference_id="p33ref_" + "2" * 24,
                state="unavailable",
                provenance=source,
            ),
        )
    )
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot=SimpleNamespace(causes=(), mechanism_episodes=())
        )
    )

    index = _evidence_index(
        bundle,
        _identity(),
        EngineeringObjective.RACE_LONG_RUN,
        SimpleNamespace(component_states=()),
        learning_prior=learning_prior,
    )

    assert tuple(item.artifact_id for item in index.entries) == ("p33ref_" + "1" * 24,)
    assert index.entries[0].producer_id == "p33.engineering_experience"
    assert index.entries[0].source_session_id == "historical-session"
    assert index.entries[0].authority_ceiling == "attention_only"
    assert index.entries[0].typed_artifact is None


def test_investigation_authority_change_requires_explicit_rebase() -> None:
    investigation = _investigation()
    changed = _identity().model_copy(
        update={"p20_state_revision": "9" * 64, "workspace_revision": "a" * 64}
    )
    reasons = _authority_stale_reasons(investigation, (), changed)
    assert reasons and "explicitly rebase" in reasons[0]

    rebase = _event(
        investigation.investigation_id,
        1,
        changed.workspace_revision,
        "workspace_rebased",
        CrewChiefEventPayload(
            message="Explicit rebase.",
            previous_workspace_revision=investigation.workspace_identity.workspace_revision,
            new_workspace_revision=changed.workspace_revision,
            previous_authority_revision=_authority_revision(
                investigation.workspace_identity
            ),
            new_authority_revision=_authority_revision(changed),
        ),
    )
    assert _authority_stale_reasons(investigation, (rebase,), changed) == ()
    assert _accepted_workspace_revision(investigation, ()) == (
        investigation.workspace_identity.workspace_revision
    )
    assert _accepted_workspace_revision(investigation, (rebase,)) == (
        changed.workspace_revision
    )


def test_learning_revision_refreshes_workspace_without_staling_p19_authority() -> None:
    investigation = _investigation()
    changed = _identity().model_copy(
        update={
            "learning_history_revision": "c" * 64,
            "learning_projection_sha256": "d" * 64,
            "workspace_revision": "e" * 64,
        }
    )

    assert _authority_revision(changed) == _authority_revision(
        investigation.workspace_identity
    )
    assert _authority_stale_reasons(investigation, (), changed) == ()
    assert _workspace_cache_key(changed, "learning.sqlite") != _workspace_cache_key(
        investigation.workspace_identity,
        "learning.sqlite",
    )


def _planner_fixture():
    cause = SimpleNamespace(
        cause_id="cause-1",
        status="possible",
        ordinal_rank=1,
        contradicting_evidence=(),
    )
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            data_quality=SimpleNamespace(status="ready"),
            lap_context=SimpleNamespace(
                contexts=(SimpleNamespace(blocker_reasons=()),)
            ),
            reasoning_snapshot=SimpleNamespace(
                causes=(cause,),
                mechanism_episodes=(),
            ),
        )
    )
    folded = SimpleNamespace(
        investigation_id="investigation-1",
        status="open",
        completed_tool_ids=("inspect_data_quality", "inspect_lap_context"),
        driver_answers=("repeatable",),
        objective=EngineeringObjective.RACE_LONG_RUN,
        hypotheses=(
            SimpleNamespace(
                cause_id="cause-1",
                progress="inspection_pending",
            ),
        ),
    )
    p26 = SimpleNamespace(component_states=(), leading_component_ids=())
    return bundle, folded, p26


def test_learning_prior_can_reorder_only_within_the_existing_safety_band() -> None:
    bundle, folded, p26 = _planner_fixture()
    prior = SimpleNamespace(
        recommended_attention_order=(
            SimpleNamespace(
                tool_id="inspect_track_demand",
                safety_band="performance_measurement",
                baseline_rank_within_band=7,
                learned_rank_within_band=1,
                reason="This inspection resolved matching prior cases sooner.",
                transfer_level="exact",
                investigation_count=3,
                session_count=2,
                independent_workflow_count=0,
            ),
            SimpleNamespace(
                tool_id="inspect_p19_causes",
                safety_band="contradiction",
                baseline_rank_within_band=1,
                learned_rank_within_band=1,
                reason="Contradiction review was previously useful.",
                transfer_level="exact",
                investigation_count=4,
                session_count=3,
                independent_workflow_count=1,
            ),
        )
    )

    subgoal = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)

    assert subgoal.selected_tool == "inspect_track_demand"
    assert "WHY THIS IS EARLIER" in subgoal.why_this_tool
    assert "P19 cause order and setup authority are unchanged" in subgoal.why_this_tool


def test_learning_prior_cannot_relabel_a_tool_into_an_earlier_safety_band() -> None:
    bundle, folded, p26 = _planner_fixture()
    prior = SimpleNamespace(
        recommended_attention_order=(
            SimpleNamespace(
                tool_id="inspect_p19_causes",
                safety_band="performance_measurement",
                baseline_rank_within_band=1,
                learned_rank_within_band=1,
                reason="Hostile cross-band promotion.",
                transfer_level="exact",
                investigation_count=9,
                session_count=9,
                independent_workflow_count=9,
            ),
        )
    )

    subgoal = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)

    assert subgoal.selected_tool == "inspect_lap_time_opportunity"
    assert "WHY THIS IS EARLIER" not in subgoal.why_this_tool


def test_known_dead_end_cannot_veto_new_live_tool_evidence() -> None:
    bundle, folded, p26 = _planner_fixture()
    folded.completed_tool_ids = (
        *folded.completed_tool_ids,
        "inspect_lap_time_opportunity",
    )
    prior = SimpleNamespace(
        recommended_attention_order=(),
        known_dead_ends=(
            SimpleNamespace(
                tool_id="inspect_time_loss_origin",
                may_deprioritize_within_band=True,
                may_veto_current_evidence=False,
            ),
        ),
    )

    subgoal = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)

    assert subgoal.selected_tool == "inspect_time_loss_origin"
    assert "WHY THIS IS EARLIER" not in subgoal.why_this_tool


def test_workspace_cache_is_namespaced_by_database_identity(tmp_path) -> None:
    identity = _identity()
    first = _workspace_cache_key(identity, tmp_path / "first.sqlite")
    second = _workspace_cache_key(identity, tmp_path / "second.sqlite")
    assert first != second
    assert first[1] == second[1] == identity.workspace_revision


def test_continue_cannot_bypass_a_pending_driver_question(monkeypatch) -> None:
    current = SimpleNamespace(
        identity=SimpleNamespace(workspace_revision="8" * 64),
        folded_state=SimpleNamespace(
            status="open", pending_driver_question_id="question-1", last_sequence=8
        ),
        current_subgoal=None,
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_crew_chief_workspace",
        lambda *args, **kwargs: current,
    )
    with pytest.raises(ValueError, match="driver question is pending"):
        continue_investigation(
            "run-1",
            "investigation-1",
            session_id="session-1",
            expected_workspace_revision="8" * 64,
        )


def test_rebase_rejects_a_foreign_stale_revision(monkeypatch) -> None:
    current = SimpleNamespace(
        identity=_identity(),
        investigation=_investigation(),
        folded_state=SimpleNamespace(status="stale", last_sequence=2),
    )
    monkeypatch.setattr(
        "racelab_engine.services.crew_chief_service.build_crew_chief_workspace",
        lambda *args, **kwargs: current,
    )
    with pytest.raises(ValueError, match="rebase revision is stale"):
        rebase_investigation(
            "run-1",
            "investigation-1",
            session_id="session-1",
            stale_workspace_revision="f" * 64,
        )


@pytest.mark.parametrize(
    "request_type,payload",
    [
        (
            RevisionRequest,
            {"session_id": "session-1", "expected_workspace_revision": "8" * 64},
        ),
        (
            OpenInvestigationRequest,
            {
                "session_id": "session-1",
                "driver_report": "Loose on entry.",
                "expected_workspace_revision": "8" * 64,
            },
        ),
    ],
)
def test_public_mutation_bodies_reject_client_authority_fields(
    request_type: type, payload: dict[str, object]
) -> None:
    for field in (
        "setup_action",
        "control_key",
        "proposed_value",
        "policy_verdict",
        "stop_testing",
    ):
        with pytest.raises(ValidationError):
            request_type.model_validate({**payload, field: "hostile"})


def test_openapi_exposes_bounded_workspace_operations_only() -> None:
    paths = app.openapi()["paths"]
    expected = {
        "/api/runs/{run_id}/crew-chief-workspace",
        "/api/runs/{run_id}/crew-chief-investigations",
        "/api/runs/{run_id}/crew-chief-investigations/{investigation_id}/continue",
        "/api/runs/{run_id}/crew-chief-investigations/{investigation_id}/driver-answer",
        "/api/runs/{run_id}/crew-chief-investigations/{investigation_id}/objective",
        "/api/runs/{run_id}/crew-chief-investigations/{investigation_id}/abandon",
        "/api/runs/{run_id}/crew-chief-investigations/{investigation_id}/rebase",
    }
    assert expected <= set(paths)
    assert all(
        "recommend" not in path and "setup-action" not in path for path in expected
    )
    for path in expected:
        for operation in paths[path].values():
            if not isinstance(operation, dict) or "parameters" not in operation:
                continue
            for parameter in operation["parameters"]:
                if parameter["in"] == "path":
                    assert parameter["schema"]["minLength"] == 1
                    assert parameter["schema"]["maxLength"] == 160


def test_real_next_gen_atlanta_workspace_preserves_authority_boundary(
    monkeypatch,
) -> None:
    run_id = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"
    session_id = "session_ed52db305244"
    from racelab_engine.storage.repository import RaceLabRepository

    if RaceLabRepository().get_overview(run_id) is None:
        pytest.skip("Persisted real Next Gen Atlanta fixture is unavailable")

    def reject_workspace_get_write(*_args, **_kwargs) -> None:
        pytest.fail("Crew Chief workspace GET must remain read-only")

    for method_name in (
        "save_investigation",
        "append_event",
        "append_terminal_event_and_experience",
        "save_objective",
        "save_success_contract",
        "save_response_record",
        "save_driver_memory",
        "save_effectiveness",
    ):
        monkeypatch.setattr(
            CrewChiefRepository,
            method_name,
            reject_workspace_get_write,
        )
    monkeypatch.setattr(
        EngineeringLearningRepository,
        "append_experience",
        reject_workspace_get_write,
    )
    monkeypatch.setattr(
        EngineeringLearningRepository,
        "append_experience_in_transaction",
        reject_workspace_get_write,
    )
    workspace = build_crew_chief_workspace(run_id, session_id=session_id)
    performance = workspace.performance_intelligence
    story = performance.speed_story
    assert workspace.identity.reasoning_snapshot_sha256 == (
        workspace.identity.p26_reasoning_snapshot_sha256
    )
    assert workspace.identity.setup_id
    assert workspace.generative_boundary.enabled is False
    assert workspace.adaptive_research.state == "data_locked"
    assert story.observed_difference_s is not None
    assert story.observed_difference_s > 0.0
    assert story.observed_direction == "loss"
    assert story.attribution_state == "blocked_by_traffic"
    assert "traffic" in story.strongest_contradiction.casefold()
    assert "100.0%" in story.strongest_contradiction
    assert "withheld" in story.systems.casefold()
    assert performance.component_influences == ()
    assert all(
        opportunity.component_candidates == ()
        for opportunity in performance.opportunity_map.opportunities
    )
    assert performance.setup_authorized is False
    assert performance.track_demand.traffic_exposure_fraction == pytest.approx(1.0)
    assert performance.track_demand.disturbance_exposure_fraction is not None
    assert performance.track_demand.disturbance_exposure_fraction < 0.25
    assert performance.track_demand.limiter_zones == ()
    if workspace.terminal_decision.kind != "controlled_test":
        assert workspace.terminal_decision.control_key is None
        assert workspace.terminal_decision.proposed_value is None
