from __future__ import annotations

import sqlite3

import pytest

from racelab_engine.storage import db as database


def test_schema_migration_ledger_is_checksum_bound_and_idempotent(tmp_path) -> None:
    path = tmp_path / "migration-ledger.sqlite"
    connection = database.initialize_database(path)
    rows = connection.execute(
        "SELECT version, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row["version"] for row in rows] == [2, 3, 4, 5, 6, 7]
    assert [row["checksum"] for row in rows] == [
        database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[2],
        database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[3],
        database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[4],
        database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[5],
        database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[6],
        database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[7],
    ]
    connection.close()

    database._INITIALIZED_DATABASES.clear()
    reopened = database.initialize_database(path)
    assert reopened.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 6
    reopened.close()

    direct = sqlite3.connect(path)
    direct.execute(
        "UPDATE schema_migrations SET checksum = 'tampered' WHERE version = ?",
        (database._LIGHTWEIGHT_MIGRATION_VERSION,),
    )
    direct.commit()
    direct.close()
    database._INITIALIZED_DATABASES.clear()
    with pytest.raises(RuntimeError, match="checksum"):
        database.initialize_database(path)


def test_newer_schema_version_fails_closed(tmp_path) -> None:
    path = tmp_path / "newer-schema.sqlite"
    connection = database.initialize_database(path)
    connection.execute(
        "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
        (database._LIGHTWEIGHT_MIGRATION_VERSION + 1, "newer", "later"),
    )
    connection.commit()
    connection.close()
    database._INITIALIZED_DATABASES.clear()

    with pytest.raises(RuntimeError, match="newer RacerZLab build"):
        database.initialize_database(path)


def test_complete_migration_ledger_validator_is_read_only_and_rejects_extra_rows(
    tmp_path,
) -> None:
    path = tmp_path / "complete-ledger.sqlite"
    connection = database.initialize_database(path)
    rows_before = connection.execute(
        "SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()

    database.validate_complete_migration_ledger(connection)

    rows_after = connection.execute(
        "SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [tuple(row) for row in rows_after] == [tuple(row) for row in rows_before]
    connection.execute(
        "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
        (0, "unexpected", "earlier"),
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        database.validate_complete_migration_ledger(connection)
    connection.close()


def test_response_receipt_migration_marks_legacy_scored_rows_explicitly(
    tmp_path,
) -> None:
    path = tmp_path / "legacy-response-receipt.sqlite"
    connection = database.initialize_database(path)
    connection.close()

    direct = sqlite3.connect(path)
    direct.execute(
        "DELETE FROM schema_migrations WHERE version >= ?",
        (3,),
    )
    direct.execute(
        "ALTER TABLE controlled_test_workflows "
        "DROP COLUMN controlled_response_receipt_state"
    )
    direct.execute(
        "ALTER TABLE controlled_test_workflows "
        "DROP COLUMN controlled_response_receipt_json"
    )
    now = "2026-08-26T12:00:00+00:00"
    columns = (
        "workflow_id,created_at,updated_at,status,source_run_id,complaint,packet_json,"
        "stage_run_ids_json,stage_eligible_lap_numbers_json,"
        "stage_experiment_contexts_json,analysis_version,reproduction_snapshot_json"
    )
    direct.executemany(
        f"INSERT INTO controlled_test_workflows ({columns}) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            (
                "legacy-scored", now, now, "scored", "legacy-source", "legacy result",
                "{}", "{}", "{}", "{}", "controlled-workflow-aba2-v1", "{}",
            ),
            (
                "legacy-planned", now, now, "planned", "legacy-source", "legacy plan",
                "{}", "{}", "{}", "{}", "controlled-workflow-aba2-v1", "{}",
            ),
        ),
    )
    direct.commit()
    direct.close()

    database._INITIALIZED_DATABASES.clear()
    migrated = database.initialize_database(path)
    rows = migrated.execute(
        "SELECT workflow_id, controlled_response_receipt_json, "
        "controlled_response_receipt_state "
        "FROM controlled_test_workflows ORDER BY workflow_id"
    ).fetchall()
    versions = migrated.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    migrated.close()

    assert [tuple(row) for row in rows] == [
        ("legacy-planned", None, "not_applicable"),
        ("legacy-scored", None, "legacy_unavailable"),
    ]
    assert [row["version"] for row in versions] == [2, 3, 4, 5, 6, 7]


def test_real_v1_upgrade_retains_and_revalidates_the_full_ledger(tmp_path) -> None:
    path = tmp_path / "v1-upgrade.sqlite"
    connection = database.initialize_database(path)
    connection.close()

    direct = sqlite3.connect(path)
    direct.execute("DELETE FROM schema_migrations")
    direct.execute(
        "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
        (1, database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[1], "legacy-v1"),
    )
    direct.execute(
        "ALTER TABLE controlled_test_workflows "
        "DROP COLUMN controlled_response_receipt_state"
    )
    direct.execute(
        "ALTER TABLE controlled_test_workflows "
        "DROP COLUMN controlled_response_receipt_json"
    )
    direct.commit()
    direct.close()

    database._INITIALIZED_DATABASES.clear()
    upgraded = database.initialize_database(path)
    assert [
        row["version"]
        for row in upgraded.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ] == [1, 2, 3, 4, 5, 6, 7]
    upgraded.close()

    direct = sqlite3.connect(path)
    direct.execute(
        "UPDATE schema_migrations SET checksum = 'tampered-v1' WHERE version = 1"
    )
    direct.commit()
    direct.close()
    database._INITIALIZED_DATABASES.clear()

    with pytest.raises(RuntimeError, match="checksum"):
        database.initialize_database(path)


def test_real_v3_upgrade_adds_both_case_mutation_receipt_ledgers(tmp_path) -> None:
    path = tmp_path / "v3-to-current.sqlite"
    connection = database.initialize_database(path)
    connection.close()

    direct = sqlite3.connect(path)
    direct.execute("DELETE FROM schema_migrations WHERE version > 3")
    direct.execute("DROP TABLE controlled_workflow_mutation_receipts")
    direct.execute("DROP TABLE crew_chief_mutation_receipts")
    direct.commit()
    direct.close()

    database._INITIALIZED_DATABASES.clear()
    upgraded = database.initialize_database(path)
    assert [
        row["version"]
        for row in upgraded.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ] == list(range(2, database._LIGHTWEIGHT_MIGRATION_VERSION + 1))
    tables = {
        row["name"]
        for row in upgraded.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "crew_chief_mutation_receipts" in tables
    assert "controlled_workflow_mutation_receipts" in tables
    upgraded.close()
