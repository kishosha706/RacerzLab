from __future__ import annotations

import json
import hashlib
import os
import sqlite3
from pathlib import Path
from threading import RLock

from racelab_engine.identity import canonical_json_sha256

DEFAULT_DB_PATH = Path("data/racelab.sqlite")

# Schema creation and the additive compatibility checks are intentionally run
# once per database file per process.  Before this guard, every repository read
# reparsed ``schema.sql``, inspected every migrated table, and renegotiated WAL
# mode.  That added several milliseconds to even a single-row lookup.
_INITIALIZED_DATABASES: dict[str, tuple[int, int]] = {}
_INITIALIZE_LOCK = RLock()
_LIGHTWEIGHT_MIGRATION_CHECKSUMS = {
    1: hashlib.sha256(b"racelab-additive-schema-through-p35.4.1-v1").hexdigest(),
    2: hashlib.sha256(b"racelab-additive-schema-through-p35.4.4-v2").hexdigest(),
    3: hashlib.sha256(b"racelab-controlled-response-receipt-persistence-v3").hexdigest(),
    4: hashlib.sha256(b"racelab-crew-case-mutation-receipts-v4").hexdigest(),
    5: hashlib.sha256(b"racelab-controlled-workflow-case-mutation-receipts-v5").hexdigest(),
    6: hashlib.sha256(b"racelab-crew-case-revision-lineage-receipts-v6").hexdigest(),
    7: hashlib.sha256(
        b"racelab-controlled-workflow-projection-identity-v7"
    ).hexdigest(),
}
_LIGHTWEIGHT_MIGRATION_VERSION = max(_LIGHTWEIGHT_MIGRATION_CHECKSUMS)
_LIGHTWEIGHT_MIGRATION_CHECKSUM = _LIGHTWEIGHT_MIGRATION_CHECKSUMS[
    _LIGHTWEIGHT_MIGRATION_VERSION
]


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


