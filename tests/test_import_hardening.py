from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api import routes_imports
from racelab_engine.io.ibt_types import IBTHeader, IBTImportResult, IBTVariableDefinition, ImportStatus
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.services import import_service as import_service_module
from racelab_engine.services.import_service import (
    ImportService,
    channel_metadata_path,
    csv_path,
    parquet_path,
    read_telemetry_manifest,
    read_telemetry_rows,
    telemetry_manifest_path,
)
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
        session=SessionSummary(
            run_id=run_id,
            source_file="fake.ibt",
            file_hash="a" * 64,
        ),
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
    assert list((tmp_path / "data").rglob("*.tmp.telemetry-manifest.json")) == []


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
    assert telemetry_manifest_path(tmp_path / "data", "duplicate-run").exists()
    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview("duplicate-run") is not None


def test_import_retires_obsolete_csv_when_promoting_parquet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "format-switch"
    legacy_csv = csv_path(tmp_path / "data", run_id)
    legacy_csv.parent.mkdir(parents=True, exist_ok=True)
    legacy_csv.write_bytes(b"legacy,csv\n1,2\n")
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result(run_id))

    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")
    service.import_ibt_file(tmp_path / "sample.ibt")

    assert parquet_path(tmp_path / "data", run_id).exists()
    assert not legacy_csv.exists()


def test_failed_format_switch_restores_obsolete_cache_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "format-switch-rollback"
    data_dir = tmp_path / "data"
    legacy_csv = csv_path(data_dir, run_id)
    legacy_csv.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b"legacy,csv\n1,2\n"
    legacy_csv.write_bytes(legacy_bytes)
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result(run_id))
    real_replace = import_service_module._atomic_replace

    def fail_final_manifest(source: Path, destination: Path) -> None:
        if destination == telemetry_manifest_path(data_dir, run_id):
            raise OSError("injected format switch failure")
        real_replace(source, destination)

    monkeypatch.setattr(import_service_module, "_atomic_replace", fail_final_manifest)
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=data_dir)

    with pytest.raises(OSError, match="format switch failure"):
        service.import_ibt_file(tmp_path / "sample.ibt")

    assert legacy_csv.read_bytes() == legacy_bytes
    assert not parquet_path(data_dir, run_id).exists()
    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview(run_id) is None


def test_import_refuses_to_save_run_when_declared_raw_channel_is_not_archived(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _fake_result("incomplete-archive")
    result.variable_definitions = [
        IBTVariableDefinition(name="UnknownFutureChannel", data_type="float", data_type_id=4)
    ]
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: result)
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")

    with pytest.raises(RuntimeError, match="UnknownFutureChannel"):
        service.import_ibt_file(tmp_path / "sample.ibt")

    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview("incomplete-archive") is None
    assert not parquet_path(tmp_path / "data", "incomplete-archive").exists()


@pytest.mark.parametrize(
    "failed_suffix",
    [".parquet", ".channels.json", ".telemetry-manifest.json"],
)
def test_each_cache_promotion_failure_rolls_back_all_artifacts_and_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_suffix: str,
) -> None:
    run_id = f"promotion-failure-{failed_suffix.removeprefix('.').replace('.', '-')}"
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result(run_id))
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")
    real_replace = import_service_module._atomic_replace
    failure_injected = False

    def fail_one_promotion(source: Path, destination: Path) -> None:
        nonlocal failure_injected
        is_final_destination = run_id in destination.name and ".tmp" not in destination.name
        if not failure_injected and is_final_destination and destination.name.endswith(failed_suffix):
            failure_injected = True
            raise OSError(f"injected {failed_suffix} promotion failure")
        real_replace(source, destination)

    monkeypatch.setattr(import_service_module, "_atomic_replace", fail_one_promotion)

    with pytest.raises(OSError, match="injected"):
        service.import_ibt_file(tmp_path / "sample.ibt")

    assert failure_injected is True
    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview(run_id) is None
    assert not parquet_path(tmp_path / "data", run_id).exists()
    assert not telemetry_manifest_path(tmp_path / "data", run_id).exists()
    assert list((tmp_path / "data").rglob(f"{run_id}*")) == []


