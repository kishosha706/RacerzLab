from __future__ import annotations

from racelab_engine.evaluation.causal import (
    ControlledEffectCase,
    evaluate_controlled_effects,
)
from racelab_engine.evaluation.planner_evaluation import (
    PlannerComparisonCase,
    evaluate_candidate_planner,
)


def _effect_case(
    workflow_id: str,
    *,
    intervention_b: float,
    restoration_a2: float = 10.0,
    placebo: bool = False,
    policy: str = "keep",
    countereffect: bool = False,
):
    return ControlledEffectCase(
        workflow_id=workflow_id,
        control_family="rf_spring",
        partition="evaluation",
        complete_aba2=True,
        one_control=True,
        exact_context=True,
        intervention_delta=0.0 if placebo else 25.0,
        baseline_a=10.0,
        intervention_b=intervention_b,
        restoration_a2=restoration_a2,
        restoration_tolerance=0.1,
        noise_threshold=0.2,
        placebo=placebo,
        mechanism_response_sign=-1 if intervention_b < 10.0 else 0,
        policy_verdict=policy,
        countereffect_occurred=countereffect,
    )


def test_controlled_effect_evaluation_requires_restoration_and_placebo():
    evaluation = evaluate_controlled_effects(
        (
            _effect_case("workflow-1", intervention_b=9.5),
            _effect_case("workflow-2", intervention_b=9.6),
            _effect_case("placebo", intervention_b=10.05, placebo=True),
            _effect_case("failed-a2", intervention_b=9.4, restoration_a2=11.0),
        )
    )
    assert evaluation.state == "valid"
    assert evaluation.qualified_workflows == 3
    assert evaluation.excluded_workflows == 1
    assert evaluation.placebo_false_positive_rate == 0.0
    assert evaluation.restoration_pass_rate == 0.75
    assert evaluation.production_causal_authority is False


def test_undo_countereffect_does_not_erase_mechanism_response():
    evaluation = evaluate_controlled_effects(
        (
            _effect_case(
                "undo-workflow",
                intervention_b=9.5,
                policy="undo",
                countereffect=True,
            ),
            _effect_case("keep-workflow", intervention_b=9.6),
            _effect_case("placebo", intervention_b=10.0, placebo=True),
        )
    )
    family = evaluation.control_families[0]
    assert family.direction_replication == 1.0
    assert family.countereffect_rate == 0.5
    assert family.keep_rate == 0.5


def test_planner_candidate_can_only_score_in_shadow():
    evaluation = evaluate_candidate_planner(
        tuple(
            PlannerComparisonCase(
                session_id=f"session-{index}",
                partition="prospective",
                deterministic_clean_laps=5,
                candidate_clean_laps=5,
                deterministic_blockers_closed=1,
                candidate_blockers_closed=2,
                deterministic_mechanisms_discriminated=1,
                candidate_mechanisms_discriminated=1,
                deterministic_mission_failures=0,
                candidate_mission_failures=0,
                deterministic_false_stop=False,
                candidate_false_stop=False,
                candidate_authority_violations=0,
            )
            for index in range(20)
        )
    )
    assert evaluation.outperforms_deterministic
    assert evaluation.state == "prospective_shadow"
    assert evaluation.planner_authority is False
    assert evaluation.authority_violations == 0


def test_authority_violation_or_false_stop_invalidates_candidate_planner():
    evaluation = evaluate_candidate_planner(
        (
            PlannerComparisonCase(
                session_id="session-1",
                partition="evaluation",
                deterministic_clean_laps=5,
                candidate_clean_laps=4,
                deterministic_blockers_closed=1,
                candidate_blockers_closed=2,
                deterministic_mechanisms_discriminated=1,
                candidate_mechanisms_discriminated=2,
                deterministic_mission_failures=0,
                candidate_mission_failures=0,
                deterministic_false_stop=False,
                candidate_false_stop=True,
                candidate_authority_violations=1,
            ),
        )
    )
    assert evaluation.state == "invalid"
    assert not evaluation.outperforms_deterministic
    assert any("authority violation" in blocker for blocker in evaluation.blockers)
