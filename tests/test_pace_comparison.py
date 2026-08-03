from __future__ import annotations

from racelab_engine.analysis.pace_comparison import build_pace_comparison
from racelab_engine.models.lap import LapSummary


def _laps(run_id: str, times: list[float]) -> list[LapSummary]:
    return [
        LapSummary(
            lap_id=f"{run_id}:{index}",
            run_id=run_id,
            lap_number=index,
            is_complete=True,
            is_useful=True,
            lap_time=lap_time,
            sample_count=100,
            classification_tags=["SOLO_CLEAN"],
        )
        for index, lap_time in enumerate(times, start=1)
    ]


def test_repeatable_median_gain_is_significant() -> None:
    result = build_pace_comparison(
        _laps("baseline", [50.0, 50.1, 49.9]),
        _laps("test", [49.5, 49.6, 49.4]),
        1,
        1,
    )

    assert result.direction == "faster"
    assert result.is_significant is True
    assert result.cohort_delta_s == -0.5


def test_overlapping_pace_is_inside_empirical_noise() -> None:
    result = build_pace_comparison(
        _laps("baseline", [50.0, 50.2, 49.8, 50.1]),
        _laps("test", [49.9, 50.3, 49.9, 50.0]),
        1,
        1,
    )

    assert result.direction == "no_clear_difference"
    assert result.is_significant is False


def test_short_runs_cannot_claim_repeatable_pace() -> None:
    result = build_pace_comparison(
        _laps("baseline", [50.0, 50.1]),
        _laps("test", [49.5, 49.6]),
        1,
        1,
    )

    assert result.direction == "insufficient_data"
    assert result.confidence_score <= 0.35


def test_unequal_runs_compare_the_same_early_stint_phase() -> None:
    result = build_pace_comparison(
        _laps("baseline", [30.0, 30.1, 30.2]),
        _laps("test", [29.5, 29.6, 29.7, 35.0, 36.0]),
        1,
        1,
    )

    assert result.direction == "faster"
    assert result.test_eligible_laps == 5
    assert result.test_median_lap_time_s == 29.6
    assert any("balanced" in note.lower() for note in result.confidence_notes)
