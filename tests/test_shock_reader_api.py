from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.io.ibt_types import IBTVariableDefinition
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import write_channel_metadata, write_telemetry_cache
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
        "recommendations",
        "warnings",
    }.issubset(payload)
    assert payload["corners"][0]["corner"] == "LF"
    assert len(payload["recommendations"]) <= 1


def test_shock_reader_api_missing_setup_has_no_numeric_suggestion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_shock_run(tmp_path, include_setup=False)
    client = TestClient(app)

    response = client.get("/api/runs/run-1/shock-reader?lap=1")

    assert response.status_code == 200
    rec = response.json()["recommendations"][0]
    assert rec["current_value"] is None
    assert rec["suggested_value"] is None
    assert rec["numeric_step"] is None


def test_shock_reader_api_returns_404_for_unknown_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get("/api/runs/missing/shock-reader")

    assert response.status_code == 404
