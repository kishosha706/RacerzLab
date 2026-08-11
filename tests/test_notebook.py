from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_notebook import router
from racelab_engine.models.notebook import NotebookFinding
from racelab_engine.services.notebook_service import (
    find_duplicate,
    get_finding,
    list_findings,
    save_finding,
    update_finding,
)
from racelab_engine.storage.db import initialize_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_notebook.sqlite"


@pytest.fixture
def notebook_client(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_save_and_get_observational_finding(db_path: Path) -> None:
    finding = save_finding(
        car_name="Camaro ZL1",
        track_name="Talladega",
        setup_name="Baseline",
        baseline_run_id="bl_run_1",
        test_run_id="test_run_1",
        comparison_id="comp_1",
        baseline_lap=2,
        test_lap=3,
        target_zone_start_pct=55.0,
        target_zone_end_pct=70.0,
        confidence_score=0.75,
        confidence_tier="high",
        test_discipline_score=88.0,
        target_zone_classification="stable_gain",
        summary_headline="Speed changed while platform remained stable",
        key_takeaways=["Speed +0.3 mph in target zone", "CFS height unchanged"],
        evidence=["Speed delta: +0.320 mph", "CFS delta: +0.008 in"],
        warnings=["Short run"],
        sector_summaries=[{"sector_name": "Sector 1", "avg_speed_delta_mph": 0.15}],
        context_changes=[{"key": "air_temp", "warning": "Air temp changed"}],
        improved_metrics=["speed_mph"],
        worsened_metrics=[],
        notes="Review the evidence only.",
        tags=["talladega", "platform"],
        db_path=db_path,
    )

    assert finding.finding_id.startswith("finding_")
    assert finding.status == "saved"
    retrieved = get_finding(finding.finding_id, db_path)
    assert retrieved is not None
    assert retrieved.summary_headline == "Speed changed while platform remained stable"
    assert retrieved.key_takeaways == [
        "Speed +0.3 mph in target zone",
        "CFS height unchanged",
    ]
    assert retrieved.evidence == ["Speed delta: +0.320 mph", "CFS delta: +0.008 in"]


def test_notebook_model_and_response_have_no_policy_or_test_fields() -> None:
    payload = NotebookFinding(finding_id="finding_observation").as_dict()
    assert {
        "verdict",
        "setup_changes",
        "next_step",
        "recommended_next_test",
        "change_to_try",
    }.isdisjoint(payload)


def test_start_finish_zone_round_trips_without_default_substitution(db_path: Path) -> None:
    finding = save_finding(
        comparison_id="start-finish-comparison",
        baseline_run_id="baseline",
        test_run_id="test",
        target_zone_start_pct=0.0,
        target_zone_end_pct=5.0,
        db_path=db_path,
    )

    loaded = get_finding(finding.finding_id, db_path)
    assert loaded is not None
    assert loaded.target_zone_start_pct == 0.0
    assert loaded.target_zone_end_pct == 5.0


def test_list_findings_filters_only_observation_metadata(db_path: Path) -> None:
    first = save_finding(
        car_name="Car A",
        track_name="Track 1",
        tags=["platform"],
        db_path=db_path,
    )
    save_finding(car_name="Car B", track_name="Track 2", tags=["tires"], db_path=db_path)
    update_finding(first.finding_id, status="archived", db_path=db_path)

    assert len(list_findings(db_path=db_path)) == 2
    assert [item.car_name for item in list_findings(track_name="Track 1", db_path=db_path)] == [
        "Car A"
    ]
    assert [item.finding_id for item in list_findings(status="archived", db_path=db_path)] == [
        first.finding_id
    ]
    assert [item.finding_id for item in list_findings(tag="platform", db_path=db_path)] == [
        first.finding_id
    ]


def test_update_is_limited_to_notes_tags_and_archive_state(db_path: Path) -> None:
    finding = save_finding(evidence=["Speed delta +0.2 mph"], db_path=db_path)
    updated = update_finding(
        finding.finding_id,
        status="archived",
        notes="Personal observation",
        tags=["reviewed"],
        db_path=db_path,
    )

    assert updated is not None
    assert updated.status == "archived"
    assert updated.notes == "Personal observation"
    assert updated.tags == ["reviewed"]
    assert updated.evidence == ["Speed delta +0.2 mph"]
    with pytest.raises(ValueError, match="saved or archived"):
        update_finding(finding.finding_id, status="confirmed", db_path=db_path)  # type: ignore[arg-type]


def test_duplicate_detection_remains_observational(db_path: Path) -> None:
    finding = save_finding(
        comparison_id="comparison-1",
        baseline_run_id="baseline-1",
        test_run_id="test-1",
        evidence=["Observed delta"],
        db_path=db_path,
    )
    duplicate = find_duplicate(
        "comparison-1",
        "baseline-1",
        "test-1",
        db_path=db_path,
    )
    assert duplicate is not None
    assert duplicate.finding_id == finding.finding_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verdict", "keep_direction"),
        ("next_step", "Increase front spring rate"),
        ("setup_changes", [{"control": "front_spring", "delta": "+50"}]),
        ("change_to_try", "Reduce rear ride height"),
        ("recommended_next_test", "Repeat this setup change"),
        ("do_not_change", ["everything else"]),
    ],
)
def test_hostile_legacy_authority_fields_are_rejected_before_persistence(
    notebook_client: TestClient,
    db_path: Path,
    field: str,
    value: object,
) -> None:
    response = notebook_client.post(
        "/api/notebook/findings/from-comparison",
        json={
            "comparison_id": "hostile-client",
            "baseline_run_id": "baseline",
            "test_run_id": "test",
            "evidence": ["Observed speed delta"],
            field: value,
        },
    )

    assert response.status_code == 422
    assert list_findings(db_path=db_path) == []


