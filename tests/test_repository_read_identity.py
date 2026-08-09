from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import (
    RaceLabRepository,
    StoredEvidenceIntegrityError,
)


def _seed_evidence_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str = "identity-run",
) -> tuple[RaceLabRepository, TelemetryEvent, Recommendation]:
    db_path = tmp_path / "racelab.sqlite"
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    laps = [
        LapSummary(
            lap_id=f"{run_id}:lap:{lap_number}",
            run_id=run_id,
            lap_number=lap_number,
            lap_type="timed",
            is_complete=True,
            is_useful=True,
            lap_time=90.0 + (lap_number - 1) * 0.5,
            pct_min=0.0,
            pct_max=100.0,
            pct_span=100.0,
            sample_count=1_000,
            avg_speed_mph=120.0,
            classification_tags=["SOLO_CLEAN"],
        )
        for lap_number in range(1, 7)
    ]
    event = TelemetryEvent(
        event_id=f"{run_id}:event:2",
        run_id=run_id,
        lap_number=2,
        event_type="PLATFORM_LOW",
        valid_for_tuning=True,
        evidence_state=EvidenceState.MEASURED,
        source_channels=["speed_mph"],
        blocker_reasons=[],
        recommended_actions=["Inspect the measured platform event."],
    )
    recommendation = Recommendation(
        recommendation_id=f"{run_id}:recommendation:1",
        run_id=run_id,
        issue="Platform",
        recommendation_text="Inspect the measured platform event.",
        evidence_event_ids=[event.event_id],
        evidence_state=EvidenceState.MEASURED,
        source_channels=["speed_mph"],
        blocker_reasons=[],
    )
    repository = RaceLabRepository(db_path)
    repository.save_import(
        RunOverview(
            run_id=run_id,
            session=SessionSummary(
                run_id=run_id,
                car_name="Cup",
                track_name="Identity Test Oval",
            ),
            laps=laps,
            events=[event],
            recommendations=[recommendation],
        )
    )
    return repository, event, recommendation


@pytest.mark.parametrize(
    ("identity_field", "identity_value"),
    [
        ("run_id", "foreign-run"),
        ("lap_id", "foreign-lap-id"),
        ("lap_number", 3),
    ],
)
def test_get_laps_rejects_embedded_identity_mismatch_instead_of_ranking_false_best(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity_field: str,
    identity_value: str | int,
) -> None:
    repository, _event, _recommendation = _seed_evidence_run(tmp_path, monkeypatch)
    original = repository.get_laps("identity-run")[-1]
    hostile = original.model_copy(
        update={identity_field: identity_value, "lap_time": 1.0}
    )
    connection = initialize_database(repository.db_path)
    with connection:
        connection.execute(
            "UPDATE laps SET lap_json = ? WHERE run_id = ? AND lap_number = ?",
            (hostile.model_dump_json(), "identity-run", 6),
        )
    connection.close()

    with pytest.raises(StoredEvidenceIntegrityError, match="lap-derived metrics are unavailable"):
        repository.get_laps("identity-run")

    overview = repository.get_overview("identity-run")
    assert overview is not None
    assert overview.best_useful_lap is not None
    assert overview.best_useful_lap.lap_time == pytest.approx(90.0)
    assert len(overview.laps) == 5
    assert any("stored lap summary" in warning for warning in overview.warnings)


def test_lap_apis_withhold_windows_and_stints_when_any_lap_identity_is_untrusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _event, _recommendation = _seed_evidence_run(tmp_path, monkeypatch)
    original = repository.get_laps("identity-run")[-1]
    hostile = original.model_copy(update={
        "run_id": "foreign-run",
        "lap_id": "foreign-run:lap:1",
        "lap_number": 1,
        "lap_time": 1.0,
    })
    connection = initialize_database(repository.db_path)
    with connection:
        connection.execute(
            "UPDATE laps SET lap_json = ? WHERE run_id = ? AND lap_number = ?",
            (hostile.model_dump_json(), "identity-run", 6),
        )
    connection.close()

    client = TestClient(app)
    for path in (
        "/api/runs/identity-run/laps",
        "/api/runs/identity-run/lap-windows",
        "/api/runs/identity-run/stints",
    ):
        response = client.get(path)
        assert response.status_code == 409
        assert "lap-derived metrics are unavailable" in response.json()["detail"]
        assert "1.0" not in response.text


@pytest.mark.parametrize(
    ("identity_field", "identity_value"),
    [
        ("event_id", "foreign-event"),
        ("run_id", "foreign-run"),
        ("lap_number", 1),
    ],
)
def test_get_events_rejects_embedded_identity_mismatch_before_lap_relabeling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity_field: str,
    identity_value: str | int,
) -> None:
    repository, event, _recommendation = _seed_evidence_run(tmp_path, monkeypatch)
    hostile = event.model_copy(update={identity_field: identity_value})
    connection = initialize_database(repository.db_path)
    with connection:
        connection.execute(
            "UPDATE events SET event_json = ? WHERE event_id = ?",
            (hostile.model_dump_json(), event.event_id),
        )
    connection.close()

    with pytest.raises(
        StoredEvidenceIntegrityError,
        match="event-derived conclusions are unavailable",
    ):
        repository.get_events("identity-run", lap=2)

    response = TestClient(app).get("/api/runs/identity-run/events?lap=2")
    assert response.status_code == 409
    assert "event-derived conclusions are unavailable" in response.json()["detail"]
    overview = repository.get_overview("identity-run")
    assert overview is not None
    assert overview.events == []
    assert any("stored telemetry event" in warning for warning in overview.warnings)


@pytest.mark.parametrize(
    ("identity_field", "identity_value"),
    [
        ("recommendation_id", "foreign-recommendation"),
        ("run_id", "foreign-run"),
    ],
)
def test_get_recommendations_rejects_embedded_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity_field: str,
    identity_value: str,
) -> None:
    repository, _event, recommendation = _seed_evidence_run(tmp_path, monkeypatch)
    hostile = recommendation.model_copy(update={identity_field: identity_value})
    connection = initialize_database(repository.db_path)
    with connection:
        connection.execute(
            "UPDATE recommendations SET recommendation_json = ? WHERE recommendation_id = ?",
            (hostile.model_dump_json(), recommendation.recommendation_id),
        )
    connection.close()

    with pytest.raises(
        StoredEvidenceIntegrityError,
        match="recommendation conclusions are unavailable",
    ):
        repository.get_recommendations("identity-run")

    overview = repository.get_overview("identity-run")
    assert overview is not None
    assert overview.recommendations == []
    assert any("stored recommendation" in warning for warning in overview.warnings)


@pytest.mark.parametrize(
    ("table_name", "json_column", "reader_name", "error_text"),
    [
        ("laps", "lap_json", "get_laps", "lap-derived metrics are unavailable"),
        ("events", "event_json", "get_events", "event-derived conclusions are unavailable"),
        (
            "recommendations",
            "recommendation_json",
            "get_recommendations",
            "recommendation conclusions are unavailable",
        ),
    ],
)
def test_direct_evidence_reads_reject_malformed_selected_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    table_name: str,
    json_column: str,
    reader_name: str,
    error_text: str,
) -> None:
    repository, _event, _recommendation = _seed_evidence_run(tmp_path, monkeypatch)
    connection = initialize_database(repository.db_path)
    with connection:
        connection.execute(
            f"UPDATE {table_name} SET {json_column} = '{{bad' WHERE run_id = ?",
            ("identity-run",),
        )
    connection.close()

    reader = getattr(repository, reader_name)
    with pytest.raises(StoredEvidenceIntegrityError, match=error_text):
        reader("identity-run")
