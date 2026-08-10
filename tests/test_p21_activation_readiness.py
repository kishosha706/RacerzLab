from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.evaluation.activation_gates import (
    ActivationEvidence,
    evaluate_activation_gate,
    p21_activation_gates,
    save_activation_decision,
)
from racelab_engine.evaluation.readiness import build_learning_readiness_projection
from racelab_engine.storage.db import initialize_database


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _gate(capability: str):
    return next(
        gate
        for gate in p21_activation_gates(created_at=NOW)
        if gate.capability_key == capability
    )


def test_every_advanced_capability_has_a_frozen_non_activated_gate():
    gates = p21_activation_gates(created_at=NOW)
    assert len(gates) == 13
    assert len({gate.capability_key for gate in gates}) == len(gates)
    assert all(not gate.manual_override_allowed for gate in gates)
    assert all(gate.maximum_state != "activated" for gate in gates)
    assert _gate("bayesian_optimization").maximum_state == "shadow"
    assert _gate("multi_control_optimization").maximum_state == "shadow"


def test_insufficient_data_fails_closed_and_is_auditable(tmp_path):
    gate = _gate("change_point")
    evidence = ActivationEvidence(
        dataset_counts={},
        counts={},
        ready_prerequisites=(),
        prospective_units=0,
        dataset_hashes=(),
        code_hash="abcdef123456",
    )
    decision = evaluate_activation_gate(gate, evidence, evaluated_at=NOW)
    assert decision.state == "locked_insufficient_data"
    assert decision.auditable
    assert not decision.manual_override_used
    assert decision.evaluation.count_deficits == {
        "uninterrupted_stints": 30,
        "null_stints": 10,
    }
    assert save_activation_decision(decision, db_path=tmp_path / "gates.sqlite")
    assert not save_activation_decision(decision, db_path=tmp_path / "gates.sqlite")


def test_counts_alone_can_reach_shadow_but_not_activation():
    gate = _gate("change_point")
    evidence = ActivationEvidence(
        dataset_counts={"long_run_tire": 1, "null_no_change": 1},
        counts={"uninterrupted_stints": 30, "null_stints": 10},
        ready_prerequisites=(),
        prospective_units=100,
        dataset_hashes=("a" * 64,),
        code_hash="abcdef123456",
    )
    decision = evaluate_activation_gate(gate, evidence, evaluated_at=NOW)
    assert decision.state == "shadow"
    assert "No frozen evaluation artifact" in decision.blockers[0]


def test_bayesian_and_multi_control_never_exceed_shadow_ceiling():
    for capability in ("bayesian_optimization", "multi_control_optimization"):
        gate = _gate(capability)
        evidence = ActivationEvidence(
            dataset_counts={"controlled_aba": 1},
            counts={
                "controlled_workflows": 100,
                "contexts": 3,
                "per_factor": 6,
                "multi_factor_experiments": 30,
            },
            ready_prerequisites=gate.prerequisite_keys,
            prospective_units=100,
            dataset_hashes=("a" * 64,),
            code_hash="abcdef123456",
        )
        decision = evaluate_activation_gate(gate, evidence, evaluated_at=NOW)
        assert decision.state == "shadow"


def _insert_run(database: Path) -> None:
    connection = initialize_database(database)
    with connection:
        connection.execute(
            "INSERT INTO runs "
            "(run_id, source_file, import_time, imported_at, car_name, track_name, "
            "session_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "fixture.ibt",
                NOW.isoformat(),
                NOW.isoformat(),
                "Next Gen",
                "Atlanta",
                "{}",
            ),
        )
    connection.close()


def test_learning_readiness_reports_qualified_counts_not_archive_volume(tmp_path):
    database = tmp_path / "readiness.sqlite"
    _insert_run(database)
    projection = build_learning_readiness_projection("run-1", db_path=database)
    counts = {count.key: count.current for count in projection.counts}
    assert projection.archived_runs == 1
    assert counts["independent_sessions"] == 0
    assert counts["controlled_workflows"] == 0
    assert counts["null_stints"] == 0
    assert projection.vehicle_profile_status == "geometry incomplete"
    assert projection.advanced_models_summary == "Shadow only"
    assert projection.deterministic_authority == "P19 reasoning / P20 awareness"
    assert next(
        capability
        for capability in projection.capabilities
        if capability.capability_key == "change_point"
    ).state == "shadow"
    assert next(
        capability
        for capability in projection.capabilities
        if capability.capability_key == "probability_calibration"
    ).state == "locked"


def test_learning_readiness_route_is_bounded_and_scope_safe(monkeypatch):
    import api.routes_evaluation as route

    monkeypatch.setattr(
        route,
        "build_learning_readiness_projection",
        lambda run_id, session_id=None: {
            "run_id": run_id,
            "session_id": session_id,
            "scope_key": f"{run_id}:{session_id or 'no-session'}",
            "generated_at": NOW.isoformat(),
            "deterministic_authority": "P19 reasoning / P20 awareness",
            "advanced_models_summary": "Shadow only",
            "archived_sessions": 0,
            "archived_runs": 1,
            "counts": [],
            "campaigns": [],
            "capabilities": [],
            "vehicle_profile_status": "geometry incomplete",
            "vehicle_profile_fields_ready": [],
            "vehicle_profile_fields_blocked": [
                "wheelbase",
                "front_track_width",
                "rear_track_width",
            ],
            "debts": [],
            "offline_evaluation_only": True,
        },
    )
    response = TestClient(app).get(
        "/api/evaluation/learning-readiness?run_id=run-1&session_id=session-1"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope_key"] == "run-1:session-1"
    assert payload["offline_evaluation_only"] is True
    assert "trace" not in payload
    assert "telemetry" not in payload


def test_learning_readiness_ui_is_learning_only_and_stale_safe():
    root = Path(__file__).resolve().parents[1]
    engineer = (root / "ui/src/tabs/EngineerTab.tsx").read_text(encoding="utf-8")
    client = (root / "ui/src/api/client.ts").read_text(encoding="utf-8")
    assert "if (!learning)" in engineer
    assert "sequence !== readinessSequence.current" in engineer
    assert "projection.run_id !== requestedRunId" in engineer
    assert "(projection.session_id ?? null) !== requestedSessionId" in engineer
    assert "Advanced models: {projection.advanced_models_summary}" in engineer
    assert "Production authority stays with" in engineer
    assert "Archived does not mean qualified" in engineer
    assert engineer.count("learning && <LearningReadinessCard") == 2
    assert engineer.count("onStartCampaign={startCampaign}") == 3
    assert "/api/evaluation/learning-readiness" in client
