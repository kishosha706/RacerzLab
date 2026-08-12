from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.main import app
from api.routes_crew_chief import OpenInvestigationRequest, RevisionRequest
from racelab_engine.models.crew_chief import (
    CrewChiefEventPayload,
    CrewChiefInvestigation,
    CrewChiefTerminalDecision,
    CrewChiefWorkspaceIdentity,
    EngineeringObjective,
)
from racelab_engine.services.crew_chief_service import (
    _event,
    _sentinel,
    build_crew_chief_workspace,
    fold_investigation,
)
from racelab_engine.services.session_service import create_session, delete_session
from racelab_engine.storage.crew_chief_repository import (
    CrewChiefIntegrityError,
    CrewChiefRepository,
)
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


def test_real_next_gen_atlanta_workspace_preserves_authority_boundary() -> None:
    run_id = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"
    session_id = "session_ed52db305244"
    from racelab_engine.storage.repository import RaceLabRepository

    if RaceLabRepository().get_overview(run_id) is None:
        pytest.skip("Persisted real Next Gen Atlanta fixture is unavailable")
    workspace = build_crew_chief_workspace(run_id, session_id=session_id)
    assert workspace.identity.reasoning_snapshot_sha256 == (
        workspace.identity.p26_reasoning_snapshot_sha256
    )
    assert workspace.identity.setup_id
    assert workspace.generative_boundary.enabled is False
    assert workspace.adaptive_research.state == "data_locked"
    if workspace.terminal_decision.kind != "controlled_test":
        assert workspace.terminal_decision.control_key is None
        assert workspace.terminal_decision.proposed_value is None
