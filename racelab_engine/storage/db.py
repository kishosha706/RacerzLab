from __future__ import annotations

import sqlite3
from pathlib import Path
import os


DEFAULT_DB_PATH = Path("data/racelab.sqlite")


def default_db_path() -> Path:
    return Path(os.environ.get("RACELAB_DB_PATH", DEFAULT_DB_PATH))


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = default_db_path()
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def _add_column_if_missing(connection: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _column_names(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _run_lightweight_migrations(connection: sqlite3.Connection) -> None:
    # Existing developer databases from the scaffold had narrower tables. These
    # additive migrations keep local data usable without pretending to be a full
    # migration framework.
    if "runs" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        for column_name, ddl in {
            "analysis_engine_version": "analysis_engine_version TEXT DEFAULT '1.0.0'",
            "analysis_config_hash": "analysis_config_hash TEXT",
            "analysis_mode": "analysis_mode TEXT DEFAULT 'row'",
            "analyzed_at": "analyzed_at TEXT",
            "imported_at": "imported_at TEXT",
            "sim_date_time": "sim_date_time TEXT",
            "track_id_or_path": "track_id_or_path TEXT",
            "weather_summary": "weather_summary TEXT",
            "setup_passed_tech": "setup_passed_tech INTEGER",
            "setup_modified": "setup_modified INTEGER",
            "air_pressure": "air_pressure REAL",
            "primary_findings_json": "primary_findings_json TEXT",
            "warnings_json": "warnings_json TEXT",
            "crew_chief_summary": "crew_chief_summary TEXT",
            "next_test": "next_test TEXT",
            "session_json": "session_json TEXT",
        }.items():
            _add_column_if_missing(connection, "runs", column_name, ddl)
    if "laps" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        for column_name, ddl in {
            "pct_span": "pct_span REAL",
            "avg_rpm": "avg_rpm REAL",
            "min_rpm": "min_rpm REAL",
            "max_rpm": "max_rpm REAL",
            "avg_throttle_pct": "avg_throttle_pct REAL",
            "max_throttle_pct": "max_throttle_pct REAL",
            "avg_brake_pct": "avg_brake_pct REAL",
            "max_brake_pct": "max_brake_pct REAL",
            "min_splitter_speed_mph": "min_splitter_speed_mph REAL",
            "max_abs_steering_deg": "max_abs_steering_deg REAL",
            "avg_abs_steering_deg": "avg_abs_steering_deg REAL",
            "lap_json": "lap_json TEXT",
        }.items():
            _add_column_if_missing(connection, "laps", column_name, ddl)
    if "events" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        for column_name, ddl in {
            "primary_metric_name": "primary_metric_name TEXT",
            "primary_metric_value": "primary_metric_value REAL",
            "recommended_actions": "recommended_actions TEXT",
            "event_json": "event_json TEXT",
        }.items():
            _add_column_if_missing(connection, "events", column_name, ddl)
    if "recommendations" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        for column_name, ddl in {
            "evidence_event_ids": "evidence_event_ids TEXT",
            "recommendation_json": "recommendation_json TEXT",
        }.items():
            _add_column_if_missing(connection, "recommendations", column_name, ddl)
    if "setup_snapshots" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        _add_column_if_missing(connection, "setup_snapshots", "snapshot_json", "snapshot_json TEXT")
    if "setup_response_observations" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        _add_column_if_missing(connection, "setup_response_observations", "magnitude_label", "magnitude_label TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "relative_delta_percent", "relative_delta_percent REAL")
        _add_column_if_missing(connection, "setup_response_observations", "response_context_key", "response_context_key TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "response_context_json", "response_context_json TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "environment_context_key", "environment_context_key TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "surrounding_setup_fingerprint", "surrounding_setup_fingerprint TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "source_run_provenance_key", "source_run_provenance_key TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "baseline_setup_passed_tech", "baseline_setup_passed_tech INTEGER")
        _add_column_if_missing(connection, "setup_response_observations", "test_setup_passed_tech", "test_setup_passed_tech INTEGER")
        _add_column_if_missing(connection, "setup_response_observations", "setup_unit", "setup_unit TEXT")
        _add_column_if_missing(connection, "setup_response_observations", "setup_value_kind", "setup_value_kind TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_setup_response_context "
            "ON setup_response_observations(response_context_key, setup_key, direction_sign)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_setup_response_source_provenance "
            "ON setup_response_observations(source_run_provenance_key) "
            "WHERE source_run_provenance_key IS NOT NULL"
        )
    if "controlled_test_workflows" in {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "stage_eligible_lap_numbers_json",
            "stage_eligible_lap_numbers_json TEXT NOT NULL DEFAULT '{}'",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "analysis_version",
            "analysis_version TEXT NOT NULL DEFAULT 'controlled-workflow-aba2-v1'",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "execution_json",
            "execution_json TEXT",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "reproduction_snapshot_json",
            "reproduction_snapshot_json TEXT NOT NULL DEFAULT '{}'",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "learning_admitted",
            "learning_admitted INTEGER",
        )


def initialize_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = connect(db_path)
    schema_path = Path(__file__).with_name("schema.sql")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    _run_lightweight_migrations(connection)
    connection.commit()
    return connection
