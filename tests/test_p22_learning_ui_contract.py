from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import app


def test_p22_learning_operations_are_learning_only_and_use_no_new_workspace():
    root = Path(__file__).resolve().parents[1]
    engineer = (root / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    app = (root / "ui/src/App.tsx").read_text(encoding="utf-8")
    client = (root / "ui/src/api/client.ts").read_text(encoding="utf-8")
    imports = (root / "api/routes_imports.py").read_text(encoding="utf-8")
    controlled = (
        root / "racelab_engine/services/controlled_workflow_service.py"
    ).read_text(encoding="utf-8")
    assert "Today&apos;s test session" in engineer
    assert "RacerZLab Learning Ledger" in engineer
    assert "Advanced capability review" in engineer
    assert "Decision: REMAIN LOCKED" in engineer
    assert "onStartCampaign={startCampaign}" in engineer
    assert "/api/evaluation/campaign-operations/start" in client
    assert "/api/evaluation/prospective-predictions" in client
    assert "Freeze P19 prediction before B" in engineer
    assert "assess_active_operations_for_run" in imports
    assert "attach_matching_outcome_after_score" in controlled
    assert "learning && <LearningReadinessCard" in engineer
    assert "Learning Ledger" not in app


def test_p22_director_language_does_not_claim_information_gain_or_setup_authority():
    root = Path(__file__).resolve().parents[1]
    operations = (
        root / "racelab_engine/evaluation/learning_operations.py"
    ).read_text(encoding="utf-8")
    prospective = (
        root / "racelab_engine/evaluation/prospective.py"
    ).read_text(encoding="utf-8")
    assert 'formal_information_gain: Literal[False] = False' in operations
    assert 'authority: Literal["collection_guidance_only"]' in operations
    assert 'authority: Literal["data_collection_only"]' in operations
    assert 'authority: Literal["shadow_only"]' in prospective
    assert "P19 has not authorized one exact controlled setup test" in prospective


def test_public_prospective_surface_returns_only_a_non_authoritative_receipt(
    monkeypatch,
):
    frozen = SimpleNamespace(
        prediction_id="ptp-" + "a" * 20,
        operation_id="operation-1",
        source_run_id="run-1",
        session_id="session-1",
        predicted_at=datetime(2026, 8, 10, tzinfo=UTC),
        reasoning_snapshot={"measurement_plan": {"control_key": "cross_weight"}},
        context={"current_value": "50.0%", "proposed_value": "50.2%"},
        observed_policy_result="undo",
    )
    monkeypatch.setattr(
        "api.routes_evaluation.freeze_p19_controlled_prediction",
        lambda *args, **kwargs: frozen,
    )
    monkeypatch.setattr(
        "api.routes_evaluation.save_prospective_prediction",
        lambda *args, **kwargs: True,
    )

    response = TestClient(app).post(
        "/api/evaluation/prospective-predictions",
        json={
            "operation_id": "operation-1",
            "run_id": "run-1",
            "session_id": "session-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "prediction_id": "ptp-" + "a" * 20,
        "operation_id": "operation-1",
        "source_run_id": "run-1",
        "session_id": "session-1",
        "predicted_at": "2026-08-10T00:00:00Z",
        "prospective": True,
        "authority": "shadow_only",
        "setup_authorized": False,
    }


def test_public_prospective_outcome_route_and_authority_schemas_are_absent():
    paths = app.openapi()["paths"]
    outcome_path = "/api/evaluation/prospective-predictions/{prediction_id}/outcome"
    assert outcome_path not in paths
    assert TestClient(app).post(
        "/api/evaluation/prospective-predictions/ptp-hostile/outcome",
        json={"workflow_id": "workflow-secret"},
    ).status_code == 404

    schemas = app.openapi()["components"]["schemas"]
    receipt = schemas["ProspectivePredictionReceipt"]["properties"]
    forbidden = {
        "reasoning_snapshot",
        "context",
        "control_key",
        "current_value",
        "proposed_value",
        "observed_policy_result",
        "p19_outcome_snapshot",
    }
    assert forbidden.isdisjoint(receipt)
    assert "ProspectiveTestPrediction" not in schemas
    assert "ProspectiveTestOutcome" not in schemas
