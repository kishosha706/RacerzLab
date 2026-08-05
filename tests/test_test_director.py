from __future__ import annotations

from racelab_engine.analysis.test_director import (
    TestExecution,
    TestEvidenceLink,
    active_reset_attempt_groups,
    build_controlled_test,
    driver_marker_bookmarks,
    score_test_execution,
)


def _ready_test():
    return build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="A small cross-weight increase will reduce entry correction demand.",
        target_phase="entry",
        success_metrics=["Median entry phase time improves beyond the driver noise floor"],
        countereffects=["Center minimum speed does not worsen"],
        evidence_links=[TestEvidenceLink(
            event_id="event-1",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="entry",
            related_setup_keys=("cross_weight_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=[50.0, 50.5],
        legal_value_provenance={"50.5": ["tech-passing-setup:run-b"]},
    )


def test_director_outputs_one_small_aba_test() -> None:
    decision = _ready_test()
    assert decision.ready is True
    assert decision.mission is None
    assert decision.card is not None
    assert decision.card.control_key == "cross_weight_percent"
    assert tuple(stage.stage for stage in decision.card.stages) == ("A", "B", "A2")
    assert decision.card.exact_change == "50.0% -> 50.5% (adjacent observed tech-passing option)"
    assert decision.card.evidence_event_ids == ("event-1",)


def test_director_returns_concrete_mission_when_evidence_is_blocked() -> None:
    decision = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="Test entry balance.",
        target_phase="entry",
        success_metrics=[],
        countereffects=[],
        evidence_links=[],
        eligible_baseline_laps=1,
        context_matched=False,
        driver_matched=False,
        sim_integrity_clear=None,
    )
    assert decision.ready is False
    assert decision.card is None
    assert decision.mission is not None
    assert decision.mission.required_laps_or_passes == 3
    assert len(decision.mission.blockers) >= 5
    assert "Stop after any incident" in decision.mission.stop_rule


def test_tire_life_blocker_generates_a_stint_mission_not_three_laps() -> None:
    decision = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="Measure tire-life response.",
        target_phase="exit",
        success_metrics=[],
        countereffects=[],
        evidence_links=[],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        external_blockers=[
            "Tire-life priority requires a clean continuous stint and repeated tire-state history."
        ],
    )

    assert decision.mission is not None
    assert decision.mission.required_laps_or_passes == 10
    assert any("tire-state" in threshold for threshold in decision.mission.acceptance_thresholds)


def test_director_blocks_missing_baseline_value_hypothesis_and_countereffect() -> None:
    decision = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=None,
        direction_sign=1,
        hypothesis=" ",
        target_phase="entry",
        success_metrics=["Entry time improves."],
        countereffects=[],
        evidence_links=[TestEvidenceLink(
            event_id="event-1",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="entry",
            related_setup_keys=("cross_weight_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
    )

    assert decision.ready is False
    assert decision.mission is not None
    assert any("baseline value" in blocker for blocker in decision.mission.blockers)
    assert any("hypothesis" in blocker for blocker in decision.mission.blockers)
    assert any("countereffect" in blocker for blocker in decision.mission.blockers)


def test_aba_quality_requires_restore_repetition_and_sim_integrity() -> None:
    invalid = score_test_execution(TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=1,
        unrelated_setup_changes=1,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.5,
        unrelated_changed_controls=("front_brake_bias_percent",),
        context_match_score=1.0,
        driver_match_score=1.0,
        sim_integrity_score=None,
        phase_effect_b_vs_a_s=-0.2,
        phase_effect_b_vs_a2_s=-0.2,
        empirical_noise_s=0.05,
        countereffect_passed=True,
    ))
    assert invalid.verdict == "invalid"
    assert invalid.controlled_effect_eligible is False
    assert invalid.score <= 49.0

    keep = score_test_execution(TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.0,
        context_match_score=0.95,
        driver_match_score=0.95,
        sim_integrity_score=0.95,
        minimum_alignment_confidence=0.95,
        target_effect_distributions_consistent=True,
        empirical_noise_observations=4, control_guardrails_passed=True,
        target_effect_distribution_state="faster",
        phase_effect_b_vs_a_s=-0.2,
        phase_effect_b_vs_a2_s=-0.18,
        empirical_noise_s=0.05,
        countereffect_passed=True,
    ))
    assert keep.verdict == "keep"
    assert keep.controlled_effect_eligible is True


def test_aba_cannot_keep_unmatched_or_one_sided_result() -> None:
    result = score_test_execution(TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.0,
        context_match_score=0.5,
        driver_match_score=0.5,
        sim_integrity_score=1.0,
        minimum_alignment_confidence=1.0,
        target_effect_distributions_consistent=False,
        empirical_noise_observations=4, control_guardrails_passed=True,
        target_effect_distribution_state="inconclusive",
        phase_effect_b_vs_a_s=-0.2,
        phase_effect_b_vs_a2_s=0.1,
        empirical_noise_s=0.05,
        countereffect_passed=True,
    ))
    assert result.verdict == "invalid"
    assert result.controlled_effect_eligible is False


