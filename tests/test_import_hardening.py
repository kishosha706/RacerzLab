from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api import routes_imports
from racelab_engine.io.ibt_types import IBTImportResult, ImportStatus
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.services import import_service as import_service_module
from racelab_engine.services.import_service import ImportService, parquet_path
from racelab_engine.storage.repository import RaceLabRepository


def _fake_result(run_id: str = "atomic-run") -> IBTImportResult:
    lap = LapSummary(
        lap_id=f"{run_id}-1",
        run_id=run_id,
        lap_number=1,
        lap_time=30.0,
        is_complete=True,
        is_useful=True,
    )
    overview = RunOverview(
        run_id=run_id,
        session=SessionSummary(run_id=run_id, source_file="fake.ibt"),
        best_useful_lap=lap,
        laps=[lap],
    )
    return IBTImportResult(
        status=ImportStatus(status="ok", message="fake import"),
        records=[{"lap": 1, "session_time": 0.0, "speed_mph": 120.0}],
        overview=overview,
    )


def test_import_db_failure_cleans_staged_cache_and_leaves_no_completed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result())
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(service.repository, "save_import", fail_save)

    with pytest.raises(RuntimeError, match="db unavailable"):
        service.import_ibt_file(tmp_path / "sample.ibt")

    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview("atomic-run") is None
    assert not parquet_path(tmp_path / "data", "atomic-run").exists()
    assert list((tmp_path / "data").rglob("*.tmp.parquet")) == []
    assert list((tmp_path / "data").rglob("*.tmp.channels.json")) == []


def test_successful_import_promotes_cache_and_duplicate_import_replaces_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result("duplicate-run"))
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")

    first, first_cache = service.import_ibt_file(tmp_path / "sample.ibt")
    second, second_cache = service.import_ibt_file(tmp_path / "sample.ibt")

    assert first.overview is not None
    assert second.overview is not None
    assert second.status.message == "Existing run updated."
    assert "Duplicate telemetry detected - updated the existing run record." in second.status.warnings
    assert first_cache is not None and first_cache.path == parquet_path(tmp_path / "data", "duplicate-run")
    assert second_cache is not None and second_cache.path == parquet_path(tmp_path / "data", "duplicate-run")
    assert first_cache.path.exists()
    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview("duplicate-run") is not None


def test_multipart_upload_uses_unique_paths_and_keeps_successful_upload_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_imports, "IMPORTS_DIR", tmp_path / "imports")
    routes_imports.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    seen_paths: list[str] = []

    def fake_import(self: ImportService, path: str) -> tuple[IBTImportResult, None]:
        seen_paths.append(path)
        return _fake_result(f"upload-{len(seen_paths)}"), None

    monkeypatch.setattr(ImportService, "import_ibt_file", fake_import)
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/api/imports/ibt",
            files={"file": ("same.ibt", b"IBT", "application/octet-stream")},
        )
        assert response.status_code == 200

    assert len(seen_paths) == 2
    assert seen_paths[0] != seen_paths[1]
    assert all(Path(path).exists() for path in seen_paths)


def test_failed_multipart_import_removes_uploaded_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_imports, "IMPORTS_DIR", tmp_path / "imports")
    routes_imports.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def fail_import(self: ImportService, path: str) -> tuple[IBTImportResult, None]:
        assert Path(path).exists()
        raise RuntimeError("decoder exploded")

    monkeypatch.setattr(ImportService, "import_ibt_file", fail_import)
    response = TestClient(app).post(
        "/api/imports/ibt",
        files={"file": ("bad.ibt", b"IBT", "application/octet-stream")},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["title"] == "Import failed"
    assert detail["message"] == "The telemetry file could not be processed."
    assert detail["impact"] == "No completed run was created."
    assert detail["next_step"] == "Try importing again, or choose a different .ibt file."
    assert detail["cleanup"] == "Temporary import files were cleaned when possible."
    assert list((tmp_path / "imports").glob("*.ibt")) == []
