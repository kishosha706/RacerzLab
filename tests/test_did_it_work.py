from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    TargetZoneComparison,
    TestDisciplineResult as DisciplineResult,
)
from racelab_engine.analysis.did_it_work import compute_verdict


def _zone(speed_delta: float | None, cfs_delta: float | None = 0.01) -> TargetZoneComparison:
    deltas = [
        ComparedChannelDelta("speed_mph", "Speed", "mph", delta=speed_delta),
        ComparedChannelDelta("cfs_ride_height_in", "CFS", "in", delta=cfs_delta),
    ]
    return TargetZoneComparison(start_pct=55.0, end_pct=70.0, channel_deltas=deltas)


def _discipline(label: str = "clean", score: int = 88) -> DisciplineResult:
    return DisciplineResult(score=score, label=label)


def test_keep_direction_verdict_for_clean_speed_gain() -> None:
    verdict = compute_verdict(_zone(0.2, 0.01), _discipline())

    assert verdict.verdict == "keep_direction"
    assert verdict.confidence_score > 0.7


def test_undo_verdict_for_speed_loss() -> None:
    verdict = compute_verdict(_zone(-0.2, 0.01), _discipline())

    assert verdict.verdict == "undo"
    assert "Speed delta" in verdict.evidence[0]


def test_retest_verdict_for_risky_gain() -> None:
    verdict = compute_verdict(_zone(0.2, -0.01), _discipline())

    assert verdict.verdict == "retest"
    assert "splitter risk worsened" in verdict.headline


def test_insufficient_evidence_is_inconclusive() -> None:
    verdict = compute_verdict(_zone(None), _discipline())

    assert verdict.verdict == "inconclusive"
    assert "unavailable" in verdict.evidence[0]


def test_mixed_discipline_forces_retest_without_fake_setup_result() -> None:
    verdict = compute_verdict(_zone(0.3, 0.02), _discipline("mixed", 50))

    assert verdict.verdict == "retest"
    assert verdict.warnings
