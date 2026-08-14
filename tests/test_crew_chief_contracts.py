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
from racelab_engine.models.intelligence import EvidenceCitation
from racelab_engine.services.crew_chief_service import (
    _authority_revision,
    _authority_stale_reasons,
    _accepted_workspace_revision,
    _evidence_index,
    _event,
    _sentinel,
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
        opened_at=datetime.now(UTC),
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
    connection.execute("DELETE FROM crew_chief_events WHERE event_id = ?", (event.event_id,))
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
    storage_db._INITIALIZED_DATABASES.pop(str((tmp_path / "crew-chief-stream-head-tamper.sqlite").resolve()), None)
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
            reasoning_snapshot=SimpleNamespace(
                causes=causes, mechanism_episodes=()
            )
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


def test_real_next_gen_atlanta_workspace_preserves_authority_boundary() -> None:
    run_id = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"
    session_id = "session_ed52db305244"
    from racelab_engine.storage.repository import RaceLabRepository

    if RaceLabRepository().get_overview(run_id) is None:
        pytest.skip("Persisted real Next Gen Atlanta fixture is unavailable")
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
