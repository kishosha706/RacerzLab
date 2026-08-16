from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.schemas import DialInRequest
from test_setup_evidence_adapter import _configure_env, _seed_run


def test_dial_in_request_decision_context_is_backward_compatible_and_typed() -> None:
    legacy = DialInRequest.model_validate({"complaint": "tight center"})
    assert legacy.objective == "race-pace"
    assert legacy.priority == "overall-pace"
    assert legacy.selected_phase is None
    assert legacy.selected_zone_start_pct is None

    contextual = DialInRequest.model_validate({
        "complaint": "tight center",
        "selected_zone_start_pct": 23.5,
        "selected_zone_end_pct": 31.0,
        "selected_zone_label": "Turn 3 center",
        "selected_phase": "center",
        "objective": "long-run",
        "priority": "tire-life",
    })
    assert contextual.selected_zone_label == "Turn 3 center"
    assert contextual.selected_phase == "center"
    assert contextual.objective == "long-run"
    assert contextual.priority == "tire-life"


def test_dial_in_api_returns_clean_response_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    client = TestClient(app)

    response = client.post("/api/runs/run-1/dial-in", json={"complaint": "loose off"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-1"
    assert payload["interpreted_symptom"] == "loose_exit"
    assert len(payload["top_swings"]) <= 3
    assert payload["top_swings"][0]["mechanism_to_verify"]
    assert payload["top_swings"][0]["candidate_control_label"]
    assert payload["top_swings"][0]["measurement_needed"]
    assert payload["top_swings"][0]["validate_with_labels"]
    assert payload["top_swings"][0]["watch_for_labels"] is not None
    assert payload["evidence_strength"]["setup_test_ready"] is False
    assert all(
        swing["knowledge_level"] != "p19_testable_control"
        for swing in payload["top_swings"]
    )
    assert "controlled p19 workflow" in payload["next_step"].lower()
    assert "hidden_evidence_summary" not in payload
    assert "evidence_groups" not in payload
    dumped = json.dumps(payload).lower()
    for forbidden in [
        "change_this",
        "proposed_value",
        "current_value",
        "direction_sign",
        "change_size",
        "keep_if",
        "undo_if",
        "one_change_test",
        "control_expectation",
        "control_guardrail",
    ]:
        assert forbidden not in dumped
    assert "increasing cross weight" not in dumped
    assert "stiffer" not in dumped
    assert "ai recommends" not in dumped
    assert "guaranteed" not in dumped


def test_dial_in_api_accepts_limit_nine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
            "speed_mph": 185.0,
            "lf_tire_temp_inner_c": 85.0,
            "rf_tire_temp_inner_c": 90.0,
            "lr_tire_temp_inner_c": 92.0,
            "rr_tire_temp_inner_c": 88.0,
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 1.0,
            "rr_shock_vel_in_s": 1.2,
        },
    )
    client = TestClient(app)

    response = client.post("/api/runs/run-1/dial-in", json={"complaint": "tight center", "limit": 9})

    assert response.status_code == 200
    payload = response.json()
    assert 3 < len(payload["top_swings"]) <= 9
    assert sum(1 for swing in payload["top_swings"] if swing["strength_label"] == "Package-level lever") <= 1
    assert {swing["setup_area"] for swing in payload["top_swings"]}.isdisjoint({"track_bar", "truck_arm_mount", "bump_stop", "packer"})
    assert "hidden_evidence_summary" not in payload


def test_dial_in_api_accepts_limit_eighteen_for_frontend_show_more(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
            "speed_mph": 185.0,
            "lf_tire_temp_inner_c": 85.0,
            "rf_tire_temp_inner_c": 90.0,
            "lr_tire_temp_inner_c": 92.0,
            "rr_tire_temp_inner_c": 88.0,
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 1.0,
            "rr_shock_vel_in_s": 1.2,
        },
    )
    client = TestClient(app)

    response = client.post("/api/runs/run-1/dial-in", json={"complaint": "tight center", "limit": 18})

    assert response.status_code == 200
    payload = response.json()
    assert 3 < len(payload["top_swings"]) <= 18
    assert len({swing["id"] for swing in payload["top_swings"]}) == len(payload["top_swings"])
    assert "hidden_evidence_summary" not in payload


def test_dial_in_api_can_include_debug_evidence_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    client = TestClient(app)

    response = client.post(
        "/api/runs/run-1/dial-in",
        json={"complaint": "loose off", "include_debug_evidence": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["hidden_evidence_summary"]["evidence_flags"]


def test_dial_in_api_normal_response_hides_diffuser_force_wording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "front_center_rh_in": 1.9,
            "rear_center_rh_in": 2.6,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
            "speed_mph": 185.0,
        },
    )
    client = TestClient(app)

    response = client.post("/api/runs/run-1/dial-in", json={"complaint": "rear scrape"})

    assert response.status_code == 200
    dumped = json.dumps(response.json()).lower()
    assert "measured downforce" not in dumped
    assert "hidden_evidence_summary" not in dumped


def test_dial_in_api_returns_clarification_without_swings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path)
    client = TestClient(app)

    response = client.post("/api/runs/run-1/dial-in", json={"complaint": "loose"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["clarification"]["needed"] is True
    assert payload["clarification"]["question"] == "Where is it happening?"
    assert payload["top_swings"] == []
    assert "hidden_evidence_summary" not in payload


def test_dial_in_api_returns_404_for_unknown_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post("/api/runs/missing-run/dial-in", json={"complaint": "loose off"})

    assert response.status_code == 404
