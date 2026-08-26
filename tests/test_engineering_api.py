from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.routes_p3_engineering import _has_corner_damper_setting

from api.main import app
from api import routes_engineering
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from test_controlled_workflow_service import _packet


client = TestClient(app)


def test_lightweight_workflow_catalog_never_builds_intelligence(monkeypatch) -> None:
    workflow = ControlledWorkflow(
        workflow_id="catalog-workflow",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        status="planned",
        source_run_id="run-a",
        complaint="tight entry",
        packet=_packet(),
    )

    class Repository:
        def list_controlled_workflow_catalog_for_run_scope(self, *_args, **_kwargs):
            return [workflow], ()

    monkeypatch.setattr(routes_engineering, "RaceLabRepository", Repository)
    monkeypatch.setattr(
        routes_engineering,
        "get_session",
        lambda *_args, **_kwargs: SimpleNamespace(run_ids=("run-a",)),
    )
    monkeypatch.setattr(
        routes_engineering,
        "build_run_intelligence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("catalog reads must not build intelligence")
        ),
    )
    first = routes_engineering.list_workflow_catalog("session-a", "run-a")
    second = routes_engineering.list_workflow_catalog("session-a", "run-a")
    assert first == second
    assert first[0].workflow_id == "catalog-workflow"


def test_score_route_defers_durability_until_final_p19_p33_atomic_commit(
    monkeypatch,
) -> None:
    del monkeypatch
    source = inspect.getsource(routes_engineering.score_controlled_workflow)

    receipt_replay = source.index("receipt_in_transaction")
    stale_check = source.index("current_for_scope_in_transaction")
    workflow_and_p33 = source.index(
        "save_scored_workflow_with_experience_if_scope_exclusive"
    )
    case_finalize = source.index("_finalize_workflow_case_in_transaction")
    receipt_save = source.index("_save_workflow_mutation_receipt")
    durable_commit = source.index("connection.commit()")
    cache_clear = source.rindex("clear_learning_cache()")

    assert receipt_replay < stale_check
    assert stale_check < workflow_and_p33 < case_finalize < receipt_save < durable_commit
    assert durable_commit < cache_clear


def test_controlled_workflow_api_exposes_strict_learning_capture_truth() -> None:
    properties = app.openapi()["components"]["schemas"]["ControlledWorkflow"][
        "properties"
    ]

    assert properties["learning_capture_state"]["enum"] == [
        "not_applicable",
        "captured",
        "blocked",
    ]
    assert properties["learning_capture_experience_id"]["anyOf"][0]["pattern"] == (
        "^p33x_[0-9a-f]{24}$"
    )
    assert properties["learning_capture_experience_sha256"]["anyOf"][0][
        "pattern"
    ] == "^[0-9a-f]{64}$"
    blocker = properties["learning_capture_blocker_reason"]["anyOf"][0]
    assert blocker["minLength"] == 1
    assert blocker["maxLength"] == 240
    assert properties["p32_opportunity_id"]["anyOf"][0]["type"] == "string"
    assert properties["p32_projection_sha256"]["anyOf"][0]["pattern"] == (
        "^[0-9a-f]{64}$"
    )
    assert properties["engineering_knowledge_projection_sha256"]["anyOf"][0][
        "pattern"
    ] == "^[0-9a-f]{64}$"


def test_score_route_returns_blocked_capture_truth_and_clears_learning_cache(
    monkeypatch,
) -> None:
    del monkeypatch
    schema = app.openapi()["components"]["schemas"][
        "ControlledWorkflowCaseMutationResponse"
    ]
    properties = schema["properties"]

    assert properties["schema_version"]["const"] == (
        "p3544.controlled-workflow-case-mutation.v1"
    )
    assert properties["case_revision"]["$ref"].endswith(
        "/EngineeringCaseRevision"
    )
    assert properties["workflow"]["$ref"].endswith("/ControlledWorkflow")
    assert {
        "mutation_id",
        "request_sha256",
        "expected_case_sha256",
        "workflow_revision_sha256",
    } <= set(schema["required"])


def test_damper_setup_provenance_requires_an_actual_corner_setting() -> None:
    assert _has_corner_damper_setting({"tape_percent": 40, "cross_weight_percent": 50.0}) is False
    assert _has_corner_damper_setting({"LF Shock": {"Rebound clicks": 6}}) is True
    assert _has_corner_damper_setting({"Chassis": {"LeftFront": {"HsCompSlope": "5"}}}) is True
    assert _has_corner_damper_setting({"extracted_values": {"lf": {"hs_comp_slope": 5}}}) is True