def test_api_returns_observation_and_rejects_policy_status(
    notebook_client: TestClient,
) -> None:
    response = notebook_client.post(
        "/api/notebook/findings/from-comparison",
        json={
            "comparison_id": "observation-client",
            "baseline_run_id": "baseline",
            "test_run_id": "test",
            "evidence": ["Observed speed delta"],
            "notes": "Personal note",
            "tags": ["review"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"] == ["Observed speed delta"]
    assert payload["notes"] == "Personal note"
    assert payload["status"] == "saved"
    assert {"verdict", "setup_changes", "next_step"}.isdisjoint(payload)

    invalid_update = notebook_client.patch(
        f"/api/notebook/findings/{payload['finding_id']}",
        json={"status": "rejected"},
    )
    assert invalid_update.status_code == 422

    legacy_filter = notebook_client.get(
        "/api/notebook/findings",
        params={"verdict": "keep_direction"},
    )
    assert legacy_filter.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/notebook/test-plans"),
        ("get", "/api/notebook/setup-memory"),
        ("post", "/api/notebook/findings/finding_any/test-plan"),
    ],
)
def test_legacy_test_plan_and_setup_memory_routes_do_not_exist(
    notebook_client: TestClient,
    method: str,
    path: str,
) -> None:
    response = (
        notebook_client.post(path, json={})
        if method == "post"
        else notebook_client.get(path)
    )
    assert response.status_code == 404


def test_existing_database_is_physically_migrated_to_observation_only(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-notebook.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE notebook_findings (
          finding_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          car_name TEXT,
          track_name TEXT,
          setup_name TEXT,
          baseline_run_id TEXT,
          test_run_id TEXT,
          comparison_id TEXT,
          baseline_lap INTEGER,
          test_lap INTEGER,
          target_zone_start_pct REAL,
          target_zone_end_pct REAL,
          verdict TEXT,
          confidence_score REAL,
          confidence_tier TEXT,
          test_discipline_score REAL,
          target_zone_classification TEXT,
          summary_headline TEXT,
          key_takeaways_json TEXT,
          evidence_json TEXT,
          warnings_json TEXT,
          sector_summaries_json TEXT,
          setup_changes_json TEXT,
          context_changes_json TEXT,
          improved_metrics_json TEXT,
          worsened_metrics_json TEXT,
          next_step TEXT,
          notes TEXT,
          tags_json TEXT,
          status TEXT
        );
        CREATE TABLE test_plans (
          test_plan_id TEXT PRIMARY KEY,
          source_finding_id TEXT,
          change_to_try TEXT
        );
        INSERT INTO notebook_findings VALUES (
          'finding_legacy', '2026-01-01', '2026-01-01',
          'Car', 'Track', 'Setup', 'baseline', 'test', 'comparison', 1, 2, 55.0, 70.0,
          'keep_direction', 0.9, 'high', 90.0, 'stable_gain', 'Observed delta',
          '["Speed changed"]', '["Speed +0.2 mph"]', '[]', '[]',
          '[{"control":"front_spring","delta":"+50"}]', '[]', '["speed"]', '[]',
          'Increase front spring rate', 'Safe personal note', '["review"]', 'confirmed'
        );
        INSERT INTO test_plans VALUES ('plan_legacy', 'finding_legacy', 'Increase front spring rate');
        """
    )
    connection.commit()
    connection.close()

    migrated = initialize_database(db_path)
    columns = {
        row["name"] for row in migrated.execute("PRAGMA table_info(notebook_findings)")
    }
    tables = {
        row["name"]
        for row in migrated.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    row = migrated.execute(
        "SELECT evidence_json, notes, tags_json, status FROM notebook_findings"
    ).fetchone()
    dump = "\n".join(migrated.iterdump())
    migrated.close()

    assert {"verdict", "setup_changes_json", "next_step"}.isdisjoint(columns)
    assert "test_plans" not in tables
    assert row is not None
    assert row["evidence_json"] == '["Speed +0.2 mph"]'
    assert row["notes"] == "Safe personal note"
    assert row["tags_json"] == '["review"]'
    assert row["status"] == "saved"
    assert "keep_direction" not in dump
    assert "Increase front spring rate" not in dump


def test_notebook_storage_is_local_and_has_no_test_plan_table(db_path: Path) -> None:
    connection = initialize_database(db_path)
    table_names = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(notebook_findings)")
    }
    connection.close()

    assert "notebook_findings" in table_names
    assert "test_plans" not in table_names
    assert {"verdict", "setup_changes_json", "next_step"}.isdisjoint(columns)
