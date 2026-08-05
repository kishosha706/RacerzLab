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


def test_localized_sustained_cfs_compression_blocks_keep_direction() -> None:
    zone = _zone(0.2, 0.012)
    deltas = [
        zone.channel_deltas[0],
        ComparedChannelDelta(
            "cfs_ride_height_in",
            "CFS",
            "in",
            delta=0.012,
            delta_min=-0.10,
            delta_low_p05=-0.03,
        ),
    ]

    verdict = compute_verdict(
        TargetZoneComparison(start_pct=55.0, end_pct=70.0, channel_deltas=deltas),
        _discipline(),
    )

    assert verdict.verdict == "retest"
    assert any("low 5th-percentile" in item for item in verdict.evidence)


def test_insufficient_evidence_is_inconclusive() -> None:
    verdict = compute_verdict(_zone(None), _discipline())

    assert verdict.verdict == "inconclusive"
    assert "unavailable" in verdict.evidence[0]


def test_mixed_discipline_forces_retest_without_fake_setup_result() -> None:
    verdict = compute_verdict(_zone(0.3, 0.02), _discipline("mixed", 50))

    assert verdict.verdict == "retest"
    assert verdict.warnings


def test_nearby_car_context_preserves_speed_gain_but_withholds_setup_credit() -> None:
    verdict = compute_verdict(
        _zone(0.3, 0.02),
        _discipline(),
        context_blocks_attribution=True,
        context_evidence=["Test proximity: Nearby Car Behind; behind 0.48 s."],
        context_retest_instruction=(
            "Keep this as an observed result, then repeat with no car within 1.5 s ahead or 0.5 s behind."
        ),
    )

    assert verdict.verdict == "retest"
    assert "Speed improved" in verdict.headline
    assert "prevents attributing it to the setup" in verdict.headline
    assert "Observed target-zone speed delta: +0.30 mph." in verdict.evidence
    assert "behind 0.48 s" in verdict.evidence[1]
    assert "Keep this as an observed result" in verdict.next_step


def test_missing_platform_delta_cannot_be_worded_as_stable_keep() -> None:
    verdict = compute_verdict(_zone(0.30, None), _discipline())

    assert verdict.verdict == "retest"
    assert "supporting evidence is incomplete" in verdict.headline
    assert "CFS ride-height delta" in verdict.evidence[1]


def test_missing_driver_traces_cannot_be_treated_as_consistent() -> None:
    verdict = compute_verdict(
        _zone(0.30, 0.01),
        _discipline(),
        driver_evidence_available=False,
    )

    assert verdict.verdict == "retest"
    assert "matched throttle, brake, and steering traces" in verdict.evidence[1]
