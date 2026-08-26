from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

import api.main as main_module
import racelab_engine.services.storage_readiness_service as readiness_module
from racelab_engine.services.storage_readiness_service import (
    StorageReadiness,
    StorageReadinessCode,
    StorageRecoveryCode,
    check_storage_readiness,
)
from racelab_engine.storage import db as database_module


def test_health_fails_closed_with_typed_database_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RACERZLAB_BACKEND_INSTANCE_TOKEN", "owned-instance")
    monkeypatch.setattr(
        main_module,
        "check_storage_readiness",
        lambda: StorageReadiness(
            code=StorageReadinessCode.DATABASE_UNAVAILABLE,
            recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
        ),
    )

    response = TestClient(main_module.app).get("/api/health")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "unavailable",
        "app": "RacerZLab",
        "version": response.json()["version"],
        "instance_id": "owned-instance",
        "readiness_code": "database_unavailable",
        "recovery_code": "restart_or_restore_local_storage",
    }


def test_health_fails_closed_with_typed_data_storage_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "check_storage_readiness",
        lambda: StorageReadiness(
            code=StorageReadinessCode.DATA_STORAGE_UNAVAILABLE,
            recovery_code=StorageRecoveryCode.FREE_SPACE_OR_RESTORE_LOCAL_STORAGE,
        ),
    )

    response = TestClient(main_module.app).get("/api/health")

    assert response.status_code == 503
    assert response.json()["readiness_code"] == "data_storage_unavailable"
    assert response.json()["recovery_code"] == "free_space_or_restore_local_storage"


def test_health_openapi_declares_typed_unavailable_response() -> None:
    schema = main_module.app.openapi()
    unavailable = schema["paths"]["/api/health"]["get"]["responses"]["503"]
    response_schema = unavailable["content"]["application/json"]["schema"]
    failure_schema = schema["components"]["schemas"]["HealthUnavailableResponse"]

    assert response_schema == {"$ref": "#/components/schemas/HealthUnavailableResponse"}
    assert failure_schema["properties"]["readiness_code"]["enum"] == [
        "database_unavailable",
        "data_storage_unavailable",
    ]
    assert failure_schema["properties"]["recovery_code"]["enum"] == [
        "restart_or_restore_local_storage",
        "free_space_or_restore_local_storage",
    ]


def test_database_exception_text_and_paths_do_not_enter_readiness_result(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = r"C:\Users\private\telemetry\racelab.sqlite"

    def broken_database() -> None:
        raise OSError(f"permission denied: {secret}")

    monkeypatch.setattr(readiness_module, "_probe_database_storage", broken_database)

    readiness = check_storage_readiness()

    assert readiness == StorageReadiness(
        code=StorageReadinessCode.DATABASE_UNAVAILABLE,
        recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
    )
    assert secret not in caplog.text


def test_corrupt_configured_database_is_not_reported_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    database.write_bytes(b"not a sqlite database")
    monkeypatch.setenv("RACELAB_DB_PATH", str(database))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path / "data"))

    readiness = check_storage_readiness()

    assert readiness == StorageReadiness(
        code=StorageReadinessCode.DATABASE_UNAVAILABLE,
        recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
    )


def test_warm_cached_database_truncation_is_not_reported_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    monkeypatch.setenv("RACELAB_DB_PATH", str(database))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path / "data"))
    assert check_storage_readiness().ready is True
    identity_before = (database.stat().st_dev, database.stat().st_ino)

    database.write_bytes(b"runtime truncation")

    assert (database.stat().st_dev, database.stat().st_ino) == identity_before
    readiness = check_storage_readiness()
    assert readiness == StorageReadiness(
        code=StorageReadinessCode.DATABASE_UNAVAILABLE,
        recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
    )


@pytest.mark.parametrize(
    "version",
    (
        database_module._LIGHTWEIGHT_MIGRATION_VERSION,
        database_module._LIGHTWEIGHT_MIGRATION_VERSION - 1,
    ),
    ids=("current-checksum", "prior-checksum"),
)
def test_warm_cached_migration_checksum_tamper_fails_readiness_and_health(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: int,
) -> None:
    database = tmp_path / "racelab.sqlite"
    monkeypatch.setenv("RACELAB_DB_PATH", str(database))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(main_module.app)
    assert client.get("/api/health").status_code == 200
    identity_before = (database.stat().st_dev, database.stat().st_ino)

    direct = sqlite3.connect(database)
    direct.execute(
        "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
        ("tampered-at-runtime", version),
    )
    direct.commit()
    direct.close()

    assert (database.stat().st_dev, database.stat().st_ino) == identity_before
    assert check_storage_readiness() == StorageReadiness(
        code=StorageReadinessCode.DATABASE_UNAVAILABLE,
        recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
    )
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["readiness_code"] == "database_unavailable"
    assert response.json()["recovery_code"] == "restart_or_restore_local_storage"
    assert "tampered-at-runtime" not in response.text
    assert str(database) not in response.text


def test_warm_cached_missing_prior_migration_fails_readiness_and_health(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    monkeypatch.setenv("RACELAB_DB_PATH", str(database))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(main_module.app)
    assert client.get("/api/health").status_code == 200
    identity_before = (database.stat().st_dev, database.stat().st_ino)

    direct = sqlite3.connect(database)
    direct.execute(
        "DELETE FROM schema_migrations WHERE version = ?",
        (database_module._LIGHTWEIGHT_MIGRATION_VERSION - 1,),
    )
    direct.commit()
    direct.close()

    assert (database.stat().st_dev, database.stat().st_ino) == identity_before
    assert check_storage_readiness() == StorageReadiness(
        code=StorageReadinessCode.DATABASE_UNAVAILABLE,
        recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
    )
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["readiness_code"] == "database_unavailable"
    assert response.json()["recovery_code"] == "restart_or_restore_local_storage"
    assert str(database) not in response.text


def test_unusable_configured_data_storage_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    blocked_data_path = tmp_path / "data-is-a-file"
    blocked_data_path.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(readiness_module, "_probe_database_storage", lambda: None)
    monkeypatch.setenv("RACELAB_DATA_DIR", str(blocked_data_path))

    readiness = check_storage_readiness()

    assert readiness == StorageReadiness(
        code=StorageReadinessCode.DATA_STORAGE_UNAVAILABLE,
        recovery_code=StorageRecoveryCode.FREE_SPACE_OR_RESTORE_LOCAL_STORAGE,
    )


def test_ready_storage_uses_database_probe_and_leaves_no_data_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def ready_database() -> None:
        calls.append("database")

    data_dir = tmp_path / "data"
    monkeypatch.setattr(readiness_module, "_probe_database_storage", ready_database)
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))

    readiness = check_storage_readiness()

    assert readiness == StorageReadiness(code=StorageReadinessCode.READY)
    assert calls == ["database"]
    assert data_dir.is_dir()
    assert list(data_dir.iterdir()) == []
