from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from api import routes_engineering
from api.routes_engineering import WorkflowCaseMutationRequest
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_case import CanonicalEngineeringCase
from racelab_engine.storage.controlled_workflow_mutation_repository import (
    ControlledWorkflowMutationIntegrityError,
    ControlledWorkflowMutationRepository,
)
from racelab_engine.storage.engineering_case_repository import (
    EngineeringCaseRepository,
)
from racelab_engine.storage.repository import RaceLabRepository
from test_controlled_workflow_service import _packet
from test_p3544_engineering_case_revision import (
    RUN_ID,
    SESSION_ID,
    _case,
    _seed_run,
)


def _case_with_workflow(
    case: CanonicalEngineeringCase,
    workflow: ControlledWorkflow,
) -> CanonicalEngineeringCase:
    values = case.model_dump(
        mode="python", exclude={"case_id", "case_sha256"}
    )
    values.update(
        active_workflow_id=workflow.workflow_id,
        active_workflow_revision=(
            routes_engineering._controlled_workflow_revision_sha256(workflow)
        ),
    )
    return CanonicalEngineeringCase.build(case_id=case.case_id, **values)


def _planned_workflow() -> ControlledWorkflow:
    now = datetime.now(timezone.utc)
    performance_binding = {
        "p32_opportunity_id": "p32-opportunity-case-bound",
        "p32_projection_sha256": "a" * 64,
        "engineering_knowledge_projection_sha256": "b" * 64,
    }
    return ControlledWorkflow(
        workflow_id="case-bound-workflow",
        created_at=now,
        updated_at=now,
        status="planned",
        source_run_id=RUN_ID,
        complaint="tight center",
        packet=_packet(),
        p32_opportunity_id=performance_binding["p32_opportunity_id"],
        p32_projection_sha256=performance_binding[
            "p32_projection_sha256"
        ],
        engineering_knowledge_projection_sha256=performance_binding[
            "engineering_knowledge_projection_sha256"
        ],
        reproduction_snapshot={
            "p352_performance_opportunity_binding": performance_binding
        },
    )


