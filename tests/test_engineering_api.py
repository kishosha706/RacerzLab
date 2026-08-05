from __future__ import annotations

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
    assert response.status_code == 422


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

    assert response.status_code == 422


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

    assert response.status_code == 422


def test_server_evidence_routes_accept_only_run_identity_and_driver_intent() -> None:
    response = client.post("/api/engineering/crew-chief/packet", json={
        "run_id": "missing-run",
        "complaint": "tight on entry",
    })

    assert response.status_code == 404
    assert "Run not found" in response.json()["detail"]


def test_workflow_route_forwards_driver_decision_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_workflow(run_id: str, complaint: str, **kwargs):
        captured.update({"run_id": run_id, "complaint": complaint, **kwargs})
        raise ValueError("captured")

    monkeypatch.setattr("api.routes_engineering.create_workflow", fake_create_workflow)
    response = client.post("/api/engineering/workflows", json={
        "run_id": "run-1",
        "complaint": "loose over the Turn 4 exit seam",
        "selected_lap": 7,
        "selected_zone_start_pct": 72.5,
        "selected_zone_end_pct": 78.0,
        "selected_zone_label": "Turn 4 exit",
        "selected_phase": "exit",
        "objective": "long-run",
        "priority": "exit-drive",
    })

    assert response.status_code == 409
    assert captured == {
        "run_id": "run-1",
        "complaint": "loose over the Turn 4 exit seam",
        "selected_lap": 7,
        "selected_zone_start_pct": 72.5,
        "selected_zone_end_pct": 78.0,
        "selected_zone_label": "Turn 4 exit",
        "selected_phase": "exit",
        "objective": "long-run",
        "priority": "exit-drive",
    }


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
    assert unlock.status_code == 409

    design = client.post("/api/engineering/experimentation/design", json={
        "history": history,
        "factors": [
            {"key": "cross", "low": 49.5, "high": 50.5},
            {"key": "bias", "low": 51.0, "high": 52.0},
        ],
    })
    assert design.status_code == 409
    assert "server-derived" in design.json()["detail"]
