from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryFile

from racelab_engine.services.import_service import default_data_dir
from racelab_engine.storage.db import (
    initialize_database,
    validate_complete_migration_ledger,
)


_log = logging.getLogger(__name__)


class StorageReadinessCode(StrEnum):
    READY = "ready"
    DATABASE_UNAVAILABLE = "database_unavailable"
    DATA_STORAGE_UNAVAILABLE = "data_storage_unavailable"


class StorageRecoveryCode(StrEnum):
    NONE = "none"
    RESTART_OR_RESTORE_LOCAL_STORAGE = "restart_or_restore_local_storage"
    FREE_SPACE_OR_RESTORE_LOCAL_STORAGE = "free_space_or_restore_local_storage"


@dataclass(frozen=True)
class StorageReadiness:
    code: StorageReadinessCode
    recovery_code: StorageRecoveryCode = StorageRecoveryCode.NONE

    @property
    def ready(self) -> bool:
        return self.code is StorageReadinessCode.READY


def _probe_data_storage(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryFile(prefix=".racerzlab-readiness-", dir=data_dir) as probe:
        probe.write(b"ready")
        probe.flush()


def _probe_database_storage() -> None:
    connection = initialize_database()
    try:
        validate_complete_migration_ledger(connection)
        connection.execute(
            "SELECT run_id, imported_at FROM runs LIMIT 1"
        ).fetchone()
    finally:
        connection.close()


def check_storage_readiness() -> StorageReadiness:
    try:
        _probe_database_storage()
    except Exception as exc:
        _log.warning(
            "Storage readiness failed (%s; %s)",
            StorageReadinessCode.DATABASE_UNAVAILABLE,
            type(exc).__name__,
        )
        return StorageReadiness(
            code=StorageReadinessCode.DATABASE_UNAVAILABLE,
            recovery_code=StorageRecoveryCode.RESTART_OR_RESTORE_LOCAL_STORAGE,
        )

    try:
        _probe_data_storage(default_data_dir())
    except Exception as exc:
        _log.warning(
            "Storage readiness failed (%s; %s)",
            StorageReadinessCode.DATA_STORAGE_UNAVAILABLE,
            type(exc).__name__,
        )
        return StorageReadiness(
            code=StorageReadinessCode.DATA_STORAGE_UNAVAILABLE,
            recovery_code=StorageRecoveryCode.FREE_SPACE_OR_RESTORE_LOCAL_STORAGE,
        )

    return StorageReadiness(code=StorageReadinessCode.READY)


__all__ = [
    "StorageReadiness",
    "StorageReadinessCode",
    "StorageRecoveryCode",
    "check_storage_readiness",
]
