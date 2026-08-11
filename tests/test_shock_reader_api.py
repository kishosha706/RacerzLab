from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.io.ibt_types import IBTVariableDefinition
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import (
    telemetry_manifest_path,
    write_channel_metadata,
    write_telemetry_cache,
)
from racelab_engine.storage.repository import RaceLabRepository
from test_setup_evidence_adapter import _configure_env


def _seed_shock_run(tmp_path: Path, *, include_setup: bool = True) -> None:
    data_dir = tmp_path / "data"
    db_path = tmp_path / "racelab.sqlite"
    rows = []
    for idx in range(120):
        value = 0.2 if idx < 80 else -0.2
        rows.append(
            {
                "lap": 1,
                "session_time": idx / 60,
                "lap_dist_pct": idx / 119,
                "speed_mph": 160.0,
                "lf_shock_vel_in_s": value,
                "rf_shock_vel_in_s": value,
                "lr_shock_vel_in_s": value,
                "rr_shock_vel_in_s": value,
                "rear_scrape_margin_mm": 20.0,
            }
        )
    write_telemetry_cache("run-1", rows, data_dir=data_dir)
    write_channel_metadata(
        "run-1",
        [IBTVariableDefinition(name=name, description=name, unit=None, data_type="float", count=1) for name in rows[0]],
        data_dir=data_dir,
    )
    setup = None
    if include_setup:
        setup = SetupSnapshot(
            setup_id="run-1:setup",
            run_id="run-1",
            setup_name="Baseline",
            extracted_values={
                corner: {
                    "ls_compression": 5,
                    "hs_compression": 5,
                    "hs_comp_slope": 5,
                    "ls_rebound": 5,
                    "hs_rebound": 5,
                    "hs_reb_slope": 5,
                }
                for corner in ("lf", "rf", "lr", "rr")
            },
        )
    repo = RaceLabRepository(db_path=db_path)
    repo.initialize()
    repo.save_import(
        RunOverview(
            run_id="run-1",
            session=SessionSummary(
                run_id="run-1",
                car_name="NASCAR Cup Series Next Gen Chevrolet Camaro ZL1",
                car_path="stockcars chevycamarozl12022",
                track_name="Charlotte Oval",
                track_display_name="Charlotte Oval",
            ),
            laps=[
                LapSummary(
                    lap_id="run-1:lap:1",
                    run_id="run-1",
                    lap_number=1,
                    lap_type="timed",
                    is_complete=True,
                    is_useful=True,
                    lap_time=30.0,
                    sample_count=120,
                )
            ],
            setup_snapshot=setup,
        )
    )


def test_shock_reader_api_returns_stable_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path)
    client = TestClient(app)

    response = client.get("/api/runs/run-1/shock-reader?lap=1")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "run_id",
        "lap_window",
        "boundary_in_s",
        "bin_width_in_s",
        "setup_snapshot_available",
        "corners",
        "setup_authority",
        "warnings",
    }.issubset(payload)
    assert payload["corners"][0]["corner"] == "LF"
    assert payload["boundary_in_s"] == 1.5
    assert "Official iRacing Next Gen guidance" in payload["boundary_basis"]
    assert payload["setup_authority"] == "withheld"
    serialized = json.dumps(payload).casefold()
    for forbidden in ("recommendations", "suggested_value", "target_value_raw", "action_text", "keep_if", "undo_if"):
        assert forbidden not in serialized


def test_shock_reader_api_returns_recovery_conflict_for_unbound_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path)
    path = telemetry_manifest_path(tmp_path / "data", "run-1")
    identity = json.loads(path.read_text(encoding="utf-8"))
    identity.pop("telemetry_cache_sha256")
    path.write_text(json.dumps(identity), encoding="utf-8")

    response = TestClient(app).get("/api/runs/run-1/shock-reader?lap=1")

    assert response.status_code == 409
    assert "re-imported" in response.json()["detail"]


def test_client_query_cannot_inject_a_shock_option_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path)
    client = TestClient(app)

    response = client.get(
        "/api/runs/run-1/shock-reader?lap=1"
        "&legal_options_by_corner_setting=4"
        "&legal_option_provenance_by_corner_setting=client-claim"
    )

    assert response.status_code == 422
    detail = response.json()["detail"].casefold()
    assert "unsupported shock reader query fields" in detail
    assert "legal_options_by_corner_setting" in detail


def test_shock_reader_api_missing_setup_has_no_numeric_suggestion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path, include_setup=False)
    client = TestClient(app)

    response = client.get("/api/runs/run-1/shock-reader?lap=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["setup_snapshot_available"] is False
    assert all(
        all(value is None for value in corner["setup_values"].values())
        for corner in payload["corners"]
    )
    assert "suggested_value" not in json.dumps(payload).casefold()


def test_shock_reader_api_returns_404_for_unknown_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get("/api/runs/missing/shock-reader")

    assert response.status_code == 404


def test_shock_reader_api_rejects_wide_or_partial_observation_zone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path)
    client = TestClient(app)

    assert client.get("/api/runs/run-1/shock-reader?lap=1&zone_start_pct=20").status_code == 400
    assert client.get(
        "/api/runs/run-1/shock-reader?lap=1&zone_start_pct=10&zone_end_pct=40"
    ).status_code == 400


def test_client_cannot_override_server_selected_shock_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path)
    client = TestClient(app)

    response = client.get("/api/runs/run-1/shock-reader?lap=1&boundary_in_s=99")

    assert response.status_code == 422
    assert "boundary_in_s" in response.json()["detail"]
