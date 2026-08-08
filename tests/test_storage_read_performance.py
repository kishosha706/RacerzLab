from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import racelab_engine.storage.db as db_module
import racelab_engine.storage.repository as repository_module
from fastapi.testclient import TestClient

import api.routes_runs as routes_runs
from api.main import app
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


def _seed_run(db_path: Path) -> RaceLabRepository:
    run_id = "read-path-run"
    overview = RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            source_file="read-path.ibt",
            car_name="Test Car",
            track_name="test-track",
            track_display_name="Test Track",
            setup_name="Baseline",
        ),
        laps=[
            LapSummary(
                lap_id=f"{run_id}:lap:2",
                run_id=run_id,
                lap_number=2,
                is_complete=True,
                is_useful=True,
                lap_time=30.25,
                pct_min=0.0,
                pct_max=100.0,
                pct_span=100.0,
                sample_count=1_800,
            )
        ],
        setup_snapshot=SetupSnapshot(
            setup_id=f"{run_id}:setup",
            run_id=run_id,
            setup_name="Baseline",
        ),
        recommendations=[
            Recommendation(
                recommendation_id=f"{run_id}:recommendation:1",
                run_id=run_id,
                priority_rank=1,
                issue="Test issue",
                recommendation_text="Collect more evidence.",
            )
        ],
    )
    repository = RaceLabRepository(db_path)
    repository.save_import(overview)
    return repository


def test_warm_database_open_does_not_repeat_schema_migrations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "warm.sqlite"
    migration_calls = 0
    original = db_module._run_lightweight_migrations

    def count_migration(connection) -> None:
        nonlocal migration_calls
        migration_calls += 1
        original(connection)

    monkeypatch.setattr(db_module, "_run_lightweight_migrations", count_migration)
    initialize_database(db_path).close()
    initialize_database(db_path).close()

    assert migration_calls == 1


def test_deleted_database_at_same_path_is_initialized_again(tmp_path: Path) -> None:
    db_path = tmp_path / "recreated.sqlite"
    initialize_database(db_path).close()
    db_path.unlink()

    connection = initialize_database(db_path)
    try:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()

    assert "runs" in tables


def test_run_list_uses_one_select_instead_of_per_run_queries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "list.sqlite"
    repository = _seed_run(db_path)
    statements: list[str] = []
    original = repository_module.initialize_database

    def traced_connection(path):
        connection = original(path)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(repository_module, "initialize_database", traced_connection)
    items = repository.list_runs()
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]

    assert len(selects) == 1
    assert items == [
        {
            "run_id": "read-path-run",
            "car_name": "Test Car",
            "track_name": "Test Track",
            "setup_name": "Baseline",
            "imported_at": items[0]["imported_at"],
            "best_lap_number": 2,
            "best_lap_time": 30.25,
            "best_lap_time_s": 30.25,
            "lap_count": 1,
            "has_setup_snapshot": True,
            "primary_issue": "Test issue",
        }
    ]


def test_overview_uses_one_database_connection(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "overview.sqlite"
    repository = _seed_run(db_path)
    open_count = 0
    original = repository_module.initialize_database

    def counted_connection(path):
        nonlocal open_count
        open_count += 1
        return original(path)

    monkeypatch.setattr(repository_module, "initialize_database", counted_connection)
    overview = repository.get_overview("read-path-run")

    assert overview is not None
    assert overview.best_useful_lap is not None
    assert overview.best_useful_lap.lap_number == 2
    assert open_count == 1


def test_channel_summary_compact_projection_preserves_default_wire_contract(monkeypatch) -> None:
    class RepositoryStub:
        @staticmethod
        def get_session(run_id: str):
            return SimpleNamespace(run_id=run_id)

    monkeypatch.setattr(routes_runs, "repository", lambda: RepositoryStub())
    monkeypatch.setattr(
        routes_runs,
        "build_channel_summary",
        lambda run_id: [
            {
                "name": "speed_mph",
                "label": "Speed",
                "description": None,
                "unit": "mph",
                "type": "float",
                "count": 1,
                "is_raw": False,
                "is_calculated": True,
                "is_proxy": False,
                "missing_status": None,
                "group": "calculated",
                "source": "calculated",
            }
        ],
    )

    client = TestClient(app)
    default_response = client.get("/api/runs/read-path-run/channels/summary")
    response = client.get("/api/runs/read-path-run/channels/summary?compact=true")

    assert default_response.status_code == 200
    assert response.status_code == 200
    default_channel = default_response.json()[0]
    channel = response.json()[0]
    assert default_channel["description"] is None
    assert default_channel["missing_status"] is None
    assert channel["name"] == "speed_mph"
    assert channel["is_raw"] is False
    assert channel["is_calculated"] is True
    assert channel["is_proxy"] is False
    assert "description" not in channel
    assert "missing_status" not in channel
