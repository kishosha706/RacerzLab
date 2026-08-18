from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import routes_compare
from racelab_engine.io.file_fingerprint import FileFingerprint
from racelab_engine.io.ibt_reader import _slug_run_id
from racelab_engine.io.ibt_types import IBTImportResult, ImportStatus
from racelab_engine.models.evidence import (
    BlockerPhysicalScope,
    EngineeringBlocker,
    EngineeringBlockerSeverity,
    EvidenceState,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.recording_identity import (
    SAME_RECORDING_MESSAGE,
    SameRecordingError,
    canonical_recording_run_id,
    require_independent_recordings,
)
from racelab_engine.services import import_service as import_service_module
from racelab_engine.services.import_service import ImportService, parquet_path
from racelab_engine.services.session_service import (
    add_run_to_session,
    create_session,
    get_session,
    rebind_recording_alias_memberships,
    set_last_opened,
)
from racelab_engine.services.setup_learning_service import (
    _source_runs_are_independent,
)
from racelab_engine.storage.repository import RaceLabRepository


def _overview(run_id: str, source_sha256: str, imported_minute: int) -> RunOverview:
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            source_file=f"{run_id}.ibt",
            file_hash=source_sha256,
            import_time=datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
            + timedelta(minutes=imported_minute),
        ),
    )


def test_full_source_sha_owns_run_identity_regardless_of_filename() -> None:
    source_sha = "a" * 64

    first = _slug_run_id(Path("first-name.ibt"), source_sha)
    renamed = _slug_run_id(Path("renamed-copy.ibt"), source_sha)

    assert first == renamed == canonical_recording_run_id(source_sha)
    assert source_sha in first


def test_source_independence_guard_rejects_run_aliases() -> None:
    source_sha = "b" * 64

    with pytest.raises(SameRecordingError, match="SAME RECORDING"):
        require_independent_recordings(
            {"legacy-a": source_sha, "legacy-b": source_sha},
            ordered_run_ids=("legacy-a", "legacy-b"),
        )


def test_legacy_recording_owner_is_reused_without_deleting_aliases(tmp_path: Path) -> None:
    source_sha = "c" * 64
    repository = RaceLabRepository(tmp_path / "racelab.sqlite")
    repository.save_import(_overview("legacy-first", source_sha, 0))
    repository.save_import(_overview("legacy-second", source_sha, 1))

    assert repository.find_recording_owner_run_id(source_sha) == "legacy-first"
    assert {item["run_id"] for item in repository.list_runs()} == {
        "legacy-first",
        "legacy-second",
    }
    assert {
        item["recording_sha256"] for item in repository.list_runs()
    } == {source_sha}
    assert not _source_runs_are_independent(
        ["legacy-first", "legacy-second"],
        db_path=repository.db_path,
    )


def test_unknown_recording_identity_cannot_enter_durable_learning(
    tmp_path: Path,
) -> None:
    repository = RaceLabRepository(tmp_path / "racelab.sqlite")

    assert not _source_runs_are_independent(
        ["missing-baseline", "missing-test", "missing-recheck"],
        db_path=repository.db_path,
    )