def test_noise_level_reversal_cannot_be_certified_as_undo() -> None:
    result = score_test_execution(TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.0,
        context_match_score=1.0,
        driver_match_score=1.0,
        sim_integrity_score=1.0,
        minimum_alignment_confidence=1.0,
        target_effect_distributions_consistent=False,
        empirical_noise_observations=4, control_guardrails_passed=True,
        target_effect_distribution_state="inconclusive",
        phase_effect_b_vs_a_s=-0.10,
        phase_effect_b_vs_a2_s=0.001,
        empirical_noise_s=0.05,
        countereffect_passed=True,
    ))

    assert result.verdict == "retest"
    assert result.controlled_effect_eligible is False


def test_mixed_sign_aba_effect_cannot_be_certified_or_learned() -> None:
    result = score_test_execution(TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.0,
        context_match_score=1.0,
        driver_match_score=1.0,
        sim_integrity_score=1.0,
        minimum_alignment_confidence=1.0,
        target_effect_distributions_consistent=False,
        empirical_noise_observations=4, control_guardrails_passed=True,
        target_effect_distribution_state="inconclusive",
        phase_effect_b_vs_a_s=-0.20,
        phase_effect_b_vs_a2_s=0.10,
        empirical_noise_s=0.05,
        countereffect_passed=True,
    ))

    assert result.verdict == "retest"
    assert result.controlled_effect_eligible is False


def test_countereffect_rollback_cannot_admit_a_non_reproduced_target_effect() -> None:
    result = score_test_execution(TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.5,
        observed_a_value=50.0,
        observed_b_value=50.5,
        observed_a2_value=50.0,
        context_match_score=1.0,
        driver_match_score=1.0,
        sim_integrity_score=1.0,
        minimum_alignment_confidence=1.0,
        target_effect_distributions_consistent=False,
        empirical_noise_observations=4, control_guardrails_passed=True,
        target_effect_distribution_state="inconclusive",
        phase_effect_b_vs_a_s=-0.20,
        phase_effect_b_vs_a2_s=0.20,
        empirical_noise_s=0.05,
        countereffect_passed=False,
    ))

    assert result.verdict == "undo"
    assert result.controlled_effect_eligible is False


def test_marker_and_reset_attempt_detection_use_rising_edges() -> None:
    rows = [
        {"session_time": 1.0, "driver_marker": False, "enter_exit_reset": False},
        {"session_time": 2.0, "driver_marker": True, "enter_exit_reset": False},
        {"session_time": 3.0, "driver_marker": True, "enter_exit_reset_state": 2, "reset_discontinuity": True},
        {"session_time": 4.0, "driver_marker": False, "enter_exit_reset_state": 2},
        {"session_time": 5.0, "driver_marker": True, "enter_exit_reset_state": 0},
        {"session_time": 6.0, "driver_marker": False, "enter_exit_reset_state": 2, "reset_event": True},
    ]
    assert driver_marker_bookmarks(rows) == (2.0, 5.0)
    assert active_reset_attempt_groups(rows) == ((0, 1), (2, 4), (5, 5))


def test_enter_exit_reset_state_alone_does_not_create_attempts() -> None:
    rows = [
        {"enter_exit_reset_state": 0},
        {"enter_exit_reset_state": 1},
        {"enter_exit_reset_state": 2},
    ]
    assert active_reset_attempt_groups(rows) == ((0, 2),)


def test_mid_lap_jump_plus_reset_action_state_creates_attempt() -> None:
    rows = [
        {"lap_dist_pct": 0.40, "enter_exit_reset_state": 2},
        {"lap_dist_pct": 0.45, "enter_exit_reset_state": 2},
        {"lap_dist_pct": 0.10, "enter_exit_reset_state": 2},
    ]
    assert active_reset_attempt_groups(rows) == ((0, 1), (2, 2))


