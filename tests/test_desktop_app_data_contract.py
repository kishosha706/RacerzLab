from __future__ import annotations

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHELL_PATH = PROJECT_ROOT / "ui/src-tauri/src/lib.rs"


def test_packaged_sidecar_uses_one_tauri_app_local_storage_root() -> None:
    shell = SHELL_PATH.read_text(encoding="utf-8")

    assert "app.path().app_local_data_dir()?" in shell
    assert 'database: root.join("racelab.sqlite")' in shell
    assert 'let data = root.join("data");' in shell
    assert 'let log_directory = root.join("logs");' in shell
    assert '.env("RACELAB_DB_PATH", &storage_paths.database)' in shell
    assert '.env("RACELAB_DATA_DIR", &storage_paths.data)' in shell
    assert '.env("RACERZLAB_BACKEND_LOG", &storage_paths.log)' in shell
    assert ".current_dir(&storage_paths.root)" in shell
    assert 'std::env::var_os("LOCALAPPDATA")' not in shell


def test_owned_sidecar_restart_reuses_the_prepared_storage_paths() -> None:
    shell = SHELL_PATH.read_text(encoding="utf-8")

    assert "storage_paths: BackendStoragePaths" in shell
    assert "capability_token: String" in shell
    assert "&capability_token," in shell
    assert "&self.capability_token," in shell
    assert '.env("RACERZLAB_BACKEND_CAPABILITY_TOKEN", capability_token)' in shell


def test_python_storage_consumers_honor_the_absolute_sidecar_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from racelab_engine.services.import_service import default_data_dir
    from racelab_engine.storage.db import default_db_path

    storage_root = tmp_path.resolve()
    database = storage_root / "racelab.sqlite"
    data = storage_root / "data"
    unrelated_working_directory = storage_root / "working-directory"
    unrelated_working_directory.mkdir()
    monkeypatch.chdir(unrelated_working_directory)
    monkeypatch.setenv("RACELAB_DB_PATH", str(database))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data))

    assert default_db_path() == database
    assert default_data_dir() == data
    assert default_db_path().is_absolute()
    assert default_data_dir().is_absolute()