def test_reimport_upgrades_existing_legacy_owner_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_sha = "e" * 64
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    repository = RaceLabRepository(db_path)
    repository.save_import(_overview("legacy-owner", source_sha, 0))

    def decoded(_path: str | Path) -> IBTImportResult:
        decoded_run_id = canonical_recording_run_id(source_sha)
        lap = LapSummary(
            lap_id=f"{decoded_run_id}:lap:1",
            run_id=decoded_run_id,
            lap_number=1,
            is_complete=True,
            is_useful=True,
            lap_time=30.0,
        )
        return IBTImportResult(
            status=ImportStatus(status="ok", message="decoded"),
            fingerprint=FileFingerprint(
                path=str(_path),
                file_size=3,
                sha256=source_sha,
                modified_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
            ),
            records=[
                {
                    "lap": 1,
                    "lap_dist_pct": 0.5,
                    "session_time": 1.0,
                    "speed_mph": 150.0,
                }
            ],
            overview=RunOverview(
                run_id=decoded_run_id,
                session=SessionSummary(
                    run_id=decoded_run_id,
                    source_file=str(_path),
                    file_hash=source_sha,
                ),
                best_useful_lap=lap,
                laps=[lap],
                engineering_blockers=[
                    EngineeringBlocker(
                        code="TEST_SCOPE",
                        severity=EngineeringBlockerSeverity.INFO,
                        scope="test",
                        message="Test scope.",
                        evidence_state=EvidenceState.NEEDS_CONFIRMATION,
                        source_artifact_ids=(f"run:{decoded_run_id}",),
                        physical_scope=BlockerPhysicalScope(run_id=decoded_run_id),
                        recovery="Collect another source.",
                    )
                ],
            ),
        )

    monkeypatch.setattr(import_service_module, "import_ibt", decoded)
    service = ImportService(db_path=db_path, data_dir=data_dir)

    result, cache = service.import_ibt_file(tmp_path / "renamed.ibt")

    assert result.overview is not None
    assert result.overview.run_id == "legacy-owner"
    assert result.overview.laps[0].run_id == "legacy-owner"
    assert result.overview.laps[0].lap_id == "legacy-owner:lap:1"
    assert result.overview.engineering_blockers[0].source_artifact_ids == (
        "run:legacy-owner",
    )
    assert result.overview.engineering_blockers[0].physical_scope is not None
    assert (
        result.overview.engineering_blockers[0].physical_scope.run_id
        == "legacy-owner"
    )
    assert repository.get_overview(canonical_recording_run_id(source_sha)) is None
    assert repository.get_overview("legacy-owner") is not None
    assert cache is not None and cache.path == parquet_path(data_dir, "legacy-owner")


def test_session_membership_converges_on_recording_owner_without_deleting_aliases(
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    source_sha = "f" * 64
    repository = RaceLabRepository(database)
    repository.save_import(_overview("owner", source_sha, 0))
    repository.save_import(_overview("alias", source_sha, 1))
    first = create_session("First", database)
    second = create_session("Second", database)
    add_run_to_session(first.session_id, "alias", database)
    add_run_to_session(second.session_id, "owner", database)
    add_run_to_session(second.session_id, "alias", database)
    set_last_opened(first.session_id, "alias", db_path=database)

    updated = rebind_recording_alias_memberships(
        "owner",
        ("owner", "alias"),
        db_path=database,
    )

    assert updated == 2
    rebound_first = get_session(first.session_id, database)
    rebound_second = get_session(second.session_id, database)
    assert rebound_first is not None and rebound_first.run_ids == ["owner"]
    assert rebound_first.last_opened_run_id == "owner"
    assert rebound_second is not None and rebound_second.run_ids == ["owner"]
    assert repository.get_overview("alias") is not None


def test_compare_fails_closed_when_two_run_ids_share_one_recording(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_sha = "d" * 64
    repository = RaceLabRepository(tmp_path / "racelab.sqlite")
    repository.save_import(_overview("alias-a", source_sha, 0))
    repository.save_import(_overview("alias-b", source_sha, 1))
    monkeypatch.setattr(
        routes_compare,
        "read_telemetry_manifest",
        lambda _run_id: {"source_file_sha256": source_sha},
    )

    with pytest.raises(HTTPException) as raised:
        routes_compare._assert_independent_compare_recordings(
            "alias-a", "alias-b", repository
        )

    assert raised.value.status_code == 400
    assert SAME_RECORDING_MESSAGE in str(raised.value.detail)


def test_compare_fails_closed_when_recording_identity_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Repository:
        def get_recording_sha256(self, _run_id: str) -> None:
            return None

    monkeypatch.setattr(routes_compare, "read_telemetry_manifest", lambda _run_id: {})

    with pytest.raises(HTTPException) as raised:
        routes_compare._assert_independent_compare_recordings(
            "unknown-a", "unknown-b", _Repository()
        )

    assert raised.value.status_code == 400
    assert "Recording identity is unavailable" in str(raised.value.detail)