def test_damper_setup_provenance_rejects_unrelated_corner_settings() -> None:
    assert _has_corner_damper_setting({"Chassis": {"LeftFront": {"Camber": "-3.0"}}}) is False
    assert _has_corner_damper_setting({"Chassis": {"Differential": {"Compression": 6}}}) is False
    assert _has_corner_damper_setting({"LF Tire": {"Pressure clicks": 6}}) is False
    assert _has_corner_damper_setting({"LF": {"Slope": 6}}) is False


def test_engineering_api_rejects_client_asserted_test_evidence() -> None:
    response = client.post("/api/engineering/test-director/plan", json={
        "control_key": "cross_weight_percent",
        "current_value": 50.0,
        "direction_sign": 1,
        "hypothesis": "Reduce the repeatable entry correction demand.",
        "target_phase": "entry",
        "success_metrics": ["Entry phase time improves beyond noise"],
        "countereffects": ["Center speed does not worsen"],
        "evidence_links": [{
            "event_id": "entry-1",
            "eligible_lap": True,
            "valid_for_tuning": True,
            "phase": "entry",
            "related_setup_keys": ["cross_weight_percent"],
        }],
        "eligible_baseline_laps": 3,
        "context_matched": True,
        "driver_matched": True,
        "sim_integrity_clear": True,
    })
    assert response.status_code == 404


def test_engineering_score_api_rejects_client_asserted_execution() -> None:
    response = client.post("/api/engineering/test-director/score", json={
        "eligible_laps_a": 3,
        "eligible_laps_b": 3,
        "eligible_laps_a2": 3,
        "unrelated_setup_changes": 0,
        "control_key": "cross_weight_percent",
        "planned_b_value": 50.5,
        "observed_a_value": 50.0,
        "observed_b_value": 50.5,
        "observed_a2_value": 50.5,
        "unrelated_changed_controls": [],
        "context_match_score": 0.95,
        "driver_match_score": 0.95,
        "sim_integrity_score": 0.95,
        "phase_effect_b_vs_a_s": -0.08,
        "phase_effect_b_vs_a2_s": -0.07,
        "empirical_noise_s": 0.03,
        "countereffect_passed": True,
    })

    assert response.status_code == 404


def test_crew_chief_api_rejects_client_asserted_opportunity() -> None:
    response = client.post("/api/engineering/crew-chief/packet", json={
        "opportunity": {
            "start_pct": 20.0,
            "end_pct": 34.0,
            "phase": "entry",
            "observed_time_loss_s": 0.12,
            "empirical_noise_s": 0.03,
            "alignment_confidence": 0.92,
            "repeatable": True,
            "evidence_links": [{
                "event_id": "entry-1",
                "eligible_lap": True,
                "valid_for_tuning": True,
                "phase": "entry",
                "related_setup_keys": ["cross_weight_percent"],
            }],
            "source_channels": ["lap_dist_pct", "speed_mph", "yaw_rate"],
            "supporting_evidence": ["Loss repeats on three eligible laps."],
            "contradictory_evidence": [],
        },
        "canonical_symptom": "tight_entry",
        "candidates": [{
            "cause_bucket": "corner_balance",
            "control_key": "cross_weight_percent",
            "direction_sign": -1,
            "score": 0.86,
            "hypothesis": "A small reduction may reduce entry correction demand.",
            "success_metrics": ["Entry phase time improves beyond noise."],
            "countereffects": ["Exit stability must not worsen."],
            "supporting_event_ids": ["entry-1"],
            "blocked_reasons": [],
        }],
        "current_setup_values": {"cross_weight_percent": 50.0},
        "eligible_baseline_laps": 3,
        "context_matched": True,
        "driver_matched": True,
        "sim_integrity_clear": True,
    })

    assert response.status_code == 404


def test_legacy_public_authority_routes_are_absent_from_openapi() -> None:
    paths = app.openapi()["paths"]
    for path in (
        "/api/engineering/test-director/plan",
        "/api/engineering/test-director/score",
        "/api/engineering/crew-chief/packet",
        "/api/engineering/experimentation/unlock",
        "/api/engineering/experimentation/design",
    ):
        assert path not in paths
        assert client.post(path, json={}).status_code == 404
    assert "/api/engineering/workflows/{workflow_id}/score" in paths


def test_workflow_creation_requires_exact_session_and_rejects_action_payloads(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "api.routes_engineering.create_workflow",
        lambda *_args, **_kwargs: pytest.fail(
            "Invalid client authority must not reach workflow planning."
        ),
    )
    missing_session = client.post("/api/engineering/workflows", json={
        "run_id": "run-1",
        "complaint": "tight on entry",
    })
    asserted_packet = client.post("/api/engineering/workflows", json={
        "run_id": "run-1",
        "session_id": "session-1",
        "complaint": "tight on entry",
        "packet": {
            "decision": "test",
            "primary_test": {"exact_change": "Set cross weight to 51%."},
        },
    })

    assert missing_session.status_code == 422
    assert asserted_packet.status_code == 422


