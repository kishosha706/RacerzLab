from __future__ import annotations

from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.evidence_contracts import EvidenceState
from racelab_engine.analysis.test_director import TestEvidenceLink


def _opportunity(**updates):
    values = {
        "start_pct": 20.0,
        "end_pct": 30.0,
        "phase": "entry",
        "observed_time_loss_s": 0.2,
        "empirical_noise_s": 0.05,
        "alignment_confidence": 0.9,
        "repeatable": True,
        "evidence_links": (TestEvidenceLink(
            event_id="entry-event",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="entry",
            related_setup_keys=("cross_weight_percent", "front_brake_bias_percent"),
        ),),
        "source_channels": ("lap_dist_pct", "speed_mph", "brake_pct"),
        "supporting_evidence": ("Entry loss repeated on three eligible laps.",),
        "contradictory_evidence": ("Center speed was unchanged.",),
    }
    values.update(updates)
    return OpportunityEvidence(**values)


def _candidate(key: str, score: float, event: str = "entry-event") -> CauseCandidate:
    semantic_identity = {
        "cross_weight_percent": ("add_crossweight_small", "factor:crossweight"),
        "front_brake_bias_percent": (
            "add_front_brake_bias_small",
            "factor:front_brake_distribution",
        ),
    }[key]
    return CauseCandidate(
        cause_bucket="corner_balance",
        effect_id=semantic_identity[0],
        control_key=key,
        direction_sign=1,
        experiment_factor_id=semantic_identity[1],
        score=score,
        hypothesis="A small controlled input may reduce the repeatable entry loss.",
        success_metrics=("Entry phase time improves beyond 0.05 s",),
        countereffects=("Center speed must not worsen",),
        supporting_event_ids=(event,),
    )


def test_packet_exposes_exactly_one_event_linked_setup_test() -> None:
    packet = build_kaizen_packet(
        opportunity=_opportunity(),
        canonical_symptom="tight_entry",
        candidates=[_candidate("cross_weight_percent", 0.8), _candidate("front_brake_bias_percent", 0.7)],
        current_setup_values={"cross_weight_percent": 50.0, "front_brake_bias_percent": 52.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5], "front_brake_bias_percent": [52.0, 52.5]},
        legal_value_provenance_by_control={"cross_weight_percent": {"50.5": ["tech:run-b"]}, "front_brake_bias_percent": {"52.5": ["tech:run-c"]}},
    )
    assert packet.decision == "test"
    assert packet.evidence_state is EvidenceState.NEEDS_CONFIRMATION
    assert packet.primary_test is not None
    assert packet.primary_test.control_key == "cross_weight_percent"
    assert packet.primary_test.evidence_event_ids == ("entry-event",)
    assert packet.held_back_alternatives == 1
    assert packet.recommendation_score_basis is not None
    assert packet.measurement_mission is None


def test_packet_returns_measurement_mission_inside_noise_or_without_event_link() -> None:
    packet = build_kaizen_packet(
        opportunity=_opportunity(observed_time_loss_s=0.03),
        canonical_symptom="tight_entry",
        candidates=[_candidate("cross_weight_percent", 0.8, event="other-event")],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={"cross_weight_percent": {"50.5": ["tech:run-b"]}},
    )
    assert packet.decision == "measure"
    assert packet.primary_test is None
    assert packet.measurement_mission is not None
    assert packet.evidence_state is EvidenceState.BLOCKED_BY_CONTEXT
    assert "No setup change is justified" in packet.race_mode_summary


def test_sourceless_zero_length_opportunity_returns_measurement_mission() -> None:
    packet = build_kaizen_packet(
        opportunity=_opportunity(
            end_pct=20.0,
            source_channels=(),
            supporting_evidence=(),
            contradictory_evidence=("The apparent loss reversed on another eligible lap.",),
        ),
        canonical_symptom="tight_entry",
        candidates=[_candidate("cross_weight_percent", 0.9)],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={"cross_weight_percent": {"50.5": ["tech:run-b"]}},
    )

    assert packet.decision == "measure"
    assert packet.primary_test is None
    assert packet.blockers


def test_noncanonical_symptom_cannot_emit_setup_test() -> None:
    packet = build_kaizen_packet(
        opportunity=_opportunity(),
        canonical_symptom="invented_not_canonical",
        candidates=[_candidate("cross_weight_percent", 0.9)],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={"cross_weight_percent": {"50.5": ["tech:run-b"]}},
    )

    assert packet.decision == "measure"
    assert packet.primary_test is None
    assert any("canonical" in blocker for blocker in packet.blockers)


def test_packet_never_uses_unlinked_higher_ranked_candidate() -> None:
    packet = build_kaizen_packet(
        opportunity=_opportunity(),
        canonical_symptom="tight_entry",
        candidates=[
            _candidate("front_brake_bias_percent", 0.99, event="unrelated"),
            _candidate("cross_weight_percent", 0.70),
        ],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={"cross_weight_percent": {"50.5": ["tech:run-b"]}},
    )
    assert packet.primary_test is not None
    assert packet.primary_test.control_key == "cross_weight_percent"
