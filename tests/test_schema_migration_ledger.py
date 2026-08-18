from __future__ import annotations

import sqlite3

import pytest

from racelab_engine.storage import db as database


def test_schema_migration_ledger_is_checksum_bound_and_idempotent(tmp_path) -> None:
    path = tmp_path / "migration-ledger.sqlite"
    connection = database.initialize_database(path)
    row = connection.execute(
        "SELECT version, checksum FROM schema_migrations"
    ).fetchone()
    assert row is not None
    assert row["version"] == database._LIGHTWEIGHT_MIGRATION_VERSION
    assert row["checksum"] == database._LIGHTWEIGHT_MIGRATION_CHECKSUM
    connection.close()

    database._INITIALIZED_DATABASES.clear()
    reopened = database.initialize_database(path)
    assert reopened.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
    reopened.close()

    direct = sqlite3.connect(path)
    direct.execute("UPDATE schema_migrations SET checksum = 'tampered'")
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
