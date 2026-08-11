from __future__ import annotations

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.lap_windows import (
    _is_lap_valid_for_ranking,
    compute_best_windows,
    compute_degradation,
    compute_lap_windows_response,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import LapWindowSummary, StintCompareResult, StintSummary


def _lap(n: int, t: float = 50.0, useful: bool = True, tags: list[str] | None = None) -> LapSummary:
    return LapSummary(
        lap_id=f"r_l{n}",
        run_id="r",
        lap_number=n,
        lap_type="timed",
        is_complete=True,
        is_useful=useful,
        lap_time=t,
        classification_tags=tags or ["SOLO_CLEAN"],
    )


def test_validity_excludes_invalid_tags_only() -> None:
    ok, _ = _is_lap_valid_for_ranking(_lap(1, tags=["SOLO_CLEAN"]))
    assert ok
    bad, _ = _is_lap_valid_for_ranking(_lap(2, tags=["PIT_ROAD"]))
    assert not bad


def test_degradation_has_no_draft_warning_field() -> None:
    deg = compute_degradation([_lap(i, 50 + i * 0.1) for i in range(1, 12)])
    dumped = deg.model_dump()
    assert "draft_warning" not in dumped


def test_response_counts_valid_laps() -> None:
    laps = [_lap(i, 50 + i * 0.1) for i in range(1, 12)]
    resp = compute_lap_windows_response(laps)
    assert resp.total_laps == 11
    assert resp.total_valid_laps == 11
    assert resp.fastest_groups[0].laps[0].valid_for_compare is True


def test_missing_lap_numbers_split_windows_and_degradation() -> None:
    laps = [
        *[_lap(number, 50 + number * 0.1) for number in range(1, 11)],
        *[_lap(number, 50 + number * 0.1) for number in range(12, 22)],
    ]

    best_20 = compute_best_windows(laps, [20])[0]
    degradation = compute_degradation(laps)

    assert best_20.is_available is False
    assert best_20.best_window is None
    assert degradation.lap_count == 10


@pytest.mark.parametrize("field", ["recommendation", "setup_action", "next_setup_change"])
def test_lap_window_contract_rejects_injected_setup_authority(field: str) -> None:
    with pytest.raises(ValidationError):
        LapWindowSummary.model_validate({
            "window_id": "window-r-1-3",
            "run_id": "r",
            "start_lap": 1,
            "end_lap": 3,
            "window_size": 3,
            field: "Increase right-rear spring by 25 lb/in.",
        })


@pytest.mark.parametrize("field", ["recommendation", "verdict", "setup_action"])
def test_stint_comparison_contract_rejects_legacy_or_injected_authority(field: str) -> None:
    baseline = StintSummary(
        stint_id="baseline",
        run_id="baseline-run",
        start_lap=1,
        end_lap=3,
        lap_count=3,
        valid_lap_count=3,
    )
    test = baseline.model_copy(update={"stint_id": "test", "run_id": "test-run"})

    with pytest.raises(ValidationError):
        StintCompareResult.model_validate({
            "baseline_stint": baseline,
            "test_stint": test,
            field: "Keep the test setup.",
        })
