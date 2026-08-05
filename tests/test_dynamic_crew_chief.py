from __future__ import annotations

from racelab_engine.analysis.dynamic_crew_chief import build_recommendations
from racelab_engine.analysis.evidence_contracts import (
    EvidenceEvaluationInput,
    SETUP_RECOMMENDATION_CONTRACT,
    evaluate_evidence_contract,
)
from racelab_engine.models.event import TelemetryEvent


def _event(event_id: str, *, valid_for_tuning: bool, confidence_score: float = 0.5, event_type: str = "PLATFORM_LOW") -> TelemetryEvent:
    return TelemetryEvent(
        event_id=event_id,
        run_id="run",
        event_type=event_type,
        confidence_score=confidence_score,
        valid_for_tuning=valid_for_tuning,
        evidence_state="calculated",
        source_channels=["lap_dist_pct", "speed_mph"],
        blocker_reasons=[],
    )


def _eligible_evidence():
    return evaluate_evidence_contract(
        SETUP_RECOMMENDATION_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=frozenset({"lap_dist_pct", "speed_mph"}),
            condition_results={
                "complete_flying_lap_coverage": True,
                "setup_snapshot_captured": True,
                "event_linked": True,
            },
            blocker_results={
                "junk_lap_context": False,
                "sample_or_sim_integrity_failure": False,
                "unisolated_setup_change": False,
                "short_run_sensitive_claim": False,
                "missing_data_substitution": False,
            },
            repetitions=1,
            requested_outputs=frozenset({"controlled_setup_test"}),
        ),
    )


def test_no_events_returns_calm_unavailable_state() -> None:
    assert build_recommendations("run", [], evidence_evaluation=_eligible_evidence()) == []


def test_events_present_but_none_valid_for_tuning_do_not_fake_recommendation() -> None:
    assert build_recommendations("run", [_event("e1", valid_for_tuning=False)], evidence_evaluation=_eligible_evidence()) == []


def test_valid_event_cannot_bypass_evidence_contract() -> None:
    assert build_recommendations("run", [_event("e1", valid_for_tuning=True)]) == []


def test_unknown_integrity_blocker_fails_closed() -> None:
    contract = SETUP_RECOMMENDATION_CONTRACT
    evidence = evaluate_evidence_contract(
        contract,
        EvidenceEvaluationInput(
            usable_channels=contract.required_channels | contract.preferred_channels,
            condition_results={item.key: True for item in contract.operating_conditions},
            blocker_results={
                item.key: (None if item.key == "sample_or_sim_integrity_failure" else False)
                for item in contract.hard_blockers
            },
            repetitions=3,
            requested_outputs=frozenset({"controlled_setup_test"}),
        ),
    )

    assert evidence.eligible is False
    assert build_recommendations(
        "run",
        [_event("e1", valid_for_tuning=True)],
        evidence_evaluation=evidence,
    ) == []


def test_multiple_tuning_candidates_use_strongest_supported_candidate() -> None:
    recommendations = build_recommendations(
        "run",
        [
            _event("e1", valid_for_tuning=True, confidence_score=0.7, event_type="WORST_SPEED_LOSS"),
            _event("e2", valid_for_tuning=True, confidence_score=0.95, event_type="MIN_SPLITTER"),
        ],
        evidence_evaluation=_eligible_evidence(),
    )

    assert len(recommendations) == 1
    assert recommendations[0].issue == "MIN_SPLITTER"
    assert recommendations[0].evidence_event_ids == ["e2"]
    assert recommendations[0].confidence_score == 0.65
    assert recommendations[0].evidence_strength == "medium"
    assert any("Preferred channels missing" in reason for reason in recommendations[0].confidence_limit_reasons)


def test_first_event_missing_optional_fields_does_not_crash() -> None:
    recommendations = build_recommendations("run", [_event("e1", valid_for_tuning=True, confidence_score=0.2)], evidence_evaluation=_eligible_evidence())

    assert recommendations[0].confidence_score == 0.2
    assert recommendations[0].evidence_strength == "low"


def test_proxy_event_keeps_cause_observational() -> None:
    event = _event(
        "e-proxy",
        valid_for_tuning=True,
        confidence_score=0.7,
        event_type="FULL_THROTTLE_SPEED_LOSS",
    ).model_copy(update={"is_proxy_based": True})

    recommendation = build_recommendations("run", [event], evidence_evaluation=_eligible_evidence())[0]

    assert "cause not established" in recommendation.cause_bucket
    assert "aero/platform" not in recommendation.cause_bucket
