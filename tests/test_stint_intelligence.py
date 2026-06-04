from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.analysis.stint_intelligence import build_stint_response, compare_stints
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.storage.repository import RaceLabRepository
from test_setup_evidence_adapter import _configure_env


def _lap(
    n: int,
    t: float,
    *,
    run_id: str = "run-1",
    useful: bool = True,
    tags: list[str] | None = None,
) -> LapSummary:
    return LapSummary(
        lap_id=f"{run_id}:lap:{n}",
        run_id=run_id,
        lap_number=n,
        lap_type="timed",
        is_complete=True,
        is_useful=useful,
        lap_time=t,
        classification_tags=tags or ["SOLO_CLEAN"],
        sample_count=120,
        min_splitter_mm=25.0,
    )


def _laps(count: int, *, run_id: str = "run-1", start_time: float = 50.0, slope: float = 0.02) -> list[LapSummary]:
    return [_lap(i, start_time + i * slope, run_id=run_id) for i in range(1, count + 1)]


def _seed_run(tmp_path: Path, run_id: str = "run-1", lap_count: int = 18) -> None:
    db_path = tmp_path / "racelab.sqlite"
    repo = RaceLabRepository(db_path=db_path)
    repo.initialize()
    repo.save_import(
        RunOverview(
            run_id=run_id,
            session=SessionSummary(
                run_id=run_id,
                car_name="NASCAR Cup Series Next Gen Chevrolet Camaro ZL1",
                track_name="Charlotte Oval",
                track_display_name="Charlotte Oval",
                setup_name="Baseline",
                session_type="Practice",
            ),
            laps=_laps(lap_count, run_id=run_id),
        )
    )


def test_stint_response_returns_curated_primary_rows_and_buckets() -> None:
    laps = _laps(42)

    response = build_stint_response(laps)

    assert response.run_id == "run-1"
    assert response.stints
    assert response.stints == response.primary_stints
    assert len(response.primary_stints) <= 6
    assert [stint.display_label_short for stint in response.primary_stints] == [
        "Full run",
        "Best 5",
        "Best 10",
        "Best 20",
        "Best 30",
        "Best 40",
    ]
    full = response.stints[0]
    assert full.valid_lap_count == 42
    assert full.rolling_5_avg_best is not None
    assert full.rolling_10_avg_best is not None
    assert full.rolling_20_avg_best is not None
    assert full.avg_lap_time is not None
    assert full.bucket_averages[0].label == "L1-5"
    assert full.bucket_averages[0].avg_lap_time is not None
    assert any(bucket.is_fastest_bucket for bucket in full.bucket_averages)


def test_primary_stints_exclude_near_duplicate_overlapping_windows() -> None:
    response = build_stint_response(_laps(50))

    labels = [stint.display_label_short for stint in response.primary_stints]
    assert labels.count("Best 40") == 1
    assert len(response.all_windows) >= len(response.primary_stints) - 1
    assert len(response.primary_stints) <= 6


def test_invalid_laps_are_excluded_without_missing_to_zero() -> None:
    laps = _laps(12)
    laps[4] = _lap(5, 49.0, useful=False, tags=["PIT_ROAD"])

    response = build_stint_response(laps)
    full = response.stints[0]

    assert full.lap_count == 12
    assert full.valid_lap_count == 11
    assert any("excluded" in warning.lower() for warning in full.warnings)
    assert full.best_lap_time != 0
    limited_bucket = full.bucket_averages[0]
    assert limited_bucket.avg_lap_time is None
    assert limited_bucket.warning is not None


def test_insufficient_laps_marked_unavailable() -> None:
    response = build_stint_response(_laps(4))

    assert response.stints == []
    assert response.warnings
    assert "No eligible stint windows yet" in response.warnings[0]
    assert any("Import or select a longer clean run" in warning for warning in response.warnings)


def test_falloff_classification_and_limited_trends_are_truthful() -> None:
    laps = [_lap(i, 50.0 + i * 0.08) for i in range(1, 25)]

    full = build_stint_response(laps).stints[0]

    assert full.stint_label in {"late falloff", "early fade", "usable with caution"}
    assert full.tire_trend_label == "tire data limited"
    assert full.shock_trend_label == "shock data limited"


def test_compare_result_computes_deltas() -> None:
    baseline = build_stint_response(_laps(15, run_id="baseline", start_time=51.0)).stints[0]
    test = build_stint_response(_laps(15, run_id="test", start_time=50.5)).stints[0]

    result = compare_stints(baseline, test)

    assert result.avg_delta is not None
    assert result.avg_delta < 0
    assert result.best_delta is not None
    assert result.bucket_deltas
    assert result.bucket_deltas[0].label == "L1-5"
    assert result.bucket_deltas[0].delta is not None
    assert result.verdict


def test_stints_endpoint_returns_summaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path)
    client = TestClient(app)

    response = client.get("/api/runs/run-1/stints")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-1"
    assert payload["stints"]
    assert payload["primary_stints"]
    assert {"stint_id", "bucket_averages", "display_label_short", "setup_usefulness_score"}.issubset(payload["stints"][0])


def test_stints_compare_endpoint_returns_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, run_id="baseline")
    _seed_run(tmp_path, run_id="test")
    client = TestClient(app)

    baseline = client.get("/api/runs/baseline/stints").json()["stints"][0]
    test = client.get("/api/runs/test/stints").json()["stints"][0]
    response = client.post(
        "/api/stints/compare",
        json={
            "baseline_run_id": "baseline",
            "baseline_stint_id": baseline["stint_id"],
            "test_run_id": "test",
            "test_stint_id": test["stint_id"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "avg_delta" in payload
    assert payload["baseline_stint"]["stint_id"] == baseline["stint_id"]
