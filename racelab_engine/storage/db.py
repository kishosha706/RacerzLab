from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from threading import RLock

DEFAULT_DB_PATH = Path("data/racelab.sqlite")

# Schema creation and the additive compatibility checks are intentionally run
# once per database file per process.  Before this guard, every repository read
# reparsed ``schema.sql``, inspected every migrated table, and renegotiated WAL
# mode.  That added several milliseconds to even a single-row lookup.
_INITIALIZED_DATABASES: dict[str, tuple[int, int]] = {}
_INITIALIZE_LOCK = RLock()


def default_db_path() -> Path:
    return Path(os.environ.get("RACELAB_DB_PATH", DEFAULT_DB_PATH))


def _database_path(db_path: str | Path | None) -> Path:
    if db_path is None:
        db_path = default_db_path()
    return Path(db_path)


def _database_key(path: Path) -> str:
    return str(path.resolve())


def _database_identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_dev, stat.st_ino


def _connect(path: Path, *, configure_journal: bool) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if configure_journal:
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a fully configured standalone connection.

    Repository traffic should continue through :func:`initialize_database`,
    whose warm path avoids renegotiating WAL mode.  Keeping ``connect`` fully
    configuring preserves its public standalone behavior.
    """
    return _connect(_database_path(db_path), configure_journal=True)


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
            "lap_eligibility_version": "lap_eligibility_version TEXT",
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
    # P19 append-only mission history tables are created here as well as in the
    # base schema so existing local databases gain durable measurement memory.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS measurement_mission_contracts (
          contract_id TEXT PRIMARY KEY,
          contract_sha256 TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL,
          contract_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS measurement_mission_attempts (
          attempt_id TEXT PRIMARY KEY,
          contract_id TEXT NOT NULL,
          contract_sha256 TEXT NOT NULL,
          run_id TEXT NOT NULL,
          completed_at TEXT NOT NULL,
          outcome TEXT NOT NULL,
          attempt_json TEXT NOT NULL,
          FOREIGN KEY(contract_id) REFERENCES measurement_mission_contracts(contract_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_measurement_attempt_contract "
        "ON measurement_mission_attempts(contract_id, completed_at, attempt_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS session_intelligence_quarantines (
          session_id TEXT PRIMARY KEY,
          reason TEXT NOT NULL,
          quarantined_at TEXT NOT NULL
        )
        """
    )
    # P21 content-addressed dataset registry. This is additive for existing
    # developer databases and never mutates registered dataset payloads.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_datasets (
          dataset_id TEXT PRIMARY KEY,
          dataset_hash TEXT NOT NULL UNIQUE,
          dataset_kind TEXT NOT NULL,
          created_at TEXT NOT NULL,
          dataset_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_dataset_kind "
        "ON evidence_datasets(dataset_kind, created_at, dataset_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_artifacts (
          evaluation_id TEXT PRIMARY KEY,
          evaluation_hash TEXT NOT NULL UNIQUE,
          capability_key TEXT NOT NULL,
          dataset_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          evaluation_json TEXT NOT NULL,
          FOREIGN KEY(dataset_id) REFERENCES evidence_datasets(dataset_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_evaluation_artifact_dataset "
        "ON evaluation_artifacts(dataset_id, created_at, evaluation_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_campaigns (
          campaign_id TEXT PRIMARY KEY,
          campaign_hash TEXT NOT NULL UNIQUE,
          campaign_kind TEXT NOT NULL,
          created_at TEXT NOT NULL,
          campaign_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_campaign_attempts (
          attempt_id TEXT PRIMARY KEY,
          attempt_hash TEXT NOT NULL UNIQUE,
          campaign_id TEXT NOT NULL,
          recorded_at TEXT NOT NULL,
          outcome TEXT NOT NULL,
          independence_unit_id TEXT NOT NULL,
          attempt_json TEXT NOT NULL,
          FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_campaign_attempt "
        "ON evidence_campaign_attempts(campaign_id, recorded_at, attempt_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_validation_records (
          record_id TEXT PRIMARY KEY,
          record_hash TEXT NOT NULL UNIQUE,
          profile_id TEXT NOT NULL,
          profile_hash TEXT NOT NULL,
          car_path TEXT NOT NULL,
          field_key TEXT NOT NULL,
          state TEXT NOT NULL,
          created_at TEXT NOT NULL,
          record_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_profile_validation_field "
        "ON profile_validation_records(profile_id, field_key, created_at, record_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_model_contracts (
          model_id TEXT PRIMARY KEY,
          model_hash TEXT NOT NULL UNIQUE,
          model_key TEXT NOT NULL,
          version TEXT NOT NULL,
          created_at TEXT NOT NULL,
          contract_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_predictions (
          prediction_id TEXT PRIMARY KEY,
          prediction_hash TEXT NOT NULL UNIQUE,
          model_id TEXT NOT NULL,
          predicted_at TEXT NOT NULL,
          prospective INTEGER NOT NULL,
          prediction_json TEXT NOT NULL,
          FOREIGN KEY(model_id) REFERENCES shadow_model_contracts(model_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_prediction_outcomes (
          outcome_id TEXT PRIMARY KEY,
          outcome_hash TEXT NOT NULL UNIQUE,
          prediction_id TEXT NOT NULL UNIQUE,
          observed_at TEXT NOT NULL,
          outcome_json TEXT NOT NULL,
          FOREIGN KEY(prediction_id) REFERENCES shadow_predictions(prediction_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_prediction_model "
        "ON shadow_predictions(model_id, predicted_at, prediction_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS activation_decisions (
          decision_id TEXT PRIMARY KEY,
          decision_hash TEXT NOT NULL UNIQUE,
          capability_key TEXT NOT NULL,
          state TEXT NOT NULL,
          evaluated_at TEXT NOT NULL,
          decision_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_activation_decision_capability "
        "ON activation_decisions(capability_key, evaluated_at, decision_id)"
    )
    # P22 prospective learning operations are append-only overlays on P21.
    # They operationalize frozen campaign and prediction contracts without
    # changing P19 reasoning or P20 whole-car authority.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_campaign_operations (
          operation_id TEXT PRIMARY KEY,
          operation_hash TEXT NOT NULL UNIQUE,
          campaign_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          operation_json TEXT NOT NULL,
          FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_campaign_operation_events (
          event_id TEXT PRIMARY KEY,
          event_hash TEXT NOT NULL UNIQUE,
          operation_id TEXT NOT NULL,
          recorded_at TEXT NOT NULL,
          event_type TEXT NOT NULL,
          event_json TEXT NOT NULL,
          FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_campaign_run_assessments (
          assessment_id TEXT PRIMARY KEY,
          assessment_hash TEXT NOT NULL UNIQUE,
          operation_id TEXT NOT NULL,
          campaign_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          source_file_fingerprint TEXT NOT NULL,
          recorded_at TEXT NOT NULL,
          state TEXT NOT NULL,
          assessment_json TEXT NOT NULL,
          FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
            ON DELETE RESTRICT,
          FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_campaign_operation_events "
        "ON evidence_campaign_operation_events(operation_id, recorded_at, event_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_campaign_run_assessment "
        "ON evidence_campaign_run_assessments(operation_id, recorded_at, assessment_id)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_run_assessment_scope "
        "ON evidence_campaign_run_assessments(operation_id, run_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS prospective_test_predictions (
          prediction_id TEXT PRIMARY KEY,
          prediction_hash TEXT NOT NULL UNIQUE,
          operation_id TEXT NOT NULL,
          source_run_id TEXT NOT NULL,
          predicted_at TEXT NOT NULL,
          prediction_json TEXT NOT NULL,
          FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS prospective_test_outcomes (
          outcome_id TEXT PRIMARY KEY,
          outcome_hash TEXT NOT NULL UNIQUE,
          prediction_id TEXT NOT NULL UNIQUE,
          workflow_id TEXT NOT NULL UNIQUE,
          observed_at TEXT NOT NULL,
          outcome_json TEXT NOT NULL,
          FOREIGN KEY(prediction_id) REFERENCES prospective_test_predictions(prediction_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_prospective_prediction_operation "
        "ON prospective_test_predictions(operation_id, predicted_at, prediction_id)"
    )
    # P23 freezes the first candidate's protocol and every observed audit state.
    # Neither table grants runtime authority.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p23_validation_protocols (
          protocol_id TEXT PRIMARY KEY,
          protocol_hash TEXT NOT NULL UNIQUE,
          protocol_version TEXT NOT NULL,
          capability_key TEXT NOT NULL,
          created_at TEXT NOT NULL,
          protocol_json TEXT NOT NULL,
          UNIQUE(capability_key, protocol_version)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p23_activation_audits (
          audit_id TEXT PRIMARY KEY,
          audit_hash TEXT NOT NULL UNIQUE,
          protocol_id TEXT NOT NULL,
          activation_decision TEXT NOT NULL,
          created_at TEXT NOT NULL,
          audit_json TEXT NOT NULL,
          FOREIGN KEY(protocol_id) REFERENCES p23_validation_protocols(protocol_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_p23_activation_audit_decision "
        "ON p23_activation_audits(activation_decision, created_at, audit_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p24_steering_truth_audits (
          audit_id TEXT PRIMARY KEY,
          audit_hash TEXT NOT NULL UNIQUE,
          run_id TEXT NOT NULL,
          source_file_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          state TEXT NOT NULL,
          audit_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_p24_truth_source "
        "ON p24_steering_truth_audits(source_file_hash, created_at, audit_id)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p24_qualification_certificates (
          certificate_id TEXT PRIMARY KEY,
          certificate_hash TEXT NOT NULL UNIQUE,
          protocol_id TEXT NOT NULL,
          campaign_id TEXT NOT NULL,
          operation_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          source_file_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          qualification_state TEXT NOT NULL,
          certificate_json TEXT NOT NULL,
          UNIQUE(operation_id, run_id),
          FOREIGN KEY(protocol_id) REFERENCES p23_validation_protocols(protocol_id)
            ON DELETE RESTRICT,
          FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
            ON DELETE RESTRICT,
          FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_p24_certificate_progress "
        "ON p24_qualification_certificates(protocol_id, qualification_state, created_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_p24_certificate_source "
        "ON p24_qualification_certificates(source_file_hash, qualification_state)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p24_negative_control_expectations (
          expectation_id TEXT PRIMARY KEY,
          expectation_hash TEXT NOT NULL UNIQUE,
          operation_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          recipe_id TEXT NOT NULL,
          expectation_json TEXT NOT NULL,
          FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p24_negative_control_results (
          result_id TEXT PRIMARY KEY,
          result_hash TEXT NOT NULL UNIQUE,
          expectation_id TEXT NOT NULL UNIQUE,
          certificate_id TEXT NOT NULL,
          observed_at TEXT NOT NULL,
          passed INTEGER NOT NULL,
          result_json TEXT NOT NULL,
          FOREIGN KEY(expectation_id) REFERENCES p24_negative_control_expectations(expectation_id)
            ON DELETE RESTRICT,
          FOREIGN KEY(certificate_id) REFERENCES p24_qualification_certificates(certificate_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p24_certificate_admissions (
          admission_id TEXT PRIMARY KEY,
          admission_hash TEXT NOT NULL UNIQUE,
          certificate_id TEXT NOT NULL,
          dataset_id TEXT NOT NULL UNIQUE,
          admitted_at TEXT NOT NULL,
          admission_json TEXT NOT NULL,
          UNIQUE(certificate_id, dataset_id),
          FOREIGN KEY(certificate_id) REFERENCES p24_qualification_certificates(certificate_id)
            ON DELETE RESTRICT,
          FOREIGN KEY(dataset_id) REFERENCES evidence_datasets(dataset_id)
            ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS p25_null_session_run_cards (
          card_id TEXT PRIMARY KEY,
          card_hash TEXT NOT NULL UNIQUE,
          reference_run_id TEXT NOT NULL,
          operation_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          state TEXT NOT NULL,
          card_json TEXT NOT NULL,
          UNIQUE(reference_run_id),
          FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
            ON DELETE RESTRICT
        )
        """
    )


def initialize_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _database_path(db_path)

    # ``:memory:`` databases are connection-local and therefore must always be
    # initialized.  Normal application and test databases use real files.
    if str(path) == ":memory:":
        connection = _connect(path, configure_journal=True)
        schema_path = Path(__file__).with_name("schema.sql")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _run_lightweight_migrations(connection)
        connection.commit()
        return connection

    key = _database_key(path)
    identity = _database_identity(path)
    if identity is not None and _INITIALIZED_DATABASES.get(key) == identity:
        return _connect(path, configure_journal=False)

    with _INITIALIZE_LOCK:
        identity = _database_identity(path)
        if identity is not None and _INITIALIZED_DATABASES.get(key) == identity:
            return _connect(path, configure_journal=False)

        connection = _connect(path, configure_journal=True)
        try:
            schema_path = Path(__file__).with_name("schema.sql")
            connection.executescript(schema_path.read_text(encoding="utf-8"))
            _run_lightweight_migrations(connection)
            connection.commit()
            refreshed_identity = _database_identity(path)
            if refreshed_identity is not None:
                _INITIALIZED_DATABASES[key] = refreshed_identity
            return connection
        except Exception:
            connection.close()
            raise