def test_failed_duplicate_promotion_restores_previous_complete_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "restore-prior-cache"
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result(run_id))
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")
    service.import_ibt_file(tmp_path / "sample.ibt")
    paths = (
        parquet_path(tmp_path / "data", run_id),
        channel_metadata_path(tmp_path / "data", run_id),
        telemetry_manifest_path(tmp_path / "data", run_id),
    )
    original = {path: path.read_bytes() for path in paths}
    real_replace = import_service_module._atomic_replace
    failure_injected = False

    def fail_metadata_promotion(source: Path, destination: Path) -> None:
        nonlocal failure_injected
        if (
            not failure_injected
            and destination == channel_metadata_path(tmp_path / "data", run_id)
        ):
            failure_injected = True
            raise OSError("injected duplicate metadata promotion failure")
        real_replace(source, destination)

    monkeypatch.setattr(import_service_module, "_atomic_replace", fail_metadata_promotion)

    with pytest.raises(OSError, match="duplicate metadata"):
        service.import_ibt_file(tmp_path / "sample.ibt")

    assert failure_injected is True
    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview(run_id) is not None
    assert {path: path.read_bytes() for path in paths} == original


def test_fixed_width_string_channel_promotes_as_scalar_not_array(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _fake_result("string-channel")
    result.header = IBTHeader(record_length=8, record_count=2, telemetry_rate_hz=60)
    result.variable_definitions = [
        IBTVariableDefinition(
            name="Label",
            data_type="char",
            data_type_id=0,
            offset=0,
            count=8,
        )
    ]
    result.records = [
        {"lap": 1, "session_time": 0.0, "speed_mph": 120.0, "Label": "future"},
        {"lap": 1, "session_time": 1 / 60, "speed_mph": 121.0, "Label": "label"},
    ]
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: result)
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")

    imported, _cache = service.import_ibt_file(tmp_path / "sample.ibt")

    assert imported.overview is not None
    assert [row["Label"] for row in read_telemetry_rows("string-channel", tmp_path / "data")] == [
        "future",
        "label",
    ]
    manifest = read_telemetry_manifest("string-channel", tmp_path / "data")
    assert manifest["lossless_archive_complete"] is True
    assert manifest["scalar_channel_count"] == 1
    assert manifest["array_channel_count"] == 0
    assert manifest["channels"][0]["samples_per_record"] == 1
    assert manifest["channels"][0]["string_buffer_bytes"] == 8


def test_partial_stage_write_failure_removes_orphan_cache_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "partial-stage-write"
    monkeypatch.setattr(import_service_module, "import_ibt", lambda _path: _fake_result(run_id))
    service = ImportService(db_path=tmp_path / "racelab.sqlite", data_dir=tmp_path / "data")

    def fail_after_partial_write(
        temp_run_id: str,
        _rows: list[dict[str, object]],
        normalized_frame: object = None,
        data_dir: str | Path | None = None,
        profile_out: dict[str, float] | None = None,
    ) -> object:
        del normalized_frame, profile_out
        path = parquet_path(Path(data_dir), temp_run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"partial parquet")
        raise OSError("injected partial cache write")

    monkeypatch.setattr(import_service_module, "write_telemetry_cache", fail_after_partial_write)

    with pytest.raises(OSError, match="partial cache write"):
        service.import_ibt_file(tmp_path / "sample.ibt")

    assert RaceLabRepository(tmp_path / "racelab.sqlite").get_overview(run_id) is None
    assert list((tmp_path / "data").rglob("*.tmp.parquet")) == []
    assert list((tmp_path / "data").rglob("*.tmp.csv")) == []


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