def test_director_rejects_unlinked_event_and_implicit_direction() -> None:
    decision = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=0,
        hypothesis="Test entry balance.",
        target_phase="entry",
        success_metrics=["Entry phase time"],
        countereffects=[],
        evidence_links=[TestEvidenceLink(
            event_id="exit-event",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="exit",
            related_setup_keys=("front_brake_bias_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
    )
    assert decision.ready is False
    assert decision.mission is not None
    assert any("direction" in blocker.lower() for blocker in decision.mission.blockers)


def test_zero_effect_cannot_receive_a_perfect_quality_score() -> None:
    result = score_test_execution(TestExecution(
        eligible_laps_a=3, eligible_laps_b=3, eligible_laps_a2=3,
        unrelated_setup_changes=0, control_key="cross_weight_percent",
        planned_b_value=50.5, observed_a_value=50.0, observed_b_value=50.5,
        observed_a2_value=50.0, context_match_score=1.0, driver_match_score=1.0,
        sim_integrity_score=1.0, minimum_alignment_confidence=1.0,
        target_effect_distributions_consistent=False,
        empirical_noise_observations=4, control_guardrails_passed=True,
        target_effect_distribution_state="inconclusive",
        phase_effect_b_vs_a_s=0.0,
        phase_effect_b_vs_a2_s=0.0, empirical_noise_s=0.02,
        countereffect_passed=True,
    ))

    assert result.score == 80.0


def test_low_alignment_confidence_invalidates_an_otherwise_fast_test() -> None:
    result = score_test_execution(TestExecution(
        eligible_laps_a=3, eligible_laps_b=3, eligible_laps_a2=3,
        unrelated_setup_changes=0, control_key="cross_weight_percent",
        planned_b_value=50.5, observed_a_value=50.0, observed_b_value=50.5,
        observed_a2_value=50.0, context_match_score=1.0, driver_match_score=1.0,
        sim_integrity_score=1.0, minimum_alignment_confidence=0.79,
        phase_effect_b_vs_a_s=-0.2, phase_effect_b_vs_a2_s=-0.2,
        empirical_noise_s=0.02, countereffect_passed=True,
    ))
    assert result.verdict == "invalid"
    assert result.controlled_effect_eligible is False


def test_non_finite_execution_effects_are_rejected() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TestExecution(
            eligible_laps_a=3, eligible_laps_b=3, eligible_laps_a2=3,
            unrelated_setup_changes=0, control_key="cross_weight_percent",
            planned_b_value=50.5, observed_a_value=50.0, observed_b_value=50.5,
            observed_a2_value=50.0, context_match_score=1.0, driver_match_score=1.0,
            sim_integrity_score=1.0, minimum_alignment_confidence=1.0,
            target_effect_distributions_consistent=True,
            phase_effect_b_vs_a_s=float("inf"),
            phase_effect_b_vs_a2_s=-0.1, empirical_noise_s=0.02,
            countereffect_passed=True,
        )


def test_observed_adjacent_option_is_the_persisted_raw_plan_value() -> None:
    from racelab_engine.services.controlled_workflow_service import _planned_numeric_value

    decision = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="Test the observed adjacent option.",
        target_phase="entry",
        success_metrics=["Target-window entry time"],
        countereffects=["Median non-target phase time must not worsen beyond empirical noise."],
        evidence_links=[TestEvidenceLink(
            event_id="entry-option",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="entry",
            related_setup_keys=("cross_weight_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=[50.0, 51.0],
        legal_value_provenance={"51.0": ["tech-passing-setup:run-51"]},
    )

    assert decision.card is not None
    assert decision.card.proposed_value_raw == 51.0
    assert decision.card.proposed_value_provenance == ("tech-passing-setup:run-51",)
    assert _planned_numeric_value(decision.card) == 51.0


def test_unproven_garage_option_returns_measurement_mission() -> None:
    decision = _ready_test().model_copy(update={})
    assert decision.ready is True
    blocked = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="Test entry balance.",
        target_phase="entry",
        success_metrics=["Entry time"],
        countereffects=["Non-target phase time"],
        evidence_links=[TestEvidenceLink(
            event_id="entry-no-option",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="entry",
            related_setup_keys=("cross_weight_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=[50.0, 50.5],
        legal_value_provenance={},
    )
    assert blocked.ready is False
    assert blocked.mission is not None
    assert any("provenance" in reason for reason in blocked.mission.blockers)


def test_zero_valued_legal_option_keeps_normalized_provenance() -> None:
    decision = build_controlled_test(
        control_key="tape_percent",
        current_value="5%",
        direction_sign=-1,
        hypothesis="Test the observed lower tape option.",
        target_phase="straight",
        success_metrics=["Target-window time"],
        countereffects=["Median non-target phase time must not worsen beyond empirical noise."],
        evidence_links=[TestEvidenceLink(
            event_id="straight-tape",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="straight",
            related_setup_keys=("tape_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=["5%", "0%"],
        legal_value_provenance={"0%": ["tech-passing-setup:tape-zero"]},
    )

    assert decision.ready is True
    assert decision.card is not None
    assert decision.card.proposed_value_raw == "0%"
    assert decision.card.proposed_value_provenance == ("tech-passing-setup:tape-zero",)


def test_steering_ratio_option_preserves_raw_type_and_ignores_pinion_options() -> None:
    decision = build_controlled_test(
        control_key="steering_ratio",
        current_value="14:1",
        direction_sign=-1,
        hypothesis="Test quicker steering feel.",
        target_phase="entry",
        success_metrics=["Steering demand"],
        countereffects=["Median non-target phase time must not worsen beyond empirical noise."],
        evidence_links=[TestEvidenceLink(
            event_id="steering-ratio",
            eligible_lap=True,
            valid_for_tuning=True,
            phase="entry",
            related_setup_keys=("steering_ratio",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=["14:1", "12:1", "11 mm/rev"],
        legal_value_provenance={
            "12:1": ["tech-passing-setup:ratio-12"],
            "11 mm/rev": ["tech-passing-setup:pinion-11"],
        },
    )

    assert decision.ready is True
    assert decision.card is not None
    assert decision.card.proposed_value_raw == "12:1"
    assert decision.card.proposed_value == "12:1"
    assert "12:1" in decision.card.exact_change
