from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.routes_p3_engineering import _has_corner_damper_setting

from api.main import app


client = TestClient(app)


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
    candidate = object()
    monkeypatch.setattr(
        "api.routes_engineering.create_workflow",
        lambda *_args, **_kwargs: candidate,
    )
    monkeypatch.setattr(
        "api.routes_engineering._derive_p19_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("P19 withheld setup authority")
        ),
    )
    monkeypatch.setattr(
        "api.routes_engineering.persist_workflow_candidate",
        lambda *_args, **_kwargs: pytest.fail(
            "A P19-rejected candidate must never be persisted."
        ),
    )

    response = client.post("/api/engineering/workflows", json={
        "run_id": "run-1",
        "session_id": "session-1",
        "complaint": "tight on entry",
    })

    assert response.status_code == 409
    assert "P19 withheld" in response.json()["detail"]


def test_workflow_route_forwards_driver_decision_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_workflow(run_id: str, complaint: str, **kwargs):
        captured.update({"run_id": run_id, "complaint": complaint, **kwargs})
        raise ValueError("captured")

    monkeypatch.setattr("api.routes_engineering.create_workflow", fake_create_workflow)
    response = client.post("/api/engineering/workflows", json={
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

    assert response.status_code == 409
    assert captured["run_id"] == "run-1"
    assert captured["complaint"] == "loose over the Turn 4 exit seam"
    assert captured["selected_lap"] == 7
    assert captured["lap_scope"] == "single_lap"
    assert captured["selected_zone_start_pct"] == 72.5
    assert captured["selected_zone_end_pct"] == 78.0
    assert captured["selected_zone_label"] == "Turn 4 exit"
    assert captured["selected_phase"] == "exit"
    assert captured["objective"] == "long-run"
    assert captured["priority"] == "exit-drive"
    assert captured["persist"] is False


def test_workflow_route_binds_the_exact_lap_window_and_representative(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_workflow(run_id: str, complaint: str, **kwargs):
        captured.update({"run_id": run_id, "complaint": complaint, **kwargs})
        raise ValueError("captured")

    monkeypatch.setattr("api.routes_engineering.create_workflow", fake_create_workflow)
    response = client.post("/api/engineering/workflows", json={
        "run_id": "run-window",
        "session_id": "session-window",
        "complaint": "tight through the long-run window",
        "selected_lap": 5,
        "lap_scope": "lap_window",
        "window_start_lap": 3,
        "window_end_lap": 7,
        "representative_lap": 5,
    })

    assert response.status_code == 409
    assert captured["lap_scope"] == "lap_window"
    assert captured["selected_lap"] == 5
    assert captured["window_start_lap"] == 3
    assert captured["window_end_lap"] == 7
    assert captured["representative_lap"] == 5


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

    assert response.status_code == 409
    assert captured == ["aba-exact"]


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
