from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    TargetZoneComparison,
    TestDisciplineResult as DisciplineResult,
)
from racelab_engine.analysis.did_it_work import compute_observation


def _zone(speed_delta: float | None, cfs_delta: float | None = 0.01) -> TargetZoneComparison:
    deltas = [
        ComparedChannelDelta("speed_mph", "Speed", "mph", delta=speed_delta),
        ComparedChannelDelta("cfs_ride_height_in", "CFS", "in", delta=cfs_delta),
    ]
    return TargetZoneComparison(start_pct=55.0, end_pct=70.0, channel_deltas=deltas)


def _discipline(label: str = "clean", score: int = 88) -> DisciplineResult:
    return DisciplineResult(score=score, label=label)


def test_clean_speed_gain_remains_an_observation_without_keep_authority() -> None:
    observation = compute_observation(_zone(0.2, 0.01), _discipline())

    assert observation.observation_state == "observed_improvement"
    assert observation.confidence_score > 0.7


def test_speed_loss_remains_an_observation_without_undo_authority() -> None:
    observation = compute_observation(_zone(-0.2, 0.01), _discipline())

    assert observation.observation_state == "observed_regression"
    assert "Speed delta" in observation.evidence[0]


def test_confirmation_observation_for_risky_gain() -> None:
    observation = compute_observation(_zone(0.2, -0.01), _discipline())

    assert observation.observation_state == "needs_confirmation"
    assert "splitter risk worsened" in observation.headline


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

    observation = compute_observation(
        TargetZoneComparison(start_pct=55.0, end_pct=70.0, channel_deltas=deltas),
        _discipline(),
    )

    assert observation.observation_state == "needs_confirmation"
    assert any("low 5th-percentile" in item for item in observation.evidence)


def test_insufficient_evidence_is_inconclusive() -> None:
    observation = compute_observation(_zone(None), _discipline())

    assert observation.observation_state == "inconclusive"
    assert "unavailable" in observation.evidence[0]


def test_mixed_discipline_forces_retest_without_fake_setup_result() -> None:
    observation = compute_observation(_zone(0.3, 0.02), _discipline("mixed", 50))

    assert observation.observation_state == "needs_confirmation"
    assert observation.warnings


def test_nearby_car_context_preserves_speed_gain_but_withholds_setup_credit() -> None:
    observation = compute_observation(
        _zone(0.3, 0.02),
        _discipline(),
        context_blocks_attribution=True,
        context_evidence=["Test proximity: Nearby Car Behind; behind 0.48 s."],
    )

    assert observation.observation_state == "needs_confirmation"
    assert "Speed improved" in observation.headline
    assert "prevents attributing it to the setup" in observation.headline
    assert "Observed target-zone speed delta: +0.30 mph." in observation.evidence
    assert "behind 0.48 s" in observation.evidence[1]


def test_missing_platform_delta_cannot_be_worded_as_stable_keep() -> None:
    observation = compute_observation(_zone(0.30, None), _discipline())

    assert observation.observation_state == "needs_confirmation"
    assert "supporting evidence is incomplete" in observation.headline
    assert "CFS ride-height delta" in observation.evidence[1]


def test_missing_driver_traces_cannot_be_treated_as_consistent() -> None:
    observation = compute_observation(
        _zone(0.30, 0.01),
        _discipline(),
        driver_evidence_available=False,
    )

    assert observation.observation_state == "needs_confirmation"
    assert "matched throttle, brake, and steering traces" in observation.evidence[1]