def connect_read_only(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open an existing database without permitting a read path to mutate it."""

    path = _database_path(db_path).resolve()
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    return connection


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def validate_complete_migration_ledger(connection: sqlite3.Connection) -> None:
    """Fail closed unless the read-only migration ledger is exact and complete."""

    rows = connection.execute(
        "SELECT version, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    versions = [int(row["version"]) for row in rows]
    if any(version > _LIGHTWEIGHT_MIGRATION_VERSION for version in versions):
        raise RuntimeError(
            "Database schema was created by a newer RacerZLab build; upgrade this app before opening it."
        )
    first_expected_version = 1 if versions and versions[0] == 1 else 2
    expected_versions = list(
        range(first_expected_version, _LIGHTWEIGHT_MIGRATION_VERSION + 1)
    )
    if versions != expected_versions:
        raise RuntimeError(
            "Database migration history is incomplete for this RacerZLab build."
        )
    if any(
        row["checksum"] != _LIGHTWEIGHT_MIGRATION_CHECKSUMS.get(int(row["version"]))
        for row in rows
    ):
        raise RuntimeError(
            "Database migration history checksum does not match this RacerZLab build."
        )


def _add_column_if_missing(connection: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _column_names(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _apply_controlled_response_receipt_migration(
    connection: sqlite3.Connection,
) -> None:
    """Add durable receipts without treating old scored rows as new evidence."""

    _add_column_if_missing(
        connection,
        "controlled_test_workflows",
        "controlled_response_receipt_json",
        "controlled_response_receipt_json TEXT",
    )
    _add_column_if_missing(
        connection,
        "controlled_test_workflows",
        "controlled_response_receipt_state",
        (
            "controlled_response_receipt_state TEXT NOT NULL "
            "DEFAULT 'not_applicable' CHECK (controlled_response_receipt_state IN "
            "('not_applicable', 'legacy_unavailable', 'persisted'))"
        ),
    )
    connection.execute(
        """
        UPDATE controlled_test_workflows
        SET controlled_response_receipt_state = CASE
          WHEN controlled_response_receipt_json IS NOT NULL THEN 'persisted'
          WHEN status = 'scored' THEN 'legacy_unavailable'
          ELSE 'not_applicable'
        END
        """
    )
    connection.execute(
        """
        INSERT INTO schema_migrations(version, checksum, applied_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (3, _LIGHTWEIGHT_MIGRATION_CHECKSUMS[3]),
    )


def _apply_crew_case_mutation_receipt_migration(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS crew_chief_mutation_receipts (
          mutation_id TEXT PRIMARY KEY,
          request_sha256 TEXT NOT NULL,
          action TEXT NOT NULL,
          run_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          investigation_id TEXT,
          expected_workspace_revision TEXT NOT NULL,
          expected_case_sha256 TEXT,
          result_workspace_revision TEXT NOT NULL,
          result_case_sha256 TEXT NOT NULL,
          result_case_revision INTEGER NOT NULL CHECK(result_case_revision >= 1),
          previous_case_sha256 TEXT,
          completed_at TEXT NOT NULL,
          workspace_json TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_crew_chief_mutation_scope
          ON crew_chief_mutation_receipts(
            run_id, session_id, completed_at, mutation_id
          );
        """
    )
    connection.execute(
        """
        INSERT INTO schema_migrations(version, checksum, applied_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (4, _LIGHTWEIGHT_MIGRATION_CHECKSUMS[4]),
    )


def _apply_controlled_workflow_case_mutation_receipt_migration(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS controlled_workflow_mutation_receipts (
          mutation_id TEXT PRIMARY KEY,
          request_sha256 TEXT NOT NULL,
          action TEXT NOT NULL,
          run_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          request_workflow_id TEXT,
          expected_case_sha256 TEXT NOT NULL,
          result_case_sha256 TEXT NOT NULL,
          result_workflow_id TEXT,
          result_workflow_revision_sha256 TEXT,
          response_sha256 TEXT NOT NULL,
          completed_at TEXT NOT NULL,
          response_json TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_controlled_workflow_mutation_scope
          ON controlled_workflow_mutation_receipts(
            run_id, session_id, completed_at, mutation_id
          );
        """
    )
    connection.execute(
        """
        INSERT INTO schema_migrations(version, checksum, applied_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (5, _LIGHTWEIGHT_MIGRATION_CHECKSUMS[5]),
    )


def _apply_crew_case_revision_lineage_receipt_migration(
    connection: sqlite3.Connection,
) -> None:
    _add_column_if_missing(
        connection,
        "crew_chief_mutation_receipts",
        "result_case_revision",
        "result_case_revision INTEGER",
    )
    _add_column_if_missing(
        connection,
        "crew_chief_mutation_receipts",
        "previous_case_sha256",
        "previous_case_sha256 TEXT",
    )
    connection.execute(
        """
        UPDATE crew_chief_mutation_receipts
        SET result_case_revision = (
              SELECT revision.case_revision
              FROM engineering_case_revisions AS revision
              WHERE revision.case_sha256 = result_case_sha256
            ),
            previous_case_sha256 = (
              SELECT revision.previous_case_sha256
              FROM engineering_case_revisions AS revision
              WHERE revision.case_sha256 = result_case_sha256
            )
        """
    )
    unresolved = connection.execute(
        """
        SELECT mutation_id FROM crew_chief_mutation_receipts
        WHERE result_case_revision IS NULL
        LIMIT 1
        """
    ).fetchone()
    if unresolved is not None:
        raise RuntimeError(
            "Crew mutation receipt cannot be bound to durable case revision lineage."
        )
    legacy_rows = connection.execute(
        """
        SELECT receipt.*, revision.case_id
        FROM crew_chief_mutation_receipts AS receipt
        JOIN engineering_case_revisions AS revision
          ON revision.case_sha256 = receipt.result_case_sha256
        """
    ).fetchall()
    for row in legacy_rows:
        try:
            workspace = json.loads(row["workspace_json"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Legacy Crew mutation receipt workspace is unreadable."
            ) from exc
        if not isinstance(workspace, dict):
            raise RuntimeError("Legacy Crew mutation receipt workspace is malformed.")
        identity = workspace.get("identity")
        if not isinstance(identity, dict):
            raise RuntimeError(
                "Legacy Crew mutation receipt workspace identity is malformed."
            )
        if not identity.get("selected_run_ids"):
            session_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'racelab_sessions'"
            ).fetchone()
            session_row = (
                connection.execute(
                    "SELECT run_ids_json FROM racelab_sessions WHERE session_id = ?",
                    (row["session_id"],),
                ).fetchone()
                if session_table is not None
                else None
            )
            try:
                selected_run_ids = (
                    json.loads(session_row["run_ids_json"])
                    if session_row is not None
                    else [row["run_id"]]
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    "Legacy Crew mutation receipt session scope is unreadable."
                ) from exc
            if (
                not isinstance(selected_run_ids, list)
                or len(selected_run_ids) != len(set(selected_run_ids))
                or row["run_id"] not in selected_run_ids
                or canonical_json_sha256(tuple(selected_run_ids))
                != identity.get("selected_scope_hash")
            ):
                raise RuntimeError(
                    "Legacy Crew mutation receipt session scope cannot be reconstructed."
                )
            identity["selected_run_ids"] = selected_run_ids
        if workspace.get("mutation_receipt") is None:
            published_at = str(row["completed_at"])
            if published_at.endswith("+00:00"):
                published_at = published_at[:-6] + "Z"
            receipt_body = {
                "schema_version": "p3544.crew-mutation-publication.v1",
                "mutation_id": row["mutation_id"],
                "request_sha256": row["request_sha256"],
                "action": row["action"],
                "case_id": row["case_id"],
                "case_revision": row["result_case_revision"],
                "case_sha256": row["result_case_sha256"],
                "previous_case_sha256": row["previous_case_sha256"],
                "published_at": published_at,
                "authority": "durability_receipt_only",
                "setup_authorized": False,
            }
            workspace["mutation_receipt"] = {
                **receipt_body,
                "receipt_sha256": canonical_json_sha256(receipt_body),
            }
            connection.execute(
                "UPDATE crew_chief_mutation_receipts SET workspace_json = ? "
                "WHERE mutation_id = ?",
                (
                    json.dumps(workspace, sort_keys=True, separators=(",", ":")),
                    row["mutation_id"],
                ),
            )
    connection.execute(
        """
        INSERT INTO schema_migrations(version, checksum, applied_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (6, _LIGHTWEIGHT_MIGRATION_CHECKSUMS[6]),
    )


def _apply_controlled_workflow_projection_identity_migration(
    connection: sqlite3.Connection,
) -> None:
    """Restore the exact P32/P35.1 identity already captured by legacy receipts."""

    identity_columns = (
        "p32_opportunity_id",
        "p32_projection_sha256",
        "engineering_knowledge_projection_sha256",
    )
    for column in identity_columns:
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            column,
            f"{column} TEXT",
        )
    rows = connection.execute(
        "SELECT workflow_id, reproduction_snapshot_json, "
        "p32_opportunity_id, p32_projection_sha256, "
        "engineering_knowledge_projection_sha256 "
        "FROM controlled_test_workflows"
    ).fetchall()
    for row in rows:
        try:
            snapshot = json.loads(row["reproduction_snapshot_json"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Legacy controlled workflow reproduction snapshot is unreadable."
            ) from exc
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                "Legacy controlled workflow reproduction snapshot is malformed."
            )
        binding = snapshot.get("p352_performance_opportunity_binding")
        stored_identity = tuple(row[column] for column in identity_columns)
        if binding is None:
            if any(value is not None for value in stored_identity):
                raise RuntimeError(
                    "Controlled workflow projection identity has no canonical receipt."
                )
            continue
        if not isinstance(binding, dict):
            raise RuntimeError(
                "Legacy controlled workflow projection identity receipt is malformed."
            )
        restored_identity = tuple(binding.get(column) for column in identity_columns)
        opportunity_id, p32_sha256, knowledge_sha256 = restored_identity
        if (
            not isinstance(opportunity_id, str)
            or not opportunity_id
            or opportunity_id != opportunity_id.strip()
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in (p32_sha256, knowledge_sha256)
            )
        ):
            raise RuntimeError(
                "Legacy controlled workflow projection identity receipt is incomplete."
            )
        if any(
            stored is not None and stored != restored
            for stored, restored in zip(stored_identity, restored_identity, strict=True)
        ):
            raise RuntimeError(
                "Controlled workflow projection identity disagrees with its canonical receipt."
            )
        connection.execute(
            "UPDATE controlled_test_workflows SET p32_opportunity_id = ?, "
            "p32_projection_sha256 = ?, "
            "engineering_knowledge_projection_sha256 = ? WHERE workflow_id = ?",
            (*restored_identity, row["workflow_id"]),
        )
    connection.execute(
        """
        INSERT INTO schema_migrations(version, checksum, applied_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (7, _LIGHTWEIGHT_MIGRATION_CHECKSUMS[7]),
    )


def _run_lightweight_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          checksum TEXT NOT NULL,
          applied_at TEXT NOT NULL
        )
        """
    )
    applied_rows = connection.execute(
        "SELECT version, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    applied_versions: set[int] = set()
    for row in applied_rows:
        version = int(row["version"])
        if version > _LIGHTWEIGHT_MIGRATION_VERSION:
            raise RuntimeError(
                "Database schema was created by a newer RacerZLab build; upgrade this app before opening it."
            )
        expected_checksum = _LIGHTWEIGHT_MIGRATION_CHECKSUMS.get(version)
        if expected_checksum is None or row["checksum"] != expected_checksum:
            raise RuntimeError(
                "Database migration history checksum does not match this RacerZLab build."
            )
        applied_versions.add(version)
    if _LIGHTWEIGHT_MIGRATION_VERSION in applied_versions:
        validate_complete_migration_ledger(connection)
        return
    if 6 in applied_versions:
        if not {2, 3, 4, 5}.issubset(applied_versions):
            raise RuntimeError(
                "Database migration history is incomplete for this RacerZLab build."
            )
        _apply_controlled_workflow_projection_identity_migration(connection)
        validate_complete_migration_ledger(connection)
        return
    if 5 in applied_versions:
        if not {2, 3, 4}.issubset(applied_versions):
            raise RuntimeError(
                "Database migration history is incomplete for this RacerZLab build."
            )
        _apply_crew_case_revision_lineage_receipt_migration(connection)
        _apply_controlled_workflow_projection_identity_migration(connection)
        validate_complete_migration_ledger(connection)
        return
    if 4 in applied_versions:
        if not {2, 3}.issubset(applied_versions):
            raise RuntimeError(
                "Database migration history is incomplete for this RacerZLab build."
            )
        _apply_controlled_workflow_case_mutation_receipt_migration(connection)
        _apply_crew_case_revision_lineage_receipt_migration(connection)
        _apply_controlled_workflow_projection_identity_migration(connection)
        validate_complete_migration_ledger(connection)
        return
    if 3 in applied_versions:
        if 2 not in applied_versions:
            raise RuntimeError(
                "Database migration history is incomplete for this RacerZLab build."
            )
        _apply_crew_case_mutation_receipt_migration(connection)
        _apply_controlled_workflow_case_mutation_receipt_migration(connection)
        _apply_crew_case_revision_lineage_receipt_migration(connection)
        _apply_controlled_workflow_projection_identity_migration(connection)
        validate_complete_migration_ledger(connection)
        return
    if 2 in applied_versions:
        _apply_controlled_response_receipt_migration(connection)
        _apply_crew_case_mutation_receipt_migration(connection)
        _apply_controlled_workflow_case_mutation_receipt_migration(connection)
        _apply_crew_case_revision_lineage_receipt_migration(connection)
        _apply_controlled_workflow_projection_identity_migration(connection)
        validate_complete_migration_ledger(connection)
        return

    # Existing developer databases from the scaffold had narrower tables. This
    # checksum-bound compatibility migration runs once per database. A future
    # schema change must add a new ordered version rather than mutating this one.
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS crew_chief_investigations (
          investigation_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          workspace_revision TEXT NOT NULL,
          status TEXT NOT NULL,
          opened_at TEXT NOT NULL,
          event_count INTEGER NOT NULL DEFAULT 0,
          event_head_hash TEXT,
          continue_action_count INTEGER NOT NULL DEFAULT 0,
          investigation_json TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_crew_chief_investigation_scope
          ON crew_chief_investigations(run_id, session_id, opened_at, investigation_id);
        CREATE TABLE IF NOT EXISTS crew_chief_events (
          event_id TEXT PRIMARY KEY,
          investigation_id TEXT NOT NULL,
          sequence INTEGER NOT NULL,
          workspace_revision TEXT NOT NULL,
          created_at TEXT NOT NULL,
          event_hash TEXT NOT NULL UNIQUE,
          event_type TEXT NOT NULL,
          event_json TEXT NOT NULL,
          UNIQUE(investigation_id, sequence),
          FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
            ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_crew_chief_event_fold
          ON crew_chief_events(investigation_id, sequence, event_id);
        CREATE TABLE IF NOT EXISTS engineering_objectives (
          objective_id TEXT PRIMARY KEY,
          investigation_id TEXT NOT NULL UNIQUE,
          workspace_revision TEXT NOT NULL,
          selected_at TEXT NOT NULL,
          objective_json TEXT NOT NULL,
          FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
            ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS crew_chief_success_contracts (
          contract_id TEXT PRIMARY KEY,
          investigation_id TEXT NOT NULL UNIQUE,
          workspace_revision TEXT NOT NULL,
          created_at TEXT NOT NULL,
          contract_json TEXT NOT NULL,
          FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
            ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS component_response_records (
          record_id TEXT PRIMARY KEY,
          source_workflow_id TEXT NOT NULL UNIQUE,
          source_run_id TEXT NOT NULL,
          context_identity TEXT NOT NULL,
          created_at TEXT NOT NULL,
          record_json TEXT NOT NULL,
          FOREIGN KEY(source_run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_component_response_context
          ON component_response_records(context_identity, created_at, record_id);
        CREATE TABLE IF NOT EXISTS crew_chief_driver_memory (
          record_id TEXT PRIMARY KEY,
          investigation_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          recorded_at TEXT NOT NULL,
          record_json TEXT NOT NULL,
          FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
            ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_crew_chief_driver_memory_scope
          ON crew_chief_driver_memory(session_id, recorded_at, record_id);
        CREATE TABLE IF NOT EXISTS crew_chief_effectiveness_records (
          record_id TEXT PRIMARY KEY,
          investigation_id TEXT NOT NULL UNIQUE,
          workspace_revision TEXT NOT NULL,
          recorded_at TEXT NOT NULL,
          record_json TEXT NOT NULL,
          FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
            ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS controlled_workflow_run_index (
          workflow_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          role TEXT NOT NULL,
          PRIMARY KEY(workflow_id, run_id, role),
          FOREIGN KEY(workflow_id) REFERENCES controlled_test_workflows(workflow_id)
            ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_controlled_workflow_run_lookup
          ON controlled_workflow_run_index(run_id, workflow_id);
        CREATE TABLE IF NOT EXISTS engineering_experience_stream_head (
          stream_id TEXT PRIMARY KEY,
          schema_version TEXT NOT NULL,
          record_count INTEGER NOT NULL,
          head_sha256 TEXT
        );
        INSERT OR IGNORE INTO engineering_experience_stream_head (
          stream_id, schema_version, record_count, head_sha256
        ) VALUES ('p33.engineering-experience.v1', 'p33.engineering-experience.v1', 0, NULL);
        CREATE TABLE IF NOT EXISTS engineering_experiences (
          sequence INTEGER PRIMARY KEY,
          experience_id TEXT NOT NULL UNIQUE,
          experience_sha256 TEXT NOT NULL UNIQUE,
          source_identity_sha256 TEXT NOT NULL UNIQUE,
          previous_entry_sha256 TEXT,
          entry_sha256 TEXT NOT NULL UNIQUE,
          source_kind TEXT NOT NULL,
          created_at TEXT NOT NULL,
          context_sha256 TEXT NOT NULL,
          run_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          driver_id TEXT,
          car_path TEXT NOT NULL,
          car_version TEXT NOT NULL,
          iracing_build TEXT NOT NULL,
          track TEXT NOT NULL,
          track_configuration TEXT NOT NULL,
          package_type TEXT NOT NULL,
          setup_family TEXT,
          setup_snapshot_sha256 TEXT NOT NULL,
          objective TEXT NOT NULL,
          phase TEXT NOT NULL,
          physical_region TEXT NOT NULL,
          problem_sha256 TEXT NOT NULL,
          source_investigation_id TEXT,
          source_workflow_id TEXT,
          record_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_engineering_experience_exact_context
          ON engineering_experiences(context_sha256, objective, phase, created_at DESC, experience_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_experience_problem
          ON engineering_experiences(problem_sha256, car_path, car_version, iracing_build, created_at DESC, experience_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_experience_vehicle_track
          ON engineering_experiences(car_path, car_version, iracing_build, track, track_configuration, phase, created_at DESC, experience_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_experience_driver
          ON engineering_experiences(driver_id, car_path, car_version, iracing_build, phase, created_at DESC, experience_id)
          WHERE driver_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_engineering_experience_investigation
          ON engineering_experiences(source_investigation_id, experience_id)
          WHERE source_investigation_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_engineering_experience_workflow
          ON engineering_experiences(source_workflow_id, experience_id)
          WHERE source_workflow_id IS NOT NULL;
        CREATE TRIGGER IF NOT EXISTS engineering_experiences_no_update
        BEFORE UPDATE ON engineering_experiences
        BEGIN
          SELECT RAISE(ABORT, 'engineering experiences are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS engineering_experiences_no_delete
        BEFORE DELETE ON engineering_experiences
        BEGIN
          SELECT RAISE(ABORT, 'engineering experiences are append-only');
        END;
        CREATE TABLE IF NOT EXISTS p34_authoritative_source_revision (
          singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
          revision INTEGER NOT NULL CHECK(revision >= 0)
        );
        INSERT OR IGNORE INTO p34_authoritative_source_revision (
          singleton_id, revision
        ) VALUES (1, 0);
        CREATE TABLE IF NOT EXISTS investigation_adaptation_stream_head (
          stream_id TEXT PRIMARY KEY,
          schema_version TEXT NOT NULL,
          record_count INTEGER NOT NULL,
          head_sha256 TEXT
        );
        INSERT OR IGNORE INTO investigation_adaptation_stream_head (
          stream_id, schema_version, record_count, head_sha256
        ) VALUES (
          'p34.investigation-adaptation.v1',
          'p34.investigation-adaptation.v1',
          0,
          NULL
        );
        CREATE TABLE IF NOT EXISTS investigation_adaptation_records (
          sequence INTEGER PRIMARY KEY,
          record_id TEXT NOT NULL UNIQUE,
          record_sha256 TEXT NOT NULL UNIQUE,
          record_kind TEXT NOT NULL,
          previous_entry_sha256 TEXT,
          entry_sha256 TEXT NOT NULL UNIQUE,
          recorded_at TEXT NOT NULL,
          investigation_id TEXT,
          workspace_revision TEXT,
          step_number INTEGER,
          policy_id TEXT,
          protocol_id TEXT,
          record_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_kind_time
          ON investigation_adaptation_records(
            record_kind, recorded_at DESC, record_id
          );
        CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_investigation
          ON investigation_adaptation_records(
            investigation_id, workspace_revision, step_number,
            record_kind, sequence DESC
          ) WHERE investigation_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_protocol
          ON investigation_adaptation_records(
            protocol_id, record_kind, sequence DESC
          ) WHERE protocol_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_workflow_certificate
          ON investigation_adaptation_records(
            protocol_id,
            record_kind,
            json_extract(record_json, '$.created_workflow_ids[0]'),
            sequence
          ) WHERE record_kind = 'outcome_certificate';
        CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_followup_parent
          ON investigation_adaptation_records(
            protocol_id,
            record_kind,
            investigation_id,
            json_extract(record_json, '$.certificate_id'),
            json_extract(record_json, '$.certificate_sha256'),
            json_extract(record_json, '$.source_workflow_id')
          ) WHERE record_kind = 'outcome_followup';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_adaptation_pair_source
          ON investigation_adaptation_records(
            investigation_id, workspace_revision, step_number
          ) WHERE record_kind = 'paired_decision';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_adaptation_outcome_source
          ON investigation_adaptation_records(investigation_id)
          WHERE record_kind = 'outcome_certificate';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_adaptation_comparison_source
          ON investigation_adaptation_records(investigation_id)
          WHERE record_kind = 'paired_comparison';
        CREATE TRIGGER IF NOT EXISTS investigation_adaptation_records_no_update
        BEFORE UPDATE ON investigation_adaptation_records
        BEGIN
          SELECT RAISE(ABORT, 'investigation adaptation records are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_adaptation_records_no_delete
        BEFORE DELETE ON investigation_adaptation_records
        BEGIN
          SELECT RAISE(ABORT, 'investigation adaptation records are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_p34_insert
        AFTER INSERT ON investigation_adaptation_records
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_p34_update
        AFTER UPDATE ON investigation_adaptation_records
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_p34_delete
        AFTER DELETE ON investigation_adaptation_records
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_investigation_insert
        AFTER INSERT ON crew_chief_investigations
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_investigation_update
        AFTER UPDATE ON crew_chief_investigations
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_investigation_delete
        AFTER DELETE ON crew_chief_investigations
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_event_insert
        AFTER INSERT ON crew_chief_events
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_event_update
        AFTER UPDATE ON crew_chief_events
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_event_delete
        AFTER DELETE ON crew_chief_events
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_p33_insert
        AFTER INSERT ON engineering_experiences
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_p33_update
        AFTER UPDATE ON engineering_experiences
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_p33_delete
        AFTER DELETE ON engineering_experiences
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_workflow_insert
        AFTER INSERT ON controlled_test_workflows
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_workflow_update
        AFTER UPDATE ON controlled_test_workflows
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_workflow_delete
        AFTER DELETE ON controlled_test_workflows
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_run_insert
        AFTER INSERT ON runs
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_run_update
        AFTER UPDATE ON runs
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        CREATE TRIGGER IF NOT EXISTS p34_source_revision_run_delete
        AFTER DELETE ON runs
        BEGIN
          UPDATE p34_authoritative_source_revision SET revision = revision + 1
          WHERE singleton_id = 1;
        END;
        """
    )
    if connection.execute(
        "SELECT COUNT(*) AS count FROM controlled_workflow_run_index"
    ).fetchone()["count"] == 0:
        rows = connection.execute(
            "SELECT workflow_id, source_run_id, stage_run_ids_json FROM controlled_test_workflows"
        ).fetchall()
        for row in rows:
            bindings = [(row["source_run_id"], "source")]
            try:
                stage_bindings = json.loads(row["stage_run_ids_json"] or "{}")
            except (TypeError, ValueError):
                stage_bindings = {}
            if isinstance(stage_bindings, dict):
                bindings.extend(
                    (run_id, str(stage))
                    for stage, run_id in stage_bindings.items()
                    if isinstance(run_id, str) and run_id
                )
            connection.executemany(
                "INSERT OR IGNORE INTO controlled_workflow_run_index(workflow_id, run_id, role) VALUES (?, ?, ?)",
                ((row["workflow_id"], run_id, role) for run_id, role in bindings),
            )
    if "crew_chief_investigations" in {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }:
        investigation_columns = _column_names(
            connection, "crew_chief_investigations"
        )
        needs_stream_head_backfill = (
            "event_count" not in investigation_columns
            or "event_head_hash" not in investigation_columns
        )
        _add_column_if_missing(
            connection,
            "crew_chief_investigations",
            "event_count",
            "event_count INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            connection,
            "crew_chief_investigations",
            "event_head_hash",
            "event_head_hash TEXT",
        )
        _add_column_if_missing(
            connection,
            "crew_chief_investigations",
            "continue_action_count",
            "continue_action_count INTEGER NOT NULL DEFAULT 0",
        )
        if needs_stream_head_backfill:
            connection.execute(
                """
                UPDATE crew_chief_investigations
                SET event_count = (
                      SELECT COUNT(*) FROM crew_chief_events
                      WHERE crew_chief_events.investigation_id = crew_chief_investigations.investigation_id
                    ),
                    event_head_hash = (
                      SELECT event_hash FROM crew_chief_events
                      WHERE crew_chief_events.investigation_id = crew_chief_investigations.investigation_id
                      ORDER BY sequence DESC LIMIT 1
                    )
                WHERE EXISTS (
                    SELECT 1 FROM crew_chief_events
                    WHERE crew_chief_events.investigation_id = crew_chief_investigations.investigation_id
                  )
                """
            )
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
            "engineering_blockers_json": "engineering_blockers_json TEXT",
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
            "event_json": "event_json TEXT",
        }.items():
            _add_column_if_missing(connection, "events", column_name, ddl)
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
            "stage_experiment_contexts_json",
            "stage_experiment_contexts_json TEXT NOT NULL DEFAULT '{}'",
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
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "learning_capture_state",
            "learning_capture_state TEXT NOT NULL DEFAULT 'not_applicable'",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "learning_capture_experience_id",
            "learning_capture_experience_id TEXT",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "learning_capture_experience_sha256",
            "learning_capture_experience_sha256 TEXT",
        )
        _add_column_if_missing(
            connection,
            "controlled_test_workflows",
            "learning_capture_blocker_reason",
            "learning_capture_blocker_reason TEXT",
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
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS engineering_cases (
          case_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          current_revision INTEGER NOT NULL,
          current_case_sha256 TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_engineering_case_scope
          ON engineering_cases(run_id, session_id);
        CREATE TABLE IF NOT EXISTS engineering_case_revisions (
          case_id TEXT NOT NULL,
          case_revision INTEGER NOT NULL,
          case_sha256 TEXT NOT NULL UNIQUE,
          previous_case_sha256 TEXT,
          created_at TEXT NOT NULL,
          change_category TEXT NOT NULL,
          source_workspace_revision TEXT NOT NULL,
          revision_json TEXT NOT NULL,
          PRIMARY KEY(case_id, case_revision),
          FOREIGN KEY(case_id) REFERENCES engineering_cases(case_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_engineering_case_revision_history
          ON engineering_case_revisions(case_id, case_revision DESC);
        CREATE TABLE IF NOT EXISTS engineering_driver_intents (
          intent_id TEXT PRIMARY KEY,
          intent_sha256 TEXT NOT NULL UNIQUE,
          case_id TEXT NOT NULL,
          intent_revision INTEGER NOT NULL,
          supersedes_intent_id TEXT,
          created_at TEXT NOT NULL,
          intent_json TEXT NOT NULL,
          UNIQUE(case_id, intent_revision),
          FOREIGN KEY(case_id) REFERENCES engineering_cases(case_id) ON DELETE CASCADE,
          FOREIGN KEY(supersedes_intent_id) REFERENCES engineering_driver_intents(intent_id)
            ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_engineering_driver_intent_current
          ON engineering_driver_intents(case_id, intent_revision DESC);
        """
    )
    connection.execute(
        """
        INSERT INTO schema_migrations(version, checksum, applied_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (2, _LIGHTWEIGHT_MIGRATION_CHECKSUMS[2]),
    )
    _apply_controlled_response_receipt_migration(connection)
    _apply_crew_case_mutation_receipt_migration(connection)
    _apply_controlled_workflow_case_mutation_receipt_migration(connection)
    _apply_crew_case_revision_lineage_receipt_migration(connection)
    _apply_controlled_workflow_projection_identity_migration(connection)
    validate_complete_migration_ledger(connection)


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
