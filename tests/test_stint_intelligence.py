from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.analysis.stint_intelligence import build_stint_response, compare_stints
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.services.session_service import add_run_to_session, create_session
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
    assert response.stints == response.stint_rows
    assert response.stints == response.primary_stints
    assert len(response.stint_rows) == 1
    assert [stint.display_label_short for stint in response.primary_stints] == [
        "Full run",
    ]
    assert [stint.display_label_short for stint in response.best_window_cards] == [
        "Best 3",
        "Best 5",
        "Best 7",
        "Best 10",
        "Best 15",
        "Best 20",
        "Best 25",
        "Best 30",
        "Best 40",
    ]
    full = response.stints[0]
    assert full.valid_lap_count == 42
    assert set(full.best_avg_by_size) == {"3", "5", "7", "10", "15", "20", "25", "30", "40", "50", "60"}
    assert full.rolling_3_avg_best is not None
    assert full.rolling_5_avg_best is not None
    assert full.rolling_7_avg_best is not None
    assert full.rolling_10_avg_best is not None
    assert full.rolling_15_avg_best is not None
    assert full.rolling_20_avg_best is not None
    assert full.rolling_25_avg_best is not None
    assert full.rolling_30_avg_best is not None
    assert full.rolling_40_avg_best is not None
    assert full.rolling_50_avg_best is None
    assert full.rolling_60_avg_best is None
    assert full.avg_lap_time is not None
    assert len(full.bucket_averages) == 12
    assert full.bucket_averages[0].label == "L1-5"
    assert full.bucket_averages[0].avg_lap_time is not None
    assert full.bucket_averages[7].label == "L36-40"
    assert full.bucket_averages[7].avg_lap_time is not None
    assert full.bucket_averages[8].label == "L41-45"
    assert full.bucket_averages[8].avg_lap_time is None
    assert full.bucket_averages[11].label == "L56-60"
    assert full.bucket_averages[11].avg_lap_time is None
    assert any(bucket.is_fastest_bucket for bucket in full.bucket_averages)
    assert full.lap_points
    assert full.lap_points[0].stint_lap == 1
    assert full.lap_points[0].lap_time is not None
    assert full.lap_points[0].delta_to_best is not None
    assert full.lap_points[0].avg_speed_mph is None
    assert full.lap_points[0].max_speed_mph is None
    assert full.lap_points[0].min_speed_mph is None
    assert full.lap_points[0].fuel is None
    assert full.lap_points[0].invalid_reason is None
    assert any(point.rolling_5 is not None for point in full.lap_points)
    assert response.run_summary is not None
    assert response.run_summary.full_stint_avg == full.avg_lap_time
    assert response.run_summary.best_20_avg == next(card for card in response.best_window_cards if card.lap_count == 20).avg_lap_time
    assert response.run_summary.best_50_avg is None
    assert response.run_summary.best_60_avg is None


def test_best_window_cards_exclude_near_duplicate_overlapping_windows_from_table_rows() -> None:
    response = build_stint_response(_laps(50))

    labels = [stint.display_label_short for stint in response.best_window_cards]
    assert labels.count("Best 40") == 1
    assert labels.count("Best 50") == 1
    assert "Best 60" not in labels
    assert "Best 40" not in [stint.display_label_short for stint in response.stint_rows]
    assert len(response.all_windows) >= len(response.best_window_cards)
    assert len(response.stint_rows) == 1


def test_50_and_60_lap_averages_are_computed_only_when_enough_valid_laps_exist() -> None:
    response = build_stint_response(_laps(65))
    full = response.stints[0]

    assert full.rolling_50_avg_best is not None
    assert full.rolling_60_avg_best is not None
    assert full.best_avg_by_size["50"] == full.rolling_50_avg_best
    assert full.best_avg_by_size["60"] == full.rolling_60_avg_best
    assert full.bucket_averages[10].label == "L51-55"
    assert full.bucket_averages[10].avg_lap_time is not None
    assert full.bucket_averages[11].label == "L56-60"
    assert full.bucket_averages[11].avg_lap_time is not None
    assert any(card.display_label_short == "Best 50" for card in response.best_window_cards)
    assert any(card.display_label_short == "Best 60" for card in response.best_window_cards)


def test_bucket_progression_contract_stays_distinct_from_best_rolling_averages() -> None:
    laps = [
        _lap(index, 51.0 if index <= 5 else 50.0 if index <= 10 else 50.5)
        for index in range(1, 31)
    ]
    full = build_stint_response(laps).stints[0]

    assert full.best_avg_by_size["5"] is not None
    assert [bucket.label for bucket in full.bucket_averages[:6]] == [
        "L1-5",
        "L6-10",
        "L11-15",
        "L16-20",
        "L21-25",
        "L26-30",
    ]
    assert all(bucket.label not in full.best_avg_by_size for bucket in full.bucket_averages)
    assert full.bucket_averages[0].avg_lap_time == 51.0
    assert full.best_avg_by_size["5"] == 50.0


