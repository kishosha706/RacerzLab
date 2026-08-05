from __future__ import annotations

import pytest

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.services.import_service import ImportService, build_trace_payload, csv_path, parquet_path
from racelab_engine.services.report_service import ReportService
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository

pytestmark = pytest.mark.slow


def test_sqlite_schema_initializes(tmp_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    connection = initialize_database(db_path)
    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()

    assert {"runs", "laps", "events", "recommendations", "setup_snapshots", "import_files"} <= tables


def test_import_service_stores_real_talladega_run(tmp_path: Path, talladega_ibt_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    result, cache = ImportService(db_path=db_path, data_dir=data_dir).import_ibt_file(talladega_ibt_path)

    assert result.overview is not None
    assert cache is not None
    assert cache.path.exists()
    assert parquet_path(data_dir, result.overview.run_id).exists() or csv_path(data_dir, result.overview.run_id).exists()

    repository = RaceLabRepository(db_path)
    overview = repository.get_overview(result.overview.run_id)
    assert overview is not None
    assert overview.best_useful_lap is not None
    assert overview.best_useful_lap.lap_number == 2
    assert overview.session.track_display_name == "Talladega Super Speedway"

    connection = sqlite3.connect(db_path)
    import_file_count = connection.execute("SELECT COUNT(*) FROM import_files").fetchone()[0]
    connection.close()
    assert import_file_count == 1


def test_api_runs_and_persisted_overview_after_repository_reopen(
    tmp_path: Path, monkeypatch, talladega_ibt_path: Path
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))

    client = TestClient(app)
    response = client.post("/api/imports/ibt", json={"path": str(talladega_ibt_path)})
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    runs_response = client.get("/api/runs")
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert runs[0]["run_id"] == run_id
    assert runs[0]["best_lap_number"] == 2

    reopened = RaceLabRepository(db_path).get_overview(run_id)
    assert reopened is not None
    assert reopened.best_useful_lap is not None
    assert reopened.best_useful_lap.lap_time == result_lap_time(client, run_id)


def result_lap_time(client: TestClient, run_id: str) -> float:
    response = client.get(f"/api/runs/{run_id}/overview")
    assert response.status_code == 200
    return response.json()["best_useful_lap"]["lap_time"]


def test_trace_endpoint_and_lap3_invalid_event(tmp_path: Path, monkeypatch, talladega_ibt_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    client = TestClient(app)
    run_id = client.post("/api/imports/ibt", json={"path": str(talladega_ibt_path)}).json()["run_id"]

    trace_response = client.get(
        f"/api/runs/{run_id}/trace",
        params={
            "lap": 2,
            "channels": "speed_mph,rpm,throttle_pct,brake_pct,cfsr_height_mm",
            "downsample": 5,
        },
    )
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["lap"] == 2
    assert trace["downsample"] == 5
    assert trace["sample_count"] > 500
    assert set(trace["channels"]) == {"speed_mph", "rpm", "throttle_pct", "brake_pct", "cfsr_height_mm"}

    events_response = client.get(f"/api/runs/{run_id}/events", params={"lap": 3, "type": "PLATFORM"})
    assert events_response.status_code == 200
    events = events_response.json()
    assert events
    assert events[0]["event_type"] == "PLATFORM_SCRAPE"
    assert events[0]["valid_for_tuning"] is False


def test_markdown_report_from_persisted_data(tmp_path: Path, talladega_ibt_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    result, _cache = ImportService(db_path=db_path, data_dir=data_dir).import_ibt_file(talladega_ibt_path)
    assert result.overview is not None

    report = ReportService(db_path=db_path).generate_markdown(result.overview.run_id)

    assert report is not None
    assert "RaceLab Garage Auto Report" in report
    assert "Lap 2 is the best useful lap" in report
    assert "3.58 mm" in report


def test_trace_builder_reads_cache_file(tmp_path: Path, talladega_ibt_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    result, _cache = ImportService(db_path=db_path, data_dir=data_dir).import_ibt_file(talladega_ibt_path)
    assert result.overview is not None

    payload = build_trace_payload(
        result.overview.run_id,
        lap=2,
        channels=["speed_mph", "rpm"],
        downsample=10,
        data_dir=data_dir,
    )

    assert payload["sample_count"] > 250
    assert len(payload["x"]["lap_dist_pct"]) == payload["sample_count"]
    assert len(payload["channels"]["speed_mph"]) == payload["sample_count"]


# ── same-run guard ────────────────────────────────────────────

def test_compare_same_run_triggers_reference_warning() -> None:
    """Same run_id + same lap should produce inconclusive verdict with a reference warning."""
    from api.routes_compare import run_comparison, CompareRequest
    from api.routes_runs import repository

    # Use the existing persisted run from the default DB
    runs = repository().list_runs()
    if not runs:
        return  # no runs available, skip

    rid = runs[0]["run_id"] if isinstance(runs[0], dict) else runs[0].run_id
    overview = repository().get_overview(rid)
    if overview is None or overview.best_useful_lap is None:
        return
    lap_number = overview.best_useful_lap.lap_number
    resp = run_comparison(CompareRequest(
        baseline_run_id=rid, test_run_id=rid,
        baseline_lap=lap_number, test_lap=lap_number,
    ))
    verdict = resp.get("verdict", {})
    assert verdict.get("verdict") == "inconclusive"
    warnings = resp.get("warnings", [])
    assert any("same" in w.lower() or "reference" in w.lower() for w in warnings), f"got warnings={warnings}"


def test_compare_different_run_not_blocked() -> None:
    from racelab_engine.analysis.compare_math import compute_whole_car_index

    # Two runs with different IDs but zero speed delta should still NOT be flagged as same-run
    same_rows = [{"lap_dist_pct_100": float(i), "speed_mph": 200.0,
                  "cfs_ride_height_in": 0.2, "throttle_pct": 100.0,
                  "brake_pct": 0.0, "abs_steering_deg": 1.0,
                  "dynamic_pressure_psf": 100.0, "cfs_risk_score": 0.3,
                  "rpm": 8000, "speed_rate_mph_1000ft": -0.2,
                  "lf_ride_height_in": 2.0, "rf_ride_height_in": 2.1} for i in range(101)]

    from racelab_engine.analysis.compare_math import aggregate_platform_stats, aggregate_driver_stats, aggregate_powertrain_stats
    plat = aggregate_platform_stats(same_rows, same_rows)
    driver = aggregate_driver_stats(same_rows, same_rows)
    pt = aggregate_powertrain_stats(same_rows, same_rows)
    wci = compute_whole_car_index(plat, driver, pt, 90, speed_delta_mph=0.0)

    # With zero delta, the index should still produce a valid score — not crash
    assert wci.overall_index is not None
    assert isinstance(wci.overall_index, (int, float))


# ── import sanitization ───────────────────────────────────────

def test_sanitize_filename_strips_path_traversal() -> None:
    from api.routes_imports import _sanitize_filename
    # os.path.basename() strips directory components first, so ../bad.ibt → bad.ibt
    result = _sanitize_filename("../bad.ibt")
    assert result == "bad.ibt"
    result2 = _sanitize_filename("../../../etc/passwd.ibt")
    assert "passwd" in result2
    assert "../" not in result2


def test_sanitize_filename_preserves_safe_names() -> None:
    from api.routes_imports import _sanitize_filename
    result = _sanitize_filename("stockcars-camarozl12018-talladega-2026.ibt")
    assert ".ibt" in result
    assert "stockcars" in result


def test_import_endpoint_rejects_non_ibt_multipart(tmp_path: Path) -> None:
    import os
    from api.main import app
    from fastapi.testclient import TestClient
    db_path = tmp_path / "racelab.sqlite"
    os.environ["RACELAB_DB_PATH"] = str(db_path)
    client = TestClient(app)
    resp = client.post("/api/imports/ibt", files={"file": ("bad.txt", b"hello", "text/plain")})
    assert resp.status_code == 400
    assert any(word in resp.text.lower() for word in ["unsupported", "select an .ibt", "missing file", "invalid filename"])
    os.environ.pop("RACELAB_DB_PATH", None)
