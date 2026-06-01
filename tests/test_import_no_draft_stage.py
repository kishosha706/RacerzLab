from __future__ import annotations

from racelab_engine.services.import_service import ImportService


def test_import_has_no_draft_stage_timings(tmp_path, talladega_ibt_path) -> None:
    svc = ImportService(db_path=tmp_path / "racerzlab.db", data_dir=tmp_path / "data")
    result, cache = svc.import_ibt_file(talladega_ibt_path)

    assert cache is not None
    assert result.overview is not None
    assert "draft_detection" not in svc.last_import_timings
    assert "draft_detection_status" not in svc.last_import_timings


def test_import_status_does_not_claim_draft_detection(tmp_path, talladega_ibt_path) -> None:
    svc = ImportService(db_path=tmp_path / "racerzlab.db", data_dir=tmp_path / "data")
    result, _ = svc.import_ibt_file(talladega_ibt_path)

    message = result.status.message.lower()
    implemented = [item.lower() for item in result.status.implemented]
    assert "draft detection" not in message
    assert all("draft detection" not in item for item in implemented)