def test_invalid_laps_are_excluded_without_missing_to_zero() -> None:
    laps = _laps(12)
    laps[4] = _lap(5, 49.0, useful=False, tags=["PIT_ROAD"])

    response = build_stint_response(laps)
    full = response.stints[0]

    assert full.lap_count == 12
    assert full.valid_lap_count == 11
    assert any("excluded" in warning.lower() for warning in full.warnings)
    assert full.best_lap_time != 0
    assert full.best_avg_by_size["5"] is not None
    assert full.best_avg_by_size["10"] is None
    limited_bucket = full.bucket_averages[0]
    assert limited_bucket.avg_lap_time is None
    assert limited_bucket.warning is not None
    invalid_point = next(point for point in full.lap_points if point.lap_number == 5)
    assert invalid_point.valid is False
    assert invalid_point.lap_time == 49.0
    assert invalid_point.delta_to_best is None
    assert invalid_point.invalid_reason is not None
    assert invalid_point.warning is not None


def test_insufficient_laps_marked_unavailable() -> None:
    response = build_stint_response(_laps(2))

    assert response.stints == []
    assert response.stint_rows == []
    assert response.best_window_cards == []
    assert response.warnings
    assert "No eligible stint windows yet" in response.warnings[0]
    assert any("Need at least 3 valid laps" in warning for warning in response.warnings)
    assert any("Import or select a longer clean run" in warning for warning in response.warnings)


def test_nan_and_infinite_lap_times_are_excluded_without_poisoning_averages() -> None:
    laps = _laps(12)
    laps[2] = _lap(3, float("nan"))
    laps[6] = _lap(7, float("inf"))

    response = build_stint_response(laps)
    full = response.stints[0]

    assert full.valid_lap_count == 10
    assert full.avg_lap_time is not None
    assert full.avg_lap_time == full.avg_lap_time
    assert full.best_lap_time != 0
    assert any("excluded" in warning.lower() for warning in full.warnings)


def test_all_invalid_laps_return_limited_state_without_crash() -> None:
    response = build_stint_response([
        _lap(1, 50.0, useful=False, tags=["OUT_LAP"]),
        _lap(2, float("nan")),
        _lap(3, 51.0, useful=False, tags=["PIT_ROAD"]),
    ])

    assert response.stints == []
    assert response.run_summary is not None
    assert response.run_summary.data_status == "Limited"
    assert response.warnings


def test_falloff_classification_and_limited_trends_are_truthful() -> None:
    laps = [_lap(i, 50.0 + i * 0.08) for i in range(1, 25)]

    full = build_stint_response(laps).stints[0]

    assert full.stint_label in {"late falloff", "early fade", "usable with caution"}
    assert full.tire_trend_label == "tire data limited"
    assert full.shock_trend_label == "shock data limited"


def test_compare_result_computes_deltas() -> None:
    baseline = build_stint_response(_laps(15, run_id="baseline", start_time=51.0)).stints[0]
    test = next(card for card in build_stint_response(_laps(15, run_id="test", start_time=50.5)).best_window_cards if card.lap_count == 5)

    result = compare_stints(baseline, test)

    assert result.avg_delta is not None
    assert result.avg_delta < 0
    assert result.best_delta is not None
    assert result.bucket_deltas
    assert result.bucket_deltas[0].label == "L1-5"
    assert result.bucket_deltas[0].delta is not None
    assert result.verdict
    assert result.same_length_avg_delta is None
    assert result.rolling_delta_by_size["5"] is not None
    assert result.comparison_warnings


def test_best_average_highlight_metadata_marks_fastest_cells() -> None:
    response = build_stint_response(_laps(65))

    assert any(card.best_average_size_flags for card in response.best_window_cards)
    best_60 = next(card for card in response.best_window_cards if card.lap_count == 60)
    assert 60 in best_60.best_average_size_flags
    assert "best_60" in best_60.highlight_tags
    assert any(stint.is_best_fastest_lap for stint in [*response.stint_rows, *response.best_window_cards])


def test_stints_endpoint_returns_summaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path)
    client = TestClient(app)

    response = client.get("/api/runs/run-1/stints")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-1"
    assert payload["stints"]
    assert payload["stint_rows"] == payload["stints"]
    assert payload["primary_stints"]
    assert payload["best_window_cards"]
    assert payload["run_summary"]["full_stint_avg"] is not None
    assert {"stint_id", "bucket_averages", "lap_points", "display_label_short", "setup_usefulness_score"}.issubset(payload["stints"][0])
    assert payload["stints"][0]["lap_points"][0]["lap_time"] is not None
    assert {"avg_speed_mph", "max_speed_mph", "min_speed_mph", "fuel", "invalid_reason"}.issubset(payload["stints"][0]["lap_points"][0])
    assert payload["stints"][0]["lap_points"][0]["fuel"] is None


def test_session_runs_endpoint_returns_only_runs_in_loaded_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, run_id="session-run-a")
    _seed_run(tmp_path, run_id="session-run-b")
    _seed_run(tmp_path, run_id="historical-run-c")
    session = create_session(name="Session Scope Test")
    add_run_to_session(session.session_id, "session-run-a")
    add_run_to_session(session.session_id, "session-run-b")
    client = TestClient(app)

    response = client.get(f"/api/sessions/{session.session_id}/runs")

    assert response.status_code == 200
    payload = response.json()
    assert [item["run_id"] for item in payload] == ["session-run-a", "session-run-b"]
    assert all(item["run_id"] != "historical-run-c" for item in payload)


def test_stints_compare_endpoint_returns_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, run_id="baseline")
    _seed_run(tmp_path, run_id="test")
    client = TestClient(app)

    baseline = client.get("/api/runs/baseline/stints").json()["stints"][0]
    test = client.get("/api/runs/test/stints").json()["best_window_cards"][1]
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