def test_workflow_candidate_is_not_persisted_when_p19_withholds_authority(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "api.routes_engineering.build_authorized_workflow_candidate",
        lambda *_args, **_kwargs: pytest.fail(
            "The retired direct route must never build or persist a candidate."
        ),
    )

    response = client.post("/api/engineering/workflows", json={
        "run_id": "run-1",
        "session_id": "session-1",
        "complaint": "tight on entry",
    })

    assert response.status_code == 409
    assert "Direct workflow creation is retired" in response.json()["detail"]
    assert "atomic route" in response.json()["detail"]


def test_workflow_route_forwards_driver_decision_context(monkeypatch) -> None:
    del monkeypatch
    request = routes_engineering.WorkflowStartRequest.model_validate({
        "run_id": "run-1",
        "session_id": "session-1",
        "complaint": "loose over the Turn 4 exit seam",
        "selected_lap": 7,
        "lap_scope": "single_lap",
        "window_start_lap": None,
        "window_end_lap": None,
        "representative_lap": None,
        "selected_zone_start_pct": 72.5,
        "selected_zone_end_pct": 78.0,
        "selected_zone_label": "Turn 4 exit",
        "selected_phase": "exit",
        "objective": "long-run",
        "priority": "exit-drive",
    })

    assert request.run_id == "run-1"
    assert request.complaint == "loose over the Turn 4 exit seam"
    assert request.selected_lap == 7
    assert request.lap_scope == "single_lap"
    assert request.selected_zone_start_pct == 72.5
    assert request.selected_zone_end_pct == 78.0
    assert request.selected_zone_label == "Turn 4 exit"
    assert request.selected_phase == "exit"
    assert request.objective == "long-run"
    assert request.priority == "exit-drive"


def test_workflow_route_binds_the_exact_lap_window_and_representative(monkeypatch) -> None:
    del monkeypatch
    request = routes_engineering.WorkflowStartRequest.model_validate({
        "run_id": "run-window",
        "session_id": "session-window",
        "complaint": "tight through the long-run window",
        "selected_lap": 5,
        "lap_scope": "lap_window",
        "window_start_lap": 3,
        "window_end_lap": 7,
        "representative_lap": 5,
    })

    assert request.lap_scope == "lap_window"
    assert request.selected_lap == 5
    assert request.window_start_lap == 3
    assert request.window_end_lap == 7
    assert request.representative_lap == 5


def test_workflow_route_rejects_incomplete_or_mismatched_lap_windows(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routes_engineering.create_workflow",
        lambda *_args, **_kwargs: pytest.fail("An invalid window must not reach planning."),
    )
    missing_bound = client.post("/api/engineering/workflows", json={
        "run_id": "run-window",
        "session_id": "session-window",
        "complaint": "tight through the long-run window",
        "selected_lap": 5,
        "lap_scope": "lap_window",
        "window_end_lap": 7,
        "representative_lap": 5,
    })
    mismatched_representative = client.post("/api/engineering/workflows", json={
        "run_id": "run-window",
        "session_id": "session-window",
        "complaint": "tight through the long-run window",
        "selected_lap": 5,
        "lap_scope": "lap_window",
        "window_start_lap": 3,
        "window_end_lap": 7,
        "representative_lap": 6,
    })

    assert missing_bound.status_code == 422
    assert mismatched_representative.status_code == 422


def test_workflow_cancel_route_forwards_the_exact_workflow_id(monkeypatch) -> None:
    captured: list[str] = []

    def fake_cancel_workflow(workflow_id: str, **_kwargs):
        captured.append(workflow_id)
        raise ValueError("captured")

    monkeypatch.setattr("api.routes_engineering.cancel_workflow", fake_cancel_workflow)
    response = client.post("/api/engineering/workflows/aba-exact/cancel")

    assert response.status_code == 422
    assert captured == []
    missing = {item["loc"][-1] for item in response.json()["detail"]}
    assert "body" in missing


def test_advanced_api_rejects_client_asserted_history() -> None:
    history = {
        "phase_exit_passed": {f"P{index}": False for index in range(7)},
        "controlled_experiments": 0,
        "distinct_contexts": 0,
        "experiments_per_factor": {},
        "held_out_validation_score": None,
        "contradiction_rate": None,
        "traceable_fraction": 0.0,
    }
    unlock = client.post("/api/engineering/experimentation/unlock", json=history)
    assert unlock.status_code == 404

    design = client.post("/api/engineering/experimentation/design", json={
        "history": history,
        "factors": [
            {"key": "cross", "low": 49.5, "high": 50.5},
            {"key": "bias", "low": 51.0, "high": 52.0},
        ],
    })
    assert design.status_code == 404
