from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from test_setup_evidence_adapter import _configure_env, _seed_run


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
    assert "hidden_evidence_summary" not in payload
    assert "evidence_groups" not in payload


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


def test_dial_in_api_returns_404_for_unknown_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post("/api/runs/missing-run/dial-in", json={"complaint": "loose off"})

    assert response.status_code == 404
