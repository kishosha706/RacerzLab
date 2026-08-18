from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.routes_runs as routes_runs
import racelab_engine.storage.db as db_module
import racelab_engine.storage.repository as repository_module
from api.main import app
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


def _seed_run(db_path: Path, run_id: str = "read-path-run") -> RaceLabRepository:
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
                timing_primary_clock="session_tick",
                timing_clock_state="qualified",
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
                "recording_sha256": None,
                "car_name": "Test Car",
            "track_name": "Test Track",
            "setup_name": "Baseline",
            "imported_at": items[0]["imported_at"],
            "best_lap_number": 2,
            "best_lap_time": 30.25,
            "best_lap_time_s": 30.25,
            "lap_count": 1,
            "has_setup_snapshot": True,
            "primary_issue": None,
        }
    ]


def test_session_run_summaries_use_one_connection_and_bounded_bulk_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "session-list.sqlite"
    repository = _seed_run(db_path, "session-run-a")
    _seed_run(db_path, "session-run-b")
    statements: list[str] = []
    open_count = 0
    original = repository_module.initialize_database

    def traced_connection(path):
        nonlocal open_count
        open_count += 1
        connection = original(path)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(repository_module, "initialize_database", traced_connection)
    items = repository.get_run_list_items(
        ["session-run-b", "missing-run", "session-run-a", "session-run-b"]
    )
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]

    assert [item["run_id"] for item in items] == ["session-run-b", "session-run-a"]
    assert open_count == 1
    assert len(selects) == 1


def test_run_lists_requalify_legacy_implausibly_fast_laps(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-run-list.sqlite"
    run_id = "legacy-fast"
    repository = RaceLabRepository(db_path)
    overview = RunOverview(
        run_id=run_id,
        session=SessionSummary(run_id=run_id, car_name="Test Car", track_name="Test Track"),
        laps=[
            LapSummary(
                lap_id=f"{run_id}:lap:{lap_number}", run_id=run_id, lap_number=lap_number,
                lap_type="timed", is_complete=True, is_useful=True, lap_time=lap_time,
                classification_tags=["SOLO_CLEAN"],
            )
            for lap_number, lap_time in ((1, 90.0), (2, 91.0), (3, 1.0))
        ],
    )
    repository.save_import(overview)
    legacy_fast = overview.laps[-1]
    connection = initialize_database(db_path)
    with connection:
        for lap in overview.laps:
            connection.execute(
                "UPDATE laps SET lap_json = ? WHERE lap_id = ?",
                (
                    lap.model_dump_json(
                        exclude={"timing_primary_clock", "timing_clock_state"}
                    ),
                    lap.lap_id,
                ),
            )
        connection.execute(
            """
            UPDATE laps
            SET lap_type = ?, is_useful = 1, classification_tags = ?, lap_json = ?
            WHERE lap_id = ?
            """,
            (
                legacy_fast.lap_type,
                '["SOLO_CLEAN"]',
                legacy_fast.model_dump_json(
                    exclude={"timing_primary_clock", "timing_clock_state"}
                ),
                legacy_fast.lap_id,
            ),
        )
        connection.execute(
            "UPDATE runs SET lap_eligibility_version = NULL WHERE run_id = ?",
            (run_id,),
        )
    connection.close()

    listed = repository.list_runs()[0]
    single = repository.get_run_list_item(run_id)
    bulk = repository.get_run_list_items([run_id])[0]
    refreshed = repository.get_overview(run_id)

    assert single is not None
    assert refreshed is not None
    assert listed["best_lap_number"] == single["best_lap_number"] == bulk["best_lap_number"] == 1
    assert listed["best_lap_time"] == single["best_lap_time"] == bulk["best_lap_time"] == 90.0
    assert refreshed.best_useful_lap is not None
    assert refreshed.best_useful_lap.lap_number == 1
    connection = initialize_database(db_path)
    version = connection.execute(
        "SELECT lap_eligibility_version FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    stored_lap_payloads = [
        row[0]
        for row in connection.execute(
            "SELECT lap_json FROM laps WHERE run_id = ? ORDER BY lap_number", (run_id,)
        ).fetchall()
    ]
    connection.close()
    assert version == "relative-pace-v2"
    assert all('"timing_primary_clock"' not in payload for payload in stored_lap_payloads)
    assert all('"timing_clock_state"' not in payload for payload in stored_lap_payloads)


def test_tech_passing_setup_candidates_use_one_indexed_bulk_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "setup-options.sqlite"
    repository = _seed_run(db_path, "matching-run")
    matching = repository.get_overview("matching-run")
    assert matching is not None
    repository.save_import(matching.model_copy(update={
        "session": matching.session.model_copy(update={
            "car_path": "cars/cup",
            "track_id_or_path": "track-1",
            "session_type": "Test",
            "setup_passed_tech": True,
        }),
    }))
    statements: list[str] = []
    open_count = 0
    original = repository_module.initialize_database

    def traced_connection(path):
        nonlocal open_count
        open_count += 1
        connection = original(path)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(repository_module, "initialize_database", traced_connection)
    candidates = repository.list_tech_passing_setup_candidates(
        car_path="cars/cup",
        track_id_or_path="track-1",
        session_type="Test",
    )
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]

    assert [(run_id, setup.run_id) for run_id, setup in candidates] == [
        ("matching-run", "matching-run")
    ]
    assert open_count == 1
    assert len(selects) == 1

    connection = original(db_path)
    try:
        query_plan = " ".join(
            str(row["detail"])
            for row in connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT runs.run_id, setup_snapshots.snapshot_json
                FROM runs
                JOIN setup_snapshots ON setup_snapshots.run_id = runs.run_id
                WHERE runs.setup_passed_tech = 1
                  AND runs.car_path = ?
                  AND runs.track_id_or_path = ?
                  AND runs.session_type = ?
                """,
                ("cars/cup", "track-1", "Test"),
            )
        )
    finally:
        connection.close()
    assert "idx_runs_tech_setup_context" in query_plan


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
