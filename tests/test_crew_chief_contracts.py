from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.main import app
from api.routes_crew_chief import OpenInvestigationRequest, RevisionRequest
from racelab_engine.identity import canonical_json_sha256
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
from racelab_engine.models.investigation_adaptation import (
    InvestigationDecision,
    InvestigationImprovementReadiness,
    P19CauseState,
)
from racelab_engine.services import crew_chief_service
from racelab_engine.services.crew_chief_service import (
    _authority_revision,
    _authority_stale_reasons,
    _canonical_p34_outcome_pair,
    _accepted_workspace_revision,
    _evidence_index,
    _event,
    _freeze_p34_pair_for_workspace,
    _memory_shadow_from_baseline,
    _memory_shadow_subgoal,
    _p34_decisions_for_workspace,
    _p34_live_eligible_tool_ids,
    _p34_negative_control_evidence,
    _p34_projection_for_identity,
    _p34_restart_context,
    _production_subgoal_from_pair,
    _sentinel,
    _subgoal,
    _workspace_cache_key,
    build_crew_chief_workspace,
    continue_investigation,
    fold_investigation,
    rebase_investigation,
)
from racelab_engine.services.investigation_adaptation_service import (
    baseline_investigation_policy,
    build_p34_negative_control_result,
    build_paired_investigation_decision,
    memory_shadow_investigation_policy,
    p34_activation_protocol,
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
from racelab_engine.storage.investigation_adaptation_repository import (
    InvestigationAdaptationRepository,
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
        p35_assessment_sha256="d" * 64,
        run_sentinel_sha256="c" * 64,
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


def _clear_lap_context(lap_number: int) -> SimpleNamespace:
    return SimpleNamespace(
        lap_number=lap_number,
        blocker_reasons=(),
        proximity_state="no_nearby_car_reported",
        proximity_coverage_fraction=1.0,
        nearby_traffic_exposure_fraction=0.0,
    )


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
        setup_effect_id="add_crossweight_small",
        experiment_factor_id="factor:crossweight",
        direction_sign=1,
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


def test_p34_prediction_pair_event_identity_is_complete_and_executable_only() -> None:
    with pytest.raises(ValidationError, match="prediction-pair identity.*complete"):
        CrewChiefEventPayload(
            message="Incomplete P34 prediction receipt.",
            adaptation_prediction_pair_id="p34pair_" + "a" * 24,
        )
    with pytest.raises(ValidationError, match="exclusive to executable Crew events"):
        _event(
            "investigation-1",
            1,
            "8" * 64,
            "objective_selected",
            CrewChiefEventPayload(
                message="Objective changed.",
                objective=EngineeringObjective.RACE_LONG_RUN,
                adaptation_prediction_pair_id="p34pair_" + "a" * 24,
                adaptation_prediction_pair_sha256="b" * 64,
                adaptation_prediction_source_snapshot_sha256="c" * 64,
            ),
        )
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


def test_pre_p35_runtime_identity_payload_restarts_without_authority_or_event_drift(
    tmp_path,
) -> None:
    identity = _identity()
    legacy_identity = identity.model_dump(mode="json")
    for field_name in (
        "p35_assessment_sha256",
        "p20_projection_sha256",
        "vehicle_runtime_identity",
    ):
        legacy_identity.pop(field_name, None)
    restored_identity = CrewChiefWorkspaceIdentity.model_validate(legacy_identity)
    assert restored_identity.vehicle_runtime_identity is None
    assert restored_identity.p35_assessment_sha256 is None
    assert restored_identity.p20_projection_sha256 is None
    assert restored_identity.authority_revision == identity.authority_revision
    assert identity.model_copy(
        update={"p20_projection_sha256": "e" * 64}
    ).authority_revision == identity.authority_revision

    investigation = _investigation()
    legacy_investigation = investigation.model_dump(mode="json")
    for field_name in (
        "p35_assessment_sha256",
        "p20_projection_sha256",
        "vehicle_runtime_identity",
    ):
        legacy_investigation["workspace_identity"].pop(field_name, None)
    restored_investigation = CrewChiefInvestigation.model_validate(
        legacy_investigation
    )
    db_path = str(tmp_path / "pre-p35-crew-restart.sqlite")
    _seed_run(db_path)
    connection = initialize_database(db_path)
    connection.execute(
        """
        INSERT INTO crew_chief_investigations (
          investigation_id, run_id, session_id, workspace_revision,
          status, opened_at, investigation_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            restored_investigation.investigation_id,
            restored_identity.run_id,
            restored_identity.session_id,
            restored_identity.workspace_revision,
            restored_investigation.status,
            restored_investigation.opened_at.isoformat(),
            json.dumps(legacy_investigation),
        ),
    )
    connection.commit()
    connection.close()
    event = _event(
        restored_investigation.investigation_id,
        1,
        restored_identity.workspace_revision,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    event_hash = event.event_hash
    repository = CrewChiefRepository(db_path)
    repository.append_event(event)
    restarted_investigation = CrewChiefRepository(db_path).get_investigation(
        restored_investigation.investigation_id
    )
    restarted_events = CrewChiefRepository(db_path).list_events(
        restored_investigation.investigation_id
    )

    assert restarted_investigation is not None
    assert restarted_investigation.workspace_identity.authority_revision == (
        identity.authority_revision
    )
    assert restarted_events[0].event_hash == event_hash
    folded = fold_investigation(
        restarted_investigation,
        restarted_events,
        (),
    )

    assert folded.last_sequence == 1
    assert event.event_hash == event_hash


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
    tmp_path,
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

        def append_terminal_event_and_experience(
            self, event, record, **_capture
        ):
            captured["event"] = event
            captured["experience"] = record
            return event

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
        db_path=tmp_path / "terminal-atomic.sqlite",
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
    tmp_path,
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
        db_path=tmp_path / "tool-pair.sqlite",
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
    tmp_path,
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

        def append_terminal_event_and_experience(
            self, event, experience, **_capture
        ):
            captured["event"] = event
            captured["experience"] = experience
            return event

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
        db_path=tmp_path / "terminal-measurement.sqlite",
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
    assert state.context_cleared_laps == 0
    assert state.mission_accepted_lap_ids == ()
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
            contexts=(_clear_lap_context(1),)
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
    assert state.context_cleared_laps == 0
    assert state.mission_accepted_lap_ids == ()
    assert state.laps[0].reasons == (
        "current run is already bound to Stage B; Stage A2 requires a new exact run",
    )


def test_run_sentinel_never_promotes_context_screening_to_mission_acceptance() -> None:
    contract = SimpleNamespace(
        contract_id="mission-contract-1",
        contract_sha256="1" * 64,
        required_laps=3,
        required_channels=("speed_mph", "throttle_pct"),
        session_run_ids=("run-1",),
        setup_sha256="2" * 64,
        compatibility_fingerprint="3" * 64,
    )
    plan = SimpleNamespace(
        kind="measurement_mission",
        measurement_mission=SimpleNamespace(
            controlled_variables=("setup",),
            acceptance_thresholds=("position-aligned response",),
            stop_rule="Stop on contamination.",
        ),
        controlled_test=None,
        mission_contract=contract,
        title="Record declared channels",
        instruction="Collect three exact passes.",
        blocker_reasons=(),
    )
    laps = tuple(
        SimpleNamespace(
            lap_id=f"run-1:{lap_number}",
            lap_number=lap_number,
            classification_tags=[],
        )
        for lap_number in (1, 2, 3)
    )
    report = SimpleNamespace(
        run_id="run-1",
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Three contract-qualified passes."),
        data_quality=SimpleNamespace(
            eligible_lap_ids=tuple(lap.lap_id for lap in laps), issues=()
        ),
        lap_context=SimpleNamespace(
            contexts=tuple(
                _clear_lap_context(lap.lap_number)
                for lap in laps
            )
        ),
        smart_guidance=None,
    )

    state = _sentinel(SimpleNamespace(report=report), SimpleNamespace(laps=laps))

    assert state.context_cleared_laps == 3
    assert state.mission_accepted_lap_ids == ()
    assert state.measurement_attempt_ids == ()
    assert state.mission_acceptance_basis == "unbound"
    assert state.collection_complete is False
    assert state.mission_state == "collecting"
    assert all(lap.status == "context_cleared" for lap in state.laps)
    assert "screening evidence only" in " ".join(state.blocker_reasons)


def test_run_sentinel_accepts_only_an_exact_channel_complete_measurement_attempt() -> None:
    contract = SimpleNamespace(
        contract_id="mission-contract-1",
        contract_sha256="1" * 64,
        required_laps=3,
        required_channels=("speed_mph", "throttle_pct"),
        session_run_ids=("run-1",),
        setup_sha256="2" * 64,
        compatibility_fingerprint="3" * 64,
    )
    plan = SimpleNamespace(
        kind="measurement_mission",
        measurement_mission=SimpleNamespace(
            controlled_variables=("setup",),
            acceptance_thresholds=("position-aligned response",),
            stop_rule="Stop on contamination.",
        ),
        controlled_test=None,
        mission_contract=contract,
        title="Record declared channels",
        instruction="Collect three exact passes.",
        blocker_reasons=(),
    )
    laps = tuple(
        SimpleNamespace(
            lap_id=f"run-1:{lap_number}",
            lap_number=lap_number,
            classification_tags=[],
        )
        for lap_number in (1, 2, 3)
    )
    report = SimpleNamespace(
        run_id="run-1",
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Three contract-qualified passes."),
        data_quality=SimpleNamespace(
            eligible_lap_ids=tuple(lap.lap_id for lap in laps), issues=()
        ),
        lap_context=SimpleNamespace(
            contexts=tuple(
                _clear_lap_context(lap.lap_number)
                for lap in laps
            )
        ),
        smart_guidance=None,
    )
    attempt = SimpleNamespace(
        attempt_id="attempt-1",
        contract_id=contract.contract_id,
        contract_sha256=contract.contract_sha256,
        run_id="run-1",
        setup_sha256=contract.setup_sha256,
        compatibility_fingerprint=contract.compatibility_fingerprint,
        outcome_authority="client_attested",
        collection_authority="unverified",
        outcome="completed_clean",
        eligible_lap_ids=tuple(lap.lap_id for lap in laps),
        observed_channels=("speed_mph", "throttle_pct"),
        integrity_blockers=(),
    )

    client_state = _sentinel(
        SimpleNamespace(report=report),
        SimpleNamespace(laps=laps),
        measurement_attempts=(attempt,),
    )
    assert client_state.mission_accepted_lap_ids == ()
    assert client_state.collection_complete is False

    attempt.collection_authority = "server_verified"

    state = _sentinel(
        SimpleNamespace(report=report),
        SimpleNamespace(laps=laps),
        measurement_attempts=(attempt,),
    )

    assert state.context_cleared_laps == 3
    assert state.mission_accepted_lap_ids == ("run-1:1", "run-1:2", "run-1:3")
    assert state.measurement_attempt_ids == ("attempt-1",)
    assert state.mission_acceptance_basis == "p19_measurement_attempt"
    assert state.collection_complete is True
    assert state.mission_state == "collection_complete"

    report.lap_context = SimpleNamespace(
        contexts=tuple(
            SimpleNamespace(
                lap_number=lap.lap_number,
                blocker_reasons=(),
                proximity_state="nearby_car_ahead",
                proximity_coverage_fraction=1.0,
                nearby_traffic_exposure_fraction=1.0,
            )
            for lap in laps
        )
    )
    traffic_blocked = _sentinel(
        SimpleNamespace(report=report),
        SimpleNamespace(laps=laps),
        measurement_attempts=(attempt,),
    )
    assert traffic_blocked.context_cleared_laps == 0
    assert traffic_blocked.mission_accepted_lap_ids == ()
    assert traffic_blocked.collection_complete is False


def test_run_sentinel_withholds_attempt_missing_a_required_channel() -> None:
    contract = SimpleNamespace(
        contract_id="mission-contract-1",
        contract_sha256="1" * 64,
        required_laps=1,
        required_channels=("speed_mph", "throttle_pct"),
        session_run_ids=("run-1",),
        setup_sha256="2" * 64,
        compatibility_fingerprint="3" * 64,
    )
    plan = SimpleNamespace(
        kind="discriminator",
        measurement_mission=SimpleNamespace(
            controlled_variables=("setup",),
            acceptance_thresholds=("position-aligned response",),
            stop_rule="Stop on contamination.",
        ),
        controlled_test=None,
        mission_contract=contract,
        title="Resolve the discriminator",
        instruction="Record the declared channels.",
        blocker_reasons=(),
    )
    lap = SimpleNamespace(lap_id="run-1:1", lap_number=1, classification_tags=[])
    report = SimpleNamespace(
        run_id="run-1",
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Resolve the discriminator."),
        data_quality=SimpleNamespace(eligible_lap_ids=(lap.lap_id,), issues=()),
        lap_context=SimpleNamespace(
            contexts=(_clear_lap_context(1),)
        ),
        smart_guidance=None,
    )
    attempt = SimpleNamespace(
        attempt_id="attempt-sparse",
        contract_id=contract.contract_id,
        contract_sha256=contract.contract_sha256,
        run_id="run-1",
        setup_sha256=contract.setup_sha256,
        compatibility_fingerprint=contract.compatibility_fingerprint,
        outcome_authority="client_attested",
        collection_authority="server_verified",
        outcome="no_signal",
        eligible_lap_ids=(lap.lap_id,),
        observed_channels=("speed_mph",),
        integrity_blockers=(),
    )

    state = _sentinel(
        SimpleNamespace(report=report),
        SimpleNamespace(laps=(lap,)),
        measurement_attempts=(attempt,),
    )

    assert state.context_cleared_laps == 1
    assert state.mission_accepted_lap_ids == ()
    assert state.collection_complete is False
    assert state.mission_state == "collecting"


def test_run_sentinel_accepts_only_the_exact_bound_controlled_stage_cohort() -> None:
    card = SimpleNamespace(
        do_not_change=("all non-target controls",),
        success_metrics=("repeatable center response",),
        stop_rule="Stop on contamination.",
        stages=(
            SimpleNamespace(stage="A", required_flying_laps=1),
            SimpleNamespace(stage="B", required_flying_laps=1),
            SimpleNamespace(stage="A2", required_flying_laps=1),
        ),
    )
    plan = SimpleNamespace(
        kind="controlled_test",
        measurement_mission=None,
        controlled_test=card,
        mission_contract=None,
        title="Record baseline A",
        instruction="Bind one clean baseline lap.",
        blocker_reasons=(),
    )
    report = SimpleNamespace(
        run_id="run-1",
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="One exact Stage A lap."),
        data_quality=SimpleNamespace(
            eligible_lap_ids=("run-1:1", "run-1:2", "run-1:3"), issues=()
        ),
        lap_context=SimpleNamespace(
            contexts=tuple(
                _clear_lap_context(lap_number)
                for lap_number in (1, 2, 3)
            )
        ),
        smart_guidance=SimpleNamespace(
            test_preflight=SimpleNamespace(stage="A", blocker_reasons=()),
            next_trustworthy_move=SimpleNamespace(
                kind="controlled_test",
                workflow_id="workflow-1",
                workflow_updated_at=datetime.now(UTC),
            ),
        ),
    )
    laps = tuple(
        SimpleNamespace(
            lap_id=f"run-1:{lap_number}",
            lap_number=lap_number,
            classification_tags=[],
        )
        for lap_number in (1, 2, 3)
    )
    workflow = SimpleNamespace(
        status="a_recorded",
        stage_run_ids={"A": "run-1", "B": None, "A2": None},
        stage_eligible_lap_numbers={"A": (2,)},
    )

    state = _sentinel(
        SimpleNamespace(report=report), SimpleNamespace(laps=laps), workflow
    )

    assert state.context_cleared_laps == 3
    assert state.mission_acceptance_basis == "controlled_workflow_stage"
    assert state.mission_accepted_lap_ids == ("run-1:2",)
    assert state.measurement_attempt_ids == ()
    assert state.collection_complete is True
    assert state.mission_state == "collection_complete"

    blocked_report = SimpleNamespace(**vars(report))
    blocked_report.lap_context = SimpleNamespace(
        contexts=tuple(
            SimpleNamespace(
                lap_number=lap_number,
                blocker_reasons=("traffic blocks the recorded cohort",)
                if lap_number == 2
                else (),
            )
            for lap_number in (1, 2, 3)
        )
    )
    blocked_state = _sentinel(
        SimpleNamespace(report=blocked_report), SimpleNamespace(laps=laps), workflow
    )
    assert blocked_state.mission_acceptance_basis == "unbound"
    assert blocked_state.mission_accepted_lap_ids == ()
    assert blocked_state.collection_complete is False


def test_run_sentinel_awaits_score_after_the_exact_a2_cohort_is_recorded() -> None:
    card = SimpleNamespace(
        do_not_change=("all non-target controls",),
        success_metrics=("repeatable center response",),
        stop_rule="Stop on contamination.",
        stages=tuple(
            SimpleNamespace(stage=stage, required_flying_laps=1)
            for stage in ("A", "B", "A2")
        ),
    )
    plan = SimpleNamespace(
        kind="controlled_test",
        measurement_mission=None,
        controlled_test=card,
        mission_contract=None,
        title="Score the controlled test",
        instruction="Review the exact A/B/A2 result.",
        blocker_reasons=(),
    )
    report = SimpleNamespace(
        run_id="run-a2",
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Score one exact A/B/A2 workflow."),
        data_quality=SimpleNamespace(eligible_lap_ids=("run-a2:7",), issues=()),
        lap_context=SimpleNamespace(
            contexts=(_clear_lap_context(7),)
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
    workflow = SimpleNamespace(
        status="a2_recorded",
        stage_run_ids={"A": "run-a", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={"A": (1,), "B": (4,), "A2": (7,)},
    )
    lap = SimpleNamespace(
        lap_id="run-a2:7", lap_number=7, classification_tags=[]
    )

    state = _sentinel(
        SimpleNamespace(report=report), SimpleNamespace(laps=(lap,)), workflow
    )

    assert state.mission_state == "awaiting_p19_score"
    assert state.stage == "awaiting_score"
    assert state.collection_complete is True
    assert state.mission_accepted_lap_ids == ("run-a2:7",)


def test_sentinel_progress_refreshes_workspace_without_changing_p19_authority() -> None:
    first = _identity()
    second = first.model_copy(
        update={
            "run_sentinel_sha256": "d" * 64,
            "workspace_revision": "e" * 64,
        }
    )

    assert _authority_revision(first) == _authority_revision(second)
    assert _workspace_cache_key(first, "crew.sqlite") != _workspace_cache_key(
        second, "crew.sqlite"
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
            adaptation_rebase_source_snapshot_sha256="d" * 64,
        ),
    )
    assert _authority_stale_reasons(investigation, (rebase,), changed) == ()
    assert _accepted_workspace_revision(investigation, ()) == (
        investigation.workspace_identity.workspace_revision
    )
    assert _accepted_workspace_revision(investigation, (rebase,)) == (
        changed.workspace_revision
    )


@pytest.mark.parametrize(
    ("identity_field", "replacement"),
    [
        ("setup_snapshot_sha256", "d" * 64),
        ("vehicle_runtime_identity_hash", "e" * 64),
    ],
)
def test_applied_control_and_vehicle_epoch_are_authority_gated(
    identity_field: str,
    replacement: str,
) -> None:
    investigation = _investigation()
    changed = _identity().model_copy(
        update={
            identity_field: replacement,
            "workspace_revision": "f" * 64,
        }
    )

    assert _authority_revision(changed) != _authority_revision(
        investigation.workspace_identity
    )
    assert _authority_stale_reasons(investigation, (), changed)


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
                support_artifact_ids=(),
                contradiction_artifact_ids=(),
            ),
        ),
    )
    p26 = SimpleNamespace(component_states=(), leading_component_ids=())
    return bundle, folded, p26


def _shadow_prior(
    *,
    tool_id: str = "inspect_track_demand",
    safety_band: str = "performance_measurement",
    baseline_rank: int = 7,
    completed_at: datetime | None = None,
    driver_state: str = "repeatable_tendency",
) -> SimpleNamespace:
    completed_at = completed_at or datetime(2026, 8, 1, tzinfo=UTC)
    experience_ids = ("p33x_" + "a" * 24, "p33x_" + "b" * 24)
    return SimpleNamespace(
        state="available",
        context_transfer_level="exact",
        driver_tendencies=(SimpleNamespace(state=driver_state),),
        useful_prior_investigations=tuple(
            SimpleNamespace(
                experience_id=experience_id,
                outcome=SimpleNamespace(completed_at=completed_at),
            )
            for experience_id in experience_ids
        ),
        context_transfers=tuple(
            SimpleNamespace(
                experience_id=experience_id,
                level="exact",
                drift_reasons=(),
                blocker_reasons=(),
            )
            for experience_id in experience_ids
        ),
        recommended_attention_order=(
            SimpleNamespace(
                tool_id=tool_id,
                safety_band=safety_band,
                baseline_rank_within_band=baseline_rank,
                learned_rank_within_band=1,
                reason="This inspection resolved matching prior cases sooner.",
                transfer_level="exact",
                source_experience_ids=experience_ids,
            ),
        ),
    )


def test_learning_prior_is_shadow_only_and_can_move_one_same_tier_position() -> None:
    bundle, folded, p26 = _planner_fixture()
    prior = _shadow_prior(
        tool_id="inspect_time_loss_origin",
        baseline_rank=2,
    )
    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    shadow = _memory_shadow_subgoal(
        bundle,
        folded,
        p26,
        SimpleNamespace(),
        prior,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert production.selected_tool == "inspect_lap_time_opportunity"
    assert shadow.selected_tool == "inspect_time_loss_origin"
    assert "SHADOW ONLY" not in shadow.why_this_tool
    assert "Qualified P33 history" in shadow.why_this_tool
    assert shadow.priority_rank == production.priority_rank


def test_p34_live_eligibility_excludes_completed_and_prerequisite_blocked_catalog_tools() -> None:
    bundle, folded, p26 = _planner_fixture()
    prior = _shadow_prior(
        tool_id="inspect_time_loss_origin",
        baseline_rank=2,
    )
    baseline_subgoal = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    workspace = SimpleNamespace(
        current_subgoal=baseline_subgoal,
        folded_state=folded,
        learning_prior=prior,
        evidence_index=SimpleNamespace(entries=()),
    )
    baseline, memory, _ = _p34_decisions_for_workspace(
        workspace,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    eligible = _p34_live_eligible_tool_ids(
        baseline,
        memory,
        completed_tool_ids=folded.completed_tool_ids,
    )

    assert eligible == (
        "inspect_lap_time_opportunity",
        "inspect_time_loss_origin",
    )
    assert not set(eligible).intersection(folded.completed_tool_ids)
    assert "inspect_data_quality" not in eligible
    assert "inspect_lap_context" not in eligible
    assert "inspect_component_state" not in eligible


def test_p34_memory_can_change_only_inspection_order_not_p19_or_setup_authority() -> None:
    bundle, folded, p26 = _planner_fixture()
    frozen_at = datetime(2026, 8, 14, tzinfo=UTC)
    favorable = _shadow_prior(
        tool_id="inspect_time_loss_origin",
        baseline_rank=2,
        completed_at=frozen_at - timedelta(days=1),
    )
    hostile = _shadow_prior(
        tool_id="inspect_time_loss_origin",
        baseline_rank=2,
        completed_at=frozen_at,
    )
    baseline_subgoal = _subgoal(bundle, folded, p26, SimpleNamespace(), favorable)
    workspace_truth = {
        "reasoning_snapshot_sha256": "2" * 64,
        "cause_order_and_states": tuple(
            (item.cause_id, item.status, item.ordinal_rank)
            for item in bundle.report.reasoning_snapshot.causes
        ),
        "p19_action": "measurement_mission",
        "p19_mission_id": "p19-mission-immutable",
        "terminal_decision": ("no_call", "Acquire another clean comparison."),
        "setup_authorized": False,
    }
    truth_before = canonical_json_sha256(workspace_truth)
    favorable_workspace = SimpleNamespace(
        current_subgoal=baseline_subgoal,
        folded_state=folded,
        learning_prior=favorable,
        evidence_index=SimpleNamespace(entries=()),
    )
    baseline_decision, memory_decision, transfer = _p34_decisions_for_workspace(
        favorable_workspace,
        decision_frozen_at=frozen_at,
    )
    assert transfer == "exact"
    assert memory_decision.action_id == "inspect_time_loss_origin"
    active_pair = SimpleNamespace(
        production_decision=memory_decision,
        activation_state="limited_attention",
        decision_frozen_at=frozen_at,
    )

    active_subgoal = _production_subgoal_from_pair(
        baseline_subgoal,
        folded,
        favorable,
        active_pair,
    )
    hostile_pair = SimpleNamespace(
        production_decision=baseline_decision,
        activation_state="shadow_only",
        decision_frozen_at=frozen_at,
    )
    hostile_subgoal = _production_subgoal_from_pair(
        baseline_subgoal,
        folded,
        hostile,
        hostile_pair,
    )

    assert baseline_subgoal.selected_tool == "inspect_lap_time_opportunity"
    assert active_subgoal.selected_tool == "inspect_time_loss_origin"
    assert hostile_subgoal == baseline_subgoal
    assert canonical_json_sha256(workspace_truth) == truth_before
    assert workspace_truth["cause_order_and_states"] == (
        ("cause-1", "possible", 1),
    )
    assert workspace_truth["p19_action"] == "measurement_mission"
    assert workspace_truth["p19_mission_id"] == "p19-mission-immutable"
    assert workspace_truth["terminal_decision"] == (
        "no_call",
        "Acquire another clean comparison.",
    )
    assert workspace_truth["setup_authorized"] is False


def test_memory_cannot_move_track_demand_ahead_of_driver_car_separation() -> None:
    bundle, folded, p26 = _planner_fixture()
    folded.completed_tool_ids = (
        *folded.completed_tool_ids,
        "inspect_lap_time_opportunity",
        "inspect_time_loss_origin",
        "inspect_corner_performance_chain",
        "inspect_exit_carry",
        "inspect_path_efficiency",
    )
    prior = _shadow_prior(
        tool_id="inspect_track_demand",
        baseline_rank=7,
    )

    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    shadow, source_ids, transfer_class = _memory_shadow_from_baseline(
        production,
        folded,
        prior,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert production.selected_tool == "inspect_driver_vehicle_separation"
    assert shadow == production
    assert source_ids == ()
    assert transfer_class == "blocked"


def test_new_qualified_current_evidence_cannot_be_delayed_by_prior_attention() -> None:
    bundle, folded, p26 = _planner_fixture()
    folded.hypotheses = (
        SimpleNamespace(
            cause_id="cause-1",
            progress="inspection_pending",
            support_artifact_ids=("current-discriminator-a",),
            contradiction_artifact_ids=(),
        ),
    )
    prior = _shadow_prior(
        tool_id="inspect_time_loss_origin",
        baseline_rank=2,
    )
    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    assert production.selected_tool == "inspect_lap_time_opportunity"
    identity = _identity()
    exact_entry = SimpleNamespace(
        artifact_id="current-discriminator-a",
        producer_id="p32.lap_time_opportunity",
        evidence_state=EvidenceState.CALCULATED,
        blocker_reasons=(),
        source_provenance_available=True,
        run_id=identity.run_id,
        session_id=identity.session_id,
        setup_id=identity.setup_id,
        workspace_run_id=identity.run_id,
        workspace_session_id=identity.session_id,
        workspace_setup_id=identity.setup_id,
        source_run_id=identity.run_id,
        source_session_id=identity.session_id,
        source_setup_id=identity.setup_id,
        source_setup_sha256=identity.setup_snapshot_sha256,
        source_build_context_sha256=identity.vehicle_runtime_identity_hash,
    )
    workspace = SimpleNamespace(
        identity=identity,
        current_subgoal=production,
        folded_state=folded,
        learning_prior=prior,
        evidence_index=SimpleNamespace(entries=(exact_entry,)),
    )

    baseline, memory, transfer_class = _p34_decisions_for_workspace(
        workspace,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert baseline.action_id == "inspect_lap_time_opportunity"
    assert memory == baseline
    assert memory.source_memory_record_ids == ()
    assert transfer_class == "blocked"


def test_wrong_provenance_current_artifact_cannot_pin_baseline_attention() -> None:
    bundle, folded, p26 = _planner_fixture()
    folded.hypotheses = (
        SimpleNamespace(
            cause_id="cause-1",
            progress="inspection_pending",
            support_artifact_ids=("stale-discriminator-a",),
            contradiction_artifact_ids=(),
        ),
    )
    prior = _shadow_prior(
        tool_id="inspect_time_loss_origin",
        baseline_rank=2,
    )
    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    identity = _identity()
    workspace = SimpleNamespace(
        identity=identity,
        current_subgoal=production,
        folded_state=folded,
        learning_prior=prior,
        evidence_index=SimpleNamespace(
            entries=(
                SimpleNamespace(
                    artifact_id="stale-discriminator-a",
                    producer_id="p32.lap_time_opportunity",
                    evidence_state=EvidenceState.CALCULATED,
                    blocker_reasons=(),
                    source_provenance_available=True,
                    run_id=identity.run_id,
                    session_id=identity.session_id,
                    setup_id=identity.setup_id,
                    workspace_run_id=identity.run_id,
                    workspace_session_id=identity.session_id,
                    workspace_setup_id=identity.setup_id,
                    source_run_id=identity.run_id,
                    source_session_id=identity.session_id,
                    source_setup_id=identity.setup_id,
                    source_setup_sha256=identity.setup_snapshot_sha256,
                    source_build_context_sha256="f" * 64,
                ),
            )
        ),
    )

    baseline, memory, transfer_class = _p34_decisions_for_workspace(
        workspace,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert baseline.action_id == "inspect_lap_time_opportunity"
    assert memory.action_id == "inspect_time_loss_origin"
    assert memory.source_memory_record_ids
    assert transfer_class == "exact"


def test_same_action_memory_retains_directly_observable_provenance() -> None:
    bundle, folded, p26 = _planner_fixture()
    prior = _shadow_prior(
        tool_id="inspect_lap_time_opportunity",
        baseline_rank=1,
    )
    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    shadow, source_ids, transfer_class = _memory_shadow_from_baseline(
        production,
        folded,
        prior,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert shadow == production
    assert source_ids == ("p33x_" + "a" * 24, "p33x_" + "b" * 24)
    assert transfer_class == "exact"


def test_learning_prior_cannot_relabel_a_tool_into_an_earlier_safety_band() -> None:
    bundle, folded, p26 = _planner_fixture()
    prior = _shadow_prior(
        tool_id="inspect_p19_causes",
        safety_band="performance_measurement",
    )

    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    shadow = _memory_shadow_subgoal(
        bundle,
        folded,
        p26,
        SimpleNamespace(),
        prior,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert shadow == production


@pytest.mark.parametrize(
    ("completed_at", "driver_state"),
    [
        (datetime(2026, 8, 15, tzinfo=UTC), "repeatable_tendency"),
        (datetime(2026, 8, 14, tzinfo=UTC), "repeatable_tendency"),
        (datetime(2026, 8, 1, tzinfo=UTC), "changed_behavior"),
    ],
)
def test_future_or_driver_drift_memory_falls_back_exactly_to_baseline(
    completed_at: datetime,
    driver_state: str,
) -> None:
    bundle, folded, p26 = _planner_fixture()
    folded.completed_tool_ids = (
        *folded.completed_tool_ids,
        "inspect_lap_time_opportunity",
        "inspect_time_loss_origin",
        "inspect_corner_performance_chain",
        "inspect_exit_carry",
        "inspect_path_efficiency",
    )
    prior = _shadow_prior(completed_at=completed_at, driver_state=driver_state)
    production = _subgoal(bundle, folded, p26, SimpleNamespace(), prior)
    shadow = _memory_shadow_subgoal(
        bundle,
        folded,
        p26,
        SimpleNamespace(),
        prior,
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert shadow == production


def test_p34_outcome_pair_is_earliest_persisted_differing_tool_revision(
    tmp_path,
) -> None:
    db_path = tmp_path / "canonical-p34-pair.sqlite"
    repository = InvestigationAdaptationRepository(db_path)
    baseline_policy = baseline_investigation_policy()
    memory_policy = memory_shadow_investigation_policy()
    for record in (baseline_policy, memory_policy, p34_activation_protocol()):
        repository.append_record(record)
    mandatory = ("workspace_identity", "data_integrity")
    baseline = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Frozen deterministic baseline.",
        mandatory_check_ids=mandatory,
    )

    def pair(
        step: int,
        memory_action: str,
        memory_baseline_ordinal: int,
    ):
        memory = InvestigationDecision(
            decision_kind="inspect_tool",
            action_id=memory_action,
            priority_tier="driver_car_confounders",
            safe_reorder_group="performance_measurement",
            baseline_ordinal=memory_baseline_ordinal,
            selected_ordinal=1,
            reason="Qualified exact-context memory shadow.",
            mandatory_check_ids=mandatory,
            source_memory_record_ids=("p33x_" + "a" * 24,),
        )
        return build_paired_investigation_decision(
            baseline_policy=baseline_policy,
            memory_policy=memory_policy,
            investigation_id="investigation-canonical-pair",
            investigation_opened_at=datetime(2026, 8, 14, 11, tzinfo=UTC),
            run_id="run-1",
            session_id="session-1",
            workspace_revision=canonical_json_sha256(["workspace", step]),
            authority_revision=canonical_json_sha256(["authority", step]),
            step_number=step,
            baseline_decision=baseline,
            memory_decision=memory,
            available_tool_ids=(
                "inspect_lap_time_opportunity",
                "inspect_time_loss_origin",
                "inspect_corner_performance_chain",
            ),
            eligible_tool_ids=(
                "inspect_lap_time_opportunity",
                "inspect_time_loss_origin",
            ),
            completed_tool_ids=(),
            available_artifact_ids=(),
            current_truth_sha256=canonical_json_sha256(["truth", step]),
                p19_snapshot_sha256="2" * 64,
                current_p19_cause_ids=("cause-1",),
                current_p19_cause_states=(
                    P19CauseState(cause_id="cause-1", state="possible"),
                ),
            current_contradiction_ids=(),
            strongest_contradiction_id=None,
            current_objective="race_long_run",
            p33_projection_sha256="0" * 64,
            p33_history_revision="a" * 64,
            p33_ledger_head_sha256="b" * 64,
            p33_context_sha256="c" * 64,
            p33_problem_sha256="d" * 64,
            track="atlanta",
            track_configuration="oval",
            package_type="speedway",
            iracing_build="2026.08.1",
            problem_family="entry",
            problem_orientation="combined",
            track_class="intermediate",
            phase="entry",
            build_review_state="same_build",
            driver_drift_state="stable",
            decision_frozen_at=datetime(2026, 8, 14, 12, step, tzinfo=UTC),
            context_transfer_class="exact",
            p20_projection_sha256="3" * 64,
            p26_projection_sha256="5" * 64,
            p32_projection_sha256="9" * 64,
        )

    same = pair(1, "inspect_lap_time_opportunity", 1)
    earliest_different = pair(2, "inspect_time_loss_origin", 2)
    later_different = pair(3, "inspect_time_loss_origin", 2)
    # Persistence order is deliberately hostile: the higher step arrives first.
    for record in (same, later_different, earliest_different):
        repository.append_paired_decision(record)

    selected = _canonical_p34_outcome_pair(
        "investigation-canonical-pair",
        db_path=db_path,
    )

    assert selected == earliest_different
    assert selected != later_different
    connection = initialize_database(db_path)
    try:
        persisted_selection = CrewChiefRepository._canonical_p34_pair_in_transaction(
            connection,
            "investigation-canonical-pair",
        )
    finally:
        connection.close()
    assert persisted_selection == earliest_different


def test_earned_attention_falls_back_for_current_shadow_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    earned = InvestigationImprovementReadiness(
        production_policy="limited_attention",
        memory_policy_state="limited_attention",
        activation_decision="limited_attention_earned",
        evaluation_decision="limited_attention_earned",
        effective_activation_decision_id="p34act_" + "a" * 24,
        effective_activation_decision_sha256="b" * 64,
        qualified_historical_investigations=20,
        qualified_prospective_investigations=12,
        observable_comparisons=32,
        unobservable_comparisons=0,
        historical_deficit=0,
        prospective_deficit=0,
        exact_recurrence_deficit=0,
        compatible_recurrence_deficit=0,
        context_deficit=0,
        problem_family_deficit=0,
        objective_deficit=0,
        safety_gate_passed=True,
        negative_controls_passed=True,
        subgroup_gate_passed=True,
        blockers=(),
        remaining_collection_missions=(),
    )
    shadow_pair = SimpleNamespace(activation_state="shadow_only")
    captured: dict[str, object] = {}

    class _Repository:
        def latest_pair(self, investigation_id: str, workspace_revision: str):
            assert investigation_id == "investigation-current-fallback"
            assert workspace_revision == "8" * 64
            return shadow_pair

    def _capture_projection(**values):
        captured.update(values)
        return SimpleNamespace(**values)

    monkeypatch.setattr(
        crew_chief_service,
        "InvestigationAdaptationRepository",
        lambda _db_path: _Repository(),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "assess_p34_repository_readiness",
        lambda _repository: earned,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "build_investigation_improvement_projection",
        _capture_projection,
    )
    current_context = SimpleNamespace(context_binding_sha256="c" * 64)
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_adaptation_context_for_pair",
        lambda *_args, **_kwargs: current_context,
    )
    identity = _identity().model_copy(
        update={"investigation_id": "investigation-current-fallback"}
    )

    _p34_projection_for_identity(
        identity,
        investigation_open=True,
        current_learning=SimpleNamespace(),
        learning_prior=SimpleNamespace(),
        folded=SimpleNamespace(status="open"),
        baseline_subgoal=None,
        evidence_index=SimpleNamespace(),
        terminal_decision=SimpleNamespace(),
        p19_cause_ids=(),
        p19_contradiction_artifact_ids=(),
        blocker_reasons=(),
        db_path=None,
    )

    fallback = captured["readiness"]
    assert isinstance(fallback, InvestigationImprovementReadiness)
    assert fallback.production_policy == "deterministic_baseline"
    assert fallback.memory_policy_state == "shadow_only"
    assert fallback.activation_decision == "no_activation_earned"
    assert fallback.qualified_historical_investigations == 20
    assert fallback.qualified_prospective_investigations == 12
    assert captured["current_pair"] is shadow_pair
    assert captured["current_context"] is current_context
    assert captured["safety_blockers"]


def test_p34_unknown_driver_state_cannot_masquerade_as_drift_evidence() -> None:
    mandatory = ("workspace_identity",)
    baseline = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Baseline.",
        mandatory_check_ids=mandatory,
    )
    memory = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_time_loss_origin",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=2,
        selected_ordinal=1,
        reason="Memory shadow.",
        mandatory_check_ids=mandatory,
        source_memory_record_ids=("p33x_" + "a" * 24,),
    )
    workspace = SimpleNamespace(
        blocker_reasons=(),
        learning_prior=SimpleNamespace(
            context_transfers=(),
            driver_tendencies=(),
        ),
    )
    current = SimpleNamespace(
        context=SimpleNamespace(
            objective="race_long_run",
            track="atlanta",
            track_configuration="oval",
            package_type="speedway",
        ),
        problem=SimpleNamespace(
            phase="entry",
            driver_demand_state="unknown",
            vehicle_response_state="unknown",
        ),
    )

    (
        _family,
        _orientation,
        _track_class,
        subgroups,
        _build_state,
        driver_state,
        transfer_class,
        bounded_memory,
        future_memory_record_ids,
        _negative_control,
    ) = _p34_restart_context(
        workspace,
        current,
        baseline,
        memory,
        "exact",
        decision_frozen_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert driver_state == "unknown"
    assert "driver_state_unknown" in subgroups
    assert "driver_drift_detected" not in subgroups
    assert transfer_class == "blocked"
    assert bounded_memory == baseline
    assert future_memory_record_ids == ()


def test_all_frozen_negative_controls_build_real_exact_fallback_pairs() -> None:
    frozen_at = datetime(2026, 8, 14, 15, tzinfo=UTC)
    baseline_policy = baseline_investigation_policy()
    memory_policy = memory_shadow_investigation_policy()
    mandatory = ("workspace_identity",)
    baseline = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Deterministic baseline remains production.",
        mandatory_check_ids=mandatory,
    )

    def transfer(
        level: str,
        *,
        mismatched_dimensions: tuple[str, ...] = (),
    ) -> SimpleNamespace:
        return SimpleNamespace(
            experience_id="p33x_" + "a" * 24,
            level=level,
            matching_dimensions=("driver_execution_state",),
            mismatched_dimensions=mismatched_dimensions,
            drift_reasons=(),
            blocker_reasons=("Physical scope is incompatible.",)
            if level == "blocked"
            else (),
        )

    cases = {
        "no_relevant_history": {
            "state": "insufficient_history",
        },
        "incompatible_history": {
            "state": "available",
            "context_transfers": (transfer("blocked"),),
        },
        "corrupt_history": {
            "state": "blocked",
            "blocker_reasons": ("The P33 ledger failed integrity validation.",),
        },
        "generic_component_knowledge_only": {
            "state": "available",
            "context_transfers": (
                transfer(
                    "weak",
                    mismatched_dimensions=("setup_snapshot_sha256",),
                ),
            ),
            "car_response_history": (
                SimpleNamespace(source_experience_ids=("p33x_" + "c" * 24,)),
            ),
            "driver_demand_state": "unknown",
            "vehicle_response_state": "changed_response",
        },
        "same_words_different_physical_scope": {
            "state": "available",
            "context_transfers": (
                transfer(
                    "weak",
                    mismatched_dimensions=("speed_load_band",),
                ),
            ),
            "recurrence": SimpleNamespace(classification="possible_recurrence"),
            "driver_demand_state": "matched_inputs",
            "vehicle_response_state": "changed_response",
        },
        "material_driver_drift": {
            "state": "available",
            "driver_tendencies": (SimpleNamespace(state="changed_behavior"),),
        },
        "future_memory_record": {
            "state": "available",
            "recurrence": SimpleNamespace(classification="possible_recurrence"),
            "useful_prior_investigations": (
                SimpleNamespace(
                    experience_id="p33x_" + "b" * 24,
                    outcome=SimpleNamespace(completed_at=frozen_at),
                ),
            ),
        },
    }
    for ordinal, (expected_control, values) in enumerate(cases.items(), start=1):
        prior = SimpleNamespace(
            projection_sha256="0" * 64,
            state=values.get("state", "available"),
            context_transfers=values.get("context_transfers", ()),
            driver_tendencies=values.get("driver_tendencies", ()),
            car_response_history=values.get("car_response_history", ()),
            recurrence=values.get(
                "recurrence", SimpleNamespace(classification="new_problem")
            ),
            useful_prior_investigations=values.get(
                "useful_prior_investigations", ()
            ),
            blocker_reasons=values.get("blocker_reasons", ()),
        )
        workspace = SimpleNamespace(
            blocker_reasons=(),
            learning_prior=prior,
        )
        current = SimpleNamespace(
            context=SimpleNamespace(
                objective="race_long_run",
                track="atlanta",
                track_configuration="oval",
                package_type="speedway",
            ),
            problem=SimpleNamespace(
                phase="entry",
                driver_demand_state=values.get(
                    "driver_demand_state", "unknown"
                ),
                vehicle_response_state=values.get(
                    "vehicle_response_state", "unknown"
                ),
            ),
        )
        (
            problem_family,
            problem_orientation,
            track_class,
            _subgroups,
            build_state,
            driver_state,
            transfer_class,
            memory,
            future_memory_record_ids,
            control_id,
        ) = _p34_restart_context(
            workspace,
            current,
            baseline,
            baseline,
            "none",
            decision_frozen_at=frozen_at,
        )
        assert control_id == expected_control
        control_evidence = _p34_negative_control_evidence(
            workspace,
            condition=control_id,
            driver_drift_state=driver_state,
            future_memory_record_ids=future_memory_record_ids,
        )
        referenced_p33_ids = (
            *control_evidence.context_transfer_record_ids,
            *control_evidence.useful_prior_experience_ids,
            *control_evidence.component_history_experience_ids,
            *control_evidence.future_memory_record_ids,
        )
        pair = build_paired_investigation_decision(
            baseline_policy=baseline_policy,
            memory_policy=memory_policy,
            investigation_id=f"negative-control-{ordinal}",
            investigation_opened_at=frozen_at - timedelta(hours=1),
            run_id="run-1",
            session_id="session-1",
            workspace_revision=canonical_json_sha256(
                ["negative-control-workspace", ordinal]
            ),
            authority_revision=canonical_json_sha256(
                ["negative-control-authority", ordinal]
            ),
            step_number=0,
            baseline_decision=baseline,
            memory_decision=memory,
            available_tool_ids=(baseline.action_id,),
            eligible_tool_ids=(baseline.action_id,),
            completed_tool_ids=(),
            available_artifact_ids=(),
            current_truth_sha256=canonical_json_sha256(
                ["negative-control-truth", ordinal]
            ),
            p19_snapshot_sha256="2" * 64,
            current_p19_cause_ids=("cause-1",),
            current_p19_cause_states=(
                P19CauseState(cause_id="cause-1", state="possible"),
            ),
            current_contradiction_ids=(),
            strongest_contradiction_id=None,
            current_objective="race_long_run",
            p33_projection_sha256="0" * 64,
            p33_history_revision="a" * 64,
            p33_ledger_head_sha256=("f" * 64 if referenced_p33_ids else None),
            p33_context_sha256="c" * 64,
            p33_problem_sha256="d" * 64,
            track="atlanta",
            track_configuration="oval",
            package_type="speedway",
            iracing_build="2026.08.1",
            problem_family=problem_family,
            problem_orientation=problem_orientation,
            track_class=track_class,
            phase="entry",
            build_review_state=build_state,
            driver_drift_state=driver_state,
            decision_frozen_at=frozen_at,
            context_transfer_class=transfer_class,
            negative_control_condition=control_id,
            negative_control_evidence=control_evidence,
            future_memory_record_ids=future_memory_record_ids,
            p20_projection_sha256="3" * 64,
            p26_projection_sha256="5" * 64,
            p32_projection_sha256="9" * 64,
        )
        result = build_p34_negative_control_result(
            pair,
            control_id=expected_control,
            evaluated_at=frozen_at + timedelta(seconds=1),
        )
        assert pair.production_decision == pair.baseline_decision
        assert pair.memory_records_consulted == ()
        assert result.passed is True


def test_iracing_build_mismatch_is_unreviewed_and_cannot_control_attention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    frozen_at = datetime(2026, 8, 14, 15, tzinfo=UTC)
    baseline = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Deterministic baseline.",
        mandatory_check_ids=("workspace_identity",),
    )
    memory = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_time_loss_origin",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=2,
        selected_ordinal=1,
        reason="Historical attention candidate.",
        mandatory_check_ids=("workspace_identity",),
        source_memory_record_ids=("p33x_" + "a" * 24,),
    )
    transfer = SimpleNamespace(
        experience_id="p33x_" + "a" * 24,
        level="exact",
        matching_dimensions=("driver_execution_state",),
        mismatched_dimensions=("iRacing_build",),
        drift_reasons=(),
        blocker_reasons=(),
    )
    workspace = SimpleNamespace(
        blocker_reasons=(),
        learning_prior=SimpleNamespace(
            state="available",
            context_transfers=(transfer,),
            useful_prior_investigations=(
                SimpleNamespace(
                    experience_id=transfer.experience_id,
                    outcome=SimpleNamespace(
                        completed_at=frozen_at - timedelta(days=1)
                    ),
                ),
            ),
            driver_tendencies=(),
            car_response_history=(),
            recurrence=SimpleNamespace(classification="possible_recurrence"),
            blocker_reasons=(),
        ),
    )
    current = SimpleNamespace(
        context=SimpleNamespace(
            objective="race_long_run",
            track="atlanta",
            track_configuration="oval",
            package_type="speedway",
        ),
        problem=SimpleNamespace(
            phase="entry",
            driver_demand_state="matched_inputs",
            vehicle_response_state="changed_response",
        ),
    )

    values = _p34_restart_context(
        workspace,
        current,
        baseline,
        memory,
        "exact",
        decision_frozen_at=frozen_at,
    )

    assert values[4] == "future_unreviewed_build"
    assert values[6] == "blocked"
    assert values[7] == baseline
    assert values[9] is None
    pair = build_paired_investigation_decision(
        baseline_policy=baseline_investigation_policy(),
        memory_policy=memory_shadow_investigation_policy(),
        investigation_id="investigation-build-mismatch",
        investigation_opened_at=frozen_at - timedelta(minutes=1),
        run_id="run-1",
        session_id="session-1",
        workspace_revision="8" * 64,
        authority_revision="7" * 64,
        step_number=0,
        baseline_decision=baseline,
        memory_decision=values[7],
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
        p19_snapshot_sha256="2" * 64,
        current_p19_cause_ids=("cause-1",),
        current_p19_cause_states=(
            P19CauseState(cause_id="cause-1", state="possible"),
        ),
        current_contradiction_ids=(),
        strongest_contradiction_id=None,
        current_objective="race_long_run",
        p33_projection_sha256="6" * 64,
        p33_history_revision="a" * 64,
        p33_ledger_head_sha256="b" * 64,
        p33_context_sha256="c" * 64,
        p33_problem_sha256="d" * 64,
        track="atlanta",
        track_configuration="oval",
        package_type="speedway",
        iracing_build="2026.08.1",
        problem_family=values[0],
        problem_orientation=values[1],
        track_class=values[2],
        phase="entry",
        build_review_state=values[4],
        driver_drift_state=values[5],
        decision_frozen_at=frozen_at,
        context_transfer_class=values[6],
        negative_control_condition=values[9],
        p20_projection_sha256="3" * 64,
        p26_projection_sha256="5" * 64,
        p32_projection_sha256="9" * 64,
    )
    assert pair.production_decision == baseline
    assert pair.negative_control_condition is None

    db_path = tmp_path / "p34-build-mismatch.sqlite"
    initialize_database(db_path).close()
    p33_state = EngineeringLearningRepository(db_path).stream_state()
    identity = _identity().model_copy(
        update={
            "learning_history_revision": p33_state.history_revision,
            "learning_ledger_head_sha256": p33_state.head_sha256,
            "learning_projection_sha256": "6" * 64,
        }
    )
    current.context.context_sha256 = "c" * 64
    current.context.iracing_build = "2026.08.1"
    current.problem.problem_sha256 = "d" * 64
    current.reasoning = SimpleNamespace(
        causes=(SimpleNamespace(cause_id="cause-1", status="possible"),)
    )
    prior = workspace.learning_prior
    prior.projection_sha256 = identity.learning_projection_sha256
    prior.current_context_sha256 = current.context.context_sha256
    prior.current_problem_sha256 = current.problem.problem_sha256
    workspace.identity = identity
    workspace.investigation = _investigation().model_copy(
        update={"workspace_identity": identity}
    )
    workspace.folded_state = SimpleNamespace(
        status="open",
        last_sequence=0,
        completed_tool_ids=(),
    )
    workspace.current_subgoal = SimpleNamespace()
    workspace.available_tools = (
        SimpleNamespace(tool_id="inspect_lap_time_opportunity"),
        SimpleNamespace(tool_id="inspect_time_loss_origin"),
    )
    workspace.evidence_index = SimpleNamespace(entries=())
    workspace.p19_cause_ids = ("cause-1",)
    workspace.p19_contradiction_artifact_ids = ()
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_decisions_for_workspace",
        lambda *_args, **_kwargs: (baseline, memory, "exact"),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_qualified_current_evidence_tool_ids",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_learning_inputs_for_workspace",
        lambda *_args, **_kwargs: current,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_current_truth_sha256",
        lambda _workspace: "1" * 64,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "resolve_effective_activation_decision",
        lambda _repository: None,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "restore_effective_activation_on_mutation",
        lambda _repository: None,
    )

    persisted_pair = _freeze_p34_pair_for_workspace(workspace, db_path=db_path)

    assert persisted_pair is not None
    assert persisted_pair.production_decision == baseline
    assert persisted_pair.context_transfer_class == "blocked"
    assert persisted_pair.build_review_state == "future_unreviewed_build"
    assert persisted_pair.negative_control_condition is None
    restarted_pair = InvestigationAdaptationRepository(db_path).latest_pair(
        workspace.investigation.investigation_id,
        identity.workspace_revision,
    )
    assert restarted_pair == persisted_pair


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


def test_first_real_pair_mutation_persists_foundation_once_across_restart(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "p34-foundation-restart.sqlite"
    initialize_database(db_path).close()
    identity = _identity()
    investigation = _investigation()
    current = SimpleNamespace(
        context=SimpleNamespace(
            context_sha256="c" * 64,
            objective="race_long_run",
            track="atlanta",
            track_configuration="oval",
            package_type="speedway",
            iracing_build="2026.08.1",
        ),
        problem=SimpleNamespace(
            problem_sha256="d" * 64,
            phase="entry",
            driver_demand_state="unknown",
            vehicle_response_state="unknown",
        ),
        reasoning=SimpleNamespace(
            causes=(SimpleNamespace(cause_id="cause-1", status="possible"),)
        ),
    )
    prior = SimpleNamespace(
        projection_sha256=identity.learning_projection_sha256,
        state="insufficient_history",
        current_context_sha256=current.context.context_sha256,
        current_problem_sha256=current.problem.problem_sha256,
        context_transfers=(),
        useful_prior_investigations=(),
        driver_tendencies=(),
        car_response_history=(),
        recurrence=SimpleNamespace(classification="new_problem"),
        blocker_reasons=(),
    )
    workspace = SimpleNamespace(
        identity=identity,
        investigation=investigation,
        folded_state=SimpleNamespace(
            status="open",
            last_sequence=0,
            completed_tool_ids=(),
        ),
        current_subgoal=SimpleNamespace(),
        learning_prior=prior,
        available_tools=(
            SimpleNamespace(tool_id="inspect_lap_time_opportunity"),
            SimpleNamespace(tool_id="inspect_time_loss_origin"),
        ),
        evidence_index=SimpleNamespace(
            entries=(
                SimpleNamespace(
                    artifact_id="late-qualified-artifact",
                    evidence_state=EvidenceState.MEASURED,
                    blocker_reasons=("Current provenance is blocked.",),
                ),
            )
        ),
        p19_cause_ids=("cause-1",),
        p19_contradiction_artifact_ids=(),
        blocker_reasons=(),
    )
    baseline = InvestigationDecision(
        decision_kind="inspect_tool",
        action_id="inspect_lap_time_opportunity",
        priority_tier="driver_car_confounders",
        safe_reorder_group="performance_measurement",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason="Deterministic baseline.",
        mandatory_check_ids=("workspace_identity",),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_decisions_for_workspace",
        lambda *_args, **_kwargs: (baseline, baseline, "none"),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_qualified_current_evidence_tool_ids",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_learning_inputs_for_workspace",
        lambda *_args, **_kwargs: current,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_current_truth_sha256",
        lambda _workspace: "e" * 64,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "resolve_effective_activation_decision",
        lambda _repository: None,
    )
    restored_mutations: list[object] = []
    monkeypatch.setattr(
        crew_chief_service,
        "restore_effective_activation_on_mutation",
        lambda repository: restored_mutations.append(repository.db_path),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_p34_restart_context",
        lambda *_args, **_kwargs: (
            "entry",
            "unresolved",
            "intermediate",
            ("no_transfer",),
            "same_build",
            "unknown",
            "none",
            baseline,
            (),
            "no_relevant_history",
        ),
    )
    build_failure: list[Exception] = []
    real_pair_builder = crew_chief_service.build_paired_investigation_decision

    monkeypatch.setattr(
        crew_chief_service,
        "build_paired_investigation_decision",
        lambda **_values: (_ for _ in ()).throw(
            ValueError("injected pre-freeze validation failure")
        ),
    )
    assert _freeze_p34_pair_for_workspace(workspace, db_path=db_path) is None
    empty_repository = InvestigationAdaptationRepository(db_path)
    empty_state = empty_repository.stream_state(validate_chain=True)
    assert (empty_state.record_count, empty_state.head_sha256) == (0, None)
    assert empty_repository.query_records(limit=10).records == ()

    def capture_pair_build(**values):
        try:
            return real_pair_builder(**values)
        except Exception as exc:
            build_failure.append(exc)
            raise

    monkeypatch.setattr(
        crew_chief_service,
        "build_paired_investigation_decision",
        capture_pair_build,
    )

    first = _freeze_p34_pair_for_workspace(workspace, db_path=db_path)
    assert not build_failure, str(build_failure)
    preflight_state = InvestigationAdaptationRepository(db_path).stream_state(
        validate_chain=True
    )
    assert first is not None, preflight_state
    assert first.available_artifact_ids == ("late-qualified-artifact",)
    assert first.qualified_available_artifact_ids == ()
    assert first.qualified_available_artifact_evidence_states == ()
    assert first.qualified_available_artifact_provenance_sha256s == ()
    first_state = InvestigationAdaptationRepository(db_path).stream_state(
        validate_chain=True
    )
    first_records = InvestigationAdaptationRepository(db_path).query_records(
        limit=10
    )
    assert first_state.record_count == 5
    assert sum(
        item.schema_version == "p34.paired-investigation-decision.v1"
        for item in first_records.records
    ) == 1
    assert sum(
        item.schema_version == "p34.investigation-policy.v1"
        for item in first_records.records
    ) == 3
    assert sum(
        item.schema_version == "p34.activation-protocol.v1"
        for item in first_records.records
    ) == 1

    restarted = _freeze_p34_pair_for_workspace(workspace, db_path=db_path)
    restarted_state = InvestigationAdaptationRepository(db_path).stream_state(
        validate_chain=True
    )
    assert restarted == first
    assert restarted_state == first_state
    assert restored_mutations == [db_path, db_path, db_path]


def test_continue_cannot_bypass_a_pending_driver_question(
    monkeypatch,
    tmp_path,
) -> None:
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
            db_path=tmp_path / "pending-driver-question.sqlite",
        )


def test_rebase_rejects_a_foreign_stale_revision(monkeypatch, tmp_path) -> None:
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
            db_path=tmp_path / "foreign-stale-revision.sqlite",
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
