from __future__ import annotations

from racelab_engine.analysis.dynamic_crew_chief import build_recommendations
from racelab_engine.models.event import TelemetryEvent


def _event(event_id: str, *, valid_for_tuning: bool, confidence_score: float = 0.5, event_type: str = "PLATFORM_LOW") -> TelemetryEvent:
    return TelemetryEvent(
        event_id=event_id,
        run_id="run",
        event_type=event_type,
        confidence_score=confidence_score,
        valid_for_tuning=valid_for_tuning,
    )


def test_no_events_returns_calm_unavailable_state() -> None:
    assert build_recommendations("run", []) == []


def test_events_present_but_none_valid_for_tuning_do_not_fake_recommendation() -> None:
    assert build_recommendations("run", [_event("e1", valid_for_tuning=False)]) == []


def test_multiple_tuning_candidates_use_first_ranked_candidate() -> None:
    recommendations = build_recommendations(
        "run",
        [
            _event("e1", valid_for_tuning=True, confidence_score=0.7, event_type="WORST_SPEED_LOSS"),
            _event("e2", valid_for_tuning=True, confidence_score=0.95, event_type="MIN_SPLITTER"),
        ],
    )

    assert len(recommendations) == 1
    assert recommendations[0].issue == "WORST_SPEED_LOSS"
    assert recommendations[0].evidence_event_ids == ["e1"]


def test_first_event_missing_optional_fields_does_not_crash() -> None:
    recommendations = build_recommendations("run", [_event("e1", valid_for_tuning=True, confidence_score=0.2)])

    assert recommendations[0].confidence_score == 0.2
    assert recommendations[0].evidence_strength == "medium"
