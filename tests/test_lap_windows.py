from __future__ import annotations

from racelab_engine.analysis.lap_windows import (
    _is_lap_valid_for_ranking,
    compute_degradation,
    compute_lap_windows_response,
)
from racelab_engine.models.lap import LapSummary


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