def test_cancel_is_exact_case_atomic_and_lost_response_replays_before_stale(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "workflow-case.sqlite"
    _seed_run(db_path)
    repository = RaceLabRepository(db_path)
    workflow = _planned_workflow()
    repository.save_controlled_workflow(workflow)
    initial_case = _case_with_workflow(_case(), workflow)
    case_repository = EngineeringCaseRepository(db_path)
    initial_revision = case_repository.finalize_case(initial_case)
    terminal_case = _case(next_move="Workflow cancelled; review current evidence.")

    monkeypatch.setattr(
        routes_engineering, "RaceLabRepository", lambda *_: repository
    )
    monkeypatch.setattr(
        routes_engineering,
        "EngineeringCaseRepository",
        lambda *_: EngineeringCaseRepository(db_path),
    )
    monkeypatch.setattr(
        routes_engineering,
        "_require_current_p19_authority",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        routes_engineering,
        "build_crew_chief_workspace",
        lambda *_args, **_kwargs: type(
            "Workspace", (), {"engineering_case": terminal_case}
        )(),
    )

    request = WorkflowCaseMutationRequest(
        case_run_id=RUN_ID,
        session_id=SESSION_ID,
        expected_case_sha256=initial_revision.case_sha256,
    )
    first = routes_engineering.cancel_controlled_workflow(
        workflow.workflow_id, request
    )
    replay = routes_engineering.cancel_controlled_workflow(
        workflow.workflow_id, request
    )

    assert replay == first
    assert first.workflow.status == "cancelled"
    assert first.workflow_revision_sha256 == (
        routes_engineering._controlled_workflow_revision_sha256(first.workflow)
    )
    assert first.workflow.reproduction_snapshot == {
        "p352_performance_opportunity_binding": {
            "p32_opportunity_id": workflow.p32_opportunity_id,
            "p32_projection_sha256": workflow.p32_projection_sha256,
            "engineering_knowledge_projection_sha256": (
                workflow.engineering_knowledge_projection_sha256
            ),
        }
    }
    assert ControlledWorkflow.model_validate(
        first.workflow.model_dump(mode="python")
    ) == first.workflow
    with pytest.raises(ValueError, match="exact case successor"):
        routes_engineering.ControlledWorkflowCaseMutationResponse.model_validate(
            {
                **first.model_dump(mode="python"),
                "workflow_revision_sha256": "f" * 64,
            }
        )
    assert first.case_revision.previous_case_sha256 == initial_revision.case_sha256
    assert case_repository.current_for_scope(RUN_ID, SESSION_ID) == first.case_revision
    connection = routes_engineering.initialize_database(db_path)
    assert connection.execute(
        "SELECT COUNT(*) FROM controlled_workflow_mutation_receipts"
    ).fetchone()[0] == 1
    connection.close()


def test_cancel_rolls_back_workflow_when_case_publication_fails(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "workflow-case-rollback.sqlite"
    _seed_run(db_path)
    repository = RaceLabRepository(db_path)
    workflow = _planned_workflow()
    repository.save_controlled_workflow(workflow)
    initial_revision = EngineeringCaseRepository(db_path).finalize_case(
        _case_with_workflow(_case(), workflow)
    )
    monkeypatch.setattr(
        routes_engineering, "RaceLabRepository", lambda *_: repository
    )
    monkeypatch.setattr(
        routes_engineering,
        "EngineeringCaseRepository",
        lambda *_: EngineeringCaseRepository(db_path),
    )
    monkeypatch.setattr(
        routes_engineering,
        "_require_current_p19_authority",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        routes_engineering,
        "_finalize_workflow_case_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("injected case publication failure")
        ),
    )

    with pytest.raises(HTTPException, match="injected case publication failure"):
        routes_engineering.cancel_controlled_workflow(
            workflow.workflow_id,
            WorkflowCaseMutationRequest(
                case_run_id=RUN_ID,
                session_id=SESSION_ID,
                expected_case_sha256=initial_revision.case_sha256,
            ),
        )

    assert repository.get_controlled_workflow(workflow.workflow_id) == workflow
    assert (
        EngineeringCaseRepository(db_path)
        .current_for_scope(RUN_ID, SESSION_ID)
        .case_sha256
        == initial_revision.case_sha256
    )
    connection = routes_engineering.initialize_database(db_path)
    assert connection.execute(
        "SELECT COUNT(*) FROM controlled_workflow_mutation_receipts"
    ).fetchone()[0] == 0
    connection.close()


def test_receipt_rejects_noncanonical_json_and_identity_rebinding(
    tmp_path,
) -> None:
    db_path = tmp_path / "workflow-receipt-integrity.sqlite"
    _seed_run(db_path)
    connection = routes_engineering.initialize_database(db_path)
    payload = {"schema_version": "test", "value": 1}
    ControlledWorkflowMutationRepository.save_receipt_in_transaction(
        connection,
        mutation_id="cwm_" + "1" * 24,
        request_sha256="1" * 64,
        action="cancel",
        run_id=RUN_ID,
        session_id=SESSION_ID,
        request_workflow_id="workflow-a",
        expected_case_sha256="2" * 64,
        result_case_sha256="3" * 64,
        result_workflow_id="workflow-a",
        result_workflow_revision_sha256="4" * 64,
        response_payload=payload,
    )
    connection.commit()

    with pytest.raises(
        ControlledWorkflowMutationIntegrityError, match="another request or scope"
    ):
        ControlledWorkflowMutationRepository.receipt_in_transaction(
            connection,
            "cwm_" + "1" * 24,
            request_sha256="5" * 64,
            action="cancel",
            run_id=RUN_ID,
            session_id=SESSION_ID,
            request_workflow_id="workflow-a",
            expected_case_sha256="2" * 64,
        )

    connection.execute(
        "UPDATE controlled_workflow_mutation_receipts "
        "SET response_json = ? WHERE mutation_id = ?",
        ('{ "schema_version": "test", "value": 1 }', "cwm_" + "1" * 24),
    )
    connection.commit()
    with pytest.raises(
        ControlledWorkflowMutationIntegrityError, match="not canonical JSON"
    ):
        ControlledWorkflowMutationRepository.receipt_in_transaction(
            connection,
            "cwm_" + "1" * 24,
            request_sha256="1" * 64,
            action="cancel",
            run_id=RUN_ID,
            session_id=SESSION_ID,
            request_workflow_id="workflow-a",
            expected_case_sha256="2" * 64,
        )
    connection.close()
