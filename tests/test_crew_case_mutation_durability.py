from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    CrewChiefEventPayload,
    CrewChiefMutationPublicationReceipt,
    DriverDiagnosticQuestion,
    EngineeringObjective,
)
from racelab_engine.models.engineering_case import CanonicalEngineeringCase
from racelab_engine.services import crew_chief_service
from racelab_engine.services.crew_chief_service import (
    _commit_crew_case_mutation,
    _event,
    record_driver_answer,
    select_objective,
)
from racelab_engine.storage import crew_chief_repository as crew_repository_module
from racelab_engine.storage import db as storage_db
from racelab_engine.storage.crew_chief_repository import (
    CrewChiefIntegrityError,
    CrewChiefRepository,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_case_repository import (
    EngineeringCaseRepository,
)
from test_crew_chief_contracts import _identity, _investigation
from test_p3544_engineering_case_revision import (
    RUN_ID,
    SESSION_ID,
    WORKSPACE,
    _case,
    _seed_run,
)


class _ReceiptIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    session_id: str
    investigation_id: str | None
    workspace_revision: str
    objective_id: EngineeringObjective


class _ReceiptWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: _ReceiptIdentity
    engineering_case: CanonicalEngineeringCase
    mutation_receipt: CrewChiefMutationPublicationReceipt | None = None


def _receipt_workspace(
    engineering_case: CanonicalEngineeringCase,
    *,
    investigation_id: str = "investigation-1",
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN,
) -> _ReceiptWorkspace:
    return _ReceiptWorkspace(
        identity=_ReceiptIdentity(
            run_id=RUN_ID,
            session_id=SESSION_ID,
            investigation_id=investigation_id,
            workspace_revision=WORKSPACE,
            objective_id=objective,
        ),
        engineering_case=engineering_case,
    )


def _seed_investigation(db_path):
    identity = _identity().model_copy(
        update={
            "run_id": RUN_ID,
            "session_id": SESSION_ID,
            "selected_scope_hash": canonical_json_sha256((RUN_ID,)),
            "selected_run_ids": (RUN_ID,),
            "workspace_revision": WORKSPACE,
        }
    )
    investigation = _investigation().model_copy(
        update={"workspace_identity": identity}
    )
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(investigation)
    opening_event = _event(
        investigation.investigation_id,
        1,
        WORKSPACE,
        "problem_interpreted",
        CrewChiefEventPayload(message="Driver report normalized."),
    )
    repository.append_events((opening_event,))
    return identity, investigation, opening_event


def test_case_finalization_failure_rolls_back_the_crew_event_and_receipt(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "crew-case-finalization-failure.sqlite"
    _seed_run(db_path)
    initial = _case()
    case_repository = EngineeringCaseRepository(db_path)
    case_repository.finalize_case(initial)
    identity, investigation, opening_event = _seed_investigation(db_path)
    event = _event(
        investigation.investigation_id,
        2,
        WORKSPACE,
        "objective_selected",
        CrewChiefEventPayload(
            message="Objective selected: qualifying_peak.",
            objective=EngineeringObjective.QUALIFYING_PEAK,
        ),
    )
    response = _receipt_workspace(
        _case(next_move="Case publication must fail."),
        objective=EngineeringObjective.QUALIFYING_PEAK,
    )
    monkeypatch.setattr(
        crew_repository_module, "CrewChiefWorkspace", _ReceiptWorkspace
    )
    monkeypatch.setattr(
        crew_chief_service, "CrewChiefWorkspace", _ReceiptWorkspace
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_transaction_workspace",
        lambda *_args, **_kwargs: response,
    )

    def fail_after_event(self, connection, case, **kwargs):
        assert connection.execute(
            "SELECT COUNT(*) FROM crew_chief_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()[0] == 1
        raise RuntimeError("hostile case-finalization failure")

    monkeypatch.setattr(
        EngineeringCaseRepository,
        "finalize_case_in_transaction",
        fail_after_event,
    )
    repository = CrewChiefRepository(db_path)
    with pytest.raises(RuntimeError, match="hostile case-finalization failure"):
        _commit_crew_case_mutation(
            db_path=db_path,
            action="hostile",
            request={"request": "rollback"},
            run_id=RUN_ID,
            session_id=SESSION_ID,
            investigation_id=investigation.investigation_id,
            objective=EngineeringObjective.QUALIFYING_PEAK,
            expected_workspace_revision=identity.workspace_revision,
            expected_case_sha256=initial.case_sha256,
            apply=lambda connection: repository.append_events_in_transaction(
                connection, (event,)
            ),
        )

    assert repository.list_events(investigation.investigation_id) == (opening_event,)
    assert case_repository.current(initial.case_id).case_sha256 == initial.case_sha256
    connection = initialize_database(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM crew_chief_mutation_receipts"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_pre_publication_receipt_is_upgraded_to_exact_revision_lineage(
    tmp_path,
) -> None:
    db_path = tmp_path / "legacy-crew-receipt.sqlite"
    _seed_run(db_path)
    revision = EngineeringCaseRepository(db_path).finalize_case(_case())
    connection = initialize_database(db_path)
    connection.execute("DELETE FROM schema_migrations WHERE version >= 6")
    completed_at = "2026-08-26T12:00:00+00:00"
    connection.execute(
        """
        INSERT INTO crew_chief_mutation_receipts(
          mutation_id, request_sha256, action, run_id, session_id,
          investigation_id, expected_workspace_revision, expected_case_sha256,
          result_workspace_revision, result_case_sha256, result_case_revision,
          previous_case_sha256, completed_at, workspace_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ccm_" + "a" * 24,
            "b" * 64,
            "open",
            RUN_ID,
            SESSION_ID,
            None,
            WORKSPACE,
            revision.case_sha256,
            WORKSPACE,
            revision.case_sha256,
            revision.case_revision,
            revision.previous_case_sha256,
            completed_at,
            json.dumps(
                {
                    "identity": {
                        "run_id": RUN_ID,
                        "session_id": SESSION_ID,
                        "selected_scope_hash": canonical_json_sha256((RUN_ID,)),
                    },
                    "engineering_case": {"case_id": revision.case_id},
                }
            ),
        ),
    )
    connection.commit()
    connection.close()

    storage_db._INITIALIZED_DATABASES.clear()
    migrated = initialize_database(db_path)
    row = migrated.execute(
        "SELECT workspace_json FROM crew_chief_mutation_receipts"
    ).fetchone()
    migrated.close()
    publication = CrewChiefMutationPublicationReceipt.model_validate(
        json.loads(row["workspace_json"])["mutation_receipt"]
    )
    assert json.loads(row["workspace_json"])["identity"]["selected_run_ids"] == [
        RUN_ID
    ]
    assert publication.case_id == revision.case_id
    assert publication.case_revision == revision.case_revision
    assert publication.case_sha256 == revision.case_sha256
    assert publication.previous_case_sha256 == revision.previous_case_sha256


def test_lost_response_retry_replays_exact_workspace_without_duplicate_truth(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "crew-case-lost-response.sqlite"
    _seed_run(db_path)
    initial = _case()
    result_case = _case(next_move="Return this exact durable response.")
    case_repository = EngineeringCaseRepository(db_path)
    case_repository.finalize_case(initial)
    identity, investigation, _ = _seed_investigation(db_path)
    event = _event(
        investigation.investigation_id,
        2,
        WORKSPACE,
        "objective_selected",
        CrewChiefEventPayload(
            message="Objective selected: race_long_run.",
            objective=EngineeringObjective.RACE_LONG_RUN,
        ),
    )
    response = _receipt_workspace(result_case)
    monkeypatch.setattr(
        crew_repository_module, "CrewChiefWorkspace", _ReceiptWorkspace
    )
    monkeypatch.setattr(
        crew_chief_service, "CrewChiefWorkspace", _ReceiptWorkspace
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_transaction_workspace",
        lambda *_args, **_kwargs: response,
    )
    repository = CrewChiefRepository(db_path)
    apply_count = 0

    def apply(connection) -> None:
        nonlocal apply_count
        apply_count += 1
        repository.append_events_in_transaction(connection, (event,))

    values = dict(
        db_path=db_path,
        action="lost_response",
        request={"request": "same-content"},
        run_id=RUN_ID,
        session_id=SESSION_ID,
        investigation_id=investigation.investigation_id,
        objective=EngineeringObjective.RACE_LONG_RUN,
        expected_workspace_revision=identity.workspace_revision,
        expected_case_sha256=initial.case_sha256,
        apply=apply,
    )
    first = _commit_crew_case_mutation(**values)
    storage_db._INITIALIZED_DATABASES.clear()
    second = _commit_crew_case_mutation(**values)

    assert second == first
    assert first.engineering_case == response.engineering_case
    assert first.mutation_receipt is not None
    assert first.mutation_receipt.case_revision == 2
    assert first.mutation_receipt.previous_case_sha256 == initial.case_sha256
    assert apply_count == 1
    assert len(repository.list_events(investigation.investigation_id)) == 2
    assert len(case_repository.history(initial.case_id)) == 2
    assert case_repository.current(initial.case_id).case == first.engineering_case

    connection = initialize_database(db_path)
    connection.execute(
        "UPDATE crew_chief_mutation_receipts SET previous_case_sha256 = ?",
        ("f" * 64,),
    )
    connection.commit()
    connection.close()
    with pytest.raises(CrewChiefIntegrityError, match="publication receipt"):
        _commit_crew_case_mutation(**values)


def test_objective_and_typed_answer_refine_one_case_bound_intent_ledger(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "crew-driver-intent-coherence.sqlite"
    _seed_run(db_path)
    case_repository = EngineeringCaseRepository(db_path)
    first = case_repository.finalize_case(_case())
    original_intent = case_repository.append_driver_intent(
        case_id=first.case_id,
        raw_driver_wording="Loose on entry.",
        objective=EngineeringObjective.RACE_LONG_RUN.value,
        source="manual",
        typed_interpretation_provenance=("initial-report",),
    )
    initial_case = _case(driver_intent=original_intent)
    case_repository.finalize_case(initial_case, change_category="driver_intent")
    identity, investigation, _ = _seed_investigation(db_path)
    repository = CrewChiefRepository(db_path)
    monkeypatch.setattr(
        crew_repository_module, "CrewChiefWorkspace", _ReceiptWorkspace
    )
    monkeypatch.setattr(
        crew_chief_service, "CrewChiefWorkspace", _ReceiptWorkspace
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_refresh_p34_attention_after_commit",
        lambda *_args, **_kwargs: None,
    )

    def transaction_workspace(
        connection, *, investigation_id, objective, **_kwargs
    ) -> _ReceiptWorkspace:
        intent = case_repository.current_driver_intent_in_transaction(
            connection, first.case_id
        )
        projected = _case(
            driver_intent=intent,
            objective_id=objective.value,
            next_move=(
                f"Projected intent revision {intent.intent_revision}."
                if intent is not None
                else "No driver intent."
            ),
        )
        return _receipt_workspace(
            projected,
            investigation_id=investigation_id,
            objective=objective,
        )

    monkeypatch.setattr(
        crew_chief_service, "_transaction_workspace", transaction_workspace
    )
    current = SimpleNamespace(
        identity=identity,
        engineering_case=initial_case,
        folded_state=SimpleNamespace(status="open", last_sequence=1),
        investigation=investigation,
    )
    monkeypatch.setattr(
        crew_chief_service,
        "build_crew_chief_workspace",
        lambda *_args, **_kwargs: current,
    )
    objective_result = select_objective(
        RUN_ID,
        investigation.investigation_id,
        session_id=SESSION_ID,
        expected_workspace_revision=WORKSPACE,
        expected_case_sha256=initial_case.case_sha256,
        objective=EngineeringObjective.QUALIFYING_PEAK,
        db_path=db_path,
    )
    objective_intent = case_repository.current_driver_intent(first.case_id)
    assert objective_intent is not None
    assert objective_intent.intent_revision == 2
    assert objective_intent.objective == EngineeringObjective.QUALIFYING_PEAK.value
    assert objective_result.engineering_case.driver_intent == objective_intent
    assert objective_result.engineering_case.objective_id == objective_intent.objective
    assert case_repository.current(first.case_id).case == objective_result.engineering_case

    question = DriverDiagnosticQuestion(
        question_id="driver-context-1",
        workspace_revision=WORKSPACE,
        question="Where does it happen?",
        answer_options=("after full throttle", "before throttle"),
        reason="Separate local response from downstream carry.",
    )
    current_after_objective = SimpleNamespace(
        identity=identity.model_copy(
            update={"objective_id": EngineeringObjective.QUALIFYING_PEAK}
        ),
        engineering_case=objective_result.engineering_case,
        folded_state=SimpleNamespace(status="open", last_sequence=2),
        investigation=investigation,
        pending_driver_question=question,
        p19_contradiction_artifact_ids=(),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "build_crew_chief_workspace",
        lambda *_args, **_kwargs: current_after_objective,
    )
    answer_result = record_driver_answer(
        RUN_ID,
        investigation.investigation_id,
        session_id=SESSION_ID,
        expected_workspace_revision=WORKSPACE,
        expected_case_sha256=objective_result.engineering_case.case_sha256,
        answer="after full throttle",
        db_path=db_path,
    )
    answer_intent = case_repository.current_driver_intent(first.case_id)
    assert answer_intent is not None
    assert answer_intent.intent_revision == 3
    assert answer_intent.objective == EngineeringObjective.QUALIFYING_PEAK.value
    assert answer_intent.phase_scope == "exit,following_straight"
    assert answer_intent.power_state_context == "power_on"
    assert answer_intent.time_origin_scope == "following_straight"
    assert answer_result.engineering_case.driver_intent == answer_intent
    assert case_repository.current(first.case_id).case == answer_result.engineering_case
    assert len(repository.list_driver_memory(SESSION_ID)) == 1
